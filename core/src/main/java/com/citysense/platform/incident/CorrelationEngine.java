package com.citysense.platform.incident;

import com.citysense.common.config.CitySenseProperties;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.observation.Observation;
import com.citysense.platform.observation.ObservationRepository;
import com.citysense.platform.observation.ObservationType;
import com.citysense.platform.realtime.CityEventMessage;
import java.time.Duration;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * Clusters observations into incidents by space and time window, then ranks urgency.
 * Rules are deterministic so every merge can be explained and tested; no LLM decides here.
 */
@Service
public class CorrelationEngine {

    /** cv_density readings below this occupancy are stored as telemetry but do not raise incidents. */
    static final double DENSITY_INCIDENT_THRESHOLD = 0.7;

    /** City events (fun) live in the civic feed and are never treated as hazards. */
    private static final Set<ObservationType> NON_HAZARD = EnumSet.of(ObservationType.EVENT);

    private final IncidentRepository incidents;
    private final ObservationRepository observations;
    private final CoordinatorRules coordinator;
    private final AuditService audit;
    private final ApplicationEventPublisher events;
    private final double radiusMeters;
    private final Duration window;

    public CorrelationEngine(IncidentRepository incidents, ObservationRepository observations,
                             CoordinatorRules coordinator, AuditService audit, ApplicationEventPublisher events,
                             CitySenseProperties props) {
        this.incidents = incidents;
        this.observations = observations;
        this.coordinator = coordinator;
        this.audit = audit;
        this.events = events;
        this.radiusMeters = props.correlation().radiusMeters();
        this.window = Duration.ofMinutes(props.correlation().windowMinutes());
    }

    public record CorrelationResult(Optional<Incident> incident, boolean created) {}

    public record Score(ObservationType dominantType, int severity, double urgency, int observationCount) {}

    @Transactional(propagation = Propagation.MANDATORY)
    public CorrelationResult correlate(Observation obs) {
        if (!raisesIncident(obs)) {
            return new CorrelationResult(Optional.empty(), false);
        }

        List<Incident> candidates = incidents.findCorrelationCandidates(
                obs.getLatitude(), obs.getLongitude(), radiusMeters, obs.getObservedAt().minus(window));
        boolean created = candidates.isEmpty();
        Incident incident = created
                ? incidents.save(new Incident(obs.getType(), obs.getType().code(), obs.getLatitude(), obs.getLongitude()))
                : candidates.get(0);

        obs.attachTo(incident.getId());
        observations.flush();
        List<Observation> members = observations.findByIncidentIdOrderByObservedAtAsc(incident.getId());

        Score score = score(members);
        incident.applyScore(score, title(score.dominantType(), members), summary(members));

        audit.record(created ? "INCIDENT_CREATED" : "INCIDENT_CORRELATED", "incident", incident.getId().toString(),
                "SUCCESS", Map.of(
                        "observationId", obs.getId().toString(),
                        "severity", score.severity(),
                        "urgency", score.urgency(),
                        "observationCount", score.observationCount()));
        events.publishEvent(CityEventMessage.of(created ? "INCIDENT_CREATED" : "INCIDENT_UPDATED",
                incident.getId(), IncidentDtos.IncidentView.of(incident)));

        coordinator.evaluate(incident, members);
        return new CorrelationResult(Optional.of(incident), created);
    }

    static boolean raisesIncident(Observation obs) {
        if (NON_HAZARD.contains(obs.getType())) {
            return false;
        }
        if (obs.getType() == ObservationType.CV_DENSITY) {
            return density(obs) >= DENSITY_INCIDENT_THRESHOLD;
        }
        return true;
    }

    /**
     * Severity (1-5): highest per-type base severity, +1 when 3+ observations corroborate,
     * +1 when 3+ distinct hazard types co-occur (e.g. rain + flood + congestion).
     * Urgency (0-100): severity dominates; confidence, corroboration and type diversity break ties.
     */
    static Score score(List<Observation> members) {
        Observation dominant = members.stream()
                .max(Comparator.comparingInt(CorrelationEngine::severityOf))
                .orElseThrow();
        int distinctTypes = (int) members.stream().map(Observation::getType).distinct().count();
        int count = members.size();

        int severity = severityOf(dominant);
        if (count >= 3) severity++;
        if (distinctTypes >= 3) severity++;
        severity = Math.min(severity, 5);

        double maxConfidence = members.stream().mapToDouble(Observation::getConfidence).max().orElse(0);
        double urgency = severity * 15
                + maxConfidence * 10
                + Math.min(count - 1, 5) * 3
                + Math.min(distinctTypes - 1, 3) * 5;
        return new Score(dominant.getType(), severity, Math.min(100, Math.round(urgency * 10) / 10.0), count);
    }

    private static int severityOf(Observation o) {
        if (o.getType() == ObservationType.CV_DENSITY && density(o) >= 0.9) {
            return 3;
        }
        return o.getType().baseSeverity();
    }

    private static double density(Observation o) {
        Object value = o.getPayload().get("density");
        return value instanceof Number n ? n.doubleValue() : 0;
    }

    private static String title(ObservationType type, List<Observation> members) {
        String label = switch (type) {
            case FLOOD -> "Flooding";
            case CRASH -> "Road crash";
            case RAIN -> "Heavy rain";
            case CONGESTION, CV_DENSITY -> "Traffic congestion";
            case COMPLAINT -> "Citizen-reported issue";
            case AGENT_FINDING -> "Agent finding";
            case EVENT -> "City event";
        };
        return members.stream()
                .map(o -> o.getPayload().get("locationName"))
                .filter(String.class::isInstance)
                .findFirst()
                .map(name -> label + " near " + name)
                .orElse(label);
    }

    private static String summary(List<Observation> members) {
        return members.stream()
                .collect(Collectors.groupingBy(o -> o.getType().code(), java.util.TreeMap::new, Collectors.counting()))
                .entrySet().stream()
                .map(e -> e.getValue() + "x " + e.getKey())
                .collect(Collectors.joining(", ", "Linked observations: ", ""));
    }
}

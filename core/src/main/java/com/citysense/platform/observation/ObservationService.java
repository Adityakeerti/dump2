package com.citysense.platform.observation;

import com.citysense.platform.audit.AuditService;
import com.citysense.platform.incident.CorrelationEngine;
import com.citysense.platform.incident.Incident;
import com.citysense.platform.incident.CorrelationEngine.CorrelationResult;
import com.citysense.platform.observation.ObservationDtos.IngestResponse;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationDtos.ObservationView;
import com.citysense.platform.realtime.CityEventMessage;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Ingestion engine: validate -> store -> correlate into an incident -> audit -> broadcast. */
@Service
public class ObservationService {

    private final ObservationRepository repo;
    private final CorrelationEngine correlation;
    private final AuditService audit;
    private final ApplicationEventPublisher events;

    public ObservationService(ObservationRepository repo, CorrelationEngine correlation, AuditService audit,
                              ApplicationEventPublisher events) {
        this.repo = repo;
        this.correlation = correlation;
        this.audit = audit;
        this.events = events;
    }

    @Transactional
    public IngestResponse ingest(ObservationRequest req, String defaultSource) {
        Observation obs = repo.save(new Observation(
                req.type(),
                req.latitude(),
                req.longitude(),
                req.observedAt() == null ? Instant.now() : req.observedAt(),
                req.source() == null || req.source().isBlank() ? defaultSource : req.source(),
                req.confidence() == null ? 1.0 : req.confidence(),
                req.status() == null ? ObservationStatus.UNVERIFIED : req.status(),
                req.payload() == null ? Map.of() : req.payload()));

        CorrelationResult result = correlation.correlate(obs);

        UUID incidentId = result.incident().map(Incident::getId).orElse(null);

        Map<String, Object> evidence = new HashMap<>();
        evidence.put("type", obs.getType().code());
        evidence.put("source", obs.getSource());
        evidence.put("newIncident", result.created());
        if (incidentId != null) {
            evidence.put("incidentId", incidentId.toString());
        }
        audit.record("OBSERVATION_INGESTED", "observation", obs.getId().toString(), "SUCCESS", evidence);

        ObservationView view = ObservationView.of(obs);
        events.publishEvent(CityEventMessage.of("OBSERVATION_CREATED", obs.getId(), view));
        return new IngestResponse(view, incidentId, result.created());
    }

    @Transactional(readOnly = true)
    public List<ObservationView> recent(ObservationType type, int limit) {
        PageRequest page = PageRequest.of(0, Math.min(limit, 500));
        List<Observation> rows = type == null
                ? repo.findAllByOrderByObservedAtDesc(page)
                : repo.findByTypeOrderByObservedAtDesc(type, page);
        return rows.stream().map(ObservationView::of).toList();
    }
}

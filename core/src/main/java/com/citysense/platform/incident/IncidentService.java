package com.citysense.platform.incident;

import com.citysense.common.error.ApiException;
import com.citysense.platform.action.AgentActionService;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.incident.IncidentDtos.IncidentDetail;
import com.citysense.platform.incident.IncidentDtos.IncidentView;
import com.citysense.platform.observation.ObservationDtos.ObservationView;
import com.citysense.platform.observation.ObservationRepository;
import com.citysense.platform.realtime.CityEventMessage;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IncidentService {

    private final IncidentRepository incidents;
    private final ObservationRepository observations;
    private final AgentActionService actions;
    private final AuditService audit;
    private final ApplicationEventPublisher events;

    public IncidentService(IncidentRepository incidents, ObservationRepository observations,
                           AgentActionService actions, AuditService audit, ApplicationEventPublisher events) {
        this.incidents = incidents;
        this.observations = observations;
        this.actions = actions;
        this.audit = audit;
        this.events = events;
    }

    /** Ranked by urgency so the dashboard shows the most pressing incident first. */
    @Transactional(readOnly = true)
    public List<IncidentView> list(IncidentStatus status) {
        var statuses = status == null ? EnumSet.of(IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED) : EnumSet.of(status);
        return incidents.findByStatusInOrderByUrgencyScoreDescUpdatedAtDesc(statuses).stream()
                .map(IncidentView::of).toList();
    }

    @Transactional(readOnly = true)
    public IncidentDetail detail(UUID id) {
        Incident incident = find(id);
        return new IncidentDetail(IncidentView.of(incident),
                observations.findByIncidentIdOrderByObservedAtAsc(id).stream().map(ObservationView::of).toList(),
                actions.forIncident(id));
    }

    @Transactional
    public IncidentView changeStatus(UUID id, IncidentStatus next) {
        Incident incident = find(id);
        IncidentStatus previous = incident.getStatus();
        if (!previous.canMoveTo(next)) {
            throw ApiException.conflict("Cannot move incident from " + previous + " to " + next);
        }
        incident.moveTo(next);
        audit.record("INCIDENT_" + next, "incident", id.toString(), "SUCCESS",
                Map.of("from", previous.name(), "to", next.name()));
        IncidentView view = IncidentView.of(incident);
        events.publishEvent(CityEventMessage.of("INCIDENT_UPDATED", id, view));
        return view;
    }

    private Incident find(UUID id) {
        return incidents.findById(id).orElseThrow(() -> ApiException.notFound("Incident", id));
    }
}

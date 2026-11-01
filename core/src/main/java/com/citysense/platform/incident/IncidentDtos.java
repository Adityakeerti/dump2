package com.citysense.platform.incident;

import com.citysense.platform.action.AgentActionDtos.ActionView;
import com.citysense.platform.observation.ObservationDtos.ObservationView;
import com.citysense.platform.observation.ObservationType;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class IncidentDtos {

    private IncidentDtos() {}

    public record IncidentView(UUID id, ObservationType type, String title, String summary, int severity,
                               double urgencyScore, double latitude, double longitude, IncidentStatus status,
                               int observationCount, Instant createdAt, Instant updatedAt) {
        public static IncidentView of(Incident i) {
            return new IncidentView(i.getId(), i.getType(), i.getTitle(), i.getSummary(), i.getSeverity(),
                    i.getUrgencyScore(), i.getLatitude(), i.getLongitude(), i.getStatus(), i.getObservationCount(),
                    i.getCreatedAt(), i.getUpdatedAt());
        }
    }

    /** Incident drawer: the incident plus its merged timeline of observations and actions. */
    public record IncidentDetail(IncidentView incident, List<ObservationView> observations, List<ActionView> actions) {}

    public record StatusChange(@NotNull IncidentStatus status) {}
}

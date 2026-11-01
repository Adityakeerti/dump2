package com.citysense.platform.observation;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public final class ObservationDtos {

    private ObservationDtos() {}

    /** Body of POST /api/events and POST /internal/observations. Optional fields get server defaults. */
    public record ObservationRequest(
            @NotNull ObservationType type,
            @NotNull @DecimalMin("-90") @DecimalMax("90") Double latitude,
            @NotNull @DecimalMin("-180") @DecimalMax("180") Double longitude,
            Instant observedAt,
            @Size(max = 64) String source,
            @DecimalMin("0") @DecimalMax("1") Double confidence,
            ObservationStatus status,
            Map<String, Object> payload) {}

    public record ObservationView(UUID id, ObservationType type, double latitude, double longitude,
                                  Instant observedAt, String source, double confidence, ObservationStatus status,
                                  Map<String, Object> payload, UUID incidentId) {
        public static ObservationView of(Observation o) {
            return new ObservationView(o.getId(), o.getType(), o.getLatitude(), o.getLongitude(), o.getObservedAt(),
                    o.getSource(), o.getConfidence(), o.getStatus(), o.getPayload(), o.getIncidentId());
        }
    }

    /** Ingestion result: the stored observation and the incident it was correlated into. */
    public record IngestResponse(ObservationView observation, UUID incidentId, boolean newIncident) {}
}

package com.citysense.platform.observation;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** The one event model: every CV reading, complaint, flood report or agent finding is an Observation. */
@Entity
@Table(name = "observations")
public class Observation {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private ObservationType type;

    // The PostGIS `geom` column is generated from these two, so it is not mapped here.
    @Column(nullable = false)
    private double latitude;

    @Column(nullable = false)
    private double longitude;

    @Column(name = "observed_at", nullable = false)
    private Instant observedAt;

    @Column(nullable = false)
    private String source;

    @Column(nullable = false)
    private double confidence;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ObservationStatus status;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> payload;

    @Column(name = "incident_id")
    private UUID incidentId;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Observation() {}

    public Observation(ObservationType type, double latitude, double longitude, Instant observedAt, String source,
                       double confidence, ObservationStatus status, Map<String, Object> payload) {
        this.type = type;
        this.latitude = latitude;
        this.longitude = longitude;
        this.observedAt = observedAt;
        this.source = source;
        this.confidence = confidence;
        this.status = status;
        this.payload = payload;
    }

    public UUID getId() { return id; }
    public ObservationType getType() { return type; }
    public double getLatitude() { return latitude; }
    public double getLongitude() { return longitude; }
    public Instant getObservedAt() { return observedAt; }
    public String getSource() { return source; }
    public double getConfidence() { return confidence; }
    public ObservationStatus getStatus() { return status; }
    public Map<String, Object> getPayload() { return payload; }
    public UUID getIncidentId() { return incidentId; }
    public Instant getCreatedAt() { return createdAt; }

    public void attachTo(UUID incidentId) {
        this.incidentId = incidentId;
    }
}

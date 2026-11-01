package com.citysense.platform.incident;

import com.citysense.platform.observation.ObservationType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "incidents")
public class Incident {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private ObservationType type;

    @Column(nullable = false)
    private String title;

    private String summary;

    @Column(nullable = false)
    private int severity;

    @Column(name = "urgency_score", nullable = false)
    private double urgencyScore;

    @Column(nullable = false)
    private double latitude;

    @Column(nullable = false)
    private double longitude;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private IncidentStatus status = IncidentStatus.OPEN;

    @Column(name = "observation_count", nullable = false)
    private int observationCount;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    protected Incident() {}

    public Incident(ObservationType type, String title, double latitude, double longitude) {
        this.type = type;
        this.title = title;
        this.latitude = latitude;
        this.longitude = longitude;
        this.severity = type.baseSeverity();
    }

    public UUID getId() { return id; }
    public ObservationType getType() { return type; }
    public String getTitle() { return title; }
    public String getSummary() { return summary; }
    public int getSeverity() { return severity; }
    public double getUrgencyScore() { return urgencyScore; }
    public double getLatitude() { return latitude; }
    public double getLongitude() { return longitude; }
    public IncidentStatus getStatus() { return status; }
    public int getObservationCount() { return observationCount; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    void applyScore(CorrelationEngine.Score score, String title, String summary) {
        this.type = score.dominantType();
        this.severity = score.severity();
        this.urgencyScore = score.urgency();
        this.observationCount = score.observationCount();
        this.title = title;
        this.summary = summary;
        this.updatedAt = Instant.now();
    }

    void moveTo(IncidentStatus next) {
        this.status = next;
        this.updatedAt = Instant.now();
    }
}

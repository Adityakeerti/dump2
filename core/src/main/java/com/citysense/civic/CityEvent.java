package com.citysense.civic;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "city_events")
public class CityEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String title;

    @Column(columnDefinition = "TEXT")
    private String description;

    @Column(nullable = false, length = 64)
    private String category;

    @Column(nullable = false, length = 16)
    private String severity;

    @Column(nullable = false)
    private double latitude;

    @Column(nullable = false)
    private double longitude;

    @Column(nullable = false)
    private Instant startsAt = Instant.now();

    private Instant endsAt;

    @Column(nullable = false)
    private Instant createdAt = Instant.now();

    @Column(length = 200)
    private String venue;

    @Column(length = 200)
    private String organizer;

    @Column(name = "source_url", columnDefinition = "TEXT")
    private String sourceUrl;

    @Column(name = "seed_key", unique = true, length = 80)
    private String seedKey;

    /** Upsert a real-world event loaded by the directory seeder. */
    public void applySeed(String seedKey, String title, String description, String category, double latitude,
                          double longitude, Instant startsAt, Instant endsAt, String venue, String organizer,
                          String sourceUrl) {
        this.seedKey = seedKey;
        this.title = title;
        this.description = description;
        this.category = category == null ? "COMMUNITY" : category.toUpperCase(java.util.Locale.ROOT);
        this.severity = "INFO";
        this.latitude = latitude;
        this.longitude = longitude;
        this.startsAt = startsAt;
        this.endsAt = endsAt;
        this.venue = venue;
        this.organizer = organizer;
        this.sourceUrl = sourceUrl;
    }

    public String getVenue() { return venue; }
    public String getOrganizer() { return organizer; }
    public String getSourceUrl() { return sourceUrl; }
    public String getSeedKey() { return seedKey; }

    public UUID getId() {
        return id;
    }

    public void setId(UUID id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getSeverity() {
        return severity;
    }

    public void setSeverity(String severity) {
        this.severity = severity;
    }

    public double getLatitude() {
        return latitude;
    }

    public void setLatitude(double latitude) {
        this.latitude = latitude;
    }

    public double getLongitude() {
        return longitude;
    }

    public void setLongitude(double longitude) {
        this.longitude = longitude;
    }

    public Instant getStartsAt() {
        return startsAt;
    }

    public void setStartsAt(Instant startsAt) {
        this.startsAt = startsAt;
    }

    public Instant getEndsAt() {
        return endsAt;
    }

    public void setEndsAt(Instant endsAt) {
        this.endsAt = endsAt;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}

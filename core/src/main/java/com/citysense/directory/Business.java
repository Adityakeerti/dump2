package com.citysense.directory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/** A popular local business in the city directory (seeded, recommendable by every agent). */
@Entity
@Table(name = "businesses")
public class Business {

    @Id
    @GeneratedValue
    private UUID id;

    @Column(name = "seed_key", unique = true, length = 80)
    private String seedKey;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, length = 48)
    private String category;

    @Column(nullable = false, length = 120)
    private String locality;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String description;

    @Column(nullable = false)
    private double latitude;

    @Column(nullable = false)
    private double longitude;

    @Column(name = "coords_precision", nullable = false, length = 16)
    private String coordsPrecision = "approximate";

    @Column(name = "source_url", columnDefinition = "TEXT")
    private String sourceUrl;

    @Column(nullable = false)
    private boolean featured = true;

    @Column(nullable = false)
    private boolean active = true;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    protected Business() {}

    public Business(String seedKey) {
        this.seedKey = seedKey;
    }

    public void apply(String name, String category, String locality, String description, double latitude,
                      double longitude, String coordsPrecision, String sourceUrl) {
        this.name = name;
        this.category = category;
        this.locality = locality;
        this.description = description;
        this.latitude = latitude;
        this.longitude = longitude;
        this.coordsPrecision = "exact".equals(coordsPrecision) ? "exact" : "approximate";
        this.sourceUrl = sourceUrl;
        this.updatedAt = Instant.now();
    }

    public UUID getId() { return id; }
    public String getSeedKey() { return seedKey; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public String getLocality() { return locality; }
    public String getDescription() { return description; }
    public double getLatitude() { return latitude; }
    public double getLongitude() { return longitude; }
    public String getCoordsPrecision() { return coordsPrecision; }
    public String getSourceUrl() { return sourceUrl; }
    public boolean isFeatured() { return featured; }
    public boolean isActive() { return active; }
}

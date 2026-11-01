package com.citysense.common.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "citysense")
public record CitySenseProperties(
        int demoMode,
        Security security,
        Seed seed,
        Correlation correlation) {

    public record Security(String jwtSecret, long jwtExpirationMinutes, String internalApiKey, String corsAllowedOrigins) {}

    public record Seed(boolean enabled, String defaultPassword) {}

    /** Observations within radiusMeters of an open incident touched in the last windowMinutes are merged into it. */
    public record Correlation(double radiusMeters, long windowMinutes) {}

    public boolean isDemoMode() {
        return demoMode == 1;
    }
}

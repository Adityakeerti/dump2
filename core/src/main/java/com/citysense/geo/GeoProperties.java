package com.citysense.geo;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Upstream map providers (OpenStreetMap stack by default) and map defaults served to clients.
 * Clients never call the providers directly; every request is proxied and cached by core.
 * The public OSM servers have usage policies (identifying User-Agent, attribution, no heavy use):
 * point the URLs at self-hosted or commercial endpoints before real traffic.
 */
@ConfigurationProperties(prefix = "citysense.geo")
public record GeoProperties(
        String tileUrlTemplate,
        String attribution,
        String nominatimUrl,
        String osrmUrl,
        String userAgent,
        String publicBaseUrl,
        int minZoom,
        int maxZoom,
        int tileCacheEntries,
        long tileCacheSeconds,
        int lookupCacheEntries,
        long nominatimMinIntervalMillis,
        long requestTimeoutSeconds,
        double defaultLatitude,
        double defaultLongitude,
        double defaultZoom,
        double geofenceRadiusMeters,
        String countryCodes) {}

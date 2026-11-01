package com.citysense.geo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Detailed vector street map with 3D buildings for the Explore map.
 *
 * <p>Default: OpenFreeMap "liberty" (free, no API key, OpenMapTiles schema, includes a
 * {@code building-3d} fill-extrusion layer). The style JSON is fetched once and cached; vector tiles,
 * fonts and sprites are then loaded by the map client straight from that provider. Set
 * {@code GEO_VECTOR_STYLE_URL=} (empty) to go back to the proxied raster OSM style.
 */
@Component
public class VectorStyleProvider {

    private static final Logger log = LoggerFactory.getLogger(VectorStyleProvider.class);
    private static final Duration TTL = Duration.ofHours(6);

    private final String styleUrl;
    private final String userAgent;
    private final ObjectMapper json;
    private final HttpClient http;
    private volatile Map<String, Object> cached;
    private volatile Instant cachedAt = Instant.EPOCH;

    public VectorStyleProvider(
            @Value("${citysense.geo.vector-style-url:https://tiles.openfreemap.org/styles/liberty}") String styleUrl,
            @Value("${citysense.geo.user-agent:CitySense}") String userAgent,
            ObjectMapper json) {
        this.styleUrl = styleUrl == null ? "" : styleUrl.trim();
        this.userAgent = userAgent;
        this.json = json;
        this.http = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public boolean enabled() {
        return !styleUrl.isEmpty();
    }

    /** The vector style, or empty when disabled/unreachable (callers then serve the raster style). */
    @SuppressWarnings("unchecked")
    public Optional<Map<String, Object>> style() {
        if (!enabled()) {
            return Optional.empty();
        }
        Map<String, Object> current = cached;
        if (current != null && Instant.now().isBefore(cachedAt.plus(TTL))) {
            return Optional.of(current);
        }
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(styleUrl))
                    .header("User-Agent", userAgent)
                    .header("Accept", "application/json")
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();
            HttpResponse<byte[]> res = http.send(req, HttpResponse.BodyHandlers.ofByteArray());
            if (res.statusCode() != 200) {
                throw new IllegalStateException("HTTP " + res.statusCode());
            }
            Map<String, Object> style = json.readValue(res.body(), Map.class);
            if (!(style.get("sources") instanceof Map) || !(style.get("layers") instanceof java.util.List)) {
                throw new IllegalStateException("not a MapLibre style");
            }
            cached = style;
            cachedAt = Instant.now();
            return Optional.of(style);
        } catch (Exception e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            log.warn("Vector map style {} unavailable ({}); serving {}", styleUrl, e.getMessage(),
                    current != null ? "the last cached copy" : "the raster style");
            return Optional.ofNullable(current);
        }
    }
}

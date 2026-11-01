package com.citysense.geo;

import com.citysense.common.error.ApiException;
import com.citysense.geo.GeoDtos.Place;
import com.citysense.geo.GeoDtos.Route;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/** Server-side proxy for map tiles (OSM), geocoding (Nominatim) and routing (OSRM). */
@Service
public class GeoService {

    private static final Logger log = LoggerFactory.getLogger(GeoService.class);
    private static final Set<String> ROUTE_PROFILES = Set.of("driving", "walking", "cycling");

    public record Tile(byte[] bytes, String contentType) {}

    private final GeoProperties props;
    private final ObjectMapper json;
    private final HttpClient http;
    private final LruCache<String, Tile> tiles;
    private final LruCache<String, Object> lookups;
    private final Object nominatimLock = new Object();
    private long lastNominatimCall;

    public GeoService(GeoProperties props, ObjectMapper json) {
        this.props = props;
        this.json = json;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(props.requestTimeoutSeconds()))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
        this.tiles = new LruCache<>(props.tileCacheEntries(), props.tileCacheSeconds());
        this.lookups = new LruCache<>(props.lookupCacheEntries(), props.tileCacheSeconds());
    }

    public Tile tile(int z, int x, int y) {
        validateTile(z, x, y, props.minZoom(), props.maxZoom());
        String key = z + "/" + x + "/" + y;
        return tiles.get(key).orElseGet(() -> {
            String url = props.tileUrlTemplate()
                    .replace("{z}", String.valueOf(z))
                    .replace("{x}", String.valueOf(x))
                    .replace("{y}", String.valueOf(y));
            HttpResponse<byte[]> res = send(url, HttpResponse.BodyHandlers.ofByteArray());
            String type = res.headers().firstValue("Content-Type").orElse("image/png");
            Tile tile = new Tile(res.body(), type);
            tiles.put(key, tile);
            return tile;
        });
    }

    @SuppressWarnings("unchecked")
    public List<Place> geocode(String query, int limit, Double nearLat, Double nearLng) {
        String q = query.trim();
        if (q.length() < 2) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Query must be at least 2 characters");
        }
        int lim = Math.max(1, Math.min(limit, 10));
        StringBuilder url = new StringBuilder(props.nominatimUrl()).append("/search?format=jsonv2&addressdetails=0")
                .append("&limit=").append(lim)
                .append("&q=").append(enc(q));
        if (props.countryCodes() != null && !props.countryCodes().isBlank()) {
            url.append("&countrycodes=").append(enc(props.countryCodes()));
        }
        if (nearLat != null && nearLng != null) {
            double d = 0.25; // ~25 km bias box; results outside are still allowed (bounded=0)
            url.append("&viewbox=").append(nearLng - d).append(',').append(nearLat + d).append(',')
                    .append(nearLng + d).append(',').append(nearLat - d);
        }
        String key = "g:" + url;
        return (List<Place>) lookups.get(key).orElseGet(() -> {
            List<Place> places = new ArrayList<>();
            for (JsonNode n : nominatim(url.toString())) {
                places.add(toPlace(n));
            }
            lookups.put(key, places);
            return places;
        });
    }

    public Place reverse(double lat, double lng) {
        validateLatLng(lat, lng);
        String url = props.nominatimUrl() + "/reverse?format=jsonv2&lat=" + lat + "&lon=" + lng;
        String key = "r:" + String.format(Locale.ROOT, "%.5f,%.5f", lat, lng);
        return (Place) lookups.get(key).orElseGet(() -> {
            JsonNode n = nominatim(url);
            if (n.has("error")) {
                throw ApiException.notFound("Place", lat + "," + lng);
            }
            Place p = toPlace(n);
            lookups.put(key, p);
            return p;
        });
    }

    public Route route(double fromLat, double fromLng, double toLat, double toLng, String profile) {
        validateLatLng(fromLat, fromLng);
        validateLatLng(toLat, toLng);
        String p = profile == null ? "driving" : profile.toLowerCase(Locale.ROOT);
        if (!ROUTE_PROFILES.contains(p)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "profile must be one of " + ROUTE_PROFILES);
        }
        String url = String.format(Locale.ROOT, "%s/route/v1/%s/%f,%f;%f,%f?overview=full&geometries=geojson",
                props.osrmUrl(), p, fromLng, fromLat, toLng, toLat);
        JsonNode body = readJson(send(url, HttpResponse.BodyHandlers.ofString()).body());
        JsonNode routes = body.path("routes");
        if (!"Ok".equals(body.path("code").asText()) || routes.isEmpty()) {
            throw new ApiException(HttpStatus.NOT_FOUND, "No route found between the given points");
        }
        JsonNode r = routes.get(0);
        @SuppressWarnings("unchecked")
        Map<String, Object> geometry = json.convertValue(r.path("geometry"), Map.class);
        return new Route(r.path("distance").asDouble(), r.path("duration").asDouble(), geometry);
    }

    /** MapLibre style document with a single raster source served by this proxy. */
    public Map<String, Object> style(String apiBaseUrl) {
        String base = props.publicBaseUrl() != null && !props.publicBaseUrl().isBlank()
                ? props.publicBaseUrl() : apiBaseUrl;
        String tileUrl = base.replaceAll("/+$", "") + "/api/geo/tiles/{z}/{x}/{y}.png";
        return Map.of(
                "version", 8,
                "name", "CitySense OSM",
                "sources", Map.of("osm", Map.of(
                        "type", "raster",
                        "tiles", List.of(tileUrl),
                        "tileSize", 256,
                        "minzoom", props.minZoom(),
                        "maxzoom", props.maxZoom(),
                        "attribution", props.attribution())),
                "layers", List.of(Map.of("id", "osm", "type", "raster", "source", "osm")));
    }

    static void validateTile(int z, int x, int y, int minZoom, int maxZoom) {
        if (z < minZoom || z > maxZoom) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "zoom must be between " + minZoom + " and " + maxZoom);
        }
        long n = 1L << z;
        if (x < 0 || y < 0 || x >= n || y >= n) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "tile x/y out of range for zoom " + z);
        }
    }

    static void validateLatLng(double lat, double lng) {
        if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "latitude/longitude out of range");
        }
    }

    private JsonNode nominatim(String url) {
        // Nominatim's public policy allows at most one request per second per application.
        synchronized (nominatimLock) {
            long wait = lastNominatimCall + props.nominatimMinIntervalMillis() - System.currentTimeMillis();
            if (wait > 0) {
                try {
                    Thread.sleep(wait);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "Interrupted");
                }
            }
            try {
                return readJson(send(url, HttpResponse.BodyHandlers.ofString()).body());
            } finally {
                lastNominatimCall = System.currentTimeMillis();
            }
        }
    }

    private Place toPlace(JsonNode n) {
        String display = n.path("display_name").asText("");
        String name = n.path("name").asText("");
        if (name.isBlank()) {
            name = display.contains(",") ? display.substring(0, display.indexOf(',')) : display;
        }
        return new Place(name, display, n.path("lat").asDouble(), n.path("lon").asDouble(),
                n.path("type").asText(null));
    }

    private <T> HttpResponse<T> send(String url, HttpResponse.BodyHandler<T> handler) {
        HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(props.requestTimeoutSeconds()))
                .header("User-Agent", props.userAgent())
                .GET().build();
        try {
            HttpResponse<T> res = http.send(req, handler);
            if (res.statusCode() >= 400) {
                log.warn("Map provider returned {} for {}", res.statusCode(), url);
                throw new ApiException(HttpStatus.BAD_GATEWAY, "Map provider error (" + res.statusCode() + ")");
            }
            return res;
        } catch (IOException e) {
            log.warn("Map provider unreachable for {}: {}", url, e.getMessage());
            throw new ApiException(HttpStatus.BAD_GATEWAY, "Map provider unreachable");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "Interrupted");
        }
    }

    private JsonNode readJson(String body) {
        try {
            return json.readTree(body);
        } catch (IOException e) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "Map provider returned malformed data");
        }
    }

    private static String enc(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }
}

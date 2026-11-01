package com.citysense.geo;

import com.citysense.geo.GeoDtos.MapConfig;
import com.citysense.geo.GeoDtos.Place;
import com.citysense.geo.GeoDtos.PlaceList;
import com.citysense.geo.GeoDtos.Route;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.Duration;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/geo")
@Tag(name = "Geo", description = "Map tiles, geocoding and routing proxied from the OpenStreetMap stack")
public class GeoController {

    private final GeoService geo;
    private final GeoProperties props;

    private final VectorStyleProvider vectorStyle;

    public GeoController(GeoService geo, GeoProperties props, VectorStyleProvider vectorStyle) {
        this.vectorStyle = vectorStyle;
        this.geo = geo;
        this.props = props;
    }

    @GetMapping("/config")
    @Operation(summary = "Map defaults for clients (style URL, default centre, geofence radius)")
    public MapConfig config() {
        return new MapConfig("/api/geo/style.json", props.defaultLatitude(), props.defaultLongitude(),
                props.defaultZoom(), props.minZoom(), props.maxZoom(), props.geofenceRadiusMeters(),
                props.attribution());
    }

    @GetMapping(value = "/style.json", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "MapLibre style: detailed vector streets + 3D buildings, or proxied raster OSM as fallback")
    public Map<String, Object> style() {
        return vectorStyle.style().orElseGet(
                () -> geo.style(ServletUriComponentsBuilder.fromCurrentContextPath().build().toUriString()));
    }

    @GetMapping("/tiles/{z}/{x}/{y}.png")
    @Operation(summary = "Raster map tile (cached proxy of the configured tile server)")
    public ResponseEntity<byte[]> tile(@PathVariable int z, @PathVariable int x, @PathVariable int y) {
        GeoService.Tile t = geo.tile(z, x, y);
        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(Duration.ofSeconds(props.tileCacheSeconds())).cachePublic())
                .contentType(MediaType.parseMediaType(t.contentType()))
                .body(t.bytes());
    }

    @GetMapping("/geocode")
    @Operation(summary = "Forward geocoding (place search), optionally biased near a point")
    public PlaceList geocode(@RequestParam String q, @RequestParam(defaultValue = "5") int limit,
                             @RequestParam(required = false) Double lat, @RequestParam(required = false) Double lng) {
        return new PlaceList(geo.geocode(q, limit, lat, lng));
    }

    @GetMapping("/reverse")
    @Operation(summary = "Reverse geocoding: address for a coordinate")
    public Place reverse(@RequestParam double lat, @RequestParam double lng) {
        return geo.reverse(lat, lng);
    }

    @GetMapping("/route")
    @Operation(summary = "Route between two points (GeoJSON LineString, metres, seconds)")
    public Route route(@RequestParam double fromLat, @RequestParam double fromLng,
                       @RequestParam double toLat, @RequestParam double toLng,
                       @RequestParam(defaultValue = "driving") String profile) {
        return geo.route(fromLat, fromLng, toLat, toLng, profile);
    }
}

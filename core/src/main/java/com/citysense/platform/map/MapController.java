package com.citysense.platform.map;

import com.citysense.platform.incident.IncidentDtos.IncidentView;
import com.citysense.platform.incident.IncidentService;
import com.citysense.platform.observation.ObservationDtos.ObservationView;
import com.citysense.platform.observation.ObservationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** GeoJSON for the live operations map (MapLibre on the dashboard, react-native-maps on mobile). */
@RestController
@RequestMapping("/api/map")
@Tag(name = "Map")
public class MapController {

    private final IncidentService incidents;
    private final ObservationService observations;

    public MapController(IncidentService incidents, ObservationService observations) {
        this.incidents = incidents;
        this.observations = observations;
    }

    @GetMapping("/features")
    @Operation(summary = "Active incidents and recent observations as a GeoJSON FeatureCollection")
    public Map<String, Object> features(@RequestParam(defaultValue = "200") int observationLimit) {
        List<Map<String, Object>> features = new ArrayList<>();
        for (IncidentView i : incidents.list(null)) {
            features.add(feature(i.longitude(), i.latitude(), Map.of(
                    "kind", "incident", "id", i.id().toString(), "type", i.type().code(), "title", i.title(),
                    "severity", i.severity(), "urgencyScore", i.urgencyScore(), "status", i.status().name())));
        }
        for (ObservationView o : observations.recent(null, observationLimit)) {
            Map<String, Object> props = new HashMap<>();
            props.put("kind", "observation");
            props.put("id", o.id().toString());
            props.put("type", o.type().code());
            props.put("status", o.status().name());
            props.put("confidence", o.confidence());
            props.put("observedAt", o.observedAt().toString());
            if (o.incidentId() != null) {
                props.put("incidentId", o.incidentId().toString());
            }
            features.add(feature(o.longitude(), o.latitude(), props));
        }
        return Map.of("type", "FeatureCollection", "features", features);
    }

    private static Map<String, Object> feature(double lng, double lat, Map<String, Object> properties) {
        return Map.of("type", "Feature",
                "geometry", Map.of("type", "Point", "coordinates", List.of(lng, lat)),
                "properties", properties);
    }
}

package com.citysense.directory;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/businesses")
@Tag(name = "Directory", description = "Popular local businesses for the Townhall feed and agent recommendations")
public class DirectoryController {

    public record BusinessView(UUID id, String name, String category, String locality, String description,
                               double latitude, double longitude, String coordsPrecision, String sourceUrl,
                               Double distanceMeters) {}

    private final BusinessRepository repo;

    public DirectoryController(BusinessRepository repo) {
        this.repo = repo;
    }

    @GetMapping
    @Operation(summary = "Popular local businesses, nearest first when lat/lng are given")
    public List<BusinessView> list(@RequestParam(required = false) Double lat,
                                   @RequestParam(required = false) Double lng,
                                   @RequestParam(required = false) Double radiusMeters,
                                   @RequestParam(required = false) String locality,
                                   @RequestParam(required = false) String category,
                                   @RequestParam(required = false) String q,
                                   @RequestParam(defaultValue = "20") int limit) {
        Double radius = lat != null && lng != null ? radiusMeters : null;
        return repo.search(lat, lng, radius, blank(locality), blank(category), blank(q), Math.max(1, Math.min(limit, 50)))
                .stream()
                .map(b -> new BusinessView(b.getId(), b.getName(), b.getCategory(), b.getLocality(), b.getDescription(),
                        b.getLatitude(), b.getLongitude(), b.getCoordsPrecision(), b.getSourceUrl(),
                        lat != null && lng != null ? haversine(lat, lng, b.getLatitude(), b.getLongitude()) : null))
                .toList();
    }

    private static String blank(String s) {
        return s == null || s.isBlank() ? null : s.trim();
    }

    static double haversine(double lat1, double lon1, double lat2, double lon2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return Math.round(6_371_000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    }
}

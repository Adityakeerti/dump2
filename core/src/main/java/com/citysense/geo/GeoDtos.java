package com.citysense.geo;

import java.util.List;
import java.util.Map;

public final class GeoDtos {

    private GeoDtos() {}

    /** Everything a client needs to draw the map; styleUrl is relative to the API base URL. */
    public record MapConfig(String styleUrl, double defaultLatitude, double defaultLongitude, double defaultZoom,
                            int minZoom, int maxZoom, double geofenceRadiusMeters, String attribution) {}

    public record Place(String name, String displayName, double latitude, double longitude, String type) {}

    public record Route(double distanceMeters, double durationSeconds, Map<String, Object> geometry) {}

    public record PlaceList(List<Place> places) {}
}

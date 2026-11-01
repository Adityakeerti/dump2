package com.citysense.platform.realtime;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

/**
 * Last line of defence for /topic/city-events, which anyone can subscribe to until authenticated
 * subscriptions exist (Stage C). Every event type family has an explicit allow-list of fields; anything
 * else, including any future event type, is reduced to its type and id. So no name, phone number,
 * personal identifier, private message, medical detail, free text or exact private location can reach an
 * unauthenticated subscriber, whatever a publishing service puts in its message.
 *
 * <p>Clients that need full details fetch them over the authenticated REST API, where ownership and
 * roles are enforced.
 */
@Component
public class LiveEventRedactor {

    /** Event-type prefix -> fields allowed onto the public channel. First match wins. */
    private static final List<Map.Entry<String, Set<String>>> ALLOWED = List.of(
            // Generated summary only (CivicDtos.ComplaintLiveEvent); never the citizen's name, text or location.
            Map.entry("COMPLAINT_", Set.of("id", "title", "category", "department", "status", "priority")),
            // Public bulletins, published by admins only.
            Map.entry("CITY_EVENT_", Set.of("id", "title", "description", "category", "severity", "latitude",
                    "longitude", "startsAt", "endsAt", "createdAt")),
            // City-wide alerts: no free-text summary; location coarsened below.
            Map.entry("INCIDENT_", Set.of("id", "type", "title", "severity", "status", "observationCount",
                    "latitude", "longitude", "createdAt", "updatedAt")),
            // Observation payloads carry reporter data (crash devices, mesh SOS victims, complaints).
            Map.entry("OBSERVATION_", Set.of("id", "type", "status", "incidentId", "observedAt")),
            // Action payloads and decision reasons are operator-only.
            Map.entry("ACTION_", Set.of("id", "incidentId", "actionType", "riskLevel", "approvalStatus", "createdAt")),
            // Mesh SOS / field reports / chats (incl. direct messages): existence only.
            Map.entry("MESH_", Set.of("id")));

    /** Incident coordinates are rounded to 2 decimals (~1 km): enough for a city-wide alert, not an address. */
    private static final Set<String> COARSE_LOCATION = Set.of("latitude", "longitude");

    private final ObjectMapper json;

    public LiveEventRedactor(ObjectMapper json) {
        this.json = json;
    }

    public CityEventMessage redact(CityEventMessage message) {
        String type = message.type() == null ? "" : message.type();
        Set<String> allowed = ALLOWED.stream()
                .filter(e -> type.startsWith(e.getKey()))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElse(Set.of());
        Map<String, Object> out = new LinkedHashMap<>();
        if (!allowed.isEmpty() && message.data() != null) {
            Map<?, ?> source = json.convertValue(message.data(), Map.class);
            for (Map.Entry<?, ?> e : source.entrySet()) {
                String key = String.valueOf(e.getKey());
                if (allowed.contains(key)) {
                    Object value = e.getValue();
                    if (type.startsWith("INCIDENT_") && COARSE_LOCATION.contains(key) && value instanceof Number n) {
                        value = Math.round(n.doubleValue() * 100.0) / 100.0;
                    }
                    out.put(key, value);
                }
            }
        }
        return new CityEventMessage(message.type(), message.entityId(), out, message.timestamp());
    }
}

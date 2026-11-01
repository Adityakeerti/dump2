package com.citysense.platform.realtime;

import java.time.Instant;

/**
 * Envelope for everything pushed on /topic/city-events. Clients switch on {@code type}
 * (e.g. OBSERVATION_CREATED, INCIDENT_UPDATED, ACTION_APPROVED) and read {@code data}.
 */
public record CityEventMessage(String type, String entityId, Object data, Instant timestamp) {

    public static CityEventMessage of(String type, Object entityId, Object data) {
        return new CityEventMessage(type, String.valueOf(entityId), data, Instant.now());
    }
}

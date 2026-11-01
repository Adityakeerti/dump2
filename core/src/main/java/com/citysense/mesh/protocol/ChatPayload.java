package com.citysense.mesh.protocol;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Layer 3 — Plaintext or group chat content.
 * Supports public nearby room or direct mesh messaging without internet.
 */
public record ChatPayload(
        String body,
        String senderName,
        String channel,
        String urgency,
        Double latitude,
        Double longitude) {

    @JsonCreator
    public ChatPayload(
            @JsonProperty("body") String body,
            @JsonProperty("senderName") String senderName,
            @JsonProperty("channel") String channel,
            @JsonProperty("urgency") String urgency,
            @JsonProperty("latitude") Double latitude,
            @JsonProperty("longitude") Double longitude) {
        this.body = body != null ? body : "";
        this.senderName = senderName != null ? senderName : "Anonymous";
        this.channel = channel != null ? channel : "NEARBY_PUBLIC";
        this.urgency = urgency != null ? urgency : "NORMAL";
        this.latitude = latitude;
        this.longitude = longitude;
    }
}

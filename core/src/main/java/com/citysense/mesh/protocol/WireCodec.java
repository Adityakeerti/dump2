package com.citysense.mesh.protocol;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;

/**
 * Encodes and decodes layered mesh frames between in-memory models and on-wire representations.
 * Mirrors Knit's WireCodec rules: ignore unknown keys for forward compatibility.
 */
public final class WireCodec {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private WireCodec() {}

    public static ObjectMapper getMapper() {
        return MAPPER;
    }

    public static String encodeWire(WireEnvelope envelope) {
        try {
            return MAPPER.writeValueAsString(envelope);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to serialize WireEnvelope: " + e.getMessage(), e);
        }
    }

    public static byte[] encodeWireBytes(WireEnvelope envelope) {
        return encodeWire(envelope).getBytes(StandardCharsets.UTF_8);
    }

    public static WireEnvelope decodeWire(String json) {
        try {
            return MAPPER.readValue(json, WireEnvelope.class);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to deserialize WireEnvelope: " + e.getMessage(), e);
        }
    }

    public static WireEnvelope decodeWire(byte[] bytes) {
        return decodeWire(new String(bytes, StandardCharsets.UTF_8));
    }

    public static String encodeRelay(RelayEnvelope envelope) {
        try {
            return MAPPER.writeValueAsString(envelope);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to serialize RelayEnvelope: " + e.getMessage(), e);
        }
    }

    public static RelayEnvelope decodeRelay(String json) {
        try {
            return MAPPER.readValue(json, RelayEnvelope.class);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to deserialize RelayEnvelope: " + e.getMessage(), e);
        }
    }

    public static String encodePayload(Object payload) {
        try {
            return MAPPER.writeValueAsString(payload);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to serialize payload: " + e.getMessage(), e);
        }
    }

    public static <T> T decodePayload(String payloadJson, Class<T> clazz) {
        try {
            return MAPPER.readValue(payloadJson, clazz);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Failed to deserialize payload to " + clazz.getSimpleName() + ": " + e.getMessage(), e);
        }
    }
}

package com.citysense.platform.observation;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.util.Arrays;

/** Wire and DB values are lowercase (e.g. "cv_density") to match event.schema.json. */
public enum ObservationType {
    CV_DENSITY("cv_density", 1),
    COMPLAINT("complaint", 2),
    FLOOD("flood", 4),
    CRASH("crash", 4),
    EVENT("event", 1),
    AGENT_FINDING("agent_finding", 2),
    RAIN("rain", 2),
    CONGESTION("congestion", 2);

    private final String code;
    private final int baseSeverity;

    ObservationType(String code, int baseSeverity) {
        this.code = code;
        this.baseSeverity = baseSeverity;
    }

    @JsonValue
    public String code() {
        return code;
    }

    public int baseSeverity() {
        return baseSeverity;
    }

    @JsonCreator
    public static ObservationType fromCode(String code) {
        return Arrays.stream(values())
                .filter(t -> t.code.equalsIgnoreCase(code) || t.name().equalsIgnoreCase(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unknown observation type: " + code));
    }

    @Converter(autoApply = true)
    public static class JpaConverter implements AttributeConverter<ObservationType, String> {
        @Override
        public String convertToDatabaseColumn(ObservationType type) {
            return type == null ? null : type.code;
        }

        @Override
        public ObservationType convertToEntityAttribute(String code) {
            return code == null ? null : fromCode(code);
        }
    }
}

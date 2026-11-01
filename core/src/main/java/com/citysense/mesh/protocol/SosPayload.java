package com.citysense.mesh.protocol;

/**
 * Layer 3 — Critical SOS distress beacon.
 * Broadcast over mesh hops when mobile towers and internet are offline.
 * Automatically triggers CitySense emergency incident correlation upon receipt.
 */
public record SosPayload(
        String victimName,
        String emergencyType,
        Double latitude,
        Double longitude,
        Integer urgencyScore,
        Integer injuriesCount,
        String medicalNeeds,
        String details) {

    public SosPayload {
        victimName = victimName != null ? victimName : "Citizen in Distress";
        emergencyType = emergencyType != null ? emergencyType : "MEDICAL";
        latitude = latitude != null ? latitude : 30.3165;
        longitude = longitude != null ? longitude : 78.0322;
        urgencyScore = urgencyScore != null ? urgencyScore : 5;
        injuriesCount = injuriesCount != null ? injuriesCount : 1;
        medicalNeeds = medicalNeeds != null ? medicalNeeds : "Immediate Emergency Assistance";
        details = details != null ? details : "";
    }
}

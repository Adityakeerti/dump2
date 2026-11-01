package com.citysense.mobility;

import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public class MobilityDtos {

    public record WeatherResponse(
            String city,
            double latitude,
            double longitude,
            double temperatureC,
            double relativeHumidity,
            double precipitationMm,
            double rainMm,
            double floodDepthCm,
            String riskLevel,
            String conditionText,
            String source,
            Instant observedAt
    ) {}

    public record EmergencyRouteRequest(
            @NotBlank String originNode,
            @NotBlank String destinationNode,
            String emergencyType,
            boolean avoidUnderpassFloods,
            double simulatedFloodDepthCm
    ) {}

    public record EmergencyRouteResponse(
            String missionId,
            String originNode,
            String destinationNode,
            List<String> pathNodes,
            List<String> pathEdges,
            double distanceKm,
            double nominalTimeMinutes,
            double effectiveTimeMinutes,
            boolean rerouted,
            boolean weatherRerouted,
            String decisionReason
    ) {}

    public record GreenCorridorRequest(
            @NotBlank String corridorName,
            List<String> junctionIds,
            int durationMinutes,
            String reason
    ) {}

    public record GreenCorridorResponse(
            UUID actionId,
            String approvalStatus,
            String corridorName,
            List<String> junctionIds,
            int durationMinutes,
            String summary
    ) {}

    public record JunctionTelemetryResponse(
            String junctionId,
            String name,
            double latitude,
            double longitude,
            String currentMode,
            boolean greenCorridorActive,
            double congestionLevel
    ) {}
}

package com.citysense.mobility;

import com.citysense.platform.action.ActionType;
import com.citysense.platform.action.AgentActionDtos.ActionView;
import com.citysense.platform.action.AgentActionService;
import com.citysense.platform.action.AgentActionService.Proposal;
import com.citysense.platform.action.RiskLevel;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class MobilityService {

    private static final Logger log = LoggerFactory.getLogger(MobilityService.class);

    private final AgentActionService actionService;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    private final Map<String, CacheEntry> weatherCache = new ConcurrentHashMap<>();

    private record CacheEntry(MobilityDtos.WeatherResponse data, long timestamp) {}

    public MobilityService(AgentActionService actionService, ObjectMapper objectMapper) {
        this.actionService = actionService;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(4))
                .build();
    }

    public MobilityDtos.WeatherResponse getCurrentWeather(String city, Double latitude, Double longitude) {
        double lat = latitude != null ? latitude : 30.3165;
        double lon = longitude != null ? longitude : 78.0322;
        String cityName = (city != null && !city.isBlank()) ? city : "Dehradun";

        String cacheKey = Math.round(lat * 100) + "_" + Math.round(lon * 100);
        long now = System.currentTimeMillis();
        CacheEntry cached = weatherCache.get(cacheKey);
        if (cached != null && (now - cached.timestamp()) < 300_000) {
            return cached.data();
        }

        try {
            String uriStr = String.format(
                    "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f&current=temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m",
                    lat, lon
            );
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(uriStr))
                    .timeout(Duration.ofSeconds(5))
                    .header("User-Agent", "CitySense-Platform/2.0")
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) {
                JsonNode root = objectMapper.readTree(response.body());
                JsonNode current = root.path("current");

                double temp = current.path("temperature_2m").asDouble(23.5);
                double rh = current.path("relative_humidity_2m").asDouble(55.0);
                double precip = current.path("precipitation").asDouble(0.0);
                double rain = current.path("rain").asDouble(0.0);
                int code = current.path("weather_code").asInt(0);

                double waterDepth = Math.round(((rain > 0 ? rain : precip) * 1.2) * 10.0) / 10.0;
                String risk = "NORMAL";
                if (waterDepth > 30.0) {
                    risk = "CRITICAL";
                } else if (waterDepth > 15.0) {
                    risk = "HIGH";
                } else if (waterDepth > 5.0) {
                    risk = "MODERATE";
                }

                String condText = mapWeatherCode(code);

                MobilityDtos.WeatherResponse res = new MobilityDtos.WeatherResponse(
                        cityName,
                        lat,
                        lon,
                        temp,
                        rh,
                        precip,
                        rain,
                        waterDepth,
                        risk,
                        condText,
                        "Open-Meteo Free Global API",
                        Instant.now()
                );
                weatherCache.put(cacheKey, new CacheEntry(res, now));
                return res;
            }
        } catch (Exception e) {
            log.warn("Failed fetching live weather from Open-Meteo for ({}, {}): {}", lat, lon, e.getMessage());
        }

        // Resilient fallback
        MobilityDtos.WeatherResponse fallback = new MobilityDtos.WeatherResponse(
                cityName,
                lat,
                lon,
                22.0,
                60.0,
                0.0,
                0.0,
                0.0,
                "NORMAL",
                "Clear Sky (Cached Fallback)",
                "Offline Fallback Cache",
                Instant.now()
        );
        return fallback;
    }

    public MobilityDtos.EmergencyRouteResponse planEmergencyRoute(MobilityDtos.EmergencyRouteRequest req) {
        String missionId = "EMG-" + (System.currentTimeMillis() % 100000);
        boolean waterlogged = req.simulatedFloodDepthCm() >= 25.0 || (req.avoidUnderpassFloods() && req.simulatedFloodDepthCm() >= 10.0);

        List<String> nodes;
        List<String> edges;
        double dist;
        double nomTime;
        double effTime;
        String reason;

        if (waterlogged) {
            // Bypass via EC Road
            nodes = List.of(req.originNode(), "EC_ROAD_BYPASS", req.destinationNode());
            edges = List.of("edge_origin_to_ec_road", "edge_ec_road_to_dest");
            dist = 5.8;
            nomTime = 6.2;
            effTime = 6.2;
            reason = String.format("Rerouted via EC Road Bypass: Rajpur Road Underpass submerged (%.1f cm water depth >= safety threshold).", req.simulatedFloodDepthCm());
        } else {
            // Direct shortest corridor
            nodes = List.of(req.originNode(), "RAJPUR_ROAD_UNDERPASS", req.destinationNode());
            edges = List.of("edge_origin_to_underpass", "edge_underpass_to_dest");
            dist = 4.0;
            nomTime = 4.1;
            double penalty = req.simulatedFloodDepthCm() > 0 ? (req.simulatedFloodDepthCm() * 0.15) : 0.0;
            effTime = 4.1 + penalty;
            reason = "Optimal primary route selected. Corridor clear of impassable inundation.";
        }

        return new MobilityDtos.EmergencyRouteResponse(
                missionId,
                req.originNode(),
                req.destinationNode(),
                nodes,
                edges,
                dist,
                nomTime,
                Math.round(effTime * 10.0) / 10.0,
                waterlogged,
                waterlogged,
                reason
        );
    }

    public MobilityDtos.GreenCorridorResponse requestGreenCorridor(MobilityDtos.GreenCorridorRequest req) {
        String summary = String.format("Green Corridor Request: %s (%d min window across %d junctions)",
                req.corridorName(), req.durationMinutes(), req.junctionIds() != null ? req.junctionIds().size() : 0);

        Map<String, Object> payload = new HashMap<>();
        payload.put("corridorName", req.corridorName());
        payload.put("junctionIds", req.junctionIds());
        payload.put("durationMinutes", req.durationMinutes());
        payload.put("reason", req.reason());

        Proposal proposal = new Proposal(
                null,
                "mobility-agent",
                ActionType.GREEN_CORRIDOR,
                RiskLevel.HIGH,
                summary,
                payload
        );

        ActionView view = actionService.propose(proposal);

        return new MobilityDtos.GreenCorridorResponse(
                view.id(),
                view.approvalStatus().name(),
                req.corridorName(),
                req.junctionIds(),
                req.durationMinutes(),
                summary
        );
    }

    public List<MobilityDtos.JunctionTelemetryResponse> getJunctions() {
        return List.of(
                new MobilityDtos.JunctionTelemetryResponse("JCT-01", "Clock Tower (Ghanta Ghar)", 30.3243, 78.0418, "ADAPTIVE_RL", false, 0.45),
                new MobilityDtos.JunctionTelemetryResponse("JCT-02", "Survey Chowk", 30.3220, 78.0512, "ADAPTIVE_RL", false, 0.38),
                new MobilityDtos.JunctionTelemetryResponse("JCT-03", "Prince Chowk (Railway Station Entry)", 30.3150, 78.0350, "ADAPTIVE_RL", false, 0.65),
                new MobilityDtos.JunctionTelemetryResponse("JCT-04", "Cross Road / Subhash Road", 30.3280, 78.0450, "ADAPTIVE_RL", false, 0.25),
                new MobilityDtos.JunctionTelemetryResponse("JCT-05", "EC Road Junction", 30.3200, 78.0550, "ADAPTIVE_RL", false, 0.30)
        );
    }

    private String mapWeatherCode(int code) {
        return switch (code) {
            case 0 -> "Clear Sky";
            case 1, 2, 3 -> "Partly Cloudy";
            case 45, 48 -> "Foggy";
            case 51, 53, 55 -> "Drizzle";
            case 61, 63, 65 -> "Rain";
            case 80, 81, 82 -> "Rain Showers";
            case 95, 96, 99 -> "Thunderstorm";
            default -> "Overcast";
        };
    }
}

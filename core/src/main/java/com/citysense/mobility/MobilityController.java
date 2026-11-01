package com.citysense.mobility;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Mobility", description = "Weather observations, emergency predictive routing, and green corridor preemption")
public class MobilityController {

    private final MobilityService mobilityService;

    public MobilityController(MobilityService mobilityService) {
        this.mobilityService = mobilityService;
    }

    @GetMapping({"/api/mobility/weather", "/api/weather/current"})
    @Operation(summary = "Fetch live Open-Meteo weather and urban water depth estimate")
    public MobilityDtos.WeatherResponse getWeather(
            @RequestParam(required = false, defaultValue = "Dehradun") String city,
            @RequestParam(required = false) Double latitude,
            @RequestParam(required = false) Double longitude) {
        return mobilityService.getCurrentWeather(city, latitude, longitude);
    }

    @PostMapping("/api/mobility/emergency-route")
    @Operation(summary = "Compute predictive emergency routing with flood depth and underpass waterlogging bypass")
    public MobilityDtos.EmergencyRouteResponse planEmergencyRoute(@Valid @RequestBody MobilityDtos.EmergencyRouteRequest req) {
        return mobilityService.planEmergencyRoute(req);
    }

    @PostMapping("/api/mobility/green-corridor")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Propose emergency green corridor for traffic coordinator approval queue")
    public MobilityDtos.GreenCorridorResponse requestGreenCorridor(@Valid @RequestBody MobilityDtos.GreenCorridorRequest req) {
        return mobilityService.requestGreenCorridor(req);
    }

    @GetMapping("/api/mobility/junctions")
    @Operation(summary = "Get real-time junction telemetry and adaptive RL signal state")
    public List<MobilityDtos.JunctionTelemetryResponse> getJunctions() {
        return mobilityService.getJunctions();
    }
}

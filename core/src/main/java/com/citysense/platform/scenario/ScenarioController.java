package com.citysense.platform.scenario;

import com.citysense.common.error.ApiException;
import com.citysense.platform.observation.ObservationDtos.IngestResponse;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationService;
import com.citysense.platform.observation.ObservationStatus;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/scenarios")
@Tag(name = "Scenarios")
public class ScenarioController {

    private final ObservationService observations;

    public ScenarioController(ObservationService observations) {
        this.observations = observations;
    }

    @GetMapping
    public List<String> list() {
        return Arrays.stream(Scenario.values()).map(s -> s.name().toLowerCase()).toList();
    }

    @PostMapping("/{name}")
    @Operation(summary = "Inject a demo scenario; all observations are labelled SIMULATED")
    public List<IngestResponse> inject(@PathVariable String name) {
        Scenario scenario = Arrays.stream(Scenario.values())
                .filter(s -> s.name().equalsIgnoreCase(name))
                .findFirst()
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Unknown scenario: " + name));
        // Each step is its own transaction, so clients see the incident build up one observation at a time.
        return scenario.steps().stream()
                .map(step -> observations.ingest(new ObservationRequest(
                        step.type(), step.latitude(), step.longitude(), null, "scenario:" + name.toLowerCase(),
                        step.confidence(), ObservationStatus.SIMULATED,
                        Map.of("locationName", step.locationName(), step.metric(), step.value(),
                                "scenario", name.toLowerCase())), "scenario"))
                .toList();
    }
}

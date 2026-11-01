package com.citysense.platform.scenario;

import com.citysense.platform.observation.ObservationType;
import java.util.List;

/**
 * One-click demo scenarios for the dashboard Scenario Control Panel. Coordinates are approximate
 * points in central Dehradun chosen for the demo, not surveyed locations.
 */
public enum Scenario {
    RAIN(List.of(
            new Step(ObservationType.RAIN, 30.3243, 78.0418, 0.9, "Clock Tower", "rainfall_mm_hr", 42))),
    FLOOD(List.of(
            new Step(ObservationType.RAIN, 30.3243, 78.0418, 0.9, "Clock Tower", "rainfall_mm_hr", 55),
            new Step(ObservationType.FLOOD, 30.3255, 78.0430, 0.85, "Clock Tower underpass", "water_depth_cm", 45),
            new Step(ObservationType.CONGESTION, 30.3236, 78.0405, 0.8, "Rajpur Road junction", "queue_length_m", 300))),
    CRASH(List.of(
            new Step(ObservationType.CRASH, 30.3165, 78.0322, 0.95, "Prince Chowk", "vehicles_involved", 2))),
    CONGESTION(List.of(
            new Step(ObservationType.CV_DENSITY, 30.3236, 78.0405, 0.9, "Rajpur Road junction", "density", 0.93)));

    private final List<Step> steps;

    Scenario(List<Step> steps) {
        this.steps = steps;
    }

    public List<Step> steps() {
        return steps;
    }

    public record Step(ObservationType type, double latitude, double longitude, double confidence,
                       String locationName, String metric, Number value) {}
}

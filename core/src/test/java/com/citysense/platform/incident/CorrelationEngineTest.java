package com.citysense.platform.incident;

import static org.assertj.core.api.Assertions.assertThat;

import com.citysense.platform.observation.Observation;
import com.citysense.platform.observation.ObservationStatus;
import com.citysense.platform.observation.ObservationType;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class CorrelationEngineTest {

    private static Observation obs(ObservationType type, double confidence, Map<String, Object> payload) {
        return new Observation(type, 30.3243, 78.0418, Instant.now(), "test", confidence,
                ObservationStatus.SIMULATED, payload);
    }

    @Test
    void cityEventsAndLowDensityDoNotRaiseIncidents() {
        assertThat(CorrelationEngine.raisesIncident(obs(ObservationType.EVENT, 1, Map.of()))).isFalse();
        assertThat(CorrelationEngine.raisesIncident(obs(ObservationType.CV_DENSITY, 1, Map.of("density", 0.4)))).isFalse();
        assertThat(CorrelationEngine.raisesIncident(obs(ObservationType.CV_DENSITY, 1, Map.of("density", 0.75)))).isTrue();
        assertThat(CorrelationEngine.raisesIncident(obs(ObservationType.FLOOD, 0.5, Map.of()))).isTrue();
    }

    @Test
    void singleFloodTakesBaseSeverity() {
        var score = CorrelationEngine.score(List.of(obs(ObservationType.FLOOD, 0.8, Map.of())));
        assertThat(score.dominantType()).isEqualTo(ObservationType.FLOOD);
        assertThat(score.severity()).isEqualTo(4);
        assertThat(score.urgency()).isEqualTo(4 * 15 + 8.0);
    }

    @Test
    void rainFloodAndCongestionTogetherEscalateToMaxSeverity() {
        var score = CorrelationEngine.score(List.of(
                obs(ObservationType.RAIN, 0.9, Map.of()),
                obs(ObservationType.FLOOD, 0.85, Map.of()),
                obs(ObservationType.CONGESTION, 0.8, Map.of())));
        // base 4 (flood) +1 for 3 corroborating observations +1 for 3 distinct types, capped at 5
        assertThat(score.severity()).isEqualTo(5);
        assertThat(score.dominantType()).isEqualTo(ObservationType.FLOOD);
        assertThat(score.observationCount()).isEqualTo(3);
        assertThat(score.urgency()).isGreaterThan(CorrelationEngine.score(
                List.of(obs(ObservationType.FLOOD, 0.85, Map.of()))).urgency());
    }

    @Test
    void urgencyIsCappedAt100() {
        var many = java.util.stream.IntStream.range(0, 20)
                .mapToObj(i -> obs(ObservationType.values()[i % 4 + 1], 1.0, Map.of()))
                .toList();
        assertThat(CorrelationEngine.score(many).urgency()).isLessThanOrEqualTo(100);
    }

    @Test
    void veryHighDensityCountsAsSeverityThree() {
        var score = CorrelationEngine.score(List.of(obs(ObservationType.CV_DENSITY, 1, Map.of("density", 0.95))));
        assertThat(score.severity()).isEqualTo(3);
    }
}

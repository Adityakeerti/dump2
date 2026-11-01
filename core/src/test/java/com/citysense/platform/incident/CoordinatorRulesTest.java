package com.citysense.platform.incident;

import static org.assertj.core.api.Assertions.assertThat;

import com.citysense.platform.action.ActionType;
import com.citysense.platform.action.AgentActionService.Proposal;
import com.citysense.platform.observation.ObservationType;
import java.util.EnumSet;
import org.junit.jupiter.api.Test;

class CoordinatorRulesTest {

    private static Incident incident(ObservationType type, int severity) {
        Incident i = new Incident(type, "Flooding near Clock Tower", 30.3243, 78.0418);
        i.applyScore(new CorrelationEngine.Score(type, severity, 0, 1), "Flooding near Clock Tower", null);
        return i;
    }

    @Test
    void floodProposesRoadClosureAndWarning() {
        var proposals = CoordinatorRules.proposalsFor(incident(ObservationType.FLOOD, 4), EnumSet.of(ObservationType.FLOOD));
        assertThat(proposals).extracting(Proposal::actionType)
                .containsExactlyInAnyOrder(ActionType.ROAD_CLOSURE, ActionType.NOTIFY_CITIZENS);
    }

    @Test
    void severeFloodAlsoProposesEvacuation() {
        var proposals = CoordinatorRules.proposalsFor(incident(ObservationType.FLOOD, 5),
                EnumSet.of(ObservationType.FLOOD, ObservationType.RAIN, ObservationType.CONGESTION));
        assertThat(proposals).extracting(Proposal::actionType).contains(ActionType.EVACUATION);
    }

    @Test
    void lowSeverityRainProposesNothing() {
        assertThat(CoordinatorRules.proposalsFor(incident(ObservationType.RAIN, 2), EnumSet.of(ObservationType.RAIN)))
                .isEmpty();
    }
}

package com.citysense.mobility;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.citysense.platform.action.ActionType;
import com.citysense.platform.action.AgentActionDtos.ActionView;
import com.citysense.platform.action.AgentActionService;
import com.citysense.platform.action.ApprovalStatus;
import com.citysense.platform.action.RiskLevel;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MobilityServiceTest {

    private AgentActionService actionService;
    private ObjectMapper objectMapper;
    private MobilityService service;

    @BeforeEach
    void setUp() {
        actionService = mock(AgentActionService.class);
        objectMapper = new ObjectMapper();
        service = new MobilityService(actionService, objectMapper);
    }

    @Test
    void planEmergencyRouteReroutesWhenUnderpassFlooded() {
        var req = new MobilityDtos.EmergencyRouteRequest(
                "DOON_HOSPITAL",
                "CLOCK_TOWER",
                "ACCIDENT",
                true,
                32.0 // 32 cm flood depth > 25cm critical threshold
        );

        var res = service.planEmergencyRoute(req);

        assertThat(res.rerouted()).isTrue();
        assertThat(res.weatherRerouted()).isTrue();
        assertThat(res.pathNodes()).contains("EC_ROAD_BYPASS");
        assertThat(res.pathNodes()).doesNotContain("RAJPUR_ROAD_UNDERPASS");
        assertThat(res.decisionReason()).contains("Rerouted via EC Road Bypass");
    }

    @Test
    void planEmergencyRoutePreservesDirectCorridorWhenDry() {
        var req = new MobilityDtos.EmergencyRouteRequest(
                "DOON_HOSPITAL",
                "CLOCK_TOWER",
                "ACCIDENT",
                true,
                0.0 // clear dry roads
        );

        var res = service.planEmergencyRoute(req);

        assertThat(res.rerouted()).isFalse();
        assertThat(res.weatherRerouted()).isFalse();
        assertThat(res.pathNodes()).contains("RAJPUR_ROAD_UNDERPASS");
        assertThat(res.pathNodes()).doesNotContain("EC_ROAD_BYPASS");
    }

    @Test
    void requestGreenCorridorSubmitsHighRiskProposalToApprovalQueue() {
        UUID actionId = UUID.randomUUID();
        when(actionService.propose(any())).thenReturn(
                new ActionView(
                        actionId,
                        null,
                        "mobility-agent",
                        ActionType.GREEN_CORRIDOR,
                        "Green Corridor Request: Ambulance 108",
                        Map.of(),
                        RiskLevel.HIGH,
                        ApprovalStatus.PENDING,
                        null,
                        null,
                        null,
                        Instant.now()
                )
        );

        var req = new MobilityDtos.GreenCorridorRequest(
                "Ambulance 108 Emergency Route",
                List.of("JCT-01", "JCT-02", "JCT-03"),
                10,
                "Critical trauma transport to Doon Hospital"
        );

        var res = service.requestGreenCorridor(req);

        assertThat(res.actionId()).isEqualTo(actionId);
        assertThat(res.approvalStatus()).isEqualTo("PENDING");
        assertThat(res.junctionIds()).hasSize(3);
    }

    @Test
    void getJunctionsReturnsKeyDehradunNodes() {
        var junctions = service.getJunctions();
        assertThat(junctions).isNotEmpty();
        assertThat(junctions).anyMatch(j -> j.name().contains("Clock Tower"));
        assertThat(junctions).anyMatch(j -> j.name().contains("Railway Station"));
    }
}

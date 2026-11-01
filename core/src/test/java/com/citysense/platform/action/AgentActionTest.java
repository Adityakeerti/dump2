package com.citysense.platform.action;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.citysense.common.error.ApiException;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AgentActionTest {

    private static AgentAction action(ActionType type, RiskLevel risk) {
        return new AgentAction(null, "test", type, "summary", Map.of(), risk);
    }

    @Test
    void highRiskStartsPendingAndLowRiskAutoExecutes() {
        assertThat(action(ActionType.ROAD_CLOSURE, RiskLevel.HIGH).getApprovalStatus()).isEqualTo(ApprovalStatus.PENDING);
        assertThat(action(ActionType.NOTIFY_CITIZENS, RiskLevel.LOW).getApprovalStatus())
                .isEqualTo(ApprovalStatus.AUTO_EXECUTED);
    }

    @Test
    void proposerCannotLowerRiskBelowTypeMinimum() {
        assertThat(RiskLevel.LOW.atLeast(ActionType.GREEN_CORRIDOR.minimumRisk())).isEqualTo(RiskLevel.HIGH);
        assertThat(RiskLevel.HIGH.atLeast(ActionType.NOTIFY_CITIZENS.minimumRisk())).isEqualTo(RiskLevel.HIGH);
    }

    @Test
    void approveRecordsDecider() {
        AgentAction a = action(ActionType.DISPATCH, RiskLevel.HIGH);
        UUID admin = UUID.randomUUID();
        a.approve(admin, "verified on CCTV");
        assertThat(a.getApprovalStatus()).isEqualTo(ApprovalStatus.APPROVED);
        assertThat(a.getDecidedBy()).isEqualTo(admin);
        assertThat(a.getDecidedAt()).isNotNull();
    }

    @Test
    void decidedActionsAreTerminal() {
        AgentAction a = action(ActionType.DISPATCH, RiskLevel.HIGH);
        a.reject(UUID.randomUUID(), "duplicate");
        assertThatThrownBy(() -> a.approve(UUID.randomUUID(), null)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> action(ActionType.NOTIFY_CITIZENS, RiskLevel.LOW).reject(UUID.randomUUID(), "x"))
                .isInstanceOf(ApiException.class);
    }
}

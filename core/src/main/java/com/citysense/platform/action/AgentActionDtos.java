package com.citysense.platform.action;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public final class AgentActionDtos {

    private AgentActionDtos() {}

    /** Used by other modules (e.g. mobility green corridor) and ai-service to propose an action. */
    public record ProposeRequest(
            UUID incidentId,
            @NotBlank @Size(max = 64) String agent,
            @NotNull ActionType actionType,
            RiskLevel riskLevel,
            @Size(max = 2000) String summary,
            Map<String, Object> payload) {}

    public record DecisionRequest(@Size(max = 2000) String reason) {}

    public record RejectRequest(@NotBlank @Size(max = 2000) String reason) {}

    public record ActionView(UUID id, UUID incidentId, String agent, ActionType actionType, String summary,
                             Map<String, Object> payload, RiskLevel riskLevel, ApprovalStatus approvalStatus,
                             UUID decidedBy, Instant decidedAt, String decisionReason, Instant createdAt) {
        public static ActionView of(AgentAction a) {
            return new ActionView(a.getId(), a.getIncidentId(), a.getAgent(), a.getActionType(), a.getSummary(),
                    a.getPayload(), a.getRiskLevel(), a.getApprovalStatus(), a.getDecidedBy(), a.getDecidedAt(),
                    a.getDecisionReason(), a.getCreatedAt());
        }
    }
}

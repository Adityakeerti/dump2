package com.citysense.platform.action;

import com.citysense.common.error.ApiException;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "agent_actions")
public class AgentAction {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "incident_id")
    private UUID incidentId;

    @Column(nullable = false)
    private String agent;

    @Enumerated(EnumType.STRING)
    @Column(name = "action_type", nullable = false)
    private ActionType actionType;

    private String summary;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> payload;

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level", nullable = false)
    private RiskLevel riskLevel;

    @Enumerated(EnumType.STRING)
    @Column(name = "approval_status", nullable = false)
    private ApprovalStatus approvalStatus;

    @Column(name = "decided_by")
    private UUID decidedBy;

    @Column(name = "decided_at")
    private Instant decidedAt;

    @Column(name = "decision_reason")
    private String decisionReason;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    // Two admins clicking approve/reject at once: the second write fails instead of overwriting.
    @Version
    private long version;

    protected AgentAction() {}

    public AgentAction(UUID incidentId, String agent, ActionType actionType, String summary,
                       Map<String, Object> payload, RiskLevel riskLevel) {
        this.incidentId = incidentId;
        this.agent = agent;
        this.actionType = actionType;
        this.summary = summary;
        this.payload = payload;
        this.riskLevel = riskLevel;
        this.approvalStatus = riskLevel == RiskLevel.LOW ? ApprovalStatus.AUTO_EXECUTED : ApprovalStatus.PENDING;
        if (approvalStatus == ApprovalStatus.AUTO_EXECUTED) {
            this.decidedAt = Instant.now();
            this.decisionReason = "Auto-executed: low risk";
        }
    }

    public void approve(UUID adminId, String reason) {
        decide(ApprovalStatus.APPROVED, adminId, reason);
    }

    public void reject(UUID adminId, String reason) {
        decide(ApprovalStatus.REJECTED, adminId, reason);
    }

    private void decide(ApprovalStatus outcome, UUID adminId, String reason) {
        if (approvalStatus != ApprovalStatus.PENDING) {
            throw ApiException.conflict("Action " + id + " is already " + approvalStatus);
        }
        this.approvalStatus = outcome;
        this.decidedBy = adminId;
        this.decidedAt = Instant.now();
        this.decisionReason = reason;
    }

    public UUID getId() { return id; }
    public UUID getIncidentId() { return incidentId; }
    public String getAgent() { return agent; }
    public ActionType getActionType() { return actionType; }
    public String getSummary() { return summary; }
    public Map<String, Object> getPayload() { return payload; }
    public RiskLevel getRiskLevel() { return riskLevel; }
    public ApprovalStatus getApprovalStatus() { return approvalStatus; }
    public UUID getDecidedBy() { return decidedBy; }
    public Instant getDecidedAt() { return decidedAt; }
    public String getDecisionReason() { return decisionReason; }
    public Instant getCreatedAt() { return createdAt; }
}

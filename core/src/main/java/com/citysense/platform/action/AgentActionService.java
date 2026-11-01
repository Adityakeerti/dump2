package com.citysense.platform.action;

import com.citysense.common.error.ApiException;
import com.citysense.platform.action.AgentActionDtos.ActionView;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.auth.AuthUser;
import com.citysense.platform.realtime.CityEventMessage;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Human-in-the-loop governance: high-impact actions wait for an admin; every transition is audited. */
@Service
public class AgentActionService {

    private final AgentActionRepository repo;
    private final AuditService audit;
    private final ApplicationEventPublisher events;

    public AgentActionService(AgentActionRepository repo, AuditService audit, ApplicationEventPublisher events) {
        this.repo = repo;
        this.audit = audit;
        this.events = events;
    }

    /** riskLevel may be null; it is always raised to the action type's minimum. */
    public record Proposal(UUID incidentId, String agent, ActionType actionType, RiskLevel riskLevel,
                           String summary, Map<String, Object> payload) {}

    @Transactional
    public ActionView propose(Proposal p) {
        RiskLevel requested = p.riskLevel() == null ? p.actionType().minimumRisk() : p.riskLevel();
        AgentAction action = repo.save(new AgentAction(p.incidentId(), p.agent(), p.actionType(), p.summary(),
                p.payload() == null ? Map.of() : p.payload(), requested.atLeast(p.actionType().minimumRisk())));

        Map<String, Object> evidence = new HashMap<>();
        evidence.put("actionType", action.getActionType().name());
        evidence.put("riskLevel", action.getRiskLevel().name());
        evidence.put("agent", action.getAgent());
        if (action.getIncidentId() != null) {
            evidence.put("incidentId", action.getIncidentId().toString());
        }
        audit.record(action.getAgent(), "ACTION_PROPOSED", "agent_action", action.getId().toString(),
                action.getApprovalStatus().name(), evidence);

        ActionView view = ActionView.of(action);
        events.publishEvent(CityEventMessage.of(
                action.getApprovalStatus() == ApprovalStatus.PENDING ? "ACTION_PENDING" : "ACTION_AUTO_EXECUTED",
                action.getId(), view));
        return view;
    }

    /** Coordinator re-evaluates on every new observation; this keeps it from re-proposing the same action. */
    @Transactional
    public void proposeOnce(Proposal p) {
        if (p.incidentId() != null && repo.existsByIncidentIdAndActionType(p.incidentId(), p.actionType())) {
            return;
        }
        propose(p);
    }

    @Transactional
    public ActionView approve(UUID id, AuthUser admin, String reason) {
        AgentAction action = find(id);
        action.approve(admin.id(), reason);
        return afterDecision(action, admin, "ACTION_APPROVED");
    }

    @Transactional
    public ActionView reject(UUID id, AuthUser admin, String reason) {
        AgentAction action = find(id);
        action.reject(admin.id(), reason);
        return afterDecision(action, admin, "ACTION_REJECTED");
    }

    @Transactional(readOnly = true)
    public List<ActionView> list(ApprovalStatus status) {
        List<AgentAction> rows = status == null
                ? repo.findAllByOrderByCreatedAtDesc()
                : repo.findByApprovalStatusOrderByCreatedAtDesc(status);
        return rows.stream().map(ActionView::of).toList();
    }

    @Transactional(readOnly = true)
    public List<ActionView> forIncident(UUID incidentId) {
        return repo.findByIncidentIdOrderByCreatedAtAsc(incidentId).stream().map(ActionView::of).toList();
    }

    private ActionView afterDecision(AgentAction action, AuthUser admin, String auditAction) {
        // Flush now so a concurrent decision fails on the @Version check before we audit and broadcast.
        repo.saveAndFlush(action);
        Map<String, Object> evidence = new HashMap<>();
        evidence.put("actionType", action.getActionType().name());
        evidence.put("riskLevel", action.getRiskLevel().name());
        if (action.getDecisionReason() != null) {
            evidence.put("reason", action.getDecisionReason());
        }
        audit.record(admin.email(), auditAction, "agent_action", action.getId().toString(),
                action.getApprovalStatus().name(), evidence);
        ActionView view = ActionView.of(action);
        events.publishEvent(CityEventMessage.of(auditAction, action.getId(), view));
        return view;
    }

    private AgentAction find(UUID id) {
        return repo.findById(id).orElseThrow(() -> ApiException.notFound("Action", id));
    }
}

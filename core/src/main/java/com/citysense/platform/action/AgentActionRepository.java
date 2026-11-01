package com.citysense.platform.action;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AgentActionRepository extends JpaRepository<AgentAction, UUID> {

    List<AgentAction> findByApprovalStatusOrderByCreatedAtDesc(ApprovalStatus status);

    List<AgentAction> findAllByOrderByCreatedAtDesc();

    List<AgentAction> findByIncidentIdOrderByCreatedAtAsc(UUID incidentId);

    boolean existsByIncidentIdAndActionType(UUID incidentId, ActionType actionType);
}

package com.citysense.platform.action;

import com.citysense.platform.action.AgentActionDtos.ActionView;
import com.citysense.platform.action.AgentActionDtos.DecisionRequest;
import com.citysense.platform.action.AgentActionDtos.ProposeRequest;
import com.citysense.platform.action.AgentActionDtos.RejectRequest;
import com.citysense.platform.action.AgentActionService.Proposal;
import com.citysense.platform.auth.AuthUser;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/actions")
@Tag(name = "Approvals")
@PreAuthorize("hasRole('ADMIN')")
public class AgentActionController {

    private final AgentActionService service;

    public AgentActionController(AgentActionService service) {
        this.service = service;
    }

    @GetMapping
    public List<ActionView> list(@RequestParam(required = false) ApprovalStatus status) {
        return service.list(status);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ActionView propose(@Valid @RequestBody ProposeRequest req) {
        return service.propose(new Proposal(req.incidentId(), req.agent(), req.actionType(), req.riskLevel(),
                req.summary(), req.payload()));
    }

    @PostMapping("/{id}/approve")
    public ActionView approve(@PathVariable UUID id, @AuthenticationPrincipal AuthUser admin,
                              @Valid @RequestBody(required = false) DecisionRequest body) {
        return service.approve(id, admin, body == null ? null : body.reason());
    }

    @PostMapping("/{id}/reject")
    public ActionView reject(@PathVariable UUID id, @AuthenticationPrincipal AuthUser admin,
                             @Valid @RequestBody RejectRequest body) {
        return service.reject(id, admin, body.reason());
    }
}

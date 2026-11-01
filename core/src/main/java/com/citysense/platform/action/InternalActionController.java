package com.citysense.platform.action;

import com.citysense.platform.action.AgentActionDtos.ActionView;
import com.citysense.platform.action.AgentActionDtos.ProposeRequest;
import com.citysense.platform.action.AgentActionService.Proposal;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** ai-service proposes actions here; they enter the same approval queue as everything else. */
@RestController
@RequestMapping("/internal/actions")
@Tag(name = "Internal")
@SecurityRequirement(name = "internalKey")
public class InternalActionController {

    private final AgentActionService service;

    public InternalActionController(AgentActionService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ActionView propose(@Valid @RequestBody ProposeRequest req) {
        return service.propose(new Proposal(req.incidentId(), req.agent(), req.actionType(), req.riskLevel(),
                req.summary(), req.payload()));
    }
}

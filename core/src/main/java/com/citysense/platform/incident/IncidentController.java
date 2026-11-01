package com.citysense.platform.incident;

import com.citysense.platform.incident.IncidentDtos.IncidentDetail;
import com.citysense.platform.incident.IncidentDtos.IncidentView;
import com.citysense.platform.incident.IncidentDtos.StatusChange;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/incidents")
@Tag(name = "Incidents")
public class IncidentController {

    private final IncidentService service;

    public IncidentController(IncidentService service) {
        this.service = service;
    }

    @GetMapping
    public List<IncidentView> list(@RequestParam(required = false) IncidentStatus status) {
        return service.list(status);
    }

    @GetMapping("/{id}")
    public IncidentDetail detail(@PathVariable UUID id) {
        return service.detail(id);
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasRole('ADMIN')")
    public IncidentView changeStatus(@PathVariable UUID id, @Valid @RequestBody StatusChange body) {
        return service.changeStatus(id, body.status());
    }
}

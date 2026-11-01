package com.citysense.platform.observation;

import com.citysense.platform.observation.ObservationDtos.IngestResponse;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationDtos.ObservationView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/events")
@Tag(name = "Observations")
public class ObservationController {

    private final ObservationService service;

    public ObservationController(ObservationService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @PreAuthorize("hasAnyRole('ADMIN', 'CREW')")
    @Operation(summary = "Inject an observation (dashboard / crew)")
    public IngestResponse inject(@Valid @RequestBody ObservationRequest req) {
        return service.ingest(req, "manual");
    }

    @GetMapping
    @Operation(summary = "Most recent observations, optionally filtered by type")
    public List<ObservationView> recent(@RequestParam(required = false) ObservationType type,
                                        @RequestParam(defaultValue = "100") int limit) {
        return service.recent(type, limit);
    }
}

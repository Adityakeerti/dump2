package com.citysense.platform.observation;

import com.citysense.platform.observation.ObservationDtos.IngestResponse;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/observations")
@Tag(name = "Internal")
@SecurityRequirement(name = "internalKey")
public class InternalObservationController {

    private final ObservationService service;

    public InternalObservationController(ObservationService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "ai-service pushes observations (e.g. cv_density) here")
    public IngestResponse ingest(@Valid @RequestBody ObservationRequest req) {
        return service.ingest(req, "ai-service");
    }
}

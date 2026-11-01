package com.citysense.civic;

import com.citysense.common.error.ApiException;
import com.citysense.platform.auth.AuthUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * Access (enforced here and in CivicService, not by the app): meta and city-event listing are public;
 * everything else needs a JWT. Filing needs a verified email and is limited per user (429). A complaint is
 * visible to its owner, ADMIN, and CREW only for their own assignments or the unassigned queue; anyone else
 * gets 404. Listing is CREW/ADMIN with the same scope; status changes follow {@link ComplaintAccessPolicy};
 * publishing city events is ADMIN.
 */
@RestController
@Tag(name = "Civic", description = "Citizen complaints, municipal grievances, and city events")
public class CivicController {

    private final CivicService civicService;
    private final CivicProperties civicProps;

    public CivicController(CivicService civicService, CivicProperties civicProps) {
        this.civicService = civicService;
        this.civicProps = civicProps;
    }

    @GetMapping("/api/complaints/meta")
    @Operation(summary = "Complaint priorities and the escalation ladder (level index -> label)")
    public CivicDtos.CivicMeta meta() {
        return new CivicDtos.CivicMeta(civicProps.priorities(), civicProps.escalationLadder());
    }

    @PostMapping("/api/complaints")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Submit a grievance (signed in, verified email); it is owned by the caller",
            description = "At most 10 complaints per user in any sliding hour (configurable); the next gets 429.")
    @ApiResponse(responseCode = "201", description = "Filed", useReturnTypeSchema = true)
    @ApiResponse(responseCode = "400", description = "Validation failed (RFC 9457 problem)", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "401", description = "Missing or invalid JWT (no body)", content = @Content)
    @ApiResponse(responseCode = "403", description = "Email not verified", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "429", description = "Filing limit reached; Retry-After gives the seconds until a slot frees up",
            headers = @Header(name = "Retry-After", description = "Seconds to wait", schema = @Schema(type = "integer")),
            content = @Content(mediaType = "application/problem+json"))
    public CivicDtos.ComplaintResponse fileComplaint(@AuthenticationPrincipal AuthUser user,
                                                     @Valid @RequestBody CivicDtos.ComplaintCreateRequest req) {
        return civicService.fileComplaint(req, user);
    }

    @GetMapping("/api/complaints/mine")
    @Operation(summary = "Complaints filed by the signed-in user, newest first")
    public List<CivicDtos.ComplaintResponse> myComplaints(@AuthenticationPrincipal AuthUser user) {
        if (user == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Sign in required");
        }
        return civicService.listMine(user.id());
    }

    @GetMapping("/api/complaints")
    @Operation(summary = "List complaints, optionally filtered by status and/or department (CREW, ADMIN)",
            description = "ADMIN: all complaints. CREW: complaints assigned to them plus unassigned FILED/ESCALATED "
                    + "complaints available for assignment; never complaints assigned to other crew members.")
    @ApiResponse(responseCode = "200", description = "OK", useReturnTypeSchema = true)
    @ApiResponse(responseCode = "400", description = "Unknown status", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "401", description = "Missing or invalid JWT (no body)", content = @Content)
    @ApiResponse(responseCode = "403", description = "Not CREW or ADMIN", content = @Content(mediaType = "application/problem+json"))
    @PreAuthorize("hasAnyRole('CREW', 'ADMIN')")
    public List<CivicDtos.ComplaintResponse> listComplaints(
            @AuthenticationPrincipal AuthUser user,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String department) {
        return civicService.listComplaints(status, department, user);
    }

    @GetMapping("/api/complaints/{trackingId}")
    @Operation(summary = "Track a complaint by tracking ID (owner, ADMIN, CREW within their scope; anyone else gets 404)")
    @ApiResponse(responseCode = "200", description = "OK", useReturnTypeSchema = true)
    @ApiResponse(responseCode = "401", description = "Missing or invalid JWT (no body)", content = @Content)
    @ApiResponse(responseCode = "404", description = "Unknown ID, or a complaint the caller may not see (indistinguishable)", content = @Content(mediaType = "application/problem+json"))
    public CivicDtos.ComplaintResponse getComplaint(@AuthenticationPrincipal AuthUser user, @PathVariable String trackingId) {
        return civicService.getComplaint(trackingId, user);
    }

    @PatchMapping("/api/complaints/{id}/status")
    @Operation(summary = "Change complaint status: CREW on their own assignments, ADMIN for the full lifecycle",
            description = "CREW: FILED|ESCALATED->ASSIGNED (self only), ASSIGNED->IN_PROGRESS, IN_PROGRESS->RESOLVED, on "
                    + "complaints assigned to them. ADMIN: FILED->ASSIGNED|REJECTED|ESCALATED, ESCALATED->ASSIGNED|REJECTED, "
                    + "ASSIGNED->ASSIGNED|IN_PROGRESS|REJECTED|FILED, IN_PROGRESS->ASSIGNED|RESOLVED|REJECTED, "
                    + "RESOLVED|REJECTED->FILED. ASSIGNED needs a crew account email; REJECTED needs resolutionNotes.")
    @ApiResponse(responseCode = "200", description = "Changed (audited)", useReturnTypeSchema = true)
    @ApiResponse(responseCode = "400", description = "Unknown status, missing worker or reason, or worker is not a crew account", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "401", description = "Missing or invalid JWT (no body)", content = @Content)
    @ApiResponse(responseCode = "403", description = "Citizen, or crew acting outside their own assignment or allowed statuses", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "404", description = "No complaint with this id, or one the caller may not see (indistinguishable)", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "409", description = "Transition not allowed from the current status", content = @Content(mediaType = "application/problem+json"))
    public CivicDtos.ComplaintResponse updateStatus(
            @AuthenticationPrincipal AuthUser user,
            @PathVariable UUID id,
            @Valid @RequestBody CivicDtos.ComplaintStatusUpdateRequest req) {
        return civicService.updateStatus(id, req, user);
    }

    @GetMapping("/api/city-events")
    @Operation(summary = "List public city events, alerts, and community notices")
    public List<CivicDtos.CityEventResponse> listCityEvents() {
        return civicService.listCityEvents();
    }

    @PostMapping("/api/city-events")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Create a city event or public bulletin notice (ADMIN)")
    @ApiResponse(responseCode = "201", description = "Published", useReturnTypeSchema = true)
    @ApiResponse(responseCode = "400", description = "Validation failed", content = @Content(mediaType = "application/problem+json"))
    @ApiResponse(responseCode = "401", description = "Missing or invalid JWT (no body)", content = @Content)
    @ApiResponse(responseCode = "403", description = "Not ADMIN", content = @Content(mediaType = "application/problem+json"))
    @PreAuthorize("hasRole('ADMIN')")
    public CivicDtos.CityEventResponse createCityEvent(@Valid @RequestBody CivicDtos.CityEventCreateRequest req) {
        return civicService.createCityEvent(req);
    }
}

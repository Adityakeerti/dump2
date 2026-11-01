package com.citysense.civic;

import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.UUID;

public class CivicDtos {

    public record CivicMeta(java.util.List<String> priorities, java.util.List<String> escalationLadder) {}

    /**
     * What a complaint event may say on the unauthenticated live channel (/topic/city-events): no name,
     * description, exact location, photo, tracking ID, worker or notes, and a generated title instead of
     * the citizen's free text. Full details stay behind the authenticated REST endpoints.
     */
    public record ComplaintLiveEvent(UUID id, String title, String category, String department, String status,
                                     String priority) {
        public static ComplaintLiveEvent of(Complaint c, boolean filed) {
            String dept = c.getDepartment() == null ? "civic" : c.getDepartment().replace('_', ' ');
            String title = filed ? "New " + dept + " complaint"
                    : dept + " complaint " + c.getStatus().replace('_', ' ').toLowerCase(java.util.Locale.ROOT);
            return new ComplaintLiveEvent(c.getId(), title, c.getCategory(), c.getDepartment(), c.getStatus(),
                    c.getPriority());
        }
    }

    public record ComplaintCreateRequest(
            @NotBlank String title,
            @NotBlank String description,
            String category,
            String department,
            String priority,
            double latitude,
            double longitude,
            String citizenName,
            String photoUrl
    ) {}

    public record ComplaintStatusUpdateRequest(
            @NotBlank String status,
            String assignedWorker,
            String resolutionNotes
    ) {}

    public record ComplaintResponse(
            UUID id,
            String trackingId,
            String citizenName,
            String title,
            String description,
            String category,
            String department,
            String priority,
            String status,
            double latitude,
            double longitude,
            String photoUrl,
            int escalationLevel,
            String assignedWorker,
            String resolutionNotes,
            Instant resolvedAt,
            Instant createdAt,
            Instant updatedAt
    ) {
        public static ComplaintResponse from(Complaint c) {
            return new ComplaintResponse(
                    c.getId(),
                    c.getTrackingId(),
                    c.getCitizenName(),
                    c.getTitle(),
                    c.getDescription(),
                    c.getCategory(),
                    c.getDepartment(),
                    c.getPriority(),
                    c.getStatus(),
                    c.getLatitude(),
                    c.getLongitude(),
                    c.getPhotoUrl(),
                    c.getEscalationLevel(),
                    c.getAssignedWorker(),
                    c.getResolutionNotes(),
                    c.getResolvedAt(),
                    c.getCreatedAt(),
                    c.getUpdatedAt()
            );
        }
    }

    public record CityEventCreateRequest(
            @NotBlank String title,
            String description,
            String category,
            String severity,
            double latitude,
            double longitude,
            Instant startsAt,
            Instant endsAt
    ) {}

    public record CityEventResponse(
            UUID id,
            String title,
            String description,
            String category,
            String severity,
            double latitude,
            double longitude,
            Instant startsAt,
            Instant endsAt,
            Instant createdAt,
            String venue,
            String organizer,
            String sourceUrl
    ) {
        public static CityEventResponse from(CityEvent e) {
            return new CityEventResponse(
                    e.getId(),
                    e.getTitle(),
                    e.getDescription(),
                    e.getCategory(),
                    e.getSeverity(),
                    e.getLatitude(),
                    e.getLongitude(),
                    e.getStartsAt(),
                    e.getEndsAt(),
                    e.getCreatedAt(),
                    e.getVenue(),
                    e.getOrganizer(),
                    e.getSourceUrl()
            );
        }
    }
}

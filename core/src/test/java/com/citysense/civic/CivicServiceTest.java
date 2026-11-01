package com.citysense.civic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.citysense.common.error.ApiException;
import com.citysense.common.error.TooManyRequestsException;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.auth.AuthUser;
import com.citysense.platform.auth.Role;
import com.citysense.platform.auth.UserRepository;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationService;
import com.citysense.platform.realtime.CityEventMessage;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;

class CivicServiceTest {

    private static final AuthUser CITIZEN = new AuthUser(UUID.randomUUID(), "citizen@example.test", Role.CITIZEN, true);
    private static final AuthUser ADMIN = new AuthUser(UUID.randomUUID(), "admin@example.test", Role.ADMIN, true);

    private static final Instant NOW = Instant.parse("2026-10-31T16:00:00Z");
    private static final Duration WINDOW = Duration.ofHours(1);

    private ComplaintRepository complaintRepo;
    private ObservationService observationService;
    private ApplicationEventPublisher eventPublisher;
    private AuditService audit;
    private UserRepository users;
    private CivicService service;

    @BeforeEach
    void setUp() {
        complaintRepo = mock(ComplaintRepository.class);
        observationService = mock(ObservationService.class);
        eventPublisher = mock(ApplicationEventPublisher.class);
        audit = mock(AuditService.class);
        users = mock(UserRepository.class);
        service = new CivicService(complaintRepo, mock(CityEventRepository.class), observationService, eventPublisher,
                users, audit, new ComplaintFilingLimit(10, WINDOW), Clock.fixed(NOW, ZoneOffset.UTC));
        when(complaintRepo.save(any(Complaint.class))).thenAnswer(inv -> {
            Complaint c = inv.getArgument(0);
            if (c.getId() == null) {
                c.setId(UUID.randomUUID());
            }
            return c;
        });
    }

    private static CivicDtos.ComplaintCreateRequest request(String title, String description, String dept) {
        return new CivicDtos.ComplaintCreateRequest(title, description, "CIVIC", dept, "HIGH", 30.3243, 78.0418,
                "Aditya", null);
    }

    @Test
    void fileComplaintAutoClassifiesRoadsDepartmentAndIsOwnedByTheCaller() {
        var res = service.fileComplaint(request("Large pothole near Clock Tower",
                "Dangerous deep pothole on main road causing traffic slow down", "AUTO"), CITIZEN);

        assertThat(res.department()).isEqualTo("PWD_ROADS");
        assertThat(res.trackingId()).matches("CS-[0-9A-HJKMNP-TV-Z]{10}");
        assertThat(res.status()).isEqualTo("FILED");
        ArgumentCaptor<Complaint> saved = ArgumentCaptor.forClass(Complaint.class);
        verify(complaintRepo).save(saved.capture());
        assertThat(saved.getValue().getUserId()).isEqualTo(CITIZEN.id());
    }

    @Test
    void fileComplaintAutoClassifiesSanitationDepartment() {
        var res = service.fileComplaint(request("Garbage pile at Paltan Bazaar",
                "Overflowing waste bins and trash not collected for three days", null), CITIZEN);
        assertThat(res.department()).isEqualTo("SANITATION");
    }

    @Test
    void filingNeedsASignedInVerifiedUser() {
        var req = request("Pothole", "Deep pothole", null);
        assertThatThrownBy(() -> service.fileComplaint(req, null))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.UNAUTHORIZED));
        AuthUser unverified = new AuthUser(UUID.randomUUID(), "new@example.test", Role.CITIZEN, false);
        assertThatThrownBy(() -> service.fileComplaint(req, unverified))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        verify(complaintRepo, never()).save(any());
    }

    // ------------------------------------------------------------------ filing rate limit (10 per user per hour)

    private Complaint filedAt(Instant at) {
        Complaint c = new Complaint();
        c.setId(UUID.randomUUID());
        c.setCreatedAt(at);
        return c;
    }

    @Test
    void theTenthComplaintInAnHourIsAccepted() {
        when(complaintRepo.countByUserIdAndCreatedAtAfter(CITIZEN.id(), NOW.minus(WINDOW))).thenReturn(9L);
        var res = service.fileComplaint(request("Pothole", "Deep pothole", null), CITIZEN);
        assertThat(res.status()).isEqualTo("FILED");
        ArgumentCaptor<Complaint> saved = ArgumentCaptor.forClass(Complaint.class);
        verify(complaintRepo).save(saved.capture());
        assertThat(saved.getValue().getCreatedAt()).isEqualTo(NOW);   // same clock as the window
    }

    @Test
    void theEleventhIsRefusedWith429AndARetryAfterAndNothingIsStoredOrBroadcast() {
        when(complaintRepo.countByUserIdAndCreatedAtAfter(CITIZEN.id(), NOW.minus(WINDOW))).thenReturn(10L);
        // The oldest complaint in the window leaves it in 30 s.
        when(complaintRepo.findFirstByUserIdAndCreatedAtAfterOrderByCreatedAtAsc(CITIZEN.id(), NOW.minus(WINDOW)))
                .thenReturn(Optional.of(filedAt(NOW.minus(WINDOW).plusSeconds(30))));

        assertThatThrownBy(() -> service.fileComplaint(request("Pothole", "Deep pothole", null), CITIZEN))
                .isInstanceOfSatisfying(TooManyRequestsException.class, e -> {
                    assertThat(e.getStatus()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
                    assertThat(e.retryAfter()).isEqualTo(Duration.ofSeconds(30));
                });
        verify(complaintRepo, never()).save(any());
        verify(observationService, never()).ingest(any(), anyString());
        verify(eventPublisher, never()).publishEvent(any());
    }

    @Test
    void retryAfterIsRoundedUpAndNeverZero() {
        when(complaintRepo.countByUserIdAndCreatedAtAfter(CITIZEN.id(), NOW.minus(WINDOW))).thenReturn(12L);
        when(complaintRepo.findFirstByUserIdAndCreatedAtAfterOrderByCreatedAtAsc(CITIZEN.id(), NOW.minus(WINDOW)))
                .thenReturn(Optional.of(filedAt(NOW.minus(WINDOW).plusMillis(1))));
        assertThatThrownBy(() -> service.fileComplaint(request("Pothole", "Deep pothole", null), CITIZEN))
                .isInstanceOfSatisfying(TooManyRequestsException.class,
                        e -> assertThat(e.retryAfter()).isEqualTo(Duration.ofSeconds(1)));
    }

    @Test
    void theWindowSlidesWithTheClock() {
        // Same history, one hour later: the window starts at the new "now - 1h", so the old filings no longer count.
        Instant later = NOW.plus(WINDOW);
        CivicService laterService = new CivicService(complaintRepo, mock(CityEventRepository.class), observationService,
                eventPublisher, users, audit, new ComplaintFilingLimit(10, WINDOW), Clock.fixed(later, ZoneOffset.UTC));
        when(complaintRepo.countByUserIdAndCreatedAtAfter(CITIZEN.id(), NOW.minus(WINDOW))).thenReturn(10L);
        when(complaintRepo.countByUserIdAndCreatedAtAfter(CITIZEN.id(), later.minus(WINDOW))).thenReturn(0L);
        assertThat(laterService.fileComplaint(request("Pothole", "Deep pothole", null), CITIZEN).status()).isEqualTo("FILED");
    }

    @Test
    void theLimitIsCountedPerUserUnderThatUsersLock() {
        AuthUser other = new AuthUser(UUID.randomUUID(), "other@example.test", Role.CITIZEN, true);
        when(complaintRepo.countByUserIdAndCreatedAtAfter(CITIZEN.id(), NOW.minus(WINDOW))).thenReturn(10L);
        when(complaintRepo.findFirstByUserIdAndCreatedAtAfterOrderByCreatedAtAsc(any(), any()))
                .thenReturn(Optional.of(filedAt(NOW.minusSeconds(60))));
        when(complaintRepo.countByUserIdAndCreatedAtAfter(other.id(), NOW.minus(WINDOW))).thenReturn(0L);

        assertThat(service.fileComplaint(request("Pothole", "Deep pothole", null), other).status()).isEqualTo("FILED");
        assertThatThrownBy(() -> service.fileComplaint(request("Pothole", "Deep pothole", null), CITIZEN))
                .isInstanceOf(TooManyRequestsException.class);

        var order = inOrder(users, complaintRepo);
        order.verify(users).lockById(other.id());
        order.verify(complaintRepo).countByUserIdAndCreatedAtAfter(other.id(), NOW.minus(WINDOW));
        order.verify(users).lockById(CITIZEN.id());
        order.verify(complaintRepo).countByUserIdAndCreatedAtAfter(CITIZEN.id(), NOW.minus(WINDOW));
    }

    @Test
    void signInAndVerificationAreCheckedBeforeTheLimit() {
        var req = request("Pothole", "Deep pothole", null);
        AuthUser unverified = new AuthUser(UUID.randomUUID(), "new@example.test", Role.CITIZEN, false);
        assertThatThrownBy(() -> service.fileComplaint(req, unverified)).isInstanceOf(ApiException.class)
                .isNotInstanceOf(TooManyRequestsException.class);
        verify(users, never()).lockById(any());
        verify(complaintRepo, never()).countByUserIdAndCreatedAtAfter(any(), any());
    }

    @Test
    void filingLimitSettingsMustBePositive() {
        assertThatThrownBy(() -> new ComplaintFilingLimit(0, WINDOW)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ComplaintFilingLimit(10, Duration.ZERO)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ComplaintFilingLimit(10, null)).isInstanceOf(IllegalArgumentException.class);
    }

    // ------------------------------------------------------------------ who sees which complaints

    private static final AuthUser CREW = new AuthUser(UUID.randomUUID(), "crew-a@example.test", Role.CREW, true);

    private Complaint complaint(String status, String worker) {
        Complaint c = filedAt(NOW);
        c.setTrackingId("CS-" + c.getId().toString().substring(0, 8).toUpperCase() + "00");
        c.setUserId(CITIZEN.id());
        c.setStatus(status);
        c.setAssignedWorker(worker);
        c.setTitle("t");
        c.setDescription("d");
        c.setCategory("CIVIC");
        c.setDepartment("PWD_ROADS");
        c.setPriority("HIGH");
        return c;
    }

    @Test
    void crewListingUsesTheCrewScopedQueryAndAdminsTheFullOne() {
        when(complaintRepo.searchForCrew("crew-a@example.test", "FILED", "PWD_ROADS")).thenReturn(List.of(complaint("FILED", null)));
        when(complaintRepo.search(null, null)).thenReturn(List.of(complaint("ASSIGNED", "crew-b@example.test")));

        assertThat(service.listComplaints("filed", "pwd_roads", CREW)).hasSize(1);
        assertThat(service.listComplaints(null, null, ADMIN)).hasSize(1);
        verify(complaintRepo, never()).search(eq("FILED"), any());
        assertThatThrownBy(() -> service.listComplaints("DONE", null, ADMIN))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(() -> service.listComplaints(null, null, CITIZEN))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test
    void crewTrackingAnotherCrewsComplaintGetsTheSame404AsAnUnknownId() {
        Complaint theirs = complaint("ASSIGNED", "crew-b@example.test");
        when(complaintRepo.findByTrackingId(theirs.getTrackingId())).thenReturn(Optional.of(theirs));
        when(complaintRepo.findByTrackingId("CS-UNKNOWN0000")).thenReturn(Optional.empty());

        ApiException hidden = catchApi(() -> service.getComplaint(theirs.getTrackingId(), CREW));
        ApiException unknown = catchApi(() -> service.getComplaint("CS-UNKNOWN0000", CREW));
        assertThat(hidden.getStatus()).isEqualTo(HttpStatus.NOT_FOUND).isEqualTo(unknown.getStatus());
        assertThat(hidden.getMessage().replace(theirs.getTrackingId(), "X"))
                .isEqualTo(unknown.getMessage().replace("CS-UNKNOWN0000", "X"));
        assertThat(service.getComplaint(theirs.getTrackingId(), ADMIN).trackingId()).isEqualTo(theirs.getTrackingId());
    }

    @Test
    void crewChangingAnotherCrewsComplaintGetsA404AndNothingChanges() {
        Complaint theirs = complaint("ASSIGNED", "crew-b@example.test");
        UUID unknownId = UUID.randomUUID();
        when(complaintRepo.findByIdForUpdate(theirs.getId())).thenReturn(Optional.of(theirs));
        when(complaintRepo.findByIdForUpdate(unknownId)).thenReturn(Optional.empty());
        var req = new CivicDtos.ComplaintStatusUpdateRequest("IN_PROGRESS", null, null);

        ApiException hidden = catchApi(() -> service.updateStatus(theirs.getId(), req, CREW));
        ApiException unknown = catchApi(() -> service.updateStatus(unknownId, req, CREW));
        assertThat(hidden.getStatus()).isEqualTo(HttpStatus.NOT_FOUND).isEqualTo(unknown.getStatus());
        assertThat(hidden.getMessage().replace(theirs.getId().toString(), "X"))
                .isEqualTo(unknown.getMessage().replace(unknownId.toString(), "X"));
        assertThat(theirs.getStatus()).isEqualTo("ASSIGNED");
        verify(complaintRepo, never()).save(any());
        verify(audit, never()).record(any(), any(), any(), any(), any(), any());
    }

    private static ApiException catchApi(Runnable r) {
        try {
            r.run();
        } catch (ApiException e) {
            return e;
        }
        throw new AssertionError("expected an ApiException");
    }

    @Test
    void trackingIdsAreRandomAndUnique() {
        Set<String> ids = new HashSet<>();
        for (int i = 0; i < 500; i++) {
            ids.add(service.newTrackingId());
        }
        assertThat(ids).hasSize(500).allMatch(id -> id.matches("CS-[0-9A-HJKMNP-TV-Z]{10}"));
    }

    @Test
    void trackingIdRetriesOnCollision() {
        when(complaintRepo.existsByTrackingId(anyString())).thenReturn(true, true, false);
        assertThat(service.newTrackingId()).startsWith("CS-");
    }

    @Test
    void observationAndLiveEventCarryNoTrackingIdTitleNameOrLocationText() {
        var res = service.fileComplaint(request("Leak outside house no. 12", "Pipe burst near my gate", "AUTO"), CITIZEN);

        ArgumentCaptor<ObservationRequest> obs = ArgumentCaptor.forClass(ObservationRequest.class);
        verify(observationService).ingest(obs.capture(), eq("civic-module"));
        assertThat(obs.getValue().payload()).containsOnlyKeys("complaintId", "department", "category")
                .containsEntry("complaintId", res.id().toString());

        ArgumentCaptor<CityEventMessage> event = ArgumentCaptor.forClass(CityEventMessage.class);
        verify(eventPublisher).publishEvent(event.capture());
        assertThat(event.getValue().data()).isInstanceOfSatisfying(CivicDtos.ComplaintLiveEvent.class, e -> {
            assertThat(e.title()).isEqualTo("New JAL SANSTHAN complaint").doesNotContain("house");
            assertThat(e.status()).isEqualTo("FILED");
        });
    }

    @Test
    void adminResolvesAndTheChangeIsAuditedAndLockedRow() {
        UUID id = UUID.randomUUID();
        Complaint existing = new Complaint();
        existing.setId(id);
        existing.setTrackingId("CS-ABCDEFGHJK");
        existing.setStatus("IN_PROGRESS");
        existing.setAssignedWorker("crew@example.test");
        existing.setTitle("Water leakage");
        existing.setDescription("Pipe burst");
        existing.setCategory("CIVIC");
        existing.setDepartment("JAL_SANSTHAN");
        existing.setPriority("HIGH");
        when(complaintRepo.findByIdForUpdate(id)).thenReturn(Optional.of(existing));

        var res = service.updateStatus(id, new CivicDtos.ComplaintStatusUpdateRequest(
                "resolved", null, "Main valve replaced and leak sealed successfully."), ADMIN);

        assertThat(res.status()).isEqualTo("RESOLVED");
        assertThat(res.assignedWorker()).isEqualTo("crew@example.test");
        assertThat(res.resolvedAt()).isNotNull();
        verify(complaintRepo, never()).findById(any());
        verify(audit).record(eq("admin@example.test"), eq("COMPLAINT_STATUS_CHANGED"), eq("complaint"), eq(id.toString()),
                eq("SUCCESS"), eq(Map.of("from", "IN_PROGRESS", "to", "RESOLVED", "role", "ADMIN",
                        "assignedWorker", "crew@example.test")));
    }

    @Test
    void citizensCannotChangeStatusAndAreRefusedBeforeAnyLookup() {
        UUID id = UUID.randomUUID();
        assertThatThrownBy(() -> service.updateStatus(id, new CivicDtos.ComplaintStatusUpdateRequest("RESOLVED", null, null), CITIZEN))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        verify(complaintRepo, never()).findByIdForUpdate(any());
    }

    @Test
    void unknownStatusIs400NotA500() {
        assertThatThrownBy(() -> service.updateStatus(UUID.randomUUID(),
                new CivicDtos.ComplaintStatusUpdateRequest("DONE", null, null), ADMIN))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.BAD_REQUEST));
    }
}

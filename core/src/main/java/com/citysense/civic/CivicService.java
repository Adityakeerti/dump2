package com.citysense.civic;

import com.citysense.common.error.ApiException;
import com.citysense.common.error.TooManyRequestsException;
import com.citysense.platform.audit.AuditService;
import com.citysense.platform.auth.AuthUser;
import com.citysense.platform.auth.Role;
import com.citysense.platform.auth.UserRepository;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationService;
import com.citysense.platform.realtime.CityEventMessage;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CivicService {

    private static final Logger log = LoggerFactory.getLogger(CivicService.class);

    /** Crockford base32 without I, L, O, U: unambiguous when read out or typed. */
    private static final char[] TRACKING_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ".toCharArray();
    private static final int TRACKING_LENGTH = 10;   // 50 random bits
    private static final SecureRandom RANDOM = new SecureRandom();

    private final ComplaintRepository complaintRepo;
    private final CityEventRepository cityEventRepo;
    private final ObservationService observationService;
    private final ApplicationEventPublisher eventPublisher;
    private final UserRepository users;
    private final AuditService audit;
    private final ComplaintFilingLimit filingLimit;
    private final Clock clock;

    @Autowired
    public CivicService(
            ComplaintRepository complaintRepo,
            CityEventRepository cityEventRepo,
            ObservationService observationService,
            ApplicationEventPublisher eventPublisher,
            UserRepository users,
            AuditService audit,
            ComplaintFilingLimit filingLimit) {
        this(complaintRepo, cityEventRepo, observationService, eventPublisher, users, audit, filingLimit, Clock.systemUTC());
    }

    /** With an explicit clock, so tests can move the filing-limit window. */
    CivicService(
            ComplaintRepository complaintRepo,
            CityEventRepository cityEventRepo,
            ObservationService observationService,
            ApplicationEventPublisher eventPublisher,
            UserRepository users,
            AuditService audit,
            ComplaintFilingLimit filingLimit,
            Clock clock) {
        this.complaintRepo = complaintRepo;
        this.cityEventRepo = cityEventRepo;
        this.observationService = observationService;
        this.eventPublisher = eventPublisher;
        this.users = users;
        this.audit = audit;
        this.filingLimit = filingLimit;
        this.clock = clock;
    }

    /**
     * Sliding-window limit, counted in the database under a lock on the user's row: concurrent filings by one
     * user are serialised, so they cannot all read "9" and all be admitted. Other users are not blocked.
     */
    private void enforceFilingLimit(UUID userId, Instant now) {
        users.lockById(userId);
        Instant since = now.minus(filingLimit.window());
        long recent = complaintRepo.countByUserIdAndCreatedAtAfter(userId, since);
        if (recent >= filingLimit.maxPerWindow()) {
            // A slot frees up when the oldest filing in the window leaves it.
            Duration wait = complaintRepo.findFirstByUserIdAndCreatedAtAfterOrderByCreatedAtAsc(userId, since)
                    .map(oldest -> Duration.between(now, oldest.getCreatedAt().plus(filingLimit.window())))
                    .orElse(filingLimit.window());
            long seconds = Math.max(1, (wait.toMillis() + 999) / 1000);   // round up, never 0
            log.info("Complaint filing limit reached for user {}", userId);
            throw new TooManyRequestsException("Complaint limit reached (" + filingLimit.maxPerWindow() + " per "
                    + humanise(filingLimit.window()) + "). Try again in " + seconds + " seconds.", Duration.ofSeconds(seconds));
        }
    }

    private static String humanise(Duration d) {
        if (d.toHours() > 0 && d.toMinutesPart() == 0 && d.toSecondsPart() == 0) {
            return d.toHours() == 1 ? "hour" : d.toHours() + " hours";
        }
        return d.toMinutes() + " minutes";
    }

    /** Random, non-sequential tracking ID (was derived from the clock: guessable and colliding every 15 min). */
    String newTrackingId() {
        for (int attempt = 0; attempt < 5; attempt++) {
            char[] out = new char[TRACKING_LENGTH];
            for (int i = 0; i < out.length; i++) {
                out[i] = TRACKING_ALPHABET[RANDOM.nextInt(TRACKING_ALPHABET.length)];
            }
            String id = "CS-" + new String(out);
            if (!complaintRepo.existsByTrackingId(id)) {
                return id;
            }
        }
        throw new IllegalStateException("Could not allocate a unique tracking ID");
    }

    /**
     * The caller must be signed in (enforced by SecurityConfig), have a verified email, and be within the
     * per-user filing limit (default 10 per sliding hour; 429 with Retry-After otherwise).
     */
    @Transactional
    public CivicDtos.ComplaintResponse fileComplaint(CivicDtos.ComplaintCreateRequest req, AuthUser user) {
        if (user == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Sign in required");
        }
        if (!user.emailVerified()) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Verify your email to continue");
        }
        Instant now = clock.instant();
        enforceFilingLimit(user.id(), now);

        Complaint complaint = new Complaint();
        complaint.setCreatedAt(now);   // the same clock as the window, so the limit counts exactly what it admits
        complaint.setTrackingId(newTrackingId());
        complaint.setUserId(user.id());
        complaint.setCitizenName(req.citizenName() != null ? req.citizenName() : "Anonymous Citizen");
        complaint.setTitle(req.title());
        complaint.setDescription(req.description());
        complaint.setCategory(req.category() != null ? req.category() : "CIVIC");
        complaint.setPriority(req.priority() != null ? req.priority().toUpperCase(Locale.ROOT) : "MEDIUM");
        complaint.setStatus("FILED");
        complaint.setLatitude(req.latitude());
        complaint.setLongitude(req.longitude());
        complaint.setPhotoUrl(req.photoUrl());
        complaint.setEscalationLevel(0);

        // Auto-classify department if not provided
        String dept = req.department();
        if (dept == null || dept.isBlank() || "AUTO".equalsIgnoreCase(dept)) {
            dept = autoClassifyDepartment(req.title(), req.description());
        }
        complaint.setDepartment(dept);

        Complaint saved = complaintRepo.save(complaint);

        // Ingest into ObservationService so Member A's correlation engine clusters it
        try {
            ObservationRequest obsReq = new ObservationRequest(
                    com.citysense.platform.observation.ObservationType.COMPLAINT,
                    req.latitude(),
                    req.longitude(),
                    Instant.now(),
                    "civic-module",
                    0.95,
                    com.citysense.platform.observation.ObservationStatus.VERIFIED,
                    // Observations are readable by any signed-in user: link by internal id only, never the
                    // tracking ID (which unlocks the complaint) or the citizen's free-text title.
                    Map.of(
                            "complaintId", saved.getId().toString(),
                            "department", saved.getDepartment(),
                            "category", saved.getCategory()
                    )
            );
            observationService.ingest(obsReq, "civic-module");
        } catch (Exception e) {
            log.warn("Could not ingest observation for complaint {}: {}", saved.getId(), e.getMessage());
        }

        // Live channel is unauthenticated until Stage C: redacted summary only.
        eventPublisher.publishEvent(CityEventMessage.of("COMPLAINT_FILED", saved.getId(),
                CivicDtos.ComplaintLiveEvent.of(saved, true)));

        return CivicDtos.ComplaintResponse.from(saved);
    }

    private static boolean visibleTo(AuthUser user, Complaint c) {
        return ComplaintAccessPolicy.canView(user, c.getUserId(), c.getAssignedWorker(), ComplaintStatus.parse(c.getStatus()));
    }

    /**
     * Owner, ADMIN, and CREW for their own assignments or the unassigned queue ({@link ComplaintAccessPolicy#canView}).
     * Anyone else gets exactly the same 404 as for an unknown ID, so a tracking ID never confirms that a complaint
     * the caller may not see exists.
     */
    @Transactional(readOnly = true)
    public CivicDtos.ComplaintResponse getComplaint(String trackingId, AuthUser user) {
        return complaintRepo.findByTrackingId(trackingId)
                .filter(c -> visibleTo(user, c))
                .map(CivicDtos.ComplaintResponse::from)
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Complaint not found: " + trackingId));
    }

    @Transactional(readOnly = true)
    public List<CivicDtos.ComplaintResponse> listMine(UUID userId) {
        return complaintRepo.findByUserIdOrderByCreatedAtDesc(userId).stream()
                .map(CivicDtos.ComplaintResponse::from).toList();
    }

    /**
     * ADMIN: every complaint. CREW: their own assignments plus the unassigned queue, filtered in the query itself
     * (never complaints assigned to someone else). Others: 403. Filters narrow the result and can be combined;
     * an unknown status is a 400.
     */
    @Transactional(readOnly = true)
    public List<CivicDtos.ComplaintResponse> listComplaints(String status, String department, AuthUser user) {
        if (!ComplaintAccessPolicy.isStaff(user)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Only crew or admins can list complaints");
        }
        String s = status == null || status.isBlank() ? null : ComplaintStatus.parse(status).name();
        String d = department == null || department.isBlank() ? null : department.trim().toUpperCase(Locale.ROOT);
        List<Complaint> list = user.role() == Role.ADMIN
                ? complaintRepo.search(s, d)
                : complaintRepo.searchForCrew(user.email(), s, d);
        return list.stream().map(CivicDtos.ComplaintResponse::from).toList();
    }

    /**
     * Role-, assignment- and transition-checked status change (rules in {@link ComplaintAccessPolicy}).
     * Citizens are refused before the lookup, so they learn nothing about complaint IDs. The row is locked
     * for the decision, and every successful change is written to the audit log.
     */
    @Transactional
    public CivicDtos.ComplaintResponse updateStatus(UUID id, CivicDtos.ComplaintStatusUpdateRequest req, AuthUser user) {
        if (!ComplaintAccessPolicy.isStaff(user)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Only crew or admins can change complaint status");
        }
        ComplaintStatus to = ComplaintStatus.parse(req.status());
        // A complaint the caller may not see (e.g. another crew member's) is indistinguishable from an unknown id.
        Complaint c = complaintRepo.findByIdForUpdate(id)
                .filter(found -> visibleTo(user, found))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Complaint not found with ID: " + id));
        ComplaintStatus from = ComplaintStatus.parse(c.getStatus());
        String previousWorker = c.getAssignedWorker();

        ComplaintAccessPolicy.Change change = ComplaintAccessPolicy.decide(
                user, from, previousWorker, to, req.assignedWorker(), req.resolutionNotes());
        if (change.to() == ComplaintStatus.ASSIGNED && user.role() == Role.ADMIN) {
            // Store the account's own email so later crew ownership checks compare like with like.
            change = new ComplaintAccessPolicy.Change(change.to(), requireCrewMember(change.assignedWorker()));
        }

        Instant now = Instant.now();
        c.setStatus(change.to().name());
        c.setAssignedWorker(change.assignedWorker());
        c.setUpdatedAt(now);
        if (req.resolutionNotes() != null && !req.resolutionNotes().isBlank()) {
            c.setResolutionNotes(req.resolutionNotes());
        }
        if (change.to() == ComplaintStatus.RESOLVED) {
            c.setResolvedAt(now);
        } else if (change.to() == ComplaintStatus.FILED) {
            c.setResolvedAt(null);   // reopened
        }
        Complaint saved = complaintRepo.save(c);

        Map<String, Object> evidence = new LinkedHashMap<>();
        evidence.put("from", from.name());
        evidence.put("to", change.to().name());
        evidence.put("role", user.role().name());
        if (change.assignedWorker() != null) {
            evidence.put("assignedWorker", change.assignedWorker());
        }
        if (previousWorker != null && !previousWorker.equalsIgnoreCase(String.valueOf(change.assignedWorker()))) {
            evidence.put("previousWorker", previousWorker);
        }
        audit.record(user.email(), "COMPLAINT_STATUS_CHANGED", "complaint", saved.getId().toString(), "SUCCESS", evidence);

        eventPublisher.publishEvent(CityEventMessage.of(
                change.to() == ComplaintStatus.RESOLVED ? "COMPLAINT_RESOLVED" : "COMPLAINT_STATUS_UPDATED",
                saved.getId(),
                CivicDtos.ComplaintLiveEvent.of(saved, false)
        ));

        return CivicDtos.ComplaintResponse.from(saved);
    }

    /** ADMIN assignments must name an existing CREW account (by email), not free text. */
    private String requireCrewMember(String email) {
        return users.findByEmailIgnoreCase(email)
                .filter(u -> u.getRole() == Role.CREW)
                .map(u -> u.getEmail())
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST,
                        "assignedWorker must be the email of a crew account"));
    }

    @Transactional(readOnly = true)
    public List<CivicDtos.CityEventResponse> listCityEvents() {
        // Upcoming and ongoing events first (soonest at the top), then past ones newest-first.
        java.time.Instant cutoff = java.time.Instant.now().minus(java.time.Duration.ofHours(12));
        List<CityEvent> all = cityEventRepo.findAllByOrderByStartsAtDesc();
        java.util.function.Predicate<CityEvent> current =
                e -> !e.getStartsAt().isBefore(cutoff) || (e.getEndsAt() != null && e.getEndsAt().isAfter(cutoff));
        return java.util.stream.Stream.concat(
                        all.stream().filter(current).sorted(java.util.Comparator.comparing(CityEvent::getStartsAt)),
                        all.stream().filter(current.negate()))
                .map(CivicDtos.CityEventResponse::from)
                .toList();
    }

    @Transactional
    public CivicDtos.CityEventResponse createCityEvent(CivicDtos.CityEventCreateRequest req) {
        CityEvent event = new CityEvent();
        event.setTitle(req.title());
        event.setDescription(req.description());
        event.setCategory(req.category() != null ? req.category() : "COMMUNITY");
        event.setSeverity(req.severity() != null ? req.severity().toUpperCase(Locale.ROOT) : "INFO");
        event.setLatitude(req.latitude());
        event.setLongitude(req.longitude());
        event.setStartsAt(req.startsAt() != null ? req.startsAt() : Instant.now());
        event.setEndsAt(req.endsAt());

        CityEvent saved = cityEventRepo.save(event);

        eventPublisher.publishEvent(CityEventMessage.of("CITY_EVENT_CREATED", saved.getId(), CivicDtos.CityEventResponse.from(saved)));

        return CivicDtos.CityEventResponse.from(saved);
    }

    private String autoClassifyDepartment(String title, String desc) {
        String combined = (title + " " + desc).toLowerCase(Locale.ROOT);
        if (combined.contains("pothole") || combined.contains("road") || combined.contains("tar") || combined.contains("footpath") || combined.contains("divider")) {
            return "PWD_ROADS";
        }
        if (combined.contains("garbage") || combined.contains("trash") || combined.contains("waste") || combined.contains("drain") || combined.contains("clean") || combined.contains("sweep")) {
            return "SANITATION";
        }
        if (combined.contains("water") || combined.contains("pipe") || combined.contains("leak") || combined.contains("supply") || combined.contains("tap") || combined.contains("sewage")) {
            return "JAL_SANSTHAN";
        }
        if (combined.contains("light") || combined.contains("pole") || combined.contains("wire") || combined.contains("power") || combined.contains("meter") || combined.contains("blackout")) {
            return "ELECTRICITY";
        }
        if (combined.contains("traffic") || combined.contains("signal") || combined.contains("jam") || combined.contains("parking") || combined.contains("accident")) {
            return "TRAFFIC_POLICE";
        }
        return "MUNICIPAL";
    }
}

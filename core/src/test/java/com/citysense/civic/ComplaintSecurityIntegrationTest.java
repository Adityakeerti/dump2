package com.citysense.civic;

import static org.assertj.core.api.Assertions.assertThat;

import com.citysense.mesh.service.MeshNodeService;
import com.citysense.platform.auth.Role;
import com.citysense.platform.auth.User;
import com.citysense.platform.auth.UserRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Type;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.converter.SimpleMessageConverter;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

/**
 * Complaint access control end to end: real HTTP, real security filter chain and JWTs, real PostGIS in a
 * THROWAWAY container with random credentials (never the developer database).
 *
 * <p>The mesh node is mocked so the test never opens the mesh UDP port (8988) on this machine.
 *
 * <p>Run: {@code mvn test -Dsurefire.excludedGroups= -Dgroups=integration} (needs Docker and the
 * {@code citysense-db:latest} image).
 */
@Tag("integration")
@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ComplaintSecurityIntegrationTest {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String PASSWORD = "it-" + hex(12);

    @Container
    static final PostgreSQLContainer<?> DB = new PostgreSQLContainer<>(
            DockerImageName.parse("citysense-db:latest").asCompatibleSubstituteFor("postgres"))
            .withDatabaseName("citysense").withUsername("citysense").withPassword(hex(16));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry r) {
        r.add("spring.datasource.url", DB::getJdbcUrl);
        r.add("spring.datasource.username", DB::getUsername);
        r.add("spring.datasource.password", DB::getPassword);
        r.add("citysense.security.jwt-secret", () -> hex(32));
        r.add("citysense.security.internal-api-key", () -> hex(24));
        r.add("citysense.seed.enabled", () -> "false");
        r.add("citysense.avatars.seed-enabled", () -> "false");
    }

    @MockBean
    MeshNodeService meshNodeService;

    @LocalServerPort
    int port;

    @Autowired
    UserRepository users;
    @Autowired
    PasswordEncoder encoder;
    @Autowired
    JdbcTemplate jdbc;
    @Autowired
    ComplaintRepository complaints;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();
    private static final Map<String, String> TOKENS = new LinkedHashMap<>();

    // Accounts (created once): two citizens, an unverified citizen, two crews, an admin.
    private static final String CIT_A = "cit-a@it.test", CIT_B = "cit-b@it.test", UNVERIFIED = "new@it.test",
            CREW_A = "crew-a@it.test", CREW_B = "crew-b@it.test", ADMIN = "admin@it.test";

    @BeforeEach
    void accounts() throws Exception {
        if (!TOKENS.isEmpty()) {
            return;
        }
        for (var a : List.of(List.of(CIT_A, Role.CITIZEN, true), List.of(CIT_B, Role.CITIZEN, true),
                List.of(UNVERIFIED, Role.CITIZEN, false), List.of(CREW_A, Role.CREW, true),
                List.of(CREW_B, Role.CREW, true), List.of(ADMIN, Role.ADMIN, true))) {
            User u = new User((String) a.get(0), encoder.encode(PASSWORD), "IT " + a.get(1), (Role) a.get(1), "en");
            if ((boolean) a.get(2)) {
                u.markEmailVerified();
            }
            users.save(u);
        }
        for (String email : List.of(CIT_A, CIT_B, UNVERIFIED, CREW_A, CREW_B, ADMIN)) {
            HttpResponse<String> r = send("POST", "/api/auth/login", Map.of("email", email, "password", PASSWORD), null);
            assertThat(r.statusCode()).as(r.body()).isEqualTo(200);
            TOKENS.put(email, json.readTree(r.body()).get("accessToken").asText());
        }
    }

    // ---------------------------------------------------------------- 1-3: anonymous

    @Test
    void anonymousCannotListReadOrModifyComplaints() throws Exception {
        JsonNode c = file(CIT_A, "Streetlight out", "Dark stretch");
        for (HttpResponse<String> r : List.of(
                send("GET", "/api/complaints", null, null),
                send("GET", "/api/complaints?status=FILED", null, null),
                send("GET", "/api/complaints/" + c.get("trackingId").asText(), null, null),
                send("GET", "/api/complaints/mine", null, null),
                send("PATCH", "/api/complaints/" + c.get("id").asText() + "/status", Map.of("status", "RESOLVED"), null),
                send("POST", "/api/complaints", complaintBody("x", "y"), null))) {
            assertThat(r.statusCode()).as(r.uri().toString()).isEqualTo(401);
            assertThat(r.body()).as("401 has no body").isEmpty();
        }
        assertThat(status(c)).isEqualTo("FILED");
        // A forged / expired token is anonymous too.
        assertThat(send("GET", "/api/complaints", null, "not-a-jwt").statusCode()).isEqualTo(401);
    }

    // ---------------------------------------------------------------- 4-5: ownership and tracking privacy

    @Test
    void citizensSeeOnlyTheirOwnComplaintsAndOthersLookIdenticalToUnknownIds() throws Exception {
        JsonNode mine = file(CIT_A, "Overflowing drain", "Near my gate");
        String tid = mine.get("trackingId").asText();

        HttpResponse<String> owner = send("GET", "/api/complaints/" + tid, null, token(CIT_A));
        assertThat(owner.statusCode()).isEqualTo(200);
        assertThat(json.readTree(owner.body()).get("description").asText()).isEqualTo("Near my gate");

        HttpResponse<String> other = send("GET", "/api/complaints/" + tid, null, token(CIT_B));
        String unknownId = "CS-ZZZZZZZZZZ";
        HttpResponse<String> unknown = send("GET", "/api/complaints/" + unknownId, null, token(CIT_B));
        assertThat(other.statusCode()).isEqualTo(404);
        assertThat(unknown.statusCode()).isEqualTo(404);
        assertThat(other.headers().firstValue("Content-Type")).isEqualTo(unknown.headers().firstValue("Content-Type"));
        JsonNode o = json.readTree(other.body()), u = json.readTree(unknown.body());
        assertThat(o.get("detail").asText().replace(tid, "<id>")).isEqualTo(u.get("detail").asText().replace(unknownId, "<id>"));
        assertThat(o.get("title").asText()).isEqualTo(u.get("title").asText());
        assertThat(other.body()).doesNotContain("Near my gate").doesNotContain("Overflowing");

        assertThat(ids(send("GET", "/api/complaints/mine", null, token(CIT_A)))).contains(mine.get("id").asText());
        assertThat(ids(send("GET", "/api/complaints/mine", null, token(CIT_B)))).doesNotContain(mine.get("id").asText());
        assertThat(send("GET", "/api/complaints", null, token(CIT_A)).statusCode()).isEqualTo(403);
    }

    @Test
    void legacyUnownedComplaintsAreVisibleToStaffOnly() throws Exception {
        String tid = "CS-LEGACY" + hex(2).toUpperCase();
        jdbc.update("INSERT INTO complaints (tracking_id, citizen_name, title, description, latitude, longitude) "
                + "VALUES (?, 'Old Anonymous', 'Old complaint', 'Filed before login was required', 30.3, 78.0)", tid);
        assertThat(send("GET", "/api/complaints/" + tid, null, token(CIT_A)).statusCode()).isEqualTo(404);
        assertThat(send("GET", "/api/complaints/" + tid, null, token(CREW_A)).statusCode()).isEqualTo(200);   // in the queue
        assertThat(send("GET", "/api/complaints/" + tid, null, token(ADMIN)).statusCode()).isEqualTo(200);

        // Legacy free-text worker: not a crew account, so no crew member sees it; admins still do.
        String assigned = "CS-LEGACY" + hex(2).toUpperCase();
        jdbc.update("INSERT INTO complaints (tracking_id, citizen_name, title, description, latitude, longitude, status, "
                + "assigned_worker) VALUES (?, 'Old Anonymous', 'Old', 'Old', 30.3, 78.0, 'ASSIGNED', 'Ramesh (ward 4)')", assigned);
        assertThat(send("GET", "/api/complaints/" + assigned, null, token(CREW_A)).statusCode()).isEqualTo(404);
        assertThat(send("GET", "/api/complaints/" + assigned, null, token(ADMIN)).statusCode()).isEqualTo(200);
    }

    // ---------------------------------------------------------------- crew see their own work and the queue only

    @Test
    void crewSeeTheirOwnAssignmentsAndTheUnassignedQueueButNotOtherCrewsWork() throws Exception {
        String queued = file(CIT_B, "Fallen branch", "Blocking footpath").get("id").asText();
        String forA = file(CIT_B, "Manhole open", "No cover").get("id").asText();
        JsonNode forBJson = file(CIT_B, "Broken bench", "Park bench broken");
        String forB = forBJson.get("id").asText();
        String rejected = file(CIT_B, "Duplicate pothole", "Same as before").get("id").asText();
        body(patch(forA, CREW_A, "ASSIGNED", null, null), 200);
        body(patch(forB, ADMIN, "ASSIGNED", CREW_B, null), 200);
        body(patch(rejected, ADMIN, "REJECTED", null, "Duplicate"), 200);

        List<String> crewA = ids(send("GET", "/api/complaints", null, token(CREW_A)));
        assertThat(crewA).contains(queued, forA).doesNotContain(forB, rejected);
        List<String> crewB = ids(send("GET", "/api/complaints", null, token(CREW_B)));
        assertThat(crewB).contains(queued, forB).doesNotContain(forA, rejected);
        assertThat(ids(send("GET", "/api/complaints", null, token(ADMIN)))).contains(queued, forA, forB, rejected);

        // Filters narrow the crew's own scope; they never widen it.
        assertThat(ids(send("GET", "/api/complaints?status=ASSIGNED", null, token(CREW_A)))).contains(forA).doesNotContain(forB);
        assertThat(ids(send("GET", "/api/complaints?status=REJECTED", null, token(CREW_A)))).doesNotContain(rejected);
        assertThat(ids(send("GET", "/api/complaints?status=ASSIGNED&department=CIVIC", null, token(ADMIN))))
                .allSatisfy(id -> assertThat(row(id).get("status").asText()).isEqualTo("ASSIGNED"));
        assertProblem(send("GET", "/api/complaints?status=DONE", null, token(CREW_A)), 400);

        // Tracking and changing another crew's complaint looks exactly like an unknown one.
        String tidB = forBJson.get("trackingId").asText();
        HttpResponse<String> hidden = send("GET", "/api/complaints/" + tidB, null, token(CREW_A));
        HttpResponse<String> unknown = send("GET", "/api/complaints/CS-ZZZZZZZZZZ", null, token(CREW_A));
        assertProblem(hidden, 404);
        assertThat(json.readTree(hidden.body()).get("detail").asText().replace(tidB, "<id>"))
                .isEqualTo(json.readTree(unknown.body()).get("detail").asText().replace("CS-ZZZZZZZZZZ", "<id>"));
        HttpResponse<String> hiddenPatch = patch(forB, CREW_A, "IN_PROGRESS", null, null);
        HttpResponse<String> unknownPatch = patch(UUID.randomUUID().toString(), CREW_A, "IN_PROGRESS", null, null);
        assertProblem(hiddenPatch, 404);
        assertProblem(unknownPatch, 404);
        assertThat(hiddenPatch.body()).doesNotContain(CREW_B).doesNotContain("Broken bench");
        assertThat(row(forB).get("status").asText()).isEqualTo("ASSIGNED");
        assertThat(send("GET", "/api/complaints/" + tidB, null, token(CREW_B)).statusCode()).isEqualTo(200);
    }

    // ---------------------------------------------------------------- 6: unauthorised status changes

    @Test
    void unauthorisedStatusChangesAreRefusedAndChangeNothing() throws Exception {
        JsonNode c = file(CIT_A, "Broken divider", "Road divider broken");
        String id = c.get("id").asText();
        // Owner and other citizens: never.
        assertProblem(patch(id, CIT_A, "RESOLVED", null, null), 403);
        assertProblem(patch(id, CIT_B, "IN_PROGRESS", null, null), 403);
        // Crew: not REJECTED / FILED / ESCALATED, not someone else's complaint, not skipping states.
        assertProblem(patch(id, CREW_A, "REJECTED", null, "no"), 403);
        assertProblem(patch(id, CREW_A, "RESOLVED", null, null), 409);
        assertProblem(patch(id, CREW_A, "ASSIGNED", CREW_B, null), 403);
        assertThat(patch(id, CREW_A, "ASSIGNED", null, null).statusCode()).isEqualTo(200);
        // Crew B can no longer see it at all: same 404 as an unknown id.
        assertProblem(patch(id, CREW_B, "IN_PROGRESS", null, null), 404);
        assertProblem(patch(id, CREW_B, "ASSIGNED", null, null), 404);
        assertProblem(patch(id, CREW_A, "IN_PROGRESS", CREW_B, null), 403);
        // Bad input: 400, not 500.
        assertProblem(patch(id, ADMIN, "DONE", null, null), 400);
        assertThat(send("PATCH", "/api/complaints/" + UUID.randomUUID() + "/status", Map.of("status", "ASSIGNED"),
                token(CREW_A)).statusCode()).isEqualTo(404);

        JsonNode row = row(id);
        assertThat(row.get("status").asText()).isEqualTo("ASSIGNED");
        assertThat(row.get("assigned_worker").asText()).isEqualTo(CREW_A);
        assertThat(auditCount(id)).isEqualTo(1);   // only the one successful change
    }

    @Test
    void twoCrewsClaimingTheSameComplaintAtOnceOnlyOneWins() throws Exception {
        String id = file(CIT_B, "Water leak", "Pipe burst").get("id").asText();
        List<CompletableFuture<Integer>> claims = new ArrayList<>();
        for (int i = 0; i < 6; i++) {
            String crew = i % 2 == 0 ? CREW_A : CREW_B;
            claims.add(CompletableFuture.supplyAsync(() -> {
                try {
                    return patch(id, crew, "ASSIGNED", null, null).statusCode();
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            }));
        }
        List<Integer> codes = claims.stream().map(CompletableFuture::join).toList();
        assertThat(codes).filteredOn(s -> s == 200).hasSize(1);
        // Losers: the winner's other attempts are illegal (409); the other crew can no longer see it (404).
        assertThat(codes).filteredOn(s -> s != 200).allMatch(s -> s == 404 || s == 409);
        assertThat(auditCount(id)).isEqualTo(1);
    }

    // ---------------------------------------------------------------- 7: authorised crew workflow

    @Test
    void crewWorksTheirOwnComplaintThroughToResolvedAndEveryStepIsAudited() throws Exception {
        JsonNode c = file(CIT_A, "Garbage not collected", "Three days");
        String id = c.get("id").asText();
        JsonNode assigned = body(patch(id, CREW_A, "ASSIGNED", null, null), 200);
        assertThat(assigned.get("assignedWorker").asText()).isEqualTo(CREW_A);
        body(patch(id, CREW_A, "IN_PROGRESS", null, null), 200);
        JsonNode resolved = body(patch(id, CREW_A, "RESOLVED", null, "Collected and cleaned"), 200);
        assertThat(resolved.get("status").asText()).isEqualTo("RESOLVED");
        assertThat(resolved.get("resolvedAt").isNull()).isFalse();

        // The owner sees the outcome; the audit trail names the crew member for each step.
        JsonNode tracked = body(send("GET", "/api/complaints/" + c.get("trackingId").asText(), null, token(CIT_A)), 200);
        assertThat(tracked.get("status").asText()).isEqualTo("RESOLVED");
        assertThat(tracked.get("resolutionNotes").asText()).isEqualTo("Collected and cleaned");
        List<Map<String, Object>> trail = jdbc.queryForList("SELECT actor, evidence->>'from' AS f, evidence->>'to' AS t "
                + "FROM audit_log WHERE action='COMPLAINT_STATUS_CHANGED' AND entity_id=? ORDER BY id", id);
        assertThat(trail).extracting(m -> m.get("actor") + ":" + m.get("f") + "->" + m.get("t"))
                .containsExactly(CREW_A + ":FILED->ASSIGNED", CREW_A + ":ASSIGNED->IN_PROGRESS", CREW_A + ":IN_PROGRESS->RESOLVED");
        assertThat(ids(send("GET", "/api/complaints", null, token(CREW_A)))).contains(id);   // resolved, still theirs
    }

    // ---------------------------------------------------------------- filing rate limit: 10 per user per hour

    /** A fresh verified citizen, so each rate-limit test starts from an empty window. */
    private String freshCitizen() throws Exception {
        String email = "rl-" + hex(4) + "@it.test";
        User u = new User(email, encoder.encode(PASSWORD), "IT rate limit", Role.CITIZEN, "en");
        u.markEmailVerified();
        users.save(u);
        HttpResponse<String> r = send("POST", "/api/auth/login", Map.of("email", email, "password", PASSWORD), null);
        assertThat(r.statusCode()).as(r.body()).isEqualTo(200);
        TOKENS.put(email, json.readTree(r.body()).get("accessToken").asText());
        return email;
    }

    private int countFiledBy(String email) {
        Integer n = jdbc.queryForObject("SELECT count(*) FROM complaints c JOIN users u ON u.id = c.user_id WHERE u.email = ?",
                Integer.class, email);
        return n == null ? 0 : n;
    }

    @Test
    void tenComplaintsAnHourAreAcceptedAndTheEleventhGets429WithRetryAfter() throws Exception {
        String citizen = freshCitizen();
        for (int i = 1; i <= 10; i++) {
            assertThat(send("POST", "/api/complaints", complaintBody("Issue " + i, "Detail " + i), token(citizen)).statusCode())
                    .as("filing %d of 10", i).isEqualTo(201);
        }
        HttpResponse<String> eleventh = send("POST", "/api/complaints", complaintBody("Issue 11", "Detail"), token(citizen));
        assertProblem(eleventh, 429);
        long retryAfter = Long.parseLong(eleventh.headers().firstValue("Retry-After").orElseThrow());
        assertThat(retryAfter).isBetween(1L, 3600L);
        assertThat(countFiledBy(citizen)).isEqualTo(10);

        // Per user: someone else is unaffected, and reads still work for the limited user.
        assertThat(send("POST", "/api/complaints", complaintBody("Other", "Unaffected"), token(freshCitizen())).statusCode())
                .isEqualTo(201);
        assertThat(ids(send("GET", "/api/complaints/mine", null, token(citizen)))).hasSize(10);
    }

    @Test
    void theWindowSlidesSoAnOldFilingFreesASlotAndOnlyOne() throws Exception {
        String citizen = freshCitizen();
        for (int i = 1; i <= 10; i++) {
            file(citizen, "Issue " + i, "Detail");
        }
        assertProblem(send("POST", "/api/complaints", complaintBody("Blocked", "Detail"), token(citizen)), 429);
        // Age the oldest filing past the one-hour window.
        jdbc.update("UPDATE complaints SET created_at = now() - interval '61 minutes' WHERE id = (SELECT c.id FROM complaints c "
                + "JOIN users u ON u.id = c.user_id WHERE u.email = ? ORDER BY c.created_at LIMIT 1)", citizen);
        assertThat(send("POST", "/api/complaints", complaintBody("Freed slot", "Detail"), token(citizen)).statusCode()).isEqualTo(201);
        assertProblem(send("POST", "/api/complaints", complaintBody("Blocked again", "Detail"), token(citizen)), 429);
        assertThat(countFiledBy(citizen)).isEqualTo(11);
    }

    @Test
    void theWindowBoundaryIsExclusive() {
        // The query counts filings strictly after (now - window): one filed exactly at the boundary has left it.
        UUID other = UUID.randomUUID();
        java.time.Instant boundary = java.time.Instant.parse("2020-01-01T00:00:00Z");
        String email = "boundary-" + hex(4) + "@it.test";
        User u = new User(email, encoder.encode(PASSWORD), "IT boundary", Role.CITIZEN, "en");
        UUID id = users.save(u).getId();
        jdbc.update("INSERT INTO complaints (tracking_id, user_id, title, description, latitude, longitude, created_at) "
                + "VALUES (?, ?::uuid, 't', 'd', 30.3, 78.0, ?)", "CS-B" + hex(4).toUpperCase(), id.toString(),
                java.sql.Timestamp.from(boundary));
        assertThat(complaints.countByUserIdAndCreatedAtAfter(id, boundary)).isZero();
        assertThat(complaints.countByUserIdAndCreatedAtAfter(id, boundary.minusMillis(1))).isEqualTo(1);
        assertThat(complaints.countByUserIdAndCreatedAtAfter(other, boundary.minusMillis(1))).isZero();
    }

    @Test
    void concurrentFilingsCannotSlipPastTheLimit() throws Exception {
        String citizen = freshCitizen();
        List<CompletableFuture<Integer>> attempts = new ArrayList<>();
        for (int i = 0; i < 15; i++) {
            int n = i;
            attempts.add(CompletableFuture.supplyAsync(() -> {
                try {
                    return send("POST", "/api/complaints", complaintBody("Burst " + n, "Detail"), token(citizen)).statusCode();
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            }));
        }
        List<Integer> codes = attempts.stream().map(CompletableFuture::join).toList();
        assertThat(codes).filteredOn(s -> s == 201).hasSize(10);
        assertThat(codes).filteredOn(s -> s != 201).hasSize(5).allMatch(s -> s == 429);
        assertThat(countFiledBy(citizen)).isEqualTo(10);
    }

    // ---------------------------------------------------------------- 8: administrator permissions

    @Test
    void adminHasTheFullExplicitLifecycleAndNothingMore() throws Exception {
        String id = file(CIT_B, "Signal not working", "Traffic signal dead").get("id").asText();
        assertThat(ids(send("GET", "/api/complaints", null, token(ADMIN)))).contains(id);

        assertProblem(patch(id, ADMIN, "ASSIGNED", CIT_A, null), 400);            // not a crew account
        assertProblem(patch(id, ADMIN, "ASSIGNED", null, null), 400);             // worker required
        assertProblem(patch(id, ADMIN, "RESOLVED", null, null), 409);             // FILED -> RESOLVED is not legal
        assertThat(body(patch(id, ADMIN, "ASSIGNED", "CREW-B@it.test", null), 200).get("assignedWorker").asText())
                .isEqualTo(CREW_B);                                                // stored as the account's email
        assertProblem(patch(id, CREW_A, "IN_PROGRESS", null, null), 404);         // crew A can't see crew B's work
        body(patch(id, ADMIN, "ASSIGNED", CREW_A, null), 200);                     // reassign
        assertProblem(patch(id, ADMIN, "REJECTED", null, null), 400);             // reason required
        body(patch(id, ADMIN, "REJECTED", null, "Duplicate of an earlier report"), 200);
        JsonNode reopened = body(patch(id, ADMIN, "FILED", null, null), 200);    // reopen
        // core serialises with non_null inclusion: cleared fields are omitted, not sent as null.
        assertThat(reopened.path("assignedWorker").isMissingNode() || reopened.get("assignedWorker").isNull()).isTrue();
        assertThat(reopened.path("resolvedAt").isMissingNode() || reopened.get("resolvedAt").isNull()).isTrue();
        assertThat(row(id).get("assigned_worker").isNull()).isTrue();
        assertThat(auditCount(id)).isEqualTo(4);

        // City bulletins: admin only to publish, public to read.
        Map<String, Object> bulletin = Map.of("title", "Road closed for repairs", "latitude", 30.3, "longitude", 78.0);
        assertThat(send("POST", "/api/city-events", bulletin, null).statusCode()).isEqualTo(401);
        assertProblem(send("POST", "/api/city-events", bulletin, token(CIT_A)), 403);
        assertProblem(send("POST", "/api/city-events", bulletin, token(CREW_A)), 403);
        assertThat(send("POST", "/api/city-events", bulletin, token(ADMIN)).statusCode()).isEqualTo(201);
        assertThat(send("GET", "/api/city-events", null, null).statusCode()).isEqualTo(200);
    }

    // ---------------------------------------------------------------- 9: legitimate workflows still work

    @Test
    void existingCitizenWorkflowsStillWork() throws Exception {
        HttpResponse<String> meta = send("GET", "/api/complaints/meta", null, null);
        assertThat(meta.statusCode()).isEqualTo(200);
        assertThat(json.readTree(meta.body()).get("escalationLadder").size()).isEqualTo(10);

        JsonNode c = file(CIT_A, "Pothole on Rajpur Road", "Deep pothole");
        assertThat(c.get("department").asText()).isEqualTo("PWD_ROADS");
        assertThat(c.get("trackingId").asText()).matches("CS-[0-9A-HJKMNP-TV-Z]{10}");
        assertThat(row(c.get("id").asText()).get("user_id").asText()).isEqualTo(users.findByEmailIgnoreCase(CIT_A).orElseThrow().getId().toString());

        assertProblem(send("POST", "/api/complaints", complaintBody("x", "y"), token(UNVERIFIED)), 403);
        assertProblem(send("POST", "/api/complaints", Map.of("title", "", "description", "", "latitude", 30, "longitude", 78),
                token(CIT_A)), 400);
        // Crew and admins can also file (e.g. on behalf of a caller).
        assertThat(send("POST", "/api/complaints", complaintBody("Tree fell", "Blocking lane"), token(CREW_A)).statusCode()).isEqualTo(201);
    }

    // ---------------------------------------------------------------- live updates are redacted

    @Test
    void anonymousLiveSubscribersNeverReceivePersonalComplaintDetails() throws Exception {
        BlockingQueue<String> frames = new LinkedBlockingQueue<>();
        WebSocketStompClient stomp = new WebSocketStompClient(new StandardWebSocketClient());
        stomp.setMessageConverter(new SimpleMessageConverter());
        StompSession session = stomp.connectAsync("ws://localhost:" + port + "/ws", new StompSessionHandlerAdapter() {})
                .get(10, TimeUnit.SECONDS);
        session.subscribe("/topic/city-events", new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return byte[].class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                frames.add(new String((byte[]) payload, StandardCharsets.UTF_8));
            }
        });
        Thread.sleep(500);   // let the subscription register before publishing

        Map<String, Object> body = new LinkedHashMap<>(complaintBody("Leak outside Asha Rawat's house 12",
                "Call me on 9876543210, I live at 14 Rajpur Road"));
        body.put("citizenName", "Asha Rawat");
        body.put("latitude", 30.324317);
        body.put("longitude", 78.041853);
        HttpResponse<String> filed = send("POST", "/api/complaints", body, token(CIT_A));
        assertThat(filed.statusCode()).isEqualTo(201);
        JsonNode c = json.readTree(filed.body());
        patch(c.get("id").asText(), CREW_A, "ASSIGNED", null, null);

        List<String> received = new ArrayList<>();
        long deadline = System.currentTimeMillis() + 5000;
        while (System.currentTimeMillis() < deadline
                && received.stream().noneMatch(f -> f.contains("COMPLAINT_STATUS_UPDATED"))) {
            String f = frames.poll(250, TimeUnit.MILLISECONDS);
            if (f != null) {
                received.add(f);
            }
        }
        session.disconnect();
        assertThat(received).anyMatch(f -> f.contains("\"COMPLAINT_FILED\""))
                .anyMatch(f -> f.contains("\"COMPLAINT_STATUS_UPDATED\""));
        for (String f : received) {
            assertThat(f).doesNotContain("Asha").doesNotContain("Rawat").doesNotContain("9876543210")
                    .doesNotContain("Rajpur").doesNotContain("house 12").doesNotContain(c.get("trackingId").asText())
                    .doesNotContain("30.324317").doesNotContain("78.041853").doesNotContain(CREW_A)
                    .doesNotContain(CIT_A);
            JsonNode m = json.readTree(f);
            Set<String> keys = new java.util.HashSet<>();
            m.get("data").fieldNames().forEachRemaining(keys::add);
            switch (m.get("type").asText()) {
                case "COMPLAINT_FILED", "COMPLAINT_STATUS_UPDATED" -> assertThat(keys)
                        .isSubsetOf(Set.of("id", "title", "category", "department", "status", "priority"));
                case "OBSERVATION_CREATED" -> assertThat(keys).isSubsetOf(Set.of("id", "type", "status", "incidentId", "observedAt"));
                default -> { }
            }
        }
    }

    // ---------------------------------------------------------------- helpers

    private static String hex(int bytes) {
        byte[] b = new byte[bytes];
        RANDOM.nextBytes(b);
        return HexFormat.of().formatHex(b);
    }

    private static String token(String email) {
        return TOKENS.get(email);
    }

    private static Map<String, Object> complaintBody(String title, String description) {
        return Map.of("title", title, "description", description, "latitude", 30.3243, "longitude", 78.0418, "priority", "HIGH");
    }

    private JsonNode file(String email, String title, String description) throws Exception {
        return body(send("POST", "/api/complaints", complaintBody(title, description), token(email)), 201);
    }

    private HttpResponse<String> patch(String id, String email, String status, String worker, String notes) throws Exception {
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("status", status);
        if (worker != null) {
            b.put("assignedWorker", worker);
        }
        if (notes != null) {
            b.put("resolutionNotes", notes);
        }
        return send("PATCH", "/api/complaints/" + id + "/status", b, token(email));
    }

    private JsonNode body(HttpResponse<String> r, int expected) throws Exception {
        assertThat(r.statusCode()).as(r.uri() + " -> " + r.body()).isEqualTo(expected);
        return json.readTree(r.body());
    }

    private void assertProblem(HttpResponse<String> r, int expected) throws Exception {
        assertThat(r.statusCode()).as(r.uri() + " -> " + r.body()).isEqualTo(expected);
        assertThat(r.headers().firstValue("Content-Type")).as(r.uri().toString())
                .hasValueSatisfying(ct -> assertThat(ct).contains("problem+json"));
        JsonNode p = json.readTree(r.body());
        assertThat(p.get("status").asInt()).isEqualTo(expected);
        assertThat(r.body()).doesNotContainIgnoringCase("exception").doesNotContain("ROLE_");
    }

    private List<String> ids(HttpResponse<String> r) throws Exception {
        assertThat(r.statusCode()).as(r.body()).isEqualTo(200);
        List<String> out = new ArrayList<>();
        json.readTree(r.body()).forEach(n -> out.add(n.get("id").asText()));
        return out;
    }

    private JsonNode row(String id) {
        return json.valueToTree(jdbc.queryForMap("SELECT status, assigned_worker, user_id::text AS user_id FROM complaints WHERE id = ?::uuid", id));
    }

    private String status(JsonNode complaint) {
        return row(complaint.get("id").asText()).get("status").asText();
    }

    private int auditCount(String id) {
        Integer n = jdbc.queryForObject("SELECT count(*) FROM audit_log WHERE action='COMPLAINT_STATUS_CHANGED' AND entity_id=?",
                Integer.class, id);
        return n == null ? 0 : n;
    }

    private HttpResponse<String> send(String method, String path, Object body, String token) throws Exception {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
                .header("Content-Type", "application/json")
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
        if (token != null) {
            b.header("Authorization", "Bearer " + token);
        }
        return http.send(b.build(), HttpResponse.BodyHandlers.ofString());
    }
}

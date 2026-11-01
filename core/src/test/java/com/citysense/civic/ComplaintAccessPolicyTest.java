package com.citysense.civic;

import static com.citysense.civic.ComplaintStatus.ASSIGNED;
import static com.citysense.civic.ComplaintStatus.ESCALATED;
import static com.citysense.civic.ComplaintStatus.FILED;
import static com.citysense.civic.ComplaintStatus.IN_PROGRESS;
import static com.citysense.civic.ComplaintStatus.REJECTED;
import static com.citysense.civic.ComplaintStatus.RESOLVED;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.citysense.common.error.ApiException;
import com.citysense.platform.auth.AuthUser;
import com.citysense.platform.auth.Role;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.http.HttpStatus;

class ComplaintAccessPolicyTest {

    private static final AuthUser CITIZEN = user(Role.CITIZEN, "c@x.test");
    private static final AuthUser CREW_A = user(Role.CREW, "crew-a@x.test");
    private static final AuthUser ADMIN = user(Role.ADMIN, "admin@x.test");

    private static AuthUser user(Role role, String email) {
        return new AuthUser(UUID.randomUUID(), email, role, true);
    }

    private static HttpStatus statusOf(Runnable r) {
        try {
            r.run();
            return HttpStatus.OK;
        } catch (ApiException e) {
            return e.getStatus();
        }
    }

    // ------------------------------------------------------------------ visibility

    @Test
    void ownerAndAdminCanViewOtherCitizensCannot() {
        UUID owner = CITIZEN.id();
        for (ComplaintStatus s : ComplaintStatus.values()) {
            assertThat(ComplaintAccessPolicy.canView(CITIZEN, owner, "crew-b@x.test", s)).as("owner, %s", s).isTrue();
            assertThat(ComplaintAccessPolicy.canView(user(Role.CITIZEN, "other@x.test"), owner, null, s)).isFalse();
            assertThat(ComplaintAccessPolicy.canView(null, owner, null, s)).isFalse();
            assertThat(ComplaintAccessPolicy.canView(ADMIN, owner, "crew-b@x.test", s)).as("admin, %s", s).isTrue();
            assertThat(ComplaintAccessPolicy.canView(ADMIN, null, "Legacy Free Text Worker", s)).isTrue();
        }
    }

    @Test
    void crewSeeTheirOwnAssignmentsInEveryStatus() {
        for (ComplaintStatus s : ComplaintStatus.values()) {
            assertThat(ComplaintAccessPolicy.canView(CREW_A, CITIZEN.id(), "crew-a@x.test", s)).as("%s", s).isTrue();
            assertThat(ComplaintAccessPolicy.canView(CREW_A, CITIZEN.id(), "CREW-A@X.TEST", s)).as("case, %s", s).isTrue();
        }
    }

    @Test
    void crewSeeUnassignedComplaintsOnlyWhileTheyAreAvailableForAssignment() {
        Set<ComplaintStatus> available = EnumSet.of(FILED, ESCALATED);
        for (ComplaintStatus s : ComplaintStatus.values()) {
            assertThat(ComplaintAccessPolicy.canView(CREW_A, CITIZEN.id(), null, s)).as("%s", s)
                    .isEqualTo(available.contains(s));
            assertThat(ComplaintAccessPolicy.canView(CREW_A, CITIZEN.id(), "  ", s)).as("blank worker, %s", s)
                    .isEqualTo(available.contains(s));
            assertThat(ComplaintAccessPolicy.isAvailableForAssignment(null, s)).isEqualTo(available.contains(s));
        }
    }

    @Test
    void crewNeverSeeComplaintsAssignedToSomeoneElse() {
        for (ComplaintStatus s : ComplaintStatus.values()) {
            assertThat(ComplaintAccessPolicy.canView(CREW_A, CITIZEN.id(), "crew-b@x.test", s)).as("%s", s).isFalse();
            assertThat(ComplaintAccessPolicy.canView(CREW_A, null, "Legacy Free Text Worker", s)).as("legacy, %s", s).isFalse();
        }
    }

    @Test
    void crewSeeComplaintsTheyFiledThemselves() {
        assertThat(ComplaintAccessPolicy.canView(CREW_A, CREW_A.id(), "crew-b@x.test", RESOLVED)).isTrue();
    }

    @Test
    void legacyUnownedComplaintsAreHiddenFromCitizens() {
        assertThat(ComplaintAccessPolicy.canView(CITIZEN, null, null, FILED)).isFalse();
        assertThat(ComplaintAccessPolicy.canView(CREW_A, null, null, FILED)).isTrue();   // in the assignment queue
        assertThat(ComplaintAccessPolicy.canView(ADMIN, null, null, RESOLVED)).isTrue();
    }

    // ------------------------------------------------------------------ the full transition table

    private static final Map<ComplaintStatus, Set<ComplaintStatus>> CREW_LEGAL = Map.of(
            FILED, EnumSet.of(ASSIGNED), ESCALATED, EnumSet.of(ASSIGNED),
            ASSIGNED, EnumSet.of(IN_PROGRESS), IN_PROGRESS, EnumSet.of(RESOLVED));

    private static final Map<ComplaintStatus, Set<ComplaintStatus>> ADMIN_LEGAL = Map.of(
            FILED, EnumSet.of(ASSIGNED, REJECTED, ESCALATED), ESCALATED, EnumSet.of(ASSIGNED, REJECTED),
            ASSIGNED, EnumSet.of(ASSIGNED, IN_PROGRESS, REJECTED, FILED),
            IN_PROGRESS, EnumSet.of(ASSIGNED, RESOLVED, REJECTED),
            RESOLVED, EnumSet.of(FILED), REJECTED, EnumSet.of(FILED));

    @ParameterizedTest
    @EnumSource(ComplaintStatus.class)
    void crewMayOnlyMoveTheirOwnComplaintsAlongTheirLegalTransitions(ComplaintStatus from) {
        for (ComplaintStatus to : ComplaintStatus.values()) {
            // worker for the state: unassigned before ASSIGNED, the crew member afterwards
            String worker = (from == FILED || from == ESCALATED) ? null : CREW_A.email();
            HttpStatus got = statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, from, worker, to, null, null));
            HttpStatus expected = !ComplaintAccessPolicy.CREW_TARGETS.contains(to) ? HttpStatus.FORBIDDEN
                    : CREW_LEGAL.getOrDefault(from, Set.of()).contains(to) ? HttpStatus.OK : HttpStatus.CONFLICT;
            assertThat(got).as("CREW %s -> %s", from, to).isEqualTo(expected);
        }
    }

    @ParameterizedTest
    @EnumSource(ComplaintStatus.class)
    void adminFollowsTheAdminTransitionTable(ComplaintStatus from) {
        for (ComplaintStatus to : ComplaintStatus.values()) {
            String worker = (from == FILED || from == ESCALATED) ? null : "crew-a@x.test";
            String requested = to == ASSIGNED ? "crew-b@x.test" : null;   // reassign to someone else
            HttpStatus got = statusOf(() -> ComplaintAccessPolicy.decide(ADMIN, from, worker, to, requested, "reason"));
            HttpStatus expected = ADMIN_LEGAL.getOrDefault(from, Set.of()).contains(to) ? HttpStatus.OK : HttpStatus.CONFLICT;
            assertThat(got).as("ADMIN %s -> %s", from, to).isEqualTo(expected);
        }
    }

    @Test
    void citizensAndAnonymousCannotChangeAnything() {
        for (ComplaintStatus to : ComplaintStatus.values()) {
            assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CITIZEN, FILED, null, to, null, "x")))
                    .isEqualTo(HttpStatus.FORBIDDEN);
            assertThat(statusOf(() -> ComplaintAccessPolicy.decide(null, FILED, null, to, null, "x")))
                    .isEqualTo(HttpStatus.UNAUTHORIZED);
        }
    }

    // ------------------------------------------------------------------ assignment

    @Test
    void crewSelfAssignsAnUnassignedComplaint() {
        var change = ComplaintAccessPolicy.decide(CREW_A, FILED, null, ASSIGNED, null, null);
        assertThat(change.assignedWorker()).isEqualTo("crew-a@x.test");
        assertThat(ComplaintAccessPolicy.decide(CREW_A, FILED, null, ASSIGNED, "CREW-A@x.test", null).assignedWorker())
                .isEqualTo("crew-a@x.test");
    }

    @Test
    void crewCannotAssignToSomeoneElseOrTouchAnotherCrewsComplaint() {
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, FILED, null, ASSIGNED, "crew-b@x.test", null)))
                .isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, ESCALATED, "crew-b@x.test", ASSIGNED, null, null)))
                .isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, ASSIGNED, "crew-b@x.test", IN_PROGRESS, null, null)))
                .isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, IN_PROGRESS, "crew-b@x.test", RESOLVED, null, null)))
                .isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, IN_PROGRESS, "Legacy Free Text Worker", RESOLVED, null, null)))
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void crewCannotReassignWhileProgressing() {
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(CREW_A, ASSIGNED, "crew-a@x.test", IN_PROGRESS, "crew-b@x.test", null)))
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void adminAssignmentNeedsAWorkerAndAChange() {
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(ADMIN, FILED, null, ASSIGNED, null, null)))
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(ADMIN, ASSIGNED, "crew-a@x.test", ASSIGNED, "CREW-A@x.test", null)))
                .isEqualTo(HttpStatus.CONFLICT);
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(ADMIN, IN_PROGRESS, "crew-a@x.test", RESOLVED, "crew-b@x.test", null)))
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void adminRejectNeedsAReasonAndReopenClearsTheAssignment() {
        assertThat(statusOf(() -> ComplaintAccessPolicy.decide(ADMIN, FILED, null, REJECTED, null, "  ")))
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(ComplaintAccessPolicy.decide(ADMIN, RESOLVED, "crew-a@x.test", FILED, null, null).assignedWorker()).isNull();
        assertThat(ComplaintAccessPolicy.decide(ADMIN, REJECTED, null, FILED, null, null).to()).isEqualTo(FILED);
    }

    @Test
    void unknownStatusValuesAreRejected() {
        assertThat(ComplaintStatus.parse(" in_progress ")).isEqualTo(IN_PROGRESS);
        assertThatThrownBy(() -> ComplaintStatus.parse("DONE"))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(() -> ComplaintStatus.parse(null)).isInstanceOf(ApiException.class);
    }
}

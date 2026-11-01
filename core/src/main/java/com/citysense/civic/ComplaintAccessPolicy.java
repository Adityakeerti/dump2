package com.citysense.civic;

import static com.citysense.civic.ComplaintStatus.ASSIGNED;
import static com.citysense.civic.ComplaintStatus.ESCALATED;
import static com.citysense.civic.ComplaintStatus.FILED;
import static com.citysense.civic.ComplaintStatus.IN_PROGRESS;
import static com.citysense.civic.ComplaintStatus.REJECTED;
import static com.citysense.civic.ComplaintStatus.RESOLVED;

import com.citysense.common.error.ApiException;
import com.citysense.platform.auth.AuthUser;
import com.citysense.platform.auth.Role;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;

/**
 * Who may see and change a complaint. Pure rules (no I/O) so every case is unit-tested.
 *
 * <p>Visibility ({@link #canView}): the owner; ADMIN; CREW only for their own assignments and the unassigned
 * queue. Anyone else is told the complaint does not exist (404), so a tracking ID or complaint id never
 * confirms a complaint the caller may not see.
 *
 * <p>Status changes (CITIZEN: never):
 * <pre>
 *   CREW   FILED|ESCALATED -> ASSIGNED     self-assignment only, complaint must be unassigned
 *          ASSIGNED        -> IN_PROGRESS  only on complaints assigned to them
 *          IN_PROGRESS     -> RESOLVED     only on complaints assigned to them
 *   ADMIN  FILED           -> ASSIGNED | REJECTED | ESCALATED
 *          ESCALATED       -> ASSIGNED | REJECTED
 *          ASSIGNED        -> ASSIGNED (reassign) | IN_PROGRESS | REJECTED | FILED (unassign)
 *          IN_PROGRESS     -> ASSIGNED (reassign) | RESOLVED | REJECTED
 *          RESOLVED        -> FILED (reopen)
 *          REJECTED        -> FILED (reopen)
 * </pre>
 * Assignment is by account: {@code assigned_worker} holds the crew member's email. ASSIGNED always needs a
 * worker; REJECTED needs a reason in resolutionNotes.
 */
public final class ComplaintAccessPolicy {

    private ComplaintAccessPolicy() {}

    public static final Set<ComplaintStatus> CREW_TARGETS = EnumSet.of(ASSIGNED, IN_PROGRESS, RESOLVED);

    private static final Map<ComplaintStatus, Set<ComplaintStatus>> CREW = Map.of(
            FILED, EnumSet.of(ASSIGNED),
            ESCALATED, EnumSet.of(ASSIGNED),
            ASSIGNED, EnumSet.of(IN_PROGRESS),
            IN_PROGRESS, EnumSet.of(RESOLVED));

    private static final Map<ComplaintStatus, Set<ComplaintStatus>> ADMIN = Map.of(
            FILED, EnumSet.of(ASSIGNED, REJECTED, ESCALATED),
            ESCALATED, EnumSet.of(ASSIGNED, REJECTED),
            ASSIGNED, EnumSet.of(ASSIGNED, IN_PROGRESS, REJECTED, FILED),
            IN_PROGRESS, EnumSet.of(ASSIGNED, RESOLVED, REJECTED),
            RESOLVED, EnumSet.of(FILED),
            REJECTED, EnumSet.of(FILED));

    public static boolean isStaff(AuthUser user) {
        return user != null && (user.role() == Role.ADMIN || user.role() == Role.CREW);
    }

    /** Statuses in which an unassigned complaint is waiting in the crew assignment queue. */
    public static final Set<ComplaintStatus> ASSIGNABLE = EnumSet.of(FILED, ESCALATED);

    /** Unassigned and still open for a crew member to pick up. */
    public static boolean isAvailableForAssignment(String assignedWorker, ComplaintStatus status) {
        return blankToNull(assignedWorker) == null && ASSIGNABLE.contains(status);
    }

    /**
     * True if the user may read this complaint:
     * <ul>
     *   <li>ADMIN: every complaint;</li>
     *   <li>CREW: complaints assigned to them (any status) and unassigned complaints available for assignment,
     *       never complaints assigned to someone else;</li>
     *   <li>anyone: complaints they filed themselves.</li>
     * </ul>
     * Unowned legacy complaints are therefore never visible to citizens. {@link ComplaintRepository#searchForCrew}
     * applies the same CREW rule to listings.
     */
    public static boolean canView(AuthUser user, UUID complaintOwner, String assignedWorker, ComplaintStatus status) {
        if (user == null) {
            return false;
        }
        if (user.role() == Role.ADMIN || (complaintOwner != null && complaintOwner.equals(user.id()))) {
            return true;
        }
        if (user.role() == Role.CREW) {
            String worker = blankToNull(assignedWorker);
            return worker != null ? worker.equalsIgnoreCase(user.email()) : ASSIGNABLE.contains(status);
        }
        return false;
    }

    /** Outcome of an allowed change: the worker the complaint will be assigned to afterwards (null = none). */
    public record Change(ComplaintStatus to, String assignedWorker) {}

    /**
     * Decides a status change or throws: 403 for a role/assignment the caller does not hold, 409 for a
     * transition that is not legal from the current state, 400 for a missing worker or reason.
     */
    public static Change decide(AuthUser user, ComplaintStatus from, String currentWorker, ComplaintStatus to,
                                String requestedWorker, String notes) {
        if (user == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Sign in required");
        }
        String me = user.email();
        String requested = blankToNull(requestedWorker);
        switch (user.role()) {
            case CREW -> {
                if (!CREW_TARGETS.contains(to)) {
                    throw new ApiException(HttpStatus.FORBIDDEN, "Crew can only set ASSIGNED, IN_PROGRESS or RESOLVED");
                }
                requireLegal(CREW, from, to);
                if (to == ASSIGNED) {
                    if (currentWorker != null && !currentWorker.equalsIgnoreCase(me)) {
                        throw new ApiException(HttpStatus.FORBIDDEN, "Complaint is assigned to another crew member");
                    }
                    if (requested != null && !requested.equalsIgnoreCase(me)) {
                        throw new ApiException(HttpStatus.FORBIDDEN, "Crew can only assign complaints to themselves");
                    }
                    return new Change(to, me);
                }
                if (currentWorker == null || !currentWorker.equalsIgnoreCase(me)) {
                    throw new ApiException(HttpStatus.FORBIDDEN, "Complaint is not assigned to you");
                }
                if (requested != null && !requested.equalsIgnoreCase(me)) {
                    throw new ApiException(HttpStatus.FORBIDDEN, "Only an admin can reassign a complaint");
                }
                return new Change(to, currentWorker);
            }
            case ADMIN -> {
                requireLegal(ADMIN, from, to);
                return switch (to) {
                    case ASSIGNED -> {
                        if (requested == null) {
                            throw new ApiException(HttpStatus.BAD_REQUEST, "assignedWorker (a crew member's email) is required");
                        }
                        if (from == ASSIGNED && requested.equalsIgnoreCase(currentWorker)) {
                            throw new ApiException(HttpStatus.CONFLICT, "Complaint is already assigned to " + requested);
                        }
                        yield new Change(to, requested);
                    }
                    case FILED -> new Change(to, null);   // reopen / unassign
                    case REJECTED -> {
                        if (blankToNull(notes) == null) {
                            throw new ApiException(HttpStatus.BAD_REQUEST, "resolutionNotes (the reason) is required to reject");
                        }
                        yield new Change(to, currentWorker);
                    }
                    default -> {
                        if (requested != null && !requested.equalsIgnoreCase(currentWorker)) {
                            throw new ApiException(HttpStatus.BAD_REQUEST, "Use status ASSIGNED to reassign a complaint");
                        }
                        yield new Change(to, currentWorker);
                    }
                };
            }
            default -> throw new ApiException(HttpStatus.FORBIDDEN, "Only crew or admins can change complaint status");
        }
    }

    private static void requireLegal(Map<ComplaintStatus, Set<ComplaintStatus>> table, ComplaintStatus from, ComplaintStatus to) {
        if (!table.getOrDefault(from, Set.of()).contains(to)) {
            throw new ApiException(HttpStatus.CONFLICT, "Cannot change status from " + from + " to " + to);
        }
    }

    private static String blankToNull(String s) {
        return s == null || s.isBlank() ? null : s.trim();
    }
}

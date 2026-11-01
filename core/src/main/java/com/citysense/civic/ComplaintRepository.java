package com.citysense.civic;

import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ComplaintRepository extends JpaRepository<Complaint, UUID> {
    Optional<Complaint> findByTrackingId(String trackingId);
    boolean existsByTrackingId(String trackingId);
    List<Complaint> findByStatus(String status);
    List<Complaint> findByDepartment(String department);
    List<Complaint> findAllByOrderByCreatedAtDesc();
    List<Complaint> findByUserIdOrderByCreatedAtDesc(UUID userId);

    /** Filings by this user strictly after {@code since} (the sliding filing-limit window). */
    long countByUserIdAndCreatedAtAfter(UUID userId, Instant since);

    /** The oldest filing still inside the window: when it leaves, a slot frees up (Retry-After). */
    Optional<Complaint> findFirstByUserIdAndCreatedAtAfterOrderByCreatedAtAsc(UUID userId, Instant since);

    /** ADMIN listing; null filters are ignored. */
    @Query("select c from Complaint c where (:status is null or c.status = :status) "
            + "and (:department is null or c.department = :department) order by c.createdAt desc")
    List<Complaint> search(@Param("status") String status, @Param("department") String department);

    /**
     * CREW listing: their own assignments (any status) plus unassigned complaints available for assignment.
     * Never complaints assigned to anyone else. Mirrors {@link ComplaintAccessPolicy#canView}.
     */
    @Query("select c from Complaint c where (lower(c.assignedWorker) = lower(:email) "
            + "or ((c.assignedWorker is null or trim(c.assignedWorker) = '') and c.status in ('FILED', 'ESCALATED'))) "
            + "and (:status is null or c.status = :status) "
            + "and (:department is null or c.department = :department) order by c.createdAt desc")
    List<Complaint> searchForCrew(@Param("email") String email, @Param("status") String status,
                                  @Param("department") String department);

    /** Row lock for status changes, so two crew members cannot both claim the same complaint. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select c from Complaint c where c.id = :id")
    Optional<Complaint> findByIdForUpdate(@Param("id") UUID id);
}

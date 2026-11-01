package com.citysense.platform.incident;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IncidentRepository extends JpaRepository<Incident, UUID> {

    /** Unresolved incidents within radiusMeters (PostGIS geography distance) touched since `since`, nearest first. */
    @Query(value = """
            SELECT i.* FROM incidents i
            WHERE i.status <> 'RESOLVED'
              AND i.updated_at >= :since
              AND ST_DWithin(i.geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
            ORDER BY ST_Distance(i.geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography)
            """, nativeQuery = true)
    List<Incident> findCorrelationCandidates(@Param("lat") double lat, @Param("lng") double lng,
                                             @Param("radius") double radiusMeters, @Param("since") Instant since);

    List<Incident> findByStatusInOrderByUrgencyScoreDescUpdatedAtDesc(Collection<IncidentStatus> statuses);
}

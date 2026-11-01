package com.citysense.avatar;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AvatarRepository extends JpaRepository<Avatar, UUID> {

    Optional<Avatar> findByHandle(String handle);

    Optional<Avatar> findByIdAndActiveTrue(UUID id);

    /** Active avatars within radiusMeters of a point, nearest first; q filters name/title/category. */
    @Query(value = """
            SELECT * FROM avatars a
            WHERE a.active
              AND ST_DWithin(a.geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
              AND (CAST(:q AS text) IS NULL OR a.name ILIKE CAST(:q AS text) OR a.title ILIKE CAST(:q AS text) OR a.category ILIKE CAST(:q AS text))
            ORDER BY ST_Distance(a.geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography)
            LIMIT :lim
            """, nativeQuery = true)
    List<Avatar> findNearby(@Param("lat") double lat, @Param("lng") double lng, @Param("radius") double radius,
                            @Param("q") String q, @Param("lim") int limit);

    @Query(value = """
            SELECT * FROM avatars a
            WHERE a.active AND (CAST(:q AS text) IS NULL OR a.name ILIKE CAST(:q AS text) OR a.title ILIKE CAST(:q AS text) OR a.category ILIKE CAST(:q AS text))
            ORDER BY a.rating DESC, a.name
            LIMIT :lim
            """, nativeQuery = true)
    List<Avatar> search(@Param("q") String q, @Param("lim") int limit);
}

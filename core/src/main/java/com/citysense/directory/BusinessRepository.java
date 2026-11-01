package com.citysense.directory;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BusinessRepository extends JpaRepository<Business, UUID> {

    Optional<Business> findBySeedKey(String seedKey);

    /** Active businesses, nearest first when a point is given, filtered by optional locality/category/text. */
    @Query(value = """
            SELECT b.* FROM businesses b
            WHERE b.active
              AND (CAST(:category AS text) IS NULL OR lower(b.category) = lower(CAST(:category AS text)))
              AND (CAST(:locality AS text) IS NULL OR b.locality ILIKE '%' || CAST(:locality AS text) || '%')
              AND (CAST(:q AS text) IS NULL OR b.name ILIKE '%' || CAST(:q AS text) || '%'
                   OR b.description ILIKE '%' || CAST(:q AS text) || '%' OR b.category ILIKE '%' || CAST(:q AS text) || '%')
              AND (CAST(:lat AS double precision) IS NULL OR CAST(:radius AS double precision) IS NULL
                   OR ST_DWithin(b.geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius))
            ORDER BY CASE WHEN CAST(:lat AS double precision) IS NULL THEN 0
                          ELSE ST_Distance(b.geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) END,
                     b.featured DESC, b.name
            LIMIT :lim
            """, nativeQuery = true)
    List<Business> search(@Param("lat") Double lat, @Param("lng") Double lng, @Param("radius") Double radius,
                          @Param("locality") String locality, @Param("category") String category,
                          @Param("q") String q, @Param("lim") int limit);
}

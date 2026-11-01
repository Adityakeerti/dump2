package com.citysense.platform.observation;

import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ObservationRepository extends JpaRepository<Observation, UUID> {

    List<Observation> findByIncidentIdOrderByObservedAtAsc(UUID incidentId);

    List<Observation> findAllByOrderByObservedAtDesc(Pageable pageable);

    List<Observation> findByTypeOrderByObservedAtDesc(ObservationType type, Pageable pageable);
}

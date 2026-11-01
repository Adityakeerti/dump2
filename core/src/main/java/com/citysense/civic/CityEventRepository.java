package com.citysense.civic;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CityEventRepository extends JpaRepository<CityEvent, UUID> {

    java.util.Optional<CityEvent> findBySeedKey(String seedKey);

    List<CityEvent> findAllByOrderByStartsAtDesc();
}

package com.citysense.mesh.repository;

import com.citysense.mesh.entity.MeshMessageEntity;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface MeshMessageRepository extends JpaRepository<MeshMessageEntity, String> {

    List<MeshMessageEntity> findTop50ByOrderByReceivedAtDesc();

    List<MeshMessageEntity> findByTypeOrderByReceivedAtDesc(String type);

    List<MeshMessageEntity> findBySenderIdOrderByReceivedAtDesc(String senderId);
}

package com.citysense.mesh.repository;

import com.citysense.mesh.entity.MeshPeerEntity;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface MeshPeerRepository extends JpaRepository<MeshPeerEntity, String> {

    List<MeshPeerEntity> findAllByOrderByLastSeenAtDesc();
}

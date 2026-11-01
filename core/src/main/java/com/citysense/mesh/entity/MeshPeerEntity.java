package com.citysense.mesh.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "mesh_peers")
public class MeshPeerEntity {

    @Id
    @Column(name = "node_id", length = 64, nullable = false)
    private String nodeId;

    @Column(name = "display_name", length = 120, nullable = false)
    private String displayName;

    @Column(name = "role", length = 32, nullable = false)
    private String role;

    @Column(name = "hops", nullable = false)
    private int hops;

    @Column(name = "capabilities", length = 255)
    private String capabilities;

    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt;

    public MeshPeerEntity() {}

    public MeshPeerEntity(String nodeId, String displayName, String role, int hops, String capabilities, Instant lastSeenAt) {
        this.nodeId = nodeId;
        this.displayName = displayName;
        this.role = role;
        this.hops = hops;
        this.capabilities = capabilities;
        this.lastSeenAt = lastSeenAt != null ? lastSeenAt : Instant.now();
    }

    public String getNodeId() {
        return nodeId;
    }

    public void setNodeId(String nodeId) {
        this.nodeId = nodeId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public int getHops() {
        return hops;
    }

    public void setHops(int hops) {
        this.hops = hops;
    }

    public String getCapabilities() {
        return capabilities;
    }

    public void setCapabilities(String capabilities) {
        this.capabilities = capabilities;
    }

    public Instant getLastSeenAt() {
        return lastSeenAt;
    }

    public void setLastSeenAt(Instant lastSeenAt) {
        this.lastSeenAt = lastSeenAt;
    }
}

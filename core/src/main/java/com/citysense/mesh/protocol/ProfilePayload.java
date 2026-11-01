package com.citysense.mesh.protocol;

/**
 * Layer 3 — Node profile and presence beacon.
 * Broadcasts node capabilities, identity, and role (e.g. AMBULANCE, POLICE, CITIZEN, DISPATCH).
 */
public record ProfilePayload(
        String nodeId,
        String displayName,
        String role,
        String capabilities,
        Integer version) {

    public ProfilePayload {
        nodeId = nodeId != null ? nodeId : "";
        displayName = displayName != null ? displayName : "MeshNode";
        role = role != null ? role : "CITIZEN";
        capabilities = capabilities != null ? capabilities : "RELAY_STORE_FORWARD";
        version = version != null ? version : 1;
    }
}

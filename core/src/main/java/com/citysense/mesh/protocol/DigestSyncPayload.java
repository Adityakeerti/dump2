package com.citysense.mesh.protocol;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Collections;
import java.util.List;

/**
 * Layer 3 — Content digest synchronization query and answer.
 * Carries store digest and summary list of custody message IDs for delta pull.
 */
public record DigestSyncPayload(
        String digest,
        List<String> heldIds) {

    @JsonCreator
    public DigestSyncPayload(
            @JsonProperty("digest") String digest,
            @JsonProperty("heldIds") List<String> heldIds) {
        this.digest = digest != null ? digest : "";
        this.heldIds = heldIds != null ? heldIds : Collections.emptyList();
    }
}

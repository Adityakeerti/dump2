package com.citysense.mesh.protocol;

/**
 * Layer 3 — Delivery acknowledgment receipt.
 */
public record ReceiptPayload(
        String ackMessageId,
        Long deliveredAt) {

    public ReceiptPayload {
        ackMessageId = ackMessageId != null ? ackMessageId : "";
        deliveredAt = deliveredAt != null ? deliveredAt : System.currentTimeMillis();
    }
}

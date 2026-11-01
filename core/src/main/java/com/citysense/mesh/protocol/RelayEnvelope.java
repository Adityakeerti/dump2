package com.citysense.mesh.protocol;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Layer 2 — The cleartext routing envelope.
 * What {@link WireEnvelope#getSigned()} decodes to.
 * Contains metadata needed by intermediate store-and-forward carriers without exposing
 * encrypted payload details.
 */
public class RelayEnvelope {

    private final String type;
    private final String id;
    private final String senderId;
    private final long sentAt;
    private final String recipientId;
    private final String group;
    private final String payload;

    @JsonCreator
    public RelayEnvelope(
            @JsonProperty("type") String type,
            @JsonProperty("id") String id,
            @JsonProperty("senderId") String senderId,
            @JsonProperty("sentAt") Long sentAt,
            @JsonProperty("recipientId") String recipientId,
            @JsonProperty("group") String group,
            @JsonProperty("payload") String payload) {
        this.type = type != null ? type : FrameType.CHAT;
        this.id = id != null ? id : "";
        this.senderId = senderId != null ? senderId : "";
        this.sentAt = sentAt != null ? sentAt : System.currentTimeMillis();
        this.recipientId = recipientId;
        this.group = group;
        this.payload = payload != null ? payload : "";
    }

    public boolean isBroadcast() {
        return recipientId == null || recipientId.isBlank();
    }

    public boolean isCustodial() {
        return FrameType.isCustodial(type);
    }

    public String getType() {
        return type;
    }

    public String getId() {
        return id;
    }

    public String getSenderId() {
        return senderId;
    }

    public long getSentAt() {
        return sentAt;
    }

    public String getRecipientId() {
        return recipientId;
    }

    public String getGroup() {
        return group;
    }

    public String getPayload() {
        return payload;
    }

    @Override
    public String toString() {
        return "RelayEnvelope{" +
                "type='" + type + '\'' +
                ", id='" + id + '\'' +
                ", senderId='" + senderId + '\'' +
                ", sentAt=" + sentAt +
                ", recipientId='" + recipientId + '\'' +
                ", group='" + group + '\'' +
                '}';
    }
}

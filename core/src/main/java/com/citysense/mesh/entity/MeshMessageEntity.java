package com.citysense.mesh.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "mesh_messages")
public class MeshMessageEntity {

    @Id
    @Column(name = "id", length = 64, nullable = false)
    private String id;

    @Column(name = "type", length = 32, nullable = false)
    private String type;

    @Column(name = "sender_id", length = 64, nullable = false)
    private String senderId;

    @Column(name = "recipient_id", length = 64)
    private String recipientId;

    @Column(name = "group_id", length = 64)
    private String groupId;

    @Column(name = "payload_json", nullable = false, columnDefinition = "TEXT")
    private String payloadJson;

    @Column(name = "wire_signature", length = 128, nullable = false)
    private String wireSignature;

    @Column(name = "hops", nullable = false)
    private int hops;

    @Column(name = "ttl", nullable = false)
    private int ttl;

    @Column(name = "is_relayed", nullable = false)
    private boolean isRelayed;

    @Column(name = "sent_at", nullable = false)
    private Instant sentAt;

    @Column(name = "received_at", nullable = false)
    private Instant receivedAt;

    public MeshMessageEntity() {}

    public MeshMessageEntity(
            String id,
            String type,
            String senderId,
            String recipientId,
            String groupId,
            String payloadJson,
            String wireSignature,
            int hops,
            int ttl,
            boolean isRelayed,
            Instant sentAt,
            Instant receivedAt) {
        this.id = id;
        this.type = type;
        this.senderId = senderId;
        this.recipientId = recipientId;
        this.groupId = groupId;
        this.payloadJson = payloadJson;
        this.wireSignature = wireSignature;
        this.hops = hops;
        this.ttl = ttl;
        this.isRelayed = isRelayed;
        this.sentAt = sentAt != null ? sentAt : Instant.now();
        this.receivedAt = receivedAt != null ? receivedAt : Instant.now();
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getSenderId() {
        return senderId;
    }

    public void setSenderId(String senderId) {
        this.senderId = senderId;
    }

    public String getRecipientId() {
        return recipientId;
    }

    public void setRecipientId(String recipientId) {
        this.recipientId = recipientId;
    }

    public String getGroupId() {
        return groupId;
    }

    public void setGroupId(String groupId) {
        this.groupId = groupId;
    }

    public String getPayloadJson() {
        return payloadJson;
    }

    public void setPayloadJson(String payloadJson) {
        this.payloadJson = payloadJson;
    }

    public String getWireSignature() {
        return wireSignature;
    }

    public void setWireSignature(String wireSignature) {
        this.wireSignature = wireSignature;
    }

    public int getHops() {
        return hops;
    }

    public void setHops(int hops) {
        this.hops = hops;
    }

    public int getTtl() {
        return ttl;
    }

    public void setTtl(int ttl) {
        this.ttl = ttl;
    }

    public boolean isRelayed() {
        return isRelayed;
    }

    public void setRelayed(boolean relayed) {
        isRelayed = relayed;
    }

    public Instant getSentAt() {
        return sentAt;
    }

    public void setSentAt(Instant sentAt) {
        this.sentAt = sentAt;
    }

    public Instant getReceivedAt() {
        return receivedAt;
    }

    public void setReceivedAt(Instant receivedAt) {
        this.receivedAt = receivedAt;
    }
}

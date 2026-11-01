package com.citysense.mesh.service;

import com.citysense.mesh.crypto.MeshCrypto;
import com.citysense.mesh.custody.CustodyStore;
import com.citysense.mesh.custody.SeenSet;
import com.citysense.mesh.entity.MeshMessageEntity;
import com.citysense.mesh.entity.MeshPeerEntity;
import com.citysense.mesh.protocol.ChatPayload;
import com.citysense.mesh.protocol.FieldReportPayload;
import com.citysense.mesh.protocol.FrameType;
import com.citysense.mesh.protocol.ProfilePayload;
import com.citysense.mesh.protocol.ReceiptPayload;
import com.citysense.mesh.protocol.RelayEnvelope;
import com.citysense.mesh.protocol.SosPayload;
import com.citysense.mesh.protocol.WireCodec;
import com.citysense.mesh.protocol.WireEnvelope;
import com.citysense.mesh.repository.MeshMessageRepository;
import com.citysense.mesh.repository.MeshPeerRepository;
import com.citysense.mesh.transport.MeshTransport;
import com.citysense.mesh.transport.UdpMeshTransport;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Core Mesh Node Service implementing Knit's store-and-forward epidemic mesh routing engine.
 * Completely independent of the internet: runs over offline UDP local broadcasts, ad-hoc wireless,
 * or loopback peer channels.
 */
@Service
public class MeshNodeService {

    private static final Logger log = LoggerFactory.getLogger(MeshNodeService.class);

    private final String localNodeId = "citysense-hq-01";
    private final String localDisplayName = "CitySense Command HQ";
    private final String localRole = "HQ";
    private final String networkKey = MeshCrypto.DEFAULT_NETWORK_KEY;

    private final SeenSet seenSet = new SeenSet();
    private final CustodyStore custodyStore;
    private final MeshBridgeService bridgeService;
    private final MeshMessageRepository messageRepo;
    private final MeshPeerRepository peerRepo;
    private MeshTransport meshTransport;

    public MeshNodeService(
            CustodyStore custodyStore,
            MeshBridgeService bridgeService,
            MeshMessageRepository messageRepo,
            MeshPeerRepository peerRepo) {
        this.custodyStore = custodyStore;
        this.bridgeService = bridgeService;
        this.messageRepo = messageRepo;
        this.peerRepo = peerRepo;
        this.meshTransport = new UdpMeshTransport();
    }

    /**
     * Package-private setter for unit testing with custom or LoopbackMeshTransport.
     */
    public void setMeshTransport(MeshTransport transport) {
        if (this.meshTransport != null && this.meshTransport.isRunning()) {
            this.meshTransport.stop();
        }
        this.meshTransport = transport;
        this.meshTransport.registerInboundListener(this::handleInbound);
    }

    @PostConstruct
    public void start() {
        meshTransport.registerInboundListener(this::handleInbound);
        meshTransport.start();
        log.info("📡 MeshNodeService active: NodeId={}, Role={}, TransportRunning={}",
                localNodeId, localRole, meshTransport.isRunning());
    }

    @PreDestroy
    public void stop() {
        if (meshTransport != null) {
            meshTransport.stop();
        }
    }

    /**
     * Inbound packet intake pipeline according to Knit's verified routing specification:
     * 1. Drop if null or expired (ttl <= 0)
     * 2. Decode signed RelayEnvelope
     * 3. Deduplicate via SeenSet: drop if already seen
     * 4. Verify cryptographic signature
     * 5. Record peer sighting / presence
     * 6. Put into store-and-forward custody
     * 7. Persist to message repository
     * 8. Relay onward if eligible (relay=true && ttl > 1)
     * 9. Deliver locally to platform bridge
     */
    public void handleInbound(WireEnvelope wire) {
        if (wire == null || wire.isExpired()) {
            log.debug("Dropped expired or null wire frame");
            return;
        }

        RelayEnvelope relay;
        try {
            relay = WireCodec.decodeRelay(wire.getSigned());
        } catch (Exception e) {
            log.warn("Corrupt signed payload inside wire envelope: {}", e.getMessage());
            return;
        }

        // Deduplication (prevents broadcast storms)
        if (!seenSet.markIfNew(relay.getId())) {
            log.debug("Dropped duplicate mesh frame {}", relay.getId());
            return;
        }

        // Cryptographic verification
        if (!MeshCrypto.verify(wire.getSigned(), wire.getSig(), networkKey)) {
            log.warn("Untrusted signature for mesh frame {}. Dropping packet.", relay.getId());
            return;
        }

        // Update peer presence
        updatePeer(relay.getSenderId(), wire.getHops());

        // Custody Store & Forward
        custodyStore.store(wire, relay);

        // Save entity to database
        try {
            messageRepo.save(new MeshMessageEntity(
                    relay.getId(),
                    relay.getType(),
                    relay.getSenderId(),
                    relay.getRecipientId(),
                    relay.getGroup(),
                    relay.getPayload(),
                    wire.getSig(),
                    wire.getHops(),
                    wire.getTtl(),
                    wire.isRelay(),
                    Instant.ofEpochMilli(relay.getSentAt()),
                    Instant.now()
            ));
        } catch (Exception dbEx) {
            log.warn("Could not persist mesh message to DB: {}", dbEx.getMessage());
        }

        // Forwarding / Relay step: re-broadcast with decremented TTL and incremented hops
        if (wire.isRelay() && wire.getTtl() > 1) {
            WireEnvelope onward = wire.relayed();
            meshTransport.send(onward);
        }

        // Deliver to CitySense Bridge
        bridgeService.processInbound(relay);
    }

    /**
     * Originates and broadcasts an offline chat message over the mesh.
     */
    public WireEnvelope originateChat(ChatPayload chat, String recipientId, String group) {
        String msgId = "m-" + UUID.randomUUID().toString().substring(0, 8);
        String payloadJson = WireCodec.encodePayload(chat);

        RelayEnvelope relay = new RelayEnvelope(
                FrameType.CHAT,
                msgId,
                localNodeId,
                System.currentTimeMillis(),
                recipientId,
                group,
                payloadJson
        );

        return sealAndTransmit(relay, true);
    }

    /**
     * Originates an offline Emergency SOS distress beacon.
     */
    public WireEnvelope originateSos(SosPayload sos) {
        String sosId = "sos-" + UUID.randomUUID().toString().substring(0, 8);
        String payloadJson = WireCodec.encodePayload(sos);

        RelayEnvelope relay = new RelayEnvelope(
                FrameType.SOS,
                sosId,
                localNodeId,
                System.currentTimeMillis(),
                null, // Broadcast to all nearby nodes
                null,
                payloadJson
        );

        return sealAndTransmit(relay, true);
    }

    /**
     * Originates an offline Field Report (flood, crash, hazard).
     */
    public WireEnvelope originateFieldReport(FieldReportPayload report) {
        String repId = "rep-" + UUID.randomUUID().toString().substring(0, 8);
        String payloadJson = WireCodec.encodePayload(report);

        RelayEnvelope relay = new RelayEnvelope(
                FrameType.FIELD_REPORT,
                repId,
                localNodeId,
                System.currentTimeMillis(),
                null,
                null,
                payloadJson
        );

        return sealAndTransmit(relay, true);
    }

    /**
     * Originates a delivery receipt for a confirmed message ID.
     */
    public WireEnvelope originateReceipt(String ackId, String recipientId) {
        ReceiptPayload receipt = new ReceiptPayload(ackId, System.currentTimeMillis());
        String recId = "rcpt-" + UUID.randomUUID().toString().substring(0, 8);
        String payloadJson = WireCodec.encodePayload(receipt);

        RelayEnvelope relay = new RelayEnvelope(
                FrameType.RECEIPT,
                recId,
                localNodeId,
                System.currentTimeMillis(),
                recipientId,
                null,
                payloadJson
        );

        return sealAndTransmit(relay, false); // Receipts are point-to-point, non-flooding
    }

    /**
     * Broadcasts node presence profile advertisement.
     */
    public WireEnvelope originateProfile() {
        ProfilePayload profile = new ProfilePayload(localNodeId, localDisplayName, localRole, "GATEWAY_CORRELATION", 1);
        String profId = "prof-" + localNodeId;
        String payloadJson = WireCodec.encodePayload(profile);

        RelayEnvelope relay = new RelayEnvelope(
                FrameType.PROFILE,
                profId,
                localNodeId,
                System.currentTimeMillis(),
                null,
                null,
                payloadJson
        );

        return sealAndTransmit(relay, true);
    }

    private WireEnvelope sealAndTransmit(RelayEnvelope relay, boolean relayFlag) {
        String signed = WireCodec.encodeRelay(relay);
        String sig = MeshCrypto.sign(signed, networkKey);

        WireEnvelope wire = new WireEnvelope(
                WireEnvelope.DEFAULT_TTL,
                0, // 0 hops at origination
                relayFlag,
                sig,
                signed
        );

        // Mark in SeenSet so we don't reprocess our own transmission
        seenSet.markIfNew(relay.getId());

        // Put in local custody
        custodyStore.store(wire, relay);

        // Broadcast out onto transport
        meshTransport.send(wire);

        return wire;
    }

    /**
     * Returns list of wire envelopes that this node holds which the peer does not have.
     */
    public List<WireEnvelope> syncMissingForPeer(List<String> peerHeldIds) {
        return custodyStore.getMissingEnvelopes(peerHeldIds);
    }

    public String getLocalDigest() {
        return custodyStore.computeDigest();
    }

    public List<RelayEnvelope> getAllCustodyRelays() {
        return custodyStore.getAllRelays();
    }

    public List<MeshPeerEntity> getDiscoveredPeers() {
        return peerRepo.findAllByOrderByLastSeenAtDesc();
    }

    public String getLocalNodeId() {
        return localNodeId;
    }

    public String getLocalRole() {
        return localRole;
    }

    public SeenSet getSeenSet() {
        return seenSet;
    }

    public CustodyStore getCustodyStore() {
        return custodyStore;
    }

    private void updatePeer(String senderId, int hops) {
        if (senderId == null || senderId.isBlank() || senderId.equals(localNodeId)) {
            return;
        }

        try {
            peerRepo.findById(senderId).ifPresentOrElse(
                    peer -> {
                        peer.setLastSeenAt(Instant.now());
                        peer.setHops(hops);
                        peerRepo.save(peer);
                    },
                    () -> {
                        String derivedRole = inferRole(senderId);
                        peerRepo.save(new MeshPeerEntity(
                                senderId,
                                "Peer-" + senderId,
                                derivedRole,
                                hops,
                                "OFFLINE_P2P",
                                Instant.now()
                        ));
                    }
            );
        } catch (Exception ex) {
            log.debug("Peer persistence skipped: {}", ex.getMessage());
        }
    }

    private String inferRole(String senderId) {
        String lower = senderId.toLowerCase();
        if (lower.contains("ambul")) return "AMBULANCE";
        if (lower.contains("police") || lower.contains("cop")) return "POLICE";
        if (lower.contains("crew") || lower.contains("worker")) return "CREW";
        if (lower.contains("fire") || lower.contains("hazmat")) return "FIRE_HAZMAT";
        return "CITIZEN";
    }
}

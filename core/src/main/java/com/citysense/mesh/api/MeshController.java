package com.citysense.mesh.api;

import com.citysense.mesh.custody.CustodyStore;
import com.citysense.mesh.entity.MeshMessageEntity;
import com.citysense.mesh.entity.MeshPeerEntity;
import com.citysense.mesh.protocol.ChatPayload;
import com.citysense.mesh.protocol.FieldReportPayload;
import com.citysense.mesh.protocol.SosPayload;
import com.citysense.mesh.protocol.WireCodec;
import com.citysense.mesh.protocol.WireEnvelope;
import com.citysense.mesh.repository.MeshMessageRepository;
import com.citysense.mesh.service.MeshNodeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST API for the Offline Mesh Messaging Service.
 * Provides controls for mobile apps, operations dashboards, and simulation scripts
 * to interact with the zero-internet mesh network.
 */
@RestController
@RequestMapping("/api/mesh")
@Tag(name = "Offline Mesh Messaging", description = "Knit-compatible zero-internet store-and-forward mesh operations")
public class MeshController {

    private final MeshNodeService meshNodeService;
    private final CustodyStore custodyStore;
    private final MeshMessageRepository messageRepo;

    public MeshController(
            MeshNodeService meshNodeService,
            CustodyStore custodyStore,
            MeshMessageRepository messageRepo) {
        this.meshNodeService = meshNodeService;
        this.custodyStore = custodyStore;
        this.messageRepo = messageRepo;
    }

    public record BroadcastRequest(
            String body,
            String senderName,
            String channel,
            String urgency,
            Double latitude,
            Double longitude) {}

    public record DmRequest(
            String recipientId,
            String body,
            String senderName,
            String urgency) {}

    public record SosRequest(
            String victimName,
            String emergencyType,
            Double latitude,
            Double longitude,
            Integer urgencyScore,
            Integer injuriesCount,
            String medicalNeeds,
            String details) {}

    public record FieldReportRequest(
            String reportType,
            Double latitude,
            Double longitude,
            Integer severity,
            String description,
            String reporterRole) {}

    public record SyncRequest(
            String peerNodeId,
            List<String> peerHeldIds) {}

    @PostMapping("/broadcast")
    @Operation(summary = "Broadcast a message over the offline mesh to all nearby nodes")
    public ResponseEntity<Map<String, Object>> broadcast(@RequestBody BroadcastRequest req) {
        ChatPayload chat = new ChatPayload(
                req.body(),
                req.senderName(),
                req.channel(),
                req.urgency(),
                req.latitude(),
                req.longitude()
        );
        WireEnvelope wire = meshNodeService.originateChat(chat, null, null);
        return ResponseEntity.ok(Map.of(
                "status", "BROADCASTED",
                "envelope", wire,
                "localDigest", meshNodeService.getLocalDigest()
        ));
    }

    @PostMapping("/dm")
    @Operation(summary = "Send a point-to-point direct message over the offline mesh")
    public ResponseEntity<Map<String, Object>> sendDm(@RequestBody DmRequest req) {
        ChatPayload chat = new ChatPayload(
                req.body(),
                req.senderName(),
                "DIRECT_MESSAGE",
                req.urgency(),
                null,
                null
        );
        WireEnvelope wire = meshNodeService.originateChat(chat, req.recipientId(), null);
        return ResponseEntity.ok(Map.of(
                "status", "DISPATCHED",
                "recipientId", req.recipientId(),
                "envelope", wire
        ));
    }

    @PostMapping("/sos")
    @Operation(summary = "Trigger a critical offline emergency distress beacon (SOS)")
    public ResponseEntity<Map<String, Object>> triggerSos(@RequestBody SosRequest req) {
        SosPayload sos = new SosPayload(
                req.victimName(),
                req.emergencyType(),
                req.latitude(),
                req.longitude(),
                req.urgencyScore(),
                req.injuriesCount(),
                req.medicalNeeds(),
                req.details()
        );
        WireEnvelope wire = meshNodeService.originateSos(sos);
        return ResponseEntity.ok(Map.of(
                "status", "SOS_DISPATCHED",
                "emergencyType", sos.emergencyType(),
                "urgencyScore", sos.urgencyScore(),
                "envelope", wire
        ));
    }

    @PostMapping("/field-report")
    @Operation(summary = "Submit an offline civic / hazard field report")
    public ResponseEntity<Map<String, Object>> submitFieldReport(@RequestBody FieldReportRequest req) {
        FieldReportPayload report = new FieldReportPayload(
                req.reportType(),
                req.latitude(),
                req.longitude(),
                req.severity(),
                req.description(),
                req.reporterRole()
        );
        WireEnvelope wire = meshNodeService.originateFieldReport(report);
        return ResponseEntity.ok(Map.of(
                "status", "REPORT_DISPATCHED",
                "reportType", report.reportType(),
                "severity", report.severity(),
                "envelope", wire
        ));
    }

    @GetMapping("/messages")
    @Operation(summary = "List received mesh messages and custody backlog")
    public ResponseEntity<List<MeshMessageEntity>> listMessages(@RequestParam(required = false) String type) {
        List<MeshMessageEntity> list = (type != null && !type.isBlank())
                ? messageRepo.findByTypeOrderByReceivedAtDesc(type)
                : messageRepo.findTop50ByOrderByReceivedAtDesc();
        return ResponseEntity.ok(list);
    }

    @GetMapping("/peers")
    @Operation(summary = "List discovered local offline mesh peers and hop distances")
    public ResponseEntity<List<MeshPeerEntity>> listPeers() {
        return ResponseEntity.ok(meshNodeService.getDiscoveredPeers());
    }

    @GetMapping("/digest")
    @Operation(summary = "Get the local StoreDigest of active custody frames")
    public ResponseEntity<Map<String, Object>> getDigest() {
        return ResponseEntity.ok(Map.of(
                "nodeId", meshNodeService.getLocalNodeId(),
                "role", meshNodeService.getLocalRole(),
                "digest", meshNodeService.getLocalDigest(),
                "custodyCount", custodyStore.size()
        ));
    }

    @PostMapping("/sync")
    @Operation(summary = "Exchange store digests with a peer to pull missing delta messages")
    public ResponseEntity<Map<String, Object>> syncPeers(@RequestBody SyncRequest req) {
        List<WireEnvelope> missingEnvelopes = meshNodeService.syncMissingForPeer(req.peerHeldIds());
        return ResponseEntity.ok(Map.of(
                "localDigest", meshNodeService.getLocalDigest(),
                "missingCount", missingEnvelopes.size(),
                "envelopes", missingEnvelopes
        ));
    }

    @PostMapping("/simulate-inbound")
    @Operation(summary = "Inject or simulate an inbound wire packet (for demos and automated scenarios)")
    public ResponseEntity<Map<String, Object>> simulateInbound(@RequestBody WireEnvelope envelope) {
        meshNodeService.handleInbound(envelope);
        return ResponseEntity.ok(Map.of(
                "status", "PROCESSED",
                "ttl", envelope.getTtl(),
                "hops", envelope.getHops(),
                "localDigest", meshNodeService.getLocalDigest()
        ));
    }
}

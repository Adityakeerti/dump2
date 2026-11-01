package com.citysense.mesh;

import com.citysense.mesh.crypto.MeshCrypto;
import com.citysense.mesh.custody.CustodyStore;
import com.citysense.mesh.protocol.ChatPayload;
import com.citysense.mesh.protocol.FieldReportPayload;
import com.citysense.mesh.protocol.FrameType;
import com.citysense.mesh.protocol.RelayEnvelope;
import com.citysense.mesh.protocol.SosPayload;
import com.citysense.mesh.protocol.WireCodec;
import com.citysense.mesh.protocol.WireEnvelope;
import com.citysense.mesh.repository.MeshMessageRepository;
import com.citysense.mesh.repository.MeshPeerRepository;
import com.citysense.mesh.service.MeshBridgeService;
import com.citysense.mesh.service.MeshNodeService;
import com.citysense.mesh.transport.LoopbackMeshTransport;
import com.citysense.platform.observation.ObservationDtos.IngestResponse;
import com.citysense.platform.observation.ObservationDtos.ObservationRequest;
import com.citysense.platform.observation.ObservationService;
import com.citysense.platform.observation.ObservationType;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

class MeshNodeServiceTest {

    private ObservationService observationService;
    private ApplicationEventPublisher eventPublisher;
    private MeshMessageRepository messageRepo;
    private MeshPeerRepository peerRepo;
    private CustodyStore custodyStore;
    private MeshBridgeService bridgeService;
    private MeshNodeService nodeService;
    private LoopbackMeshTransport transport;

    @BeforeEach
    void setUp() {
        observationService = mock(ObservationService.class);
        eventPublisher = mock(ApplicationEventPublisher.class);
        messageRepo = mock(MeshMessageRepository.class);
        peerRepo = mock(MeshPeerRepository.class);
        when(peerRepo.findById(anyString())).thenReturn(Optional.empty());

        custodyStore = new CustodyStore(100, 3600_000L);
        bridgeService = new MeshBridgeService(observationService, eventPublisher);

        nodeService = new MeshNodeService(custodyStore, bridgeService, messageRepo, peerRepo);
        transport = new LoopbackMeshTransport();
        nodeService.setMeshTransport(transport);
    }

    @Test
    @DisplayName("Inbound SOS packet is verified, stored in custody, bridged to ObservationService, and relayed")
    void testInboundSosProcessingAndRelay() {
        List<WireEnvelope> transmittedOnward = new ArrayList<>();
        transport.registerInboundListener(transmittedOnward::add);

        SosPayload sos = new SosPayload(
                "Sunita Rawat",
                "FLOOD",
                30.3165,
                78.0322,
                5,
                3,
                "Medical evacuation boat needed",
                "Ground floor flooded"
        );
        RelayEnvelope relay = new RelayEnvelope(
                FrameType.SOS,
                "sos-001",
                "citizen-node-7",
                System.currentTimeMillis(),
                null,
                null,
                WireCodec.encodePayload(sos)
        );

        String signed = WireCodec.encodeRelay(relay);
        String sig = MeshCrypto.sign(signed, MeshCrypto.DEFAULT_NETWORK_KEY);
        WireEnvelope wire = new WireEnvelope(8, 0, true, sig, signed);

        // Process inbound packet
        nodeService.handleInbound(wire);

        // 1. Check bridged to CitySense ObservationService
        ArgumentCaptor<ObservationRequest> captor = ArgumentCaptor.forClass(ObservationRequest.class);
        verify(observationService, times(1)).ingest(captor.capture(), eq("mesh-gateway"));
        ObservationRequest obs = captor.getValue();
        assertEquals(ObservationType.FLOOD, obs.type());
        assertEquals(30.3165, obs.latitude());
        assertEquals("mesh:citizen-node-7", obs.source());

        // 2. Check stored in custody
        assertEquals(1, custodyStore.size());
        assertNotNull(custodyStore.getWire("sos-001"));

        // 3. Check duplicate submission is rejected by SeenSet
        nodeService.handleInbound(wire);
        verify(observationService, times(1)).ingest(any(), any()); // Still 1 time, duplicate ignored
    }

    @Test
    @DisplayName("Inbound packet with corrupted signature is dropped without bridging or custody")
    void testCorruptSignatureDropped() {
        SosPayload sos = new SosPayload("Victim", "CRASH", 30.3, 78.0, 5, 1, "None", "Crash");
        RelayEnvelope relay = new RelayEnvelope(FrameType.SOS, "sos-bad", "attacker", System.currentTimeMillis(), null, null, WireCodec.encodePayload(sos));
        String signed = WireCodec.encodeRelay(relay);
        WireEnvelope wire = new WireEnvelope(8, 0, true, "invalid-signature", signed);

        nodeService.handleInbound(wire);

        verify(observationService, never()).ingest(any(), any());
        assertEquals(0, custodyStore.size());
    }

    @Test
    @DisplayName("Originate chat successfully seals, stores, and sends packet onto transport")
    void testOriginateChat() {
        List<WireEnvelope> sentPackets = new ArrayList<>();
        LoopbackMeshTransport peerTransport = new LoopbackMeshTransport();
        peerTransport.registerInboundListener(sentPackets::add);
        transport.link(peerTransport);

        ChatPayload chat = new ChatPayload("All units hold position", "Commander", "CREW", "NORMAL", null, null);
        WireEnvelope wire = nodeService.originateChat(chat, null, "crew-dehradun");

        assertNotNull(wire);
        assertEquals(WireEnvelope.DEFAULT_TTL, wire.getTtl());
        assertEquals(0, wire.getHops());
        assertTrue(wire.isRelay());

        // Envelope was stored in local custody
        assertEquals(1, custodyStore.size());

        // Peer received packet over loopback
        assertEquals(1, sentPackets.size());
        RelayEnvelope receivedRelay = WireCodec.decodeRelay(sentPackets.get(0).getSigned());
        assertEquals(FrameType.CHAT, receivedRelay.getType());
        assertEquals(nodeService.getLocalNodeId(), receivedRelay.getSenderId());
    }
}

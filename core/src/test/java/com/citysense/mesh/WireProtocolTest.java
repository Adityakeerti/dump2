package com.citysense.mesh;

import com.citysense.mesh.crypto.MeshCrypto;
import com.citysense.mesh.protocol.ChatPayload;
import com.citysense.mesh.protocol.FieldReportPayload;
import com.citysense.mesh.protocol.FrameType;
import com.citysense.mesh.protocol.RelayEnvelope;
import com.citysense.mesh.protocol.SosPayload;
import com.citysense.mesh.protocol.WireCodec;
import com.citysense.mesh.protocol.WireEnvelope;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class WireProtocolTest {

    @Test
    @DisplayName("WireEnvelope relay preserves signed bytes byte-for-byte while decrementing TTL")
    void testWireEnvelopeRelayed() {
        String signedData = "{\"type\":\"chat\",\"id\":\"m-001\",\"senderId\":\"alice\"}";
        String sig = MeshCrypto.sign(signedData, "test-key");

        WireEnvelope original = new WireEnvelope(8, 0, true, sig, signedData);
        assertEquals(8, original.getTtl());
        assertEquals(0, original.getHops());
        assertTrue(original.isRelay());

        WireEnvelope hop1 = original.relayed();
        assertEquals(7, hop1.getTtl());
        assertEquals(1, hop1.getHops());
        assertEquals(original.getSigned(), hop1.getSigned(), "Signed payload must survive byte-for-byte");
        assertEquals(original.getSig(), hop1.getSig(), "Signature must remain identical");

        WireEnvelope hop2 = hop1.relayed();
        assertEquals(6, hop2.getTtl());
        assertEquals(2, hop2.getHops());
    }

    @Test
    @DisplayName("TTL bounds and expiration work correctly")
    void testTtlBounds() {
        WireEnvelope expired = new WireEnvelope(0, 5, true, "sig", "data");
        assertTrue(expired.isExpired());

        WireEnvelope zeroHop = expired.relayed();
        assertEquals(0, zeroHop.getTtl());
        assertTrue(zeroHop.isExpired());
    }

    @Test
    @DisplayName("WireCodec serialization roundtrip preserves all envelope fields")
    void testWireCodecRoundtrip() {
        ChatPayload chat = new ChatPayload(
                "Need emergency medical kit near clock tower",
                "Dr. Sharma",
                "EMERGENCY_CREW",
                "HIGH",
                30.3165,
                78.0322
        );
        String payloadJson = WireCodec.encodePayload(chat);

        RelayEnvelope relay = new RelayEnvelope(
                FrameType.CHAT,
                "msg-101",
                "node-doctor-1",
                System.currentTimeMillis(),
                null,
                "crew-medical",
                payloadJson
        );

        String signed = WireCodec.encodeRelay(relay);
        String sig = MeshCrypto.sign(signed, MeshCrypto.DEFAULT_NETWORK_KEY);
        WireEnvelope wire = new WireEnvelope(8, 0, true, sig, signed);

        // Encode to JSON string
        String json = WireCodec.encodeWire(wire);
        assertNotNull(json);

        // Decode from JSON
        WireEnvelope decodedWire = WireCodec.decodeWire(json);
        assertEquals(wire.getTtl(), decodedWire.getTtl());
        assertEquals(wire.getHops(), decodedWire.getHops());
        assertEquals(wire.getSig(), decodedWire.getSig());
        assertEquals(wire.getSigned(), decodedWire.getSigned());

        // Decode relay and payload
        RelayEnvelope decodedRelay = WireCodec.decodeRelay(decodedWire.getSigned());
        assertEquals("msg-101", decodedRelay.getId());
        assertEquals("node-doctor-1", decodedRelay.getSenderId());
        assertTrue(decodedRelay.isBroadcast());

        ChatPayload decodedChat = WireCodec.decodePayload(decodedRelay.getPayload(), ChatPayload.class);
        assertEquals("Dr. Sharma", decodedChat.senderName());
        assertEquals(30.3165, decodedChat.latitude());
    }

    @Test
    @DisplayName("MeshCrypto HMAC verification fails if signed bytes are tampered")
    void testCryptoTamperDetection() {
        String originalData = "{\"id\":\"sos-1\",\"victim\":\"John\",\"urgency\":5}";
        String key = "secure-network-key";
        String sig = MeshCrypto.sign(originalData, key);

        assertTrue(MeshCrypto.verify(originalData, sig, key), "Valid signature must verify");

        // Tamper with data
        String tamperedData = "{\"id\":\"sos-1\",\"victim\":\"John\",\"urgency\":1}";
        assertFalse(MeshCrypto.verify(tamperedData, sig, key), "Tampered data must fail verification");

        // Wrong key
        assertFalse(MeshCrypto.verify(originalData, sig, "wrong-key"), "Wrong key must fail verification");
    }

    @Test
    @DisplayName("SOS and FieldReport payloads construct and serialize cleanly")
    void testSosAndFieldReportPayloads() {
        SosPayload sos = new SosPayload(
                "Aarav Verma",
                "FLOOD",
                30.3245,
                78.0412,
                5,
                2,
                "Inflatable boat and dry rations",
                "Water level rising rapidly inside underpass"
        );
        String sosJson = WireCodec.encodePayload(sos);
        SosPayload decodedSos = WireCodec.decodePayload(sosJson, SosPayload.class);
        assertEquals("Aarav Verma", decodedSos.victimName());
        assertEquals("FLOOD", decodedSos.emergencyType());
        assertEquals(5, decodedSos.urgencyScore());

        FieldReportPayload report = new FieldReportPayload(
                "ROAD_BLOCK",
                30.3180,
                78.0400,
                4,
                "Uprooted pine tree blocking Rajpur Road",
                "CREW"
        );
        String repJson = WireCodec.encodePayload(report);
        FieldReportPayload decodedReport = WireCodec.decodePayload(repJson, FieldReportPayload.class);
        assertEquals("ROAD_BLOCK", decodedReport.reportType());
        assertEquals(4, decodedReport.severity());
    }
}

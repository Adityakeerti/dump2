package com.citysense.mesh;

import com.citysense.mesh.custody.CustodyStore;
import com.citysense.mesh.custody.SeenSet;
import com.citysense.mesh.custody.StoreDigest;
import com.citysense.mesh.protocol.FrameType;
import com.citysense.mesh.protocol.RelayEnvelope;
import com.citysense.mesh.protocol.WireEnvelope;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CustodyAndDigestTest {

    @Test
    @DisplayName("SeenSet deduplicates repeat packets and terminates broadcast loops")
    void testSeenSetDeduplication() {
        SeenSet seenSet = new SeenSet(100);

        assertTrue(seenSet.markIfNew("m-001"), "First occurrence must be new");
        assertFalse(seenSet.markIfNew("m-001"), "Duplicate packet must be rejected");
        assertTrue(seenSet.contains("m-001"));

        assertTrue(seenSet.markIfNew("m-002"));
        assertEquals(2, seenSet.size());
    }

    @Test
    @DisplayName("StoreDigest is deterministic, order-independent, and changes on delta")
    void testStoreDigestProperties() {
        String digest1 = StoreDigest.compute(List.of("id-A", "id-B", "id-C"));
        String digest2 = StoreDigest.compute(List.of("id-C", "id-A", "id-B"));

        assertEquals(digest1, digest2, "Digest must be order-independent (commutative XOR)");

        String digest3 = StoreDigest.compute(List.of("id-A", "id-B"));
        assertNotEquals(digest1, digest3, "Digest must change when member set differs");

        String emptyDigest = StoreDigest.compute(List.of());
        assertEquals("00000000000000000000000000000000", emptyDigest);
    }

    @Test
    @DisplayName("CustodyStore stores custodial frames and calculates missing delta sets for peers")
    void testCustodyDeltaSync() {
        CustodyStore store = new CustodyStore(100, 3600_000L);

        RelayEnvelope relayA = new RelayEnvelope(FrameType.CHAT, "msg-A", "alice", 1000L, null, null, "{}");
        WireEnvelope wireA = new WireEnvelope(8, 0, true, "sigA", "signedA");

        RelayEnvelope relayB = new RelayEnvelope(FrameType.SOS, "sos-B", "bob", 2000L, null, null, "{}");
        WireEnvelope wireB = new WireEnvelope(8, 0, true, "sigB", "signedB");

        store.store(wireA, relayA);
        store.store(wireB, relayB);

        assertEquals(2, store.size());
        assertEquals(Set.of("msg-A", "sos-B"), store.getAllIds());

        // Peer already has msg-A, asks what it is missing
        List<WireEnvelope> missingForPeer = store.getMissingEnvelopes(List.of("msg-A"));
        assertEquals(1, missingForPeer.size());
        assertEquals("signedB", missingForPeer.get(0).getSigned());

        // Peer has everything
        List<WireEnvelope> noneMissing = store.getMissingEnvelopes(List.of("msg-A", "sos-B"));
        assertTrue(noneMissing.isEmpty());
    }
}

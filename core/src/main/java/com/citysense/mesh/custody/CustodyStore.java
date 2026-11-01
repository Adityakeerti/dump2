package com.citysense.mesh.custody;

import com.citysense.mesh.protocol.RelayEnvelope;
import com.citysense.mesh.protocol.WireEnvelope;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * Thread-safe Store-and-Forward Custody Store.
 * Retains storable frames so they can be forwarded when discovering new peers or answering
 * digest delta sync queries.
 */
@Component
public class CustodyStore {

    public record CustodyItem(
            WireEnvelope wireEnvelope,
            RelayEnvelope relayEnvelope,
            long storedAtMs) {}

    private final int maxItems;
    private final long ttlRetentionMs;
    private final Map<String, CustodyItem> items = new ConcurrentHashMap<>();

    public CustodyStore() {
        this(5_000, 24 * 60 * 60 * 1000L); // 5000 items, 24h retention
    }

    public CustodyStore(int maxItems, long ttlRetentionMs) {
        this.maxItems = maxItems;
        this.ttlRetentionMs = ttlRetentionMs;
    }

    public boolean store(WireEnvelope wire, RelayEnvelope relay) {
        if (wire == null || relay == null || relay.getId() == null || relay.getId().isBlank()) {
            return false;
        }
        if (!relay.isCustodial()) {
            return false;
        }

        sweepExpired();

        if (items.size() >= maxItems && !items.containsKey(relay.getId())) {
            // Evict oldest item
            items.keySet().stream().findFirst().ifPresent(items::remove);
        }

        items.put(relay.getId(), new CustodyItem(wire, relay, System.currentTimeMillis()));
        return true;
    }

    public WireEnvelope getWire(String id) {
        CustodyItem item = items.get(id);
        return item != null ? item.wireEnvelope() : null;
    }

    public RelayEnvelope getRelay(String id) {
        CustodyItem item = items.get(id);
        return item != null ? item.relayEnvelope() : null;
    }

    public List<WireEnvelope> getAllWires() {
        sweepExpired();
        List<WireEnvelope> result = new ArrayList<>();
        for (CustodyItem item : items.values()) {
            result.add(item.wireEnvelope());
        }
        return Collections.unmodifiableList(result);
    }

    public List<RelayEnvelope> getAllRelays() {
        sweepExpired();
        List<RelayEnvelope> result = new ArrayList<>();
        for (CustodyItem item : items.values()) {
            result.add(item.relayEnvelope());
        }
        return Collections.unmodifiableList(result);
    }

    public Set<String> getAllIds() {
        sweepExpired();
        return Collections.unmodifiableSet(new HashSet<>(items.keySet()));
    }

    public String computeDigest() {
        return StoreDigest.compute(getAllIds());
    }

    public List<WireEnvelope> getMissingEnvelopes(Collection<String> peerHeldIds) {
        sweepExpired();
        Set<String> peerSet = peerHeldIds != null ? new HashSet<>(peerHeldIds) : Collections.emptySet();
        List<WireEnvelope> missing = new ArrayList<>();
        for (Map.Entry<String, CustodyItem> entry : items.entrySet()) {
            if (!peerSet.contains(entry.getKey())) {
                missing.add(entry.getValue().wireEnvelope());
            }
        }
        return missing;
    }

    public int size() {
        return items.size();
    }

    public void clear() {
        items.clear();
    }

    private void sweepExpired() {
        long now = System.currentTimeMillis();
        items.entrySet().removeIf(e -> (now - e.getValue().storedAtMs()) > ttlRetentionMs);
    }
}

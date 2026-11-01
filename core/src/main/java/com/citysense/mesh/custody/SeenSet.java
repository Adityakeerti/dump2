package com.citysense.mesh.custody;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * Bounded thread-safe set tracking seen message IDs to terminate flood loops.
 * Emulates Knit's SeenSet: packets arriving with an already-seen ID are dropped instantly.
 */
public class SeenSet {

    private final int maxCapacity;
    private final Set<String> cache;

    public SeenSet() {
        this(10_000);
    }

    public SeenSet(int maxCapacity) {
        this.maxCapacity = maxCapacity;
        // Bounded LRU LinkedHashMap wrapped in synchronized set
        Map<String, Boolean> lruMap = new LinkedHashMap<>(maxCapacity, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, Boolean> eldest) {
                return size() > maxCapacity;
            }
        };
        this.cache = Collections.synchronizedSet(Collections.newSetFromMap(lruMap));
    }

    /**
     * Atomically marks the id as seen.
     * @return true if the id is newly seen (should be processed/relayed),
     *         false if duplicate (should be dropped).
     */
    public boolean markIfNew(String id) {
        if (id == null || id.isBlank()) {
            return false;
        }
        return cache.add(id);
    }

    public boolean contains(String id) {
        return cache.contains(id);
    }

    public int size() {
        return cache.size();
    }

    public void clear() {
        cache.clear();
    }
}

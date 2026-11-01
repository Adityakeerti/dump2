package com.citysense.geo;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** Small thread-safe LRU cache with per-entry expiry; enough for a single core instance. */
final class LruCache<K, V> {

    private record Entry<V>(V value, Instant expiresAt) {}

    private final long ttlSeconds;
    private final Map<K, Entry<V>> map;

    LruCache(int maxEntries, long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
        this.map = new LinkedHashMap<>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<K, Entry<V>> eldest) {
                return size() > maxEntries;
            }
        };
    }

    synchronized Optional<V> get(K key) {
        Entry<V> e = map.get(key);
        if (e == null) {
            return Optional.empty();
        }
        if (e.expiresAt().isBefore(Instant.now())) {
            map.remove(key);
            return Optional.empty();
        }
        return Optional.of(e.value());
    }

    synchronized void put(K key, V value) {
        map.put(key, new Entry<>(value, Instant.now().plusSeconds(ttlSeconds)));
    }
}

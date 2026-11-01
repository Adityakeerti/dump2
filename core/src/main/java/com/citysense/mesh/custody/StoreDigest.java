package com.citysense.mesh.custody;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collection;
import java.util.HexFormat;

/**
 * Calculates a compact, order-independent content digest over a set of active custody frame IDs.
 * Implements Knit's XOR digest principle: two nodes with identical live stores compute the exact
 * same digest, allowing 1-step O(1) sync checks.
 */
public final class StoreDigest {

    private StoreDigest() {}

    /**
     * Computes a 128-bit XOR digest over all message IDs in the collection.
     */
    public static String compute(Collection<String> messageIds) {
        if (messageIds == null || messageIds.isEmpty()) {
            return "00000000000000000000000000000000";
        }

        byte[] accumulator = new byte[16];
        try {
            MessageDigest md = MessageDigest.getInstance("MD5"); // Fast 128-bit hash for digest accumulation
            for (String id : messageIds) {
                if (id == null || id.isBlank()) continue;
                byte[] idHash = md.digest(id.getBytes(StandardCharsets.UTF_8));
                md.reset();
                for (int i = 0; i < 16; i++) {
                    accumulator[i] ^= idHash[i];
                }
            }
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("Digest algorithm missing", e);
        }

        return HexFormat.of().formatHex(accumulator);
    }
}

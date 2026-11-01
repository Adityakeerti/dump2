package com.citysense.mesh.crypto;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Provides cryptographic origin authentication and integrity verification for mesh frames.
 * Ensures the signed bytes cannot be tampered with or modified during multi-hop relay.
 */
public final class MeshCrypto {

    private static final Logger log = LoggerFactory.getLogger(MeshCrypto.class);
    private static final String HMAC_ALGO = "HmacSHA256";
    public static final String DEFAULT_NETWORK_KEY = "citysense-offline-mesh-secure-v1-key";

    private MeshCrypto() {}

    /**
     * Signs the canonical signed string using HMAC-SHA256.
     */
    public static String sign(String signedData, String key) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGO);
            SecretKeySpec secretKey = new SecretKeySpec(
                    (key != null && !key.isBlank() ? key : DEFAULT_NETWORK_KEY).getBytes(StandardCharsets.UTF_8),
                    HMAC_ALGO
            );
            mac.init(secretKey);
            byte[] hmacBytes = mac.doFinal(signedData.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hmacBytes);
        } catch (Exception e) {
            log.error("Failed to sign mesh payload: {}", e.getMessage());
            return "";
        }
    }

    /**
     * Verifies the signature in constant time to prevent timing attacks.
     */
    public static boolean verify(String signedData, String signature, String key) {
        if (signedData == null || signature == null || signature.isBlank()) {
            return false;
        }
        String expectedSig = sign(signedData, key);
        return MessageDigest.isEqual(
                expectedSig.getBytes(StandardCharsets.UTF_8),
                signature.getBytes(StandardCharsets.UTF_8)
        );
    }

    /**
     * Computes a SHA-256 fingerprint for message IDs or payload integrity.
     */
    public static String sha256Hex(String data) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(data.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 algorithm missing", e);
        }
    }
}

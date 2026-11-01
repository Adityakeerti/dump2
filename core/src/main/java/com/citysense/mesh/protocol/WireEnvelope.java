package com.citysense.mesh.protocol;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Layer 1 — The on-radio / on-wire envelope.
 * Frozen unit that intermediate relays re-encode only to decrement TTL and increment hops.
 * {@code signed} and {@code sig} pass through byte-for-byte, preserving cryptographic integrity
 * across every hop without re-signing.
 */
public class WireEnvelope {

    public static final int DEFAULT_TTL = 8;
    public static final int MAX_TTL = 16;

    private final int ttl;
    private final int hops;
    private final boolean relay;
    private final String sig;
    private final String signed;

    @JsonCreator
    public WireEnvelope(
            @JsonProperty("ttl") Integer ttl,
            @JsonProperty("hops") Integer hops,
            @JsonProperty("relay") Boolean relay,
            @JsonProperty("sig") String sig,
            @JsonProperty("signed") String signed) {
        this.ttl = (ttl != null) ? ttl : DEFAULT_TTL;
        this.hops = (hops != null) ? hops : 0;
        this.relay = (relay != null) ? relay : true;
        this.sig = (sig != null) ? sig : "";
        this.signed = (signed != null) ? signed : "";
    }

    /**
     * Produces an onward relayed copy: decrements TTL (capped to DEFAULT_TTL) and increments hops.
     * {@code signed} and {@code sig} are passed untouched byte-for-byte.
     */
    public WireEnvelope relayed() {
        int boundedTtl = Math.min(this.ttl, DEFAULT_TTL);
        int nextTtl = Math.max(0, boundedTtl - 1);
        return new WireEnvelope(nextTtl, this.hops + 1, this.relay, this.sig, this.signed);
    }

    public boolean isExpired() {
        return this.ttl <= 0;
    }

    public int getTtl() {
        return ttl;
    }

    public int getHops() {
        return hops;
    }

    public boolean isRelay() {
        return relay;
    }

    public String getSig() {
        return sig;
    }

    public String getSigned() {
        return signed;
    }

    @Override
    public String toString() {
        return "WireEnvelope{" +
                "ttl=" + ttl +
                ", hops=" + hops +
                ", relay=" + relay +
                ", sig='" + (sig.length() > 8 ? sig.substring(0, 8) + "..." : sig) + '\'' +
                ", signedLength=" + signed.length() +
                '}';
    }
}

package com.citysense.mesh.transport;

import com.citysense.mesh.protocol.WireEnvelope;
import java.util.function.Consumer;

/**
 * Transport seam abstracting offline radio/network layers.
 * Transports can be UDP broadcast on local LAN/Wi-Fi ad-hoc, Bluetooth LE bridges, or Loopback in-memory buses.
 */
public interface MeshTransport {

    /**
     * Sends a WireEnvelope out onto the transport.
     */
    void send(WireEnvelope envelope);

    /**
     * Registers a listener callback invoked when a valid inbound WireEnvelope arrives.
     */
    void registerInboundListener(Consumer<WireEnvelope> listener);

    /**
     * Starts the transport listener.
     */
    void start();

    /**
     * Stops the transport listener.
     */
    void stop();

    /**
     * Returns whether the transport is actively listening.
     */
    boolean isRunning();
}

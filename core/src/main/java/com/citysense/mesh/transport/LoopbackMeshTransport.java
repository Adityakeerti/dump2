package com.citysense.mesh.transport;

import com.citysense.mesh.protocol.WireEnvelope;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

/**
 * In-memory loopback transport for development, deterministic testing, and multi-node simulations
 * without touching hardware sockets or requiring any network connectivity.
 */
public class LoopbackMeshTransport implements MeshTransport {

    private final List<Consumer<WireEnvelope>> listeners = new CopyOnWriteArrayList<>();
    private final List<MeshTransport> linkedPeers = new CopyOnWriteArrayList<>();
    private volatile boolean running = true;

    @Override
    public void send(WireEnvelope envelope) {
        if (!running || envelope == null) return;
        for (MeshTransport peer : linkedPeers) {
            if (peer instanceof LoopbackMeshTransport loopback) {
                loopback.deliverDirect(envelope);
            }
        }
    }

    public void deliverDirect(WireEnvelope envelope) {
        if (!running || envelope == null) return;
        for (Consumer<WireEnvelope> listener : listeners) {
            try {
                listener.accept(envelope);
            } catch (Exception ignored) {}
        }
    }

    public void link(MeshTransport peer) {
        if (peer != null && !linkedPeers.contains(peer)) {
            linkedPeers.add(peer);
        }
    }

    @Override
    public void registerInboundListener(Consumer<WireEnvelope> listener) {
        if (listener != null) {
            listeners.add(listener);
        }
    }

    @Override
    public void start() {
        this.running = true;
    }

    @Override
    public void stop() {
        this.running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}

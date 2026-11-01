package com.citysense.mesh.transport;

import com.citysense.mesh.protocol.WireCodec;
import com.citysense.mesh.protocol.WireEnvelope;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketException;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Real offline UDP broadcast and loopback transport.
 * Operates over local LAN, ad-hoc wireless, or Wi-Fi hotspot with zero internet connection required.
 */
public class UdpMeshTransport implements MeshTransport {

    private static final Logger log = LoggerFactory.getLogger(UdpMeshTransport.class);
    public static final int DEFAULT_PORT = 8988;
    private static final int BUFFER_SIZE = 65535;

    private final int port;
    private final List<Consumer<WireEnvelope>> listeners = new CopyOnWriteArrayList<>();
    private DatagramSocket socket;
    private Thread listenerThread;
    private volatile boolean running = false;

    public UdpMeshTransport() {
        this(DEFAULT_PORT);
    }

    public UdpMeshTransport(int port) {
        this.port = port;
    }

    @Override
    public synchronized void start() {
        if (running) return;

        try {
            socket = new DatagramSocket(port);
            socket.setBroadcast(true);
            running = true;

            listenerThread = new Thread(this::listenLoop, "CitySense-UdpMesh-" + port);
            listenerThread.setDaemon(true);
            listenerThread.start();
            log.info("UDP Mesh Transport actively listening on offline port {}", port);
        } catch (SocketException e) {
            log.warn("Could not bind UDP Mesh Transport to port {}: {} (Offline mesh will operate in in-memory mode)",
                    port, e.getMessage());
            running = false;
        }
    }

    private void listenLoop() {
        byte[] buffer = new byte[BUFFER_SIZE];
        while (running && socket != null && !socket.isClosed()) {
            try {
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                socket.receive(packet);

                byte[] data = new byte[packet.getLength()];
                System.arraycopy(packet.getData(), packet.getOffset(), data, 0, packet.getLength());

                try {
                    WireEnvelope envelope = WireCodec.decodeWire(data);
                    for (Consumer<WireEnvelope> listener : listeners) {
                        try {
                            listener.accept(envelope);
                        } catch (Exception ex) {
                            log.error("Error in mesh inbound listener: {}", ex.getMessage());
                        }
                    }
                } catch (Exception parseEx) {
                    log.debug("Non-wire packet received on UDP mesh port: {}", parseEx.getMessage());
                }
            } catch (IOException e) {
                if (!running) break;
                log.warn("Error receiving UDP mesh packet: {}", e.getMessage());
            }
        }
    }

    @Override
    public void send(WireEnvelope envelope) {
        if (envelope == null) return;

        byte[] payload = WireCodec.encodeWireBytes(envelope);

        try (DatagramSocket sender = new DatagramSocket()) {
            sender.setBroadcast(true);

            // 1. Broadcast to local subnet (ad-hoc Wi-Fi, LAN, or emergency hotspot)
            try {
                InetAddress broadcastAddr = InetAddress.getByName("255.255.255.255");
                DatagramPacket broadcastPacket = new DatagramPacket(payload, payload.length, broadcastAddr, port);
                sender.send(broadcastPacket);
            } catch (Exception ex) {
                log.debug("Broadcast send skipped: {}", ex.getMessage());
            }

            // 2. Loopback to local interface for co-located test nodes/agents
            try {
                InetAddress loopbackAddr = InetAddress.getByName("127.0.0.1");
                DatagramPacket loopbackPacket = new DatagramPacket(payload, payload.length, loopbackAddr, port);
                sender.send(loopbackPacket);
            } catch (Exception ex) {
                log.debug("Loopback send skipped: {}", ex.getMessage());
            }
        } catch (Exception e) {
            log.warn("Failed to transmit UDP mesh envelope: {}", e.getMessage());
        }
    }

    @Override
    public void registerInboundListener(Consumer<WireEnvelope> listener) {
        if (listener != null) {
            listeners.add(listener);
        }
    }

    @Override
    public synchronized void stop() {
        running = false;
        if (socket != null && !socket.isClosed()) {
            socket.close();
            socket = null;
        }
        if (listenerThread != null) {
            listenerThread.interrupt();
            listenerThread = null;
        }
        log.info("UDP Mesh Transport stopped.");
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    public int getPort() {
        return port;
    }
}

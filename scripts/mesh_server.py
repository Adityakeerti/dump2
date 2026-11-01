#!/usr/bin/env python3
"""
CitySense Offline Mesh HTTP & WebSocket-like Server
===================================================
Binds to 0.0.0.0 so any phone on the local Wi-Fi or mobile hotspot
can open the UI and test peer-to-peer messaging completely offline.

Usage:
  python scripts/mesh_server.py [--port 8088]
"""

import sys
import os
import json
import time
import uuid
import hmac
import socket
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

DEFAULT_HTTP_PORT = 8088
DEFAULT_UDP_PORT = 8988
DEFAULT_NETWORK_KEY = "citysense-offline-mesh-secure-v1-key"

# In-memory mesh custody & peers
messages = []
seen_ids = set()
peers = {}
lock = threading.Lock()

def sign(data_str: str, key: str = DEFAULT_NETWORK_KEY) -> str:
    key_bytes = key.encode("utf-8")
    data_bytes = data_str.encode("utf-8")
    return hmac.new(key_bytes, data_bytes, hashlib.sha256).hexdigest()

def compute_digest():
    with lock:
        if not messages:
            return "00000000000000000000000000000000"
        acc = bytearray(16)
        for m in messages:
            h = hashlib.md5(m["id"].encode("utf-8")).digest()
            for i in range(16):
                acc[i] ^= h[i]
        return acc.hex()

def send_udp_broadcast(wire_dict):
    try:
        data = json.dumps(wire_dict).encode("utf-8")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(data, ("127.0.0.1", DEFAULT_UDP_PORT))
        s.sendto(data, ("255.255.255.255", DEFAULT_UDP_PORT))
        s.close()
    except Exception:
        pass

def udp_listener_thread():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", DEFAULT_UDP_PORT))
    except Exception:
        return
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            envelope = json.loads(data.decode("utf-8"))
            signed_str = envelope.get("signed", "")
            relay = json.loads(signed_str)
            mid = relay.get("id")
            with lock:
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    msg_obj = {
                        "id": mid,
                        "type": relay.get("type", "chat"),
                        "senderId": relay.get("senderId", "peer"),
                        "recipientId": relay.get("recipientId"),
                        "groupId": relay.get("group"),
                        "payloadJson": relay.get("payload", "{}"),
                        "hops": envelope.get("hops", 0),
                        "ttl": envelope.get("ttl", 8),
                        "sentAt": relay.get("sentAt", int(time.time() * 1000)),
                        "receivedAt": int(time.time() * 1000)
                    }
                    messages.append(msg_obj)
        except Exception:
            pass

class MeshHTTPHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Concise logging
        if "/api/mesh/messages" not in args[0] and "/api/mesh/peers" not in args[0]:
            print(f">> HTTP {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_GET(self):
        url_path = self.path.split("?")[0]

        if url_path in ["", "/", "/ui", "/ui.html"]:
            self.serve_ui()
            return

        if url_path in ["/knit.apk", "/knit-2.10.1.apk"]:
            self.serve_apk()
            return

        if url_path == "/api/mesh/messages":
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with lock:
                data = list(reversed(messages[-100:]))
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if url_path == "/api/mesh/peers":
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            now = time.time()
            with lock:
                active_peers = [p for p in peers.values() if (now - p.get("lastSeen", 0)) < 30]
            self.wfile.write(json.dumps(active_peers).encode("utf-8"))
            return

        if url_path == "/api/mesh/digest":
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            digest = compute_digest()
            with lock:
                count = len(messages)
            self.wfile.write(json.dumps({"digest": digest, "count": count}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        url_path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body) if body else {}

        if url_path == "/api/mesh/heartbeat":
            node_id = data.get("nodeId", "peer-" + uuid.uuid4().hex[:4])
            with lock:
                peers[node_id] = {
                    "nodeId": node_id,
                    "displayName": data.get("displayName", node_id),
                    "role": data.get("role", "CITIZEN"),
                    "lastSeen": time.time()
                }
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "OK"}).encode("utf-8"))
            return

        if url_path == "/api/mesh/broadcast":
            mid = "m-" + uuid.uuid4().hex[:8]
            payload = {
                "body": data.get("body", ""),
                "senderName": data.get("senderName", "Anonymous"),
                "channel": data.get("channel", "NEARBY_PUBLIC"),
                "urgency": data.get("urgency", "NORMAL")
            }
            self.record_and_broadcast(mid, "chat", data.get("nodeId", "node-1"), data.get("role", "CITIZEN"), payload)
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "BROADCASTED", "id": mid}).encode("utf-8"))
            return

        if url_path == "/api/mesh/sos":
            mid = "sos-" + uuid.uuid4().hex[:8]
            payload = {
                "victimName": data.get("victimName", "Victim"),
                "emergencyType": data.get("emergencyType", "MEDICAL"),
                "latitude": data.get("latitude", 30.3165),
                "longitude": data.get("longitude", 78.0322),
                "urgencyScore": data.get("urgencyScore", 5),
                "injuriesCount": data.get("injuriesCount", 1),
                "medicalNeeds": data.get("medicalNeeds", "Immediate Help"),
                "details": data.get("details", "")
            }
            self.record_and_broadcast(mid, "sos", data.get("nodeId", "node-1"), "AMBULANCE", payload)
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "SOS_BROADCASTED", "id": mid}).encode("utf-8"))
            return

        if url_path == "/api/mesh/field-report":
            mid = "rep-" + uuid.uuid4().hex[:8]
            payload = {
                "reportType": data.get("reportType", "HAZARD"),
                "latitude": data.get("latitude", 30.3165),
                "longitude": data.get("longitude", 78.0322),
                "severity": data.get("severity", 3),
                "description": data.get("description", ""),
                "reporterRole": data.get("reporterRole", "CITIZEN")
            }
            self.record_and_broadcast(mid, "field_report", data.get("nodeId", "node-1"), data.get("reporterRole", "CITIZEN"), payload)
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "REPORTED", "id": mid}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def record_and_broadcast(self, mid, mtype, sender_id, role, payload_dict):
        payload_str = json.dumps(payload_dict)
        now_ms = int(time.time() * 1000)

        relay = {
            "type": mtype,
            "id": mid,
            "senderId": sender_id,
            "sentAt": now_ms,
            "recipientId": None,
            "group": None,
            "payload": payload_str
        }

        signed_str = json.dumps(relay, separators=(",", ":"))
        signature = sign(signed_str)

        wire = {
            "ttl": 8,
            "hops": 0,
            "relay": True,
            "sig": signature,
            "signed": signed_str
        }

        with lock:
            seen_ids.add(mid)
            messages.append({
                "id": mid,
                "type": mtype,
                "senderId": sender_id,
                "senderRole": role,
                "payloadJson": payload_str,
                "hops": 0,
                "ttl": 8,
                "sentAt": now_ms,
                "receivedAt": now_ms
            })

        # Relay onto local UDP port 8988 as well
        send_udp_broadcast(wire)

        print(f"[*] Broadcasted [{mtype.upper()}] frame: ID={mid} From={sender_id}")

    def serve_ui(self):
        # The mesh messenger page was moved with the other single-file UIs to residuals/.
        ui_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "residuals", "mesh_messenger.ui.html"
        )

        try:
            with open(ui_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error loading ui.html: {e}".encode("utf-8"))

    def serve_apk(self):
        apk_path = "knit.apk"
        if not os.path.exists(apk_path):
            apk_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knit.apk")
        if not os.path.exists(apk_path):
            apk_path = r"C:\Users\megha\Downloads\knit-2.10.1.apk"

        if os.path.exists(apk_path):
            size = os.path.getsize(apk_path)
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Disposition", 'attachment; filename="knit-2.10.1.apk"')
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(apk_path, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"APK not found")

def get_local_ips():
    ips = []
    try:
        # Connect dummy UDP socket to find primary routing IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    try:
        host_name = socket.gethostname()
        for ip in socket.gethostbyname_ex(host_name)[2]:
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    if not ips:
        ips.append("127.0.0.1")
    return ips

def main():
    port = DEFAULT_HTTP_PORT
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    elif "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            port = int(sys.argv[idx + 1])

    # Start background UDP sync listener
    t = threading.Thread(target=udp_listener_thread, daemon=True)
    t.start()

    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, MeshHTTPHandler)

    local_ips = get_local_ips()

    print("========================================================================")
    print(" [*] CITYSENSE OFFLINE MESH MESSAGING SERVER (0.0.0.0 BIND)")
    print("========================================================================")
    print(f" Server is bound to all network interfaces on port {port}.")
    print("\n [>] OPEN THIS URL ON PHONE 1 & PHONE 2 (WITH INTERNET OFF):")
    for ip in local_ips:
        print(f"     -> http://{ip}:{port}/ui.html")
    print(f"     -> http://localhost:{port}/ui.html (on this PC)")
    print("\n [*] ZERO-INTERNET SETUP INSTRUCTIONS:")
    print("     1. Turn OFF Mobile Data / Cellular on both phones.")
    print("     2. Connect Phone 1, Phone 2, and this PC to the same Wi-Fi")
    print("        (OR turn on Mobile Hotspot on Phone 1 and connect PC + Phone 2 to it).")
    print(f"     3. Open http://{local_ips[0]}:{port}/ui.html in Chrome/Safari on both phones!")
    print("     4. Type a message or hit the red 'SOS' button to test real-time mesh messaging!")
    print("========================================================================\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")

if __name__ == "__main__":
    main()

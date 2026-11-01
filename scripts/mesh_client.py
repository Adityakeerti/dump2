#!/usr/bin/env python3
"""
CitySense Offline Mesh Client (Knit Wire-Compatible)
===================================================
A zero-internet, zero-dependency Python mesh node that talks directly
to the CitySense Core Spring Boot mesh service over local UDP broadcast.

Usage:
  # Listen for live mesh packets:
  python scripts/mesh_client.py listen --port 8988

  # Broadcast an Emergency SOS Distress Beacon:
  python scripts/mesh_client.py sos --victim "Aarav Sharma" --type FLOOD --lat 30.3245 --lon 78.0412 --urgency 5 --details "Trapped in flooded underpass"

  # Broadcast an Offline Field Report:
  python scripts/mesh_client.py report --type ROAD_BLOCK --lat 30.3180 --lon 78.0400 --severity 4 --desc "Fallen tree blocking Rajpur Road"

  # Send an Offline Chat Message:
  python scripts/mesh_client.py chat --body "All units hold position at Clock Tower" --sender "Ambulance-1" --channel CREW

  # Run an automated multi-hop simulation demo:
  python scripts/mesh_client.py demo
"""

import sys
import os
import json
import time
import uuid
import hmac
import socket
import hashlib
import argparse

DEFAULT_PORT = 8988
DEFAULT_NETWORK_KEY = "citysense-offline-mesh-secure-v1-key"
DEFAULT_TTL = 8

def sign(data_str: str, key: str = DEFAULT_NETWORK_KEY) -> str:
    """Computes HMAC-SHA256 signature matching CitySense Java MeshCrypto."""
    key_bytes = key.encode("utf-8")
    data_bytes = data_str.encode("utf-8")
    return hmac.new(key_bytes, data_bytes, hashlib.sha256).hexdigest()

def verify(data_str: str, signature: str, key: str = DEFAULT_NETWORK_KEY) -> bool:
    """Verifies HMAC-SHA256 signature in constant time."""
    expected = sign(data_str, key)
    return hmac.compare_digest(expected, signature)

def build_wire_envelope(relay_dict: dict, ttl: int = DEFAULT_TTL, relay: bool = True) -> dict:
    """Wraps Layer 2 RelayEnvelope into Layer 1 WireEnvelope."""
    signed_str = json.dumps(relay_dict, separators=(",", ":"))
    signature = sign(signed_str)
    return {
        "ttl": ttl,
        "hops": 0,
        "relay": relay,
        "sig": signature,
        "signed": signed_str
    }

def send_wire_envelope(envelope: dict, port: int = DEFAULT_PORT):
    """Broadcasts packet over UDP to 255.255.255.255 and 127.0.0.1 (works 100% offline)."""
    payload = json.dumps(envelope).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    # 1. Loopback
    try:
        sock.sendto(payload, ("127.0.0.1", port))
    except Exception as e:
        pass
        
    # 2. Local subnet broadcast (ad-hoc Wi-Fi, hotspot, LAN)
    try:
        sock.sendto(payload, ("255.255.255.255", port))
    except Exception as e:
        pass
        
    sock.close()

def cmd_listen(port: int):
    """Listens for inbound wire packets on local UDP port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", port))
    except Exception as e:
        print(f"[!] Could not bind to port {port}: {e}")
        return

    print(f"[*] Offline Mesh Listener active on UDP port {port}")
    print("[*] Waiting for zero-internet mesh frames... (Press Ctrl+C to stop)\n")

    seen_ids = set()

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            envelope = json.loads(data.decode("utf-8"))
            
            sig = envelope.get("sig", "")
            signed_str = envelope.get("signed", "")
            ttl = envelope.get("ttl", 0)
            hops = envelope.get("hops", 0)

            if not verify(signed_str, sig):
                print(f"[!] Dropped packet from {addr}: INVALID SIGNATURE")
                continue

            relay = json.loads(signed_str)
            msg_id = relay.get("id")

            if msg_id in seen_ids:
                print(f"[~] Dropped duplicate packet: ID={msg_id}")
                continue
            seen_ids.add(msg_id)

            msg_type = relay.get("type", "UNKNOWN")
            sender = relay.get("senderId", "ANON")
            payload = json.loads(relay.get("payload", "{}"))

            print("=" * 60)
            print(f">> RECEIVED MESH FRAME [{msg_type.upper()}] from {sender} (Hops: {hops}, TTL: {ttl})")
            print(f"   Message ID : {msg_id}")
            print(f"   Payload    : {json.dumps(payload, indent=2)}")
            print("=" * 60 + "\n")

        except KeyboardInterrupt:
            print("\n[*] Listener stopped.")
            break
        except Exception as e:
            print(f"[!] Error processing packet: {e}")

def cmd_sos(args):
    """Sends an Emergency SOS Distress Beacon."""
    sos_payload = {
        "victimName": args.victim,
        "emergencyType": args.type,
        "latitude": args.lat,
        "longitude": args.lon,
        "urgencyScore": args.urgency,
        "injuriesCount": args.injuries,
        "medicalNeeds": args.medical,
        "details": args.details
    }
    msg_id = f"sos-{uuid.uuid4().hex[:8]}"
    relay = {
        "type": "sos",
        "id": msg_id,
        "senderId": args.node_id,
        "sentAt": int(time.time() * 1000),
        "recipientId": None,
        "group": None,
        "payload": json.dumps(sos_payload, separators=(",", ":"))
    }
    wire = build_wire_envelope(relay)
    send_wire_envelope(wire, args.port)
    print(f"[*] SOS DISTRESS BEACON BROADCASTED over offline mesh:")
    print(f"   ID: {msg_id}")
    print(f"   Victim: {args.victim} | Emergency: {args.type} | Urgency: {args.urgency}/5")
    print(f"   Location: ({args.lat}, {args.lon})")

def cmd_report(args):
    """Sends an Offline Field Report."""
    rep_payload = {
        "reportType": args.type,
        "latitude": args.lat,
        "longitude": args.lon,
        "severity": args.severity,
        "description": args.desc,
        "reporterRole": args.role
    }
    msg_id = f"rep-{uuid.uuid4().hex[:8]}"
    relay = {
        "type": "field_report",
        "id": msg_id,
        "senderId": args.node_id,
        "sentAt": int(time.time() * 1000),
        "recipientId": None,
        "group": None,
        "payload": json.dumps(rep_payload, separators=(",", ":"))
    }
    wire = build_wire_envelope(relay)
    send_wire_envelope(wire, args.port)
    print(f"[*] FIELD REPORT BROADCASTED over offline mesh:")
    print(f"   ID: {msg_id}")
    print(f"   Type: {args.type} | Severity: {args.severity}/5")
    print(f"   Description: {args.desc}")

def cmd_chat(args):
    """Sends an Offline Chat Message."""
    chat_payload = {
        "body": args.body,
        "senderName": args.sender,
        "channel": args.channel,
        "urgency": args.urgency,
        "latitude": args.lat,
        "longitude": args.lon
    }
    msg_id = f"m-{uuid.uuid4().hex[:8]}"
    relay = {
        "type": "chat",
        "id": msg_id,
        "senderId": args.node_id,
        "sentAt": int(time.time() * 1000),
        "recipientId": args.to,
        "group": args.group,
        "payload": json.dumps(chat_payload, separators=(",", ":"))
    }
    wire = build_wire_envelope(relay)
    send_wire_envelope(wire, args.port)
    print(f">> MESH CHAT TRANSMITTED:")
    print(f"   ID: {msg_id}")
    print(f"   From: {args.sender} ({args.node_id}) -> {'ALL (Broadcast)' if not args.to else args.to}")
    print(f"   Body: \"{args.body}\"")

def cmd_demo(port: int):
    """Runs an automated multi-step simulation demonstrating mesh features."""
    print("==================================================================")
    print("   CITYSENSE OFFLINE MESH SIMULATION (KNIT PROTOCOL ENGINE)")
    print("==================================================================")
    print("[1] Simulating Node 1 (Trapped Citizen: Sunita Rawat) broadcasting SOS...")
    sos_payload = {
        "victimName": "Sunita Rawat",
        "emergencyType": "FLOOD",
        "latitude": 30.3165,
        "longitude": 78.0322,
        "urgencyScore": 5,
        "injuriesCount": 2,
        "medicalNeeds": "Rescue boat, hypothermia treatment",
        "details": "Water surging past 1.5m at Prince Chowk underpass"
    }
    relay_sos = {
        "type": "sos",
        "id": "demo-sos-001",
        "senderId": "node-citizen-sunita",
        "sentAt": int(time.time() * 1000),
        "recipientId": None,
        "group": None,
        "payload": json.dumps(sos_payload, separators=(",", ":"))
    }
    wire_sos = build_wire_envelope(relay_sos)
    send_wire_envelope(wire_sos, port)
    print(f"    -> Broadcasted Wire Envelope: ID=demo-sos-001, TTL={wire_sos['ttl']}, Hops={wire_sos['hops']}")
    time.sleep(0.5)

    print("\n[2] Simulating Node 2 (Emergency Ambulance 04) reporting dispatch over mesh chat...")
    chat_payload = {
        "body": "Ambulance 04 acknowledged Prince Chowk SOS. Heading via Chakrata bypass.",
        "senderName": "Ambulance Crew 04",
        "channel": "EMERGENCY_CREW",
        "urgency": "HIGH",
        "latitude": 30.3200,
        "longitude": 78.0380
    }
    relay_chat = {
        "type": "chat",
        "id": "demo-chat-002",
        "senderId": "node-ambulance-04",
        "sentAt": int(time.time() * 1000),
        "recipientId": None,
        "group": "crew-dehradun",
        "payload": json.dumps(chat_payload, separators=(",", ":"))
    }
    wire_chat = build_wire_envelope(relay_chat)
    send_wire_envelope(wire_chat, port)
    print(f"    -> Broadcasted Wire Envelope: ID=demo-chat-002, Channel=EMERGENCY_CREW")
    time.sleep(0.5)

    print("\n[3] Simulating Store-and-Forward Re-transmission (Testing deduplication)...")
    send_wire_envelope(wire_sos, port)
    print(f"    -> Re-sent demo-sos-001 packet (Core SeenSet drops duplicate).")

    print("\n[OK] Simulation complete. Packets broadcasted over offline UDP port.")
    print("    If Spring Boot Core is running, check /api/mesh/messages or WebSocket /topic/city-events!")
    print("==================================================================")

def main():
    parser = argparse.ArgumentParser(description="CitySense Offline Mesh Client (Knit Protocol)")
    subparsers = parser.add_subparsers(dest="command")

    # listen
    p_listen = subparsers.add_parser("listen", help="Listen for inbound mesh frames")
    p_listen.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port")

    # sos
    p_sos = subparsers.add_parser("sos", help="Broadcast an Emergency SOS")
    p_sos.add_argument("--victim", default="Citizen in Distress")
    p_sos.add_argument("--type", default="MEDICAL", choices=["MEDICAL", "FLOOD", "CRASH", "FIRE", "TRAPPED"])
    p_sos.add_argument("--lat", type=float, default=30.3165)
    p_sos.add_argument("--lon", type=float, default=78.0322)
    p_sos.add_argument("--urgency", type=int, default=5)
    p_sos.add_argument("--injuries", type=int, default=1)
    p_sos.add_argument("--medical", default="First Aid")
    p_sos.add_argument("--details", default="")
    p_sos.add_argument("--node-id", default="field-client-1")
    p_sos.add_argument("--port", type=int, default=DEFAULT_PORT)

    # report
    p_rep = subparsers.add_parser("report", help="Broadcast an Offline Field Report")
    p_rep.add_argument("--type", default="HAZARD", choices=["FLOOD", "CRASH", "ROAD_BLOCK", "HAZARD", "RAIN"])
    p_rep.add_argument("--lat", type=float, default=30.3165)
    p_rep.add_argument("--lon", type=float, default=78.0322)
    p_rep.add_argument("--severity", type=int, default=3)
    p_rep.add_argument("--desc", default="Civic issue observed")
    p_rep.add_argument("--role", default="CITIZEN")
    p_rep.add_argument("--node-id", default="field-client-1")
    p_rep.add_argument("--port", type=int, default=DEFAULT_PORT)

    # chat
    p_chat = subparsers.add_parser("chat", help="Send an Offline Mesh Chat")
    p_chat.add_argument("--body", required=True)
    p_chat.add_argument("--sender", default="Responder")
    p_chat.add_argument("--channel", default="NEARBY_PUBLIC")
    p_chat.add_argument("--urgency", default="NORMAL")
    p_chat.add_argument("--to", default=None)
    p_chat.add_argument("--group", default=None)
    p_chat.add_argument("--lat", type=float, default=None)
    p_chat.add_argument("--lon", type=float, default=None)
    p_chat.add_argument("--node-id", default="field-client-1")
    p_chat.add_argument("--port", type=int, default=DEFAULT_PORT)

    # demo
    p_demo = subparsers.add_parser("demo", help="Run automated mesh simulation demo")
    p_demo.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args()

    if args.command == "listen":
        cmd_listen(args.port)
    elif args.command == "sos":
        cmd_sos(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "demo":
        cmd_demo(args.port)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

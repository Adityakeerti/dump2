import { Client } from "@stomp/stompjs";
import { useEffect, useRef, useState } from "react";
import type { LiveMessage } from "../api/types";
import { websocketUrl } from "../config";

/** Subscribes to core's STOMP topic (/topic/city-events) and reports each message. */
export function useLiveEvents(onMessage: (m: LiveMessage) => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    const client = new Client({
      brokerURL: websocketUrl("/ws"),
      reconnectDelay: 5000,
      heartbeatIncoming: 10000,
      heartbeatOutgoing: 10000,
      // React Native's WebSocket needs these for STOMP frames to parse correctly.
      forceBinaryWSFrames: true,
      appendMissingNULLonIncoming: true,
      onConnect: () => {
        setConnected(true);
        client.subscribe("/topic/city-events", (frame) => {
          try {
            handler.current(JSON.parse(frame.body) as LiveMessage);
          } catch {
            // ignore malformed frames
          }
        });
      },
      onWebSocketClose: () => setConnected(false),
      onStompError: () => setConnected(false),
    });
    client.activate();
    return () => {
      void client.deactivate();
    };
  }, []);

  return connected;
}

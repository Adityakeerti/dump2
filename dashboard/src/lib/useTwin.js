import { useEffect, useRef, useState } from "react";

const MAX_EVENTS = 400;
const MAX_DECISIONS = 400;
const MAX_HISTORY = 360;

// Live connection to the digital twin's WebSocket stream (hello snapshot + per-tick deltas).
export function useTwin() {
  const [snap, setSnap] = useState({
    connected: false, topology: null, state: null, events: [], decisions: [], history: [], episodes: [], finished: [],
  });
  const retry = useRef(0);

  useEffect(() => {
    let ws;
    let closed = false;
    let timer;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/twin/stream`);
      ws.onopen = () => { retry.current = 0; };
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data);
        if (msg.type === "hello") {
          setSnap({
            connected: true, topology: msg.topology, state: msg.state, events: msg.events, decisions: msg.decisions,
            history: msg.history, episodes: msg.episodes, finished: msg.finished_platoons,
          });
          return;
        }
        setSnap((s) => {
          const episodeRows = msg.events.filter((e) => e.kind === "episode_complete").map((e) => e.summary);
          const reset = msg.state.episode !== s.state?.episode || msg.state.policy !== s.state?.policy;
          return {
            ...s,
            connected: true,
            state: msg.state,
            events: msg.events.length ? [...s.events, ...msg.events].slice(-MAX_EVENTS) : s.events,
            decisions: msg.decisions.length ? [...s.decisions, ...msg.decisions].slice(-MAX_DECISIONS) : s.decisions,
            history: reset ? (msg.history_row ? [msg.history_row] : [])
              : msg.history_row && msg.history_row.t !== s.history.at(-1)?.t ? [...s.history, msg.history_row].slice(-MAX_HISTORY) : s.history,
            episodes: episodeRows.length ? [...s.episodes, ...episodeRows] : s.episodes,
            finished: reset ? msg.finished || [] : msg.finished?.length ? [...s.finished, ...msg.finished].slice(-200) : s.finished,
          };
        });
      };
      ws.onclose = () => {
        setSnap((s) => ({ ...s, connected: false }));
        if (closed) return;
        retry.current = Math.min(retry.current + 1, 6);
        timer = setTimeout(connect, 500 * 2 ** retry.current);
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); ws?.close(); };
  }, []);

  return snap;
}

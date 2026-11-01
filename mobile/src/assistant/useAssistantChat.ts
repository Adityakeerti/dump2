import { router, usePathname } from "expo-router";
import { useCallback, useState } from "react";
import { errorMessage } from "../api/client";
import { agentApi } from "../api/endpoints";
import type { AgentReply, ClientAction, PendingAgentAction, PlanStep } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useUserLocation } from "../hooks/useUserLocation";
import { useVoice } from "../hooks/useVoice";
import { useAssistant } from "./AssistantContext";

export interface ChatMsg {
  id: string;
  from: "me" | "agent";
  text: string;
  plan?: PlanStep[] | null;
  pending?: PendingAgentAction | null;
  /** Outcome of the pending action once the citizen decided (filed / discarded / error). */
  outcome?: string;
  viaVoice?: boolean;
}

const TAB_SCREENS = new Set(["explore", "townhall", "updates", "saved", "settings"]);
export const plain = (t: string) => t.replace(/\*\*/g, "").replace(/^#+\s*/gm, "").replace(/`/g, "").replace(/^---$/gm, "");

/**
 * Conversation with the main agent (City Sense), shared by the hovering panel and the Townhall guide:
 * text + voice in, spoken replies (unless muted), and the app actions the agent asks for.
 */
export function useAssistantChat({ onLeaveTab }: { onLeaveTab?: () => void } = {}) {
  const { language, setLanguage } = useAuth();
  const { requestMapFocus, messages, setMessages, sessionRef: session } = useAssistant();
  const lang: "hi" | "en" = language === "hi" ? "hi" : "en";
  const voice = useVoice(lang);
  const { coords } = useUserLocation();
  const pathname = usePathname();
  const [busy, setBusy] = useState(false);

  const runActions = useCallback(
    (actions?: ClientAction[] | null) => {
      // The chat stays where it is; the app moves underneath it.
      for (const a of actions ?? []) {
        if (a.type === "navigate") {
          if (a.screen === "avatar" && a.id) router.push({ pathname: "/avatar/[id]", params: { id: a.id } });
          else if (a.screen === "complaint" && a.id) router.push({ pathname: "/complaint/[trackingId]", params: { trackingId: a.id } });
          else if (a.screen === "complaint_new") router.push("/complaint/new");
          else if (TAB_SCREENS.has(a.screen) && `/${a.screen}` !== pathname) {
            router.navigate(`/${a.screen}` as never);
            onLeaveTab?.();
          }
        } else if (a.type === "focus_map" && a.latitude != null && a.longitude != null) {
          requestMapFocus({ latitude: a.latitude, longitude: a.longitude, label: a.label });
        } else if (a.type === "set_preference") {
          if (a.language) void setLanguage(a.language);
          if (a.voiceAutoPlay !== undefined) voice.setAutoPlayPref(a.voiceAutoPlay);
        }
      }
    },
    [onLeaveTab, pathname, requestMapFocus, setLanguage, voice],
  );

  const send = useCallback(
    async (text: string, viaVoice = false) => {
      const message = text.trim();
      if (!message || busy) return;
      setMessages((m) => [...m, { id: `${Date.now()}-me`, from: "me", text: message, viaVoice }]);
      setBusy(true);
      try {
        const reply: AgentReply = await agentApi.assistant({
          message,
          sessionId: session.current,
          language: lang,
          latitude: coords?.latitude,
          longitude: coords?.longitude,
          screen: pathname,
        });
        session.current = reply.sessionId;
        const id = `${Date.now()}-ag`;
        setMessages((m) => [...m, { id, from: "agent", text: plain(reply.answer), plan: reply.plan, pending: reply.pendingAction }]);
        if (voice.autoPlay && reply.answer) void voice.speak(id, plain(reply.answer));
        runActions(reply.clientActions);
      } catch (e) {
        setMessages((m) => [...m, { id: `${Date.now()}-err`, from: "agent", text: `⚠️ ${errorMessage(e)}` }]);
      } finally {
        setBusy(false);
      }
    },
    [busy, coords, lang, pathname, runActions, session, setMessages, voice],
  );

  const toggleMic = useCallback(async () => {
    if (busy || voice.state === "transcribing") return;
    if (voice.state === "recording") {
      try {
        void send(await voice.stopAndTranscribe(), true);
      } catch (e) {
        setMessages((m) => [...m, { id: `${Date.now()}-err`, from: "agent", text: `⚠️ ${errorMessage(e)}` }]);
      }
      return;
    }
    const problem = await voice.startRecording().catch((e) => errorMessage(e));
    if (problem) setMessages((m) => [...m, { id: `${Date.now()}-err`, from: "agent", text: `⚠️ ${problem}` }]);
  }, [busy, send, setMessages, voice]);

  const settle = useCallback(
    (msgId: string, outcome: string) => setMessages((m) => m.map((x) => (x.id === msgId ? { ...x, outcome } : x))),
    [setMessages],
  );

  /** Start over: clear the thread and open a new agent session. */
  const reset = useCallback(() => {
    voice.stopSpeaking();
    session.current = undefined;
    setMessages([]);
  }, [session, setMessages, voice]);

  return {
    lang,
    voice,
    messages,
    busy,
    send,
    toggleMic,
    settle,
    reset,
    listening: voice.state === "recording",
    transcribing: voice.state === "transcribing",
  };
}

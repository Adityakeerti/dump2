import { createContext, type MutableRefObject, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ChatMsg } from "./useAssistantChat";
import { storage } from "../utils/storage";

const AVATAR_KEY = "cs.mainAvatar";

export interface MapFocus {
  latitude: number;
  longitude: number;
  label?: string;
  /** Changes on every request so the same place can be focused twice. */
  nonce: number;
}

/** How the hovering panel opens: where it anchors and an optional first message (e.g. from the bar's mic). */
export interface PanelRequest {
  anchor: "top" | "bottom";
  prompt?: string;
  viaVoice?: boolean;
  /** false: open without raising the keyboard (e.g. continuing a conversation after navigation). */
  focus?: boolean;
}

interface AssistantState {
  /** Chosen main-avatar look; null until loaded or chosen. */
  avatarId: string | null;
  loaded: boolean;
  chooseAvatar: (id: string) => Promise<void>;
  panel: PanelRequest | null;
  openPanel: (req: PanelRequest) => void;
  closePanel: () => void;
  /** Map focus requested by the main agent ("show Clock Tower on the map"); Explore consumes it. */
  mapFocus: MapFocus | null;
  requestMapFocus: (f: Omit<MapFocus, "nonce">) => void;
  /** One conversation with the main agent, shared by the hovering panel and the Townhall guide. */
  messages: ChatMsg[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMsg[]>>;
  sessionRef: MutableRefObject<string | undefined>;
}

const Ctx = createContext<AssistantState | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [avatarId, setAvatarId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [panel, setPanel] = useState<PanelRequest | null>(null);
  const [mapFocus, setMapFocus] = useState<MapFocus | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const sessionRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    void storage
      .getItem(AVATAR_KEY)
      .then(setAvatarId)
      .finally(() => setLoaded(true));
  }, []);

  const chooseAvatar = useCallback(async (id: string) => {
    setAvatarId(id);
    await storage.setItem(AVATAR_KEY, id);
  }, []);

  const openPanel = useCallback((req: PanelRequest) => setPanel(req), []);
  const closePanel = useCallback(() => setPanel(null), []);
  const requestMapFocus = useCallback((f: Omit<MapFocus, "nonce">) => setMapFocus({ ...f, nonce: Date.now() }), []);

  const value = useMemo(
    () => ({ avatarId, loaded, chooseAvatar, panel, openPanel, closePanel, mapFocus, requestMapFocus, messages, setMessages, sessionRef }),
    [avatarId, loaded, chooseAvatar, panel, openPanel, closePanel, mapFocus, requestMapFocus, messages],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAssistant() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAssistant must be used inside AssistantProvider");
  return ctx;
}

/** For screens that may render outside the provider (e.g. Explore in tests): no-op fallback. */
export function useAssistantOptional() {
  return useContext(Ctx);
}

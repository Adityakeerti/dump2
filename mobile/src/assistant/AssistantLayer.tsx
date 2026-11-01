import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { usePathname } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Easing,
  type LayoutChangeEvent,
  Pressable,
  ScrollView,
  type ScrollViewInstance,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { MAIN_AVATARS, type MainAvatar, mainAvatarById } from "../content/mainAvatars";
import { useKeyboardHeight } from "../hooks/useKeyboardHeight";
import { useVoice } from "../hooks/useVoice";
import { useReducedMotion } from "../motion";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";
import { type PanelRequest, useAssistant } from "./AssistantContext";
import { PendingActionCard } from "../components/PendingActionCard";
import { AvatarBubbles, type BubbleMode } from "./AvatarBubbles";
import { useAssistantChat } from "./useAssistantChat";
import { Waves } from "./Waves";

const EXECUTOR: Record<string, string> = {
  main_voice_agent: "City Sense",
  civic_complaint: "Complaint desk",
  emergency_traffic: "Emergency desk",
  city_pulse: "City Pulse",
  knowledge_specialist: "Knowledge desk",
};

/** Mirrors TabBar: 8 top padding + ~56 item row + max(inset, 8) bottom padding. */
export function tabBarHeight(bottomInset: number) {
  return 64 + Math.max(bottomInset, 8);
}
/** Explore's search bar: top inset + 10 + 48 tall; the assistant bar sits right below it. */
export const exploreBarTop = (topInset: number) => topInset + 10 + 48 + 8;

/**
 * Global layer over the tabs: first-run guide chooser, the hovering panel, and the assistant bar on
 * tabs without a search bar (Explore renders its own bar right under the search box).
 */
export function AssistantLayer() {
  const { avatarId, loaded, chooseAvatar, panel, closePanel } = useAssistant();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  if (!loaded) return null;
  if (!avatarId) return <AvatarChooser onChoose={chooseAvatar} />;
  // Explore has the bar under its search box; Townhall is the guide's own full-screen stage.
  const ownBar = pathname === "/explore" || pathname === "/" || pathname === "/townhall";
  return (
    <>
      {!ownBar && !panel ? (
        <View style={[styles.barSlot, { bottom: tabBarHeight(insets.bottom) + 10 }]} pointerEvents="box-none">
          <AssistantBar anchor="bottom" />
        </View>
      ) : null}
      {panel ? <AssistantPanel request={panel} onClose={closePanel} /> : null}
    </>
  );
}

/** Avatar inside a circular mask (or the full sticker), gently floating. */
export function BobbingAvatar({
  avatar,
  size,
  variant = "mask",
}: {
  avatar: MainAvatar;
  size: number;
  /** "mask": face in a ring (bar, panel); "portrait": whole sticker, unmasked (chooser). */
  variant?: "mask" | "portrait";
}) {
  const reduced = useReducedMotion();
  const t = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (reduced) return;
    // Slow, gentle float: the avatar stays steady and just drifts up and down a little.
    const half = variant === "portrait" ? 2400 : 1800;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(t, { toValue: 1, duration: half, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(t, { toValue: 0, duration: half, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [reduced, t, variant]);
  const lift = variant === "portrait" ? 0.015 : 0.03;
  const motion = {
    transform: [{ translateY: t.interpolate({ inputRange: [0, 1], outputRange: [size * lift, -size * lift] }) }],
  };
  if (variant === "portrait") {
    return (
      <Animated.View style={[{ width: size, height: size }, motion]}>
        <Image source={avatar.portrait} style={{ width: size, height: size }} contentFit="contain" accessibilityIgnoresInvertColors />
      </Animated.View>
    );
  }
  return (
    <View style={[styles.mask, { width: size, height: size, borderRadius: size / 2, borderColor: avatar.ring }]}>
      <Animated.View style={[{ width: size, height: size }, motion]}>
        <Image source={avatar.bust} style={{ width: size, height: size }} contentFit="cover" accessibilityIgnoresInvertColors />
      </Animated.View>
    </View>
  );
}

/** Placeholder text that fades between lines (the guide's prompts) so the bar never feels static. */
function CyclingText({ lines, style }: { lines: string[]; style: object }) {
  const reduced = useReducedMotion();
  const fade = useRef(new Animated.Value(1)).current;
  const [i, setI] = useState(0);
  const key = lines.join("\u0001");
  useEffect(() => {
    setI(0);
    if (lines.length < 2) return;
    const id = setInterval(() => {
      if (reduced) return setI((x) => (x + 1) % lines.length);
      Animated.timing(fade, { toValue: 0, duration: 220, useNativeDriver: true }).start(() => {
        setI((x) => (x + 1) % lines.length);
        Animated.timing(fade, { toValue: 1, duration: 260, useNativeDriver: true }).start();
      });
    }, 3600);
    return () => clearInterval(id);
  }, [key, reduced]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Animated.Text style={[style, { opacity: fade }]} numberOfLines={1}>
      {lines[i % lines.length]}
    </Animated.Text>
  );
}

/**
 * The main agent's bar: avatar in the left corner, a text area in the middle (tap -> hovering panel),
 * mic on the right. The mic records right here, with waves filling the bar; the transcript then opens
 * the panel and is sent.
 */
export function AssistantBar({ anchor }: { anchor: PanelRequest["anchor"] }) {
  const { avatarId, openPanel } = useAssistant();
  const { language } = useAuth();
  const avatar = mainAvatarById(avatarId);
  const lang = language === "hi" ? "hi" : "en";
  const voice = useVoice(lang);
  const [width, setWidth] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const listening = voice.state === "recording";
  const transcribing = voice.state === "transcribing";

  const mic = async () => {
    setError(null);
    if (transcribing) return;
    if (listening) {
      try {
        const text = await voice.stopAndTranscribe();
        openPanel({ anchor, prompt: text, viaVoice: true });
      } catch (e) {
        setError(errorMessage(e));
      }
      return;
    }
    const problem = await voice.startRecording().catch((e) => errorMessage(e));
    if (problem) setError(problem);
  };

  const prompts = [
    lang === "hi" ? `${avatar.name} से कुछ भी पूछें…` : `Ask ${avatar.name} anything…`,
    ...avatar.phrases[lang],
  ];
  const bubble: BubbleMode = listening ? "listening" : transcribing ? "thinking" : "idle";

  return (
    <View style={styles.bar} onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}>
      {(listening || transcribing) && width > 0 ? (
        <Waves width={width} height={BAR_HEIGHT} level={voice.level} mode={listening ? "listening" : "thinking"} radius={18} />
      ) : null}
      <View>
        <BobbingAvatar avatar={avatar} size={44} />
        {bubble !== "idle" ? (
          <View style={styles.barBubble} pointerEvents="none">
            <AvatarBubbles mode={bubble} dark />
          </View>
        ) : null}
      </View>
      <Tap
        feedback="dim"
        style={styles.barText}
        onPress={() => openPanel({ anchor })}
        disabled={listening || transcribing}
        accessibilityLabel={`Type a message to ${avatar.name}, your City Sense guide`}
      >
        {error ? (
          <Text style={[styles.barPlaceholder, { color: colors.danger }]} numberOfLines={1}>
            ⚠️ {error}
          </Text>
        ) : listening ? (
          <Text style={[styles.barPlaceholder, styles.barLive]}>{lang === "hi" ? "सुन रहा हूँ… भेजने के लिए ■" : "Listening… tap ■ to send"}</Text>
        ) : transcribing ? (
          <Text style={[styles.barPlaceholder, styles.barLive]}>{lang === "hi" ? "समझ रहा हूँ…" : "Understanding…"}</Text>
        ) : (
          <CyclingText lines={prompts} style={styles.barPlaceholder} />
        )}
      </Tap>
      <Tap
        style={[styles.barMic, listening && { backgroundColor: colors.danger }]}
        onPress={mic}
        disabled={transcribing}
        accessibilityLabel={listening ? "Stop and send" : `Speak to ${avatar.name}`}
      >
        {transcribing ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name={listening ? "stop" : "mic"} size={20} color="#fff" />}
      </Tap>
    </View>
  );
}

const BAR_HEIGHT = 62;

const SUGGESTIONS = [
  "What can you do?",
  "Show my complaints",
  "Latest notices",
  "Recommend a cafe nearby",
  "Show Clock Tower on the map",
  "Report sewage overflow near me",
  "हिंदी में बात करो",
];

/** Conversation list shared by the hovering panel and the Townhall guide. */
export function ChatThread({
  chat,
  emptyText,
  style,
  bubbleStyle,
}: {
  chat: ReturnType<typeof useAssistantChat>;
  emptyText?: string;
  style?: object;
  bubbleStyle?: object;
}) {
  const reduced = useReducedMotion();
  const scroll = useRef<ScrollViewInstance>(null);
  return (
    <ScrollView
      ref={scroll}
      nestedScrollEnabled
      style={[{ flex: 1 }, style]}
      contentContainerStyle={{ gap: 8, paddingVertical: 6 }}
      keyboardShouldPersistTaps="handled"
      onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: !reduced })}
    >
      {chat.messages.length === 0 && emptyText ? <Text style={styles.empty}>{emptyText}</Text> : null}
      {chat.messages.map((m) => (
        <FadeIn key={m.id} from="below" style={[styles.msg, m.from === "me" ? styles.mine : styles.theirs, bubbleStyle]}>
          <Text style={[styles.msgText, m.from === "me" && { color: "#fff" }]}>
            {m.viaVoice ? "🎙️ " : ""}
            {m.text}
          </Text>
          {m.plan && m.plan.length > 0 ? (
            <View style={styles.steps}>
              {m.plan.map((s) => (
                <Text key={s.id} style={styles.step}>
                  {s.status === "completed" ? "✓" : s.status === "failed" ? "✕" : "•"} {EXECUTOR[s.executor] ?? s.executor}: {s.action}
                </Text>
              ))}
            </View>
          ) : null}
          {m.pending && !m.outcome ? <PendingActionCard pending={m.pending} onDone={(o) => chat.settle(m.id, o)} compact /> : null}
          {m.outcome ? <Text style={styles.outcome}>{m.outcome}</Text> : null}
        </FadeIn>
      ))}
      {chat.busy ? (
        <View style={styles.thinkingRow}>
          <AvatarBubbles mode="thinking" />
        </View>
      ) : null}
    </ScrollView>
  );
}

/** Input with mic; while listening the waves fill the row itself. */
export function ChatInput({
  chat,
  name,
  autoFocus,
  style,
}: {
  chat: ReturnType<typeof useAssistantChat>;
  name: string;
  autoFocus?: boolean;
  style?: object;
}) {
  const [draft, setDraft] = useState("");
  const [width, setWidth] = useState(0);
  const { lang, listening, transcribing, busy, voice } = chat;
  const submit = () => {
    const t = draft;
    setDraft("");
    void chat.send(t);
  };
  return (
    <View style={[styles.inputRow, style]} onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}>
      {(listening || transcribing) && width > 0 ? (
        <Waves width={width} height={52} level={voice.level} mode={listening ? "listening" : "thinking"} radius={16} />
      ) : null}
      <TextInput
        value={draft}
        onChangeText={setDraft}
        autoFocus={autoFocus}
        placeholder={
          listening ? (lang === "hi" ? "सुन रहा हूँ… भेजने के लिए ■" : "Listening… tap ■ to send") : lang === "hi" ? "कुछ भी पूछें या कहें…" : `Message ${name}…`
        }
        placeholderTextColor={listening ? colors.navy : "#8A8A95"}
        style={styles.input}
        onSubmitEditing={submit}
        returnKeyType="send"
        maxLength={1000}
        editable={!listening && !transcribing}
      />
      {draft.trim() ? (
        <Tap style={styles.sendBtn} onPress={submit} disabled={busy} accessibilityLabel="Send">
          <Ionicons name="arrow-up" size={20} color="#fff" />
        </Tap>
      ) : (
        <Tap
          style={[styles.sendBtn, listening && { backgroundColor: colors.danger }]}
          onPress={chat.toggleMic}
          disabled={busy || transcribing}
          accessibilityLabel={listening ? "Stop and send" : `Speak to ${name}`}
        >
          {transcribing ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name={listening ? "stop" : "mic"} size={20} color="#fff" />}
        </Tap>
      )}
    </View>
  );
}

export function Suggestions({ chat, items = SUGGESTIONS }: { chat: ReturnType<typeof useAssistantChat>; items?: string[] }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} style={{ flexGrow: 0 }} keyboardShouldPersistTaps="handled">
      {items.map((s, i) => (
        <FadeIn key={s} index={i} from="below">
          <Tap style={styles.chip} onPress={() => chat.send(s)} disabled={chat.busy} accessibilityLabel={s}>
            <Text style={styles.chipText}>{s}</Text>
          </Tap>
        </FadeIn>
      ))}
    </ScrollView>
  );
}

/** The expanded assistant: a card hovering over the screen, with conversation, chips, text and mic. */
function AssistantPanel({ request, onClose }: { request: PanelRequest; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const { avatarId } = useAssistant();
  const avatar = mainAvatarById(avatarId);
  const chat = useAssistantChat();
  const { lang, voice, listening, transcribing, busy } = chat;
  const reduced = useReducedMotion();
  const { height: windowHeight } = useWindowDimensions();
  const keyboard = useKeyboardHeight();
  const enter = useRef(new Animated.Value(reduced ? 1 : 0)).current;

  useEffect(() => {
    if (!reduced) Animated.spring(enter, { toValue: 1, friction: 8, tension: 90, useNativeDriver: true }).start();
    if (request.prompt) void chat.send(request.prompt, request.viaVoice);
    return () => voice.stopSpeaking();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => {
    voice.stopSpeaking();
    void voice.cancelRecording();
    if (reduced) return onClose();
    Animated.timing(enter, { toValue: 0, duration: 180, easing: Easing.in(Easing.quad), useNativeDriver: true }).start(onClose);
  };

  const bubbleMode: BubbleMode = listening ? "listening" : transcribing || busy ? "thinking" : voice.speakingId ? "speaking" : "idle";
  // Hovers from just under the search bar down to just above the tab bar, or above the keyboard.
  const top = exploreBarTop(insets.top);
  const bottom = keyboard > 0 ? keyboard + 8 : Math.max(tabBarHeight(insets.bottom) + 8, windowHeight * 0.12);
  const from = request.anchor === "top" ? -24 : 24;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <Pressable style={styles.backdrop} onPress={close} accessibilityLabel="Close assistant" />
      <Animated.View
        style={[
          styles.card,
          { top, bottom },
          {
            opacity: enter,
            transform: [
              { translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [from, 0] }) },
              { scale: enter.interpolate({ inputRange: [0, 1], outputRange: [0.96, 1] }) },
            ],
          },
        ]}
      >
        <View style={styles.header}>
          <View>
            <BobbingAvatar avatar={avatar} size={46} />
            <View style={styles.headerBubble} pointerEvents="none">
              <AvatarBubbles mode={bubbleMode} phrases={chat.messages.length === 0 ? avatar.phrases[lang] : []} interval={5200} initialDelay={900} dark />
            </View>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>{avatar.name} · City Sense</Text>
            <Text style={styles.subtitle}>
              {listening ? "Listening…" : transcribing || busy ? "Thinking…" : voice.speakingId ? "Speaking…" : "Main agent · voice or text"}
            </Text>
          </View>
          <Tap feedback="dim" hitSlop={10} onPress={voice.toggleAutoPlay} accessibilityLabel={voice.autoPlay ? "Mute voice" : "Unmute voice"}>
            <Ionicons name={voice.autoPlay ? "volume-high" : "volume-mute"} size={21} color={colors.navy} />
          </Tap>
          <Tap feedback="dim" hitSlop={10} onPress={close} accessibilityLabel="Close">
            <Ionicons name="close" size={24} color={colors.textMuted} />
          </Tap>
        </View>

        <ChatThread
          chat={chat}
          emptyText={
            lang === "hi"
              ? `${avatar.name} से कुछ भी पूछें — शिकायतें, नोटिस, नक्शा, या शहर की कोई भी बात।`
              : `Ask ${avatar.name} anything — complaints, notices, the map, or anything about the city.`
          }
        />
        {!listening ? <Suggestions chat={chat} /> : null}
        <ChatInput chat={chat} name={avatar.name} autoFocus={!request.prompt && request.focus !== false} />
      </Animated.View>
    </View>
  );
}

/** First launch: the citizen picks how their City Sense guide looks. Changeable later in Settings. */
export function AvatarChooser({ onChoose, onCancel }: { onChoose: (id: string) => void; onCancel?: () => void }) {
  const insets = useSafeAreaInsets();
  const { avatarId } = useAssistant();
  const [picked, setPicked] = useState<string>(avatarId ?? MAIN_AVATARS[0].id);
  return (
    <FadeIn from="none" style={[StyleSheet.absoluteFill, styles.chooser, { paddingTop: insets.top + 32, paddingBottom: insets.bottom + 20 }]}>
      <Text style={styles.chooserTitle}>Choose your City Sense guide</Text>
      <Text style={styles.chooserSub}>
        Your guide is the main agent: ask about the city, report issues, or tell it to open complaints, notices and the map — by voice or text.
      </Text>
      <View style={styles.choices}>
        {MAIN_AVATARS.map((a) => {
          const on = a.id === picked;
          return (
            <Tap
              key={a.id}
              style={[styles.choice, on && { borderColor: a.ring, backgroundColor: "#FBF3F5" }]}
              onPress={() => setPicked(a.id)}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              accessibilityLabel={`${a.name}: ${a.tagline}`}
            >
              <View>
                <BobbingAvatar avatar={a} size={130} variant="portrait" />
                <View style={styles.choiceBubble} pointerEvents="none">
                  <AvatarBubbles
                    mode="idle"
                    phrases={[`Hi, I'm ${a.name}!`, ...a.phrases.en.slice(0, 3)]}
                    interval={3600}
                    initialDelay={a.id === MAIN_AVATARS[0].id ? 500 : 2300}
                    dark={on}
                  />
                </View>
              </View>
              <Text style={styles.choiceName}>{a.name}</Text>
              <Text style={styles.choiceTag}>{a.tagline}</Text>
              <Ionicons name={on ? "radio-button-on" : "radio-button-off"} size={20} color={on ? a.ring : colors.textMuted} />
            </Tap>
          );
        })}
      </View>
      <View style={{ flex: 1 }} />
      <Tap style={styles.continueBtn} onPress={() => onChoose(picked)} accessibilityLabel="Continue with this guide">
        <Text style={styles.continueText}>Continue with {mainAvatarById(picked).name}</Text>
      </Tap>
      {onCancel ? (
        <Tap feedback="dim" style={{ alignSelf: "center", padding: 12 }} onPress={onCancel} accessibilityLabel="Cancel">
          <Text style={styles.chooserSub}>Cancel</Text>
        </Tap>
      ) : null}
    </FadeIn>
  );
}

const styles = StyleSheet.create({
  mask: { overflow: "hidden", borderWidth: 2, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  barSlot: { position: "absolute", left: 14, right: 14 },
  bar: {
    height: BAR_HEIGHT,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingLeft: 8,
    paddingRight: 8,
    borderRadius: 18,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    elevation: 5,
    shadowColor: "#000",
    shadowOpacity: 0.14,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 3 },
  },
  barBubble: { position: "absolute", left: 28, top: 44, zIndex: 3 },
  barText: { flex: 1, height: 46, justifyContent: "center", paddingHorizontal: 12, borderRadius: 12, backgroundColor: "rgba(245,245,248,0.85)" },
  barPlaceholder: { fontFamily: fonts.medium, fontSize: 14, color: "#7A7A85" },
  barLive: { color: colors.navy, fontFamily: fonts.semibold },
  barMic: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  backdrop: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(15,23,42,0.4)" },
  card: {
    position: "absolute",
    left: 10,
    right: 10,
    backgroundColor: colors.surface,
    borderRadius: 24,
    paddingHorizontal: 14,
    paddingTop: 20,
    paddingBottom: 12,
    gap: 8,
    elevation: 18,
    shadowColor: "#000",
    shadowOpacity: 0.22,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
  },
  header: { flexDirection: "row", alignItems: "center", gap: 12 },
  headerBubble: { position: "absolute", left: 32, bottom: 36, zIndex: 2 },
  title: { fontFamily: fonts.bold, fontSize: 17, color: colors.text },
  subtitle: { fontFamily: fonts.medium, fontSize: 12, color: colors.textMuted },
  empty: { fontFamily: fonts.regular, fontSize: 13, color: colors.textMuted, textAlign: "center", marginTop: 12, paddingHorizontal: 12 },
  msg: { maxWidth: "90%", borderRadius: 14, paddingHorizontal: 12, paddingVertical: 8 },
  mine: { alignSelf: "flex-end", backgroundColor: colors.primary, borderBottomRightRadius: 4 },
  theirs: { alignSelf: "flex-start", backgroundColor: colors.surfaceAlt, borderBottomLeftRadius: 4 },
  msgText: { fontFamily: fonts.regular, fontSize: 14, lineHeight: 20, color: colors.text },
  steps: { marginTop: 6, paddingTop: 5, borderTopWidth: 1, borderTopColor: colors.border, gap: 1 },
  step: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  outcome: { marginTop: 4, fontFamily: fonts.semibold, fontSize: 12, color: colors.navy },
  thinkingRow: { alignSelf: "flex-start", paddingVertical: 4 },
  chips: { gap: 6 },
  chip: { backgroundColor: colors.chip, borderRadius: radius.pill, paddingHorizontal: 11, paddingVertical: 6 },
  chipText: { fontFamily: fonts.medium, fontSize: 12, color: colors.text },
  inputRow: {
    height: 52,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surfaceAlt,
    borderRadius: 16,
    paddingLeft: 14,
    paddingRight: 6,
    overflow: "hidden",
  },
  input: { flex: 1, fontFamily: fonts.regular, fontSize: 15, color: colors.text },
  sendBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  chooser: { backgroundColor: colors.surface, paddingHorizontal: 20, zIndex: 50 },
  chooserTitle: { fontFamily: fonts.display, fontSize: 28, color: colors.text, textAlign: "center" },
  chooserSub: { marginTop: 8, fontFamily: fonts.regular, fontSize: 14, color: colors.textMuted, textAlign: "center", lineHeight: 20 },
  choices: { flexDirection: "row", gap: 12, marginTop: 28 },
  choice: {
    flex: 1,
    alignItems: "center",
    gap: 6,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingVertical: 18,
    paddingHorizontal: 10,
  },
  choiceBubble: { position: "absolute", right: -14, top: -16 },
  choiceName: { fontFamily: fonts.bold, fontSize: 18, color: colors.text, marginTop: 4 },
  choiceTag: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted, textAlign: "center" },
  continueBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 15, alignItems: "center" },
  continueText: { fontFamily: fonts.bold, fontSize: 16, color: "#fff" },
});

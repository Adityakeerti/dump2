import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Animated, type LayoutChangeEvent, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { AvatarBubbles, type BubbleMode } from "../assistant/AvatarBubbles";
import { BobbingAvatar, ChatThread } from "../assistant/AssistantLayer";
import type { useAssistantChat } from "../assistant/useAssistantChat";
import { Waves } from "../assistant/Waves";
import { PageDots } from "../components/PageDots";
import type { MainAvatar } from "../content/mainAvatars";
import { useReducedMotion } from "../motion";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";

type Chat = ReturnType<typeof useAssistantChat>;

/** Quick prompts in the chat card, like the design's "Introduce yourself / Pricing / Official Website". */
const CHIPS = [
  { emoji: "🙋", label: "Introduce yourself", prompt: "Introduce yourself" },
  { emoji: "🎉", label: "Events this month", prompt: "What's happening in Dehradun this month?" },
  { emoji: "☕", label: "Cafe nearby", prompt: "Recommend a cafe nearby" },
  { emoji: "📝", label: "My complaints", prompt: "Show my complaints" },
  { emoji: "🚰", label: "Report sewage", prompt: "Report sewage overflow near me" },
  { emoji: "📢", label: "Latest notices", prompt: "Latest notices" },
];

/**
 * Townhall page 1, laid out like the design's profile view: back button and name pill on top (pill
 * opens the guide card), the guide in full view with round action buttons down its right side, page
 * dots and a caption under it, and the chat card (prompt chips + message box with send and mic)
 * sitting right on top of the tab bar.
 */
export function GuideStage({
  avatar,
  chat,
  height,
  width,
  keyboardLift,
  pageIndex,
  onOpenCard,
  onNext,
  onChangeGuide,
  topInset,
}: {
  avatar: MainAvatar;
  chat: Chat;
  height: number;
  width: number;
  /** How far the keyboard overlaps this page (keyboard height minus the tab bar). */
  keyboardLift: number;
  /** Vertical page shown (for the dots under the avatar). */
  pageIndex: number;
  onOpenCard: () => void;
  onNext: () => void;
  onChangeGuide: () => void;
  topInset: number;
}) {
  const reduced = useReducedMotion();
  const { voice, listening, transcribing, busy, messages, lang } = chat;
  const talking = messages.length > 0 || keyboardLift > 0;
  const [dockH, setDockH] = useState(130);

  // The guide steps back (smaller, higher) while a conversation is on screen.
  const stage = useRef(new Animated.Value(talking ? 1 : 0)).current;
  useEffect(() => {
    if (reduced) stage.setValue(talking ? 1 : 0);
    else Animated.spring(stage, { toValue: talking ? 1 : 0, friction: 9, tension: 60, useNativeDriver: true }).start();
  }, [talking, reduced, stage]);

  const top = topInset + 10;
  const headerH = 44;
  const stageTop = top + headerH + 8;
  // Avatar fills the space between the header and the caption, which sits right on the chat card.
  const captionH = 50;
  const avail = height - stageTop - dockH - captionH - 8;
  const size = Math.max(160, Math.min(width * 0.96, avail));
  const stageH = avail; // avatar is centred in this band
  const mode: BubbleMode = listening ? "listening" : transcribing || busy ? "thinking" : voice.speakingId ? "speaking" : "idle";
  const threadMax = Math.max(120, height - stageTop - dockH - keyboardLift - size * 0.45);

  return (
    <View style={{ width, height, backgroundColor: colors.surface }}>
      {/* Header: name pill (opens the guide card) */}
      <View style={[styles.header, { top }]}>
        <Tap style={styles.pill} onPress={onOpenCard} accessibilityLabel={`${avatar.name}: open guide card`}>
          <Text style={styles.pillName}>{avatar.name}</Text>
          <View style={styles.pillFace}>
            <Image source={avatar.bust} style={{ width: 30, height: 30 }} contentFit="cover" />
          </View>
        </Tap>
      </View>

      {/* The guide, full view */}
      <Animated.View
        pointerEvents="box-none"
        style={[
          styles.stage,
          { top: stageTop, height: stageH, justifyContent: "center" },
          {
            transform: [
              { translateY: stage.interpolate({ inputRange: [0, 1], outputRange: [0, -size * 0.22] }) },
              { scale: stage.interpolate({ inputRange: [0, 1], outputRange: [1, 0.55] }) },
            ],
          },
        ]}
      >
        <BobbingAvatar avatar={avatar} size={size} variant="portrait" />
        <View style={[styles.bubble, { top: (stageH - size) / 2 + size * 0.02, left: width * 0.06 }]} pointerEvents="none">
          <AvatarBubbles mode={mode} phrases={talking ? [] : avatar.phrases[lang]} interval={4200} initialDelay={800} dark />
        </View>
      </Animated.View>

      {/* Page dots + caption, right above the chat card */}
      {!talking ? (
        <FadeIn from="none" style={[styles.caption, { bottom: dockH + 8 }]}>
          <PageDots count={3} index={pageIndex} />
          <View style={styles.captionRow}>
            <Ionicons name="star" size={15} color={colors.star} />
            <Text style={styles.captionStrong}>City Sense guide</Text>
            <Text style={styles.captionMuted}>(main agent · voice or text)</Text>
          </View>
        </FadeIn>
      ) : null}

      {/* Round actions down the right side, over the avatar like the design */}
      {!talking ? (
        <View style={[styles.rail, { top: stageTop + (stageH - size) / 2 + size * 0.36 }]}>
          <Round
            onPress={voice.toggleAutoPlay}
            a11y={voice.autoPlay ? "Mute voice replies" : "Unmute voice replies"}
            style={styles.roundOutline}
            icon={<Ionicons name={voice.autoPlay ? "volume-high-outline" : "volume-mute-outline"} size={22} color={colors.text} />}
          />
          <Tap feedback="dim" onPress={onNext} accessibilityLabel="Townhall" style={styles.saveItem}>
            <Ionicons name="business-outline" size={26} color={colors.text} />
            <Text style={styles.saveText}>Town</Text>
          </Tap>
          <Round
            onPress={() => chat.send("Show my complaints")}
            a11y="My complaints"
            style={{ backgroundColor: colors.primary }}
            icon={<Ionicons name="megaphone" size={20} color="#fff" />}
          />
          <Round
            onPress={() => chat.send("Latest notices")}
            a11y="Latest notices"
            style={[styles.roundOutline, { borderColor: colors.accentBlue }]}
            icon={<Ionicons name="newspaper-outline" size={20} color={colors.accentBlue} />}
          />
          <Round onPress={onChangeGuide} a11y="Change your guide" style={{ backgroundColor: colors.navy }} icon={<Ionicons name="swap-horizontal" size={20} color="#fff" />} />
          <Tap feedback="dim" onPress={onOpenCard} accessibilityLabel="More about your guide" hitSlop={8}>
            <Ionicons name="add-circle-outline" size={30} color={colors.text} />
          </Tap>
        </View>
      ) : null}

      {/* Conversation above the chat card */}
      {messages.length > 0 || busy ? (
        <View style={[styles.threadWrap, { bottom: dockH + keyboardLift + 6 }]}>
          <View style={styles.threadHead}>
            <Text style={styles.threadTitle}>Chat with {avatar.name}</Text>
            <Tap feedback="dim" hitSlop={10} onPress={chat.reset} accessibilityLabel="Start a new conversation">
              <Text style={styles.link}>New chat</Text>
            </Tap>
          </View>
          <ChatThread chat={chat} style={{ flex: 0, maxHeight: threadMax }} />
        </View>
      ) : null}

      {/* Chat card docked on the tab bar */}
      <View style={[styles.dock, { bottom: keyboardLift }]} onLayout={(e: LayoutChangeEvent) => setDockH(e.nativeEvent.layout.height)}>
        {!listening ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} keyboardShouldPersistTaps="handled">
            {CHIPS.map((c, i) => (
              <FadeIn key={c.label} index={i} from="below">
                <Tap style={styles.chip} onPress={() => chat.send(c.prompt)} disabled={busy} accessibilityLabel={c.label}>
                  <Text style={styles.chipText}>
                    {c.emoji} {c.label}
                  </Text>
                </Tap>
              </FadeIn>
            ))}
          </ScrollView>
        ) : null}
        <MessageBox chat={chat} />
      </View>
    </View>
  );
}

/** Grey message field with the send arrow and the mic side by side (waves fill it while listening). */
function MessageBox({ chat }: { chat: Chat }) {
  const [draft, setDraft] = useState("");
  const [width, setWidth] = useState(0);
  const { lang, listening, transcribing, busy, voice } = chat;
  const submit = () => {
    const t = draft.trim();
    if (!t) return;
    setDraft("");
    void chat.send(t);
  };
  return (
    <View style={styles.box} onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}>
      {(listening || transcribing) && width > 0 ? (
        <Waves width={width} height={50} level={voice.level} mode={listening ? "listening" : "thinking"} radius={14} />
      ) : null}
      <TextInput
        value={draft}
        onChangeText={setDraft}
        placeholder={listening ? (lang === "hi" ? "सुन रहा हूँ… भेजने के लिए ■" : "Listening… tap ■ to send") : lang === "hi" ? "अपना संदेश लिखें…" : "Type your message here..."}
        placeholderTextColor={listening ? colors.navy : "#7C7C86"}
        style={styles.boxInput}
        onSubmitEditing={submit}
        returnKeyType="send"
        maxLength={1000}
        editable={!listening && !transcribing}
      />
      <Tap feedback="dim" hitSlop={8} onPress={submit} disabled={busy || !draft.trim()} accessibilityLabel="Send">
        <Ionicons name="send-outline" size={21} color={draft.trim() ? colors.accentBlue : "#9DB6E8"} />
      </Tap>
      <Tap
        feedback="scale"
        style={[styles.mic, listening && { backgroundColor: colors.danger }]}
        onPress={chat.toggleMic}
        disabled={busy || transcribing}
        accessibilityLabel={listening ? "Stop and send" : "Speak"}
      >
        {transcribing ? (
          <ActivityIndicator size="small" color={colors.text} />
        ) : (
          <Ionicons name={listening ? "stop" : "mic"} size={21} color={listening ? "#fff" : colors.text} />
        )}
      </Tap>
    </View>
  );
}

function Round({ icon, onPress, a11y, style }: { icon: React.ReactNode; onPress: () => void; a11y: string; style?: object }) {
  return (
    <Tap feedback="scale" onPress={onPress} accessibilityLabel={a11y} style={[styles.round, style]}>
      {icon}
    </Tap>
  );
}

const styles = StyleSheet.create({
  header: { position: "absolute", left: 16, right: 16, height: 44, flexDirection: "row", alignItems: "center", justifyContent: "center", zIndex: 4 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: colors.navy,
    borderRadius: radius.pill,
    paddingLeft: 34,
    paddingRight: 6,
    height: 42,
  },
  pillName: { fontFamily: fonts.bold, fontSize: 17, color: "#fff" },
  pillFace: { width: 32, height: 32, borderRadius: 16, overflow: "hidden", backgroundColor: "#fff" },
  stage: { position: "absolute", left: 0, right: 0, alignItems: "center" },
  bubble: { position: "absolute" },
  caption: { position: "absolute", left: 0, right: 0, alignItems: "center", gap: 8, height: 50, justifyContent: "flex-end" },
  captionRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  captionStrong: { fontFamily: fonts.semibold, fontSize: 13, color: colors.text },
  captionMuted: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted },
  rail: { position: "absolute", right: 14, alignItems: "center", gap: 12, zIndex: 3 },
  round: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  roundOutline: { backgroundColor: "#fff", borderWidth: 1.5, borderColor: colors.border },
  saveItem: { alignItems: "center" },
  saveText: { fontFamily: fonts.medium, fontSize: 11, color: colors.textMuted },
  threadWrap: {
    position: "absolute",
    left: 12,
    right: 12,
    padding: 10,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.97)",
    borderWidth: 1,
    borderColor: colors.border,
    elevation: 4,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 2 },
  },
  threadHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 2 },
  threadTitle: { fontFamily: fonts.bold, fontSize: 13, color: colors.text },
  link: { fontFamily: fonts.bold, fontSize: 12, color: colors.accentBlue },
  dock: {
    position: "absolute",
    left: 10,
    right: 10,
    paddingHorizontal: 10,
    paddingTop: 10,
    paddingBottom: 10,
    gap: 8,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: colors.border,
    elevation: 8,
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: -2 },
  },
  chips: { gap: 6 },
  chip: { backgroundColor: colors.chip, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6 },
  chipText: { fontFamily: fonts.medium, fontSize: 12, color: colors.text },
  box: {
    height: 50,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: "#EEF0F4",
    borderRadius: 14,
    paddingLeft: 14,
    paddingRight: 6,
    overflow: "hidden",
  },
  boxInput: { flex: 1, fontFamily: fonts.regular, fontSize: 15, color: colors.text },
  mic: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
});

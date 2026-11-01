import { Ionicons } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, ScrollView, type ScrollViewInstance, StyleSheet, Text, TextInput, View } from "react-native";
import { errorMessage } from "../api/client";
import { agentApi } from "../api/endpoints";
import type { AgentReply, PlanStep } from "../api/types";
import { useVoice } from "../hooks/useVoice";
import { PendingActionCard } from "./PendingActionCard";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";

type Point = { latitude: number; longitude: number };
type Turn = { id: string; question?: string; reply?: AgentReply; error?: string; confirmed?: string };

const EXECUTOR: Record<string, string> = {
  main_voice_agent: "City Sense",
  city_pulse: "City Pulse",
  knowledge_specialist: "Knowledge desk",
  civic_complaint: "Complaint desk",
  emergency_traffic: "Emergency desk",
};

/** Strip the light markdown the agent uses so the sheet reads as plain prose. */
const plain = (t: string) => t.replace(/\*\*/g, "").replace(/^#+\s*/gm, "").replace(/`/g, "");

/**
 * Tap-anywhere briefing from the main agent (City Sense): what this place is, live conditions and
 * civic info. Follow-up questions go through the full agent hierarchy with the spot as context.
 */
export function PlaceSheet({ point, language, onClose }: { point: Point; language: string; onClose: () => void }) {
  const voice = useVoice(language);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const session = useRef<string | undefined>(undefined);
  const label = useRef<string | undefined>(undefined);
  const scroll = useRef<ScrollViewInstance>(null);
  const lang = language === "hi" ? "hi" : "en";

  // Answers for an earlier tapped point (or a closed sheet) are dropped when they arrive late.
  const pointSeq = useRef(0);

  const ask = async (question?: string) => {
    const mySeq = pointSeq.current;
    const id = `${Date.now()}`;
    setTurns((t) => [...t, { id, question }]);
    setBusy(true);
    try {
      const reply = await agentApi.place({
        latitude: point.latitude,
        longitude: point.longitude,
        label: label.current,
        question,
        sessionId: session.current,
        language: lang,
      });
      if (mySeq !== pointSeq.current) return;
      session.current = reply.sessionId;
      label.current ??= reply.actionData?.place?.label;
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, reply } : x)));
      // No auto-play here: a map tap is exploratory, so the briefing is read aloud only when the
      // citizen taps ▶ (or speaks a follow-up question, where a spoken reply is expected).
      if (question && voice.autoPlay && reply.answer) void voice.speak(id, plain(reply.answer));
    } catch (e) {
      if (mySeq !== pointSeq.current) return;
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: errorMessage(e) } : x)));
    } finally {
      if (mySeq === pointSeq.current) setBusy(false);
    }
  };

  // New spot -> fresh briefing.
  useEffect(() => {
    pointSeq.current++;
    session.current = undefined;
    label.current = undefined;
    setTurns([]);
    setBusy(false);
    void ask();
    return () => {
      pointSeq.current++;
      voice.stopSpeaking();
    };
  }, [point.latitude, point.longitude]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = () => {
    const q = draft.trim();
    if (!q || busy) return;
    setDraft("");
    void ask(q);
  };

  const title = label.current ?? turns[0]?.reply?.actionData?.place?.label;

  return (
    <FadeIn from="below" style={styles.sheet}>
      <View style={styles.header}>
        <View style={styles.badge}>
          <Ionicons name="sparkles" size={14} color="#fff" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>City Sense · main agent</Text>
          <Text style={styles.title} numberOfLines={1}>
            {title ? `Near ${title}` : "Looking at this spot…"}
          </Text>
        </View>
        <Tap feedback="dim" hitSlop={10} onPress={voice.toggleAutoPlay} accessibilityLabel={voice.autoPlay ? "Mute voice" : "Unmute voice"}>
          <Ionicons name={voice.autoPlay ? "volume-high" : "volume-mute"} size={20} color={colors.navy} />
        </Tap>
        <Tap feedback="dim" hitSlop={10} onPress={onClose} accessibilityLabel="Close">
          <Ionicons name="close" size={22} color={colors.textMuted} />
        </Tap>
      </View>

      <ScrollView ref={scroll} style={styles.body} contentContainerStyle={{ gap: 10, paddingBottom: 6 }}
        onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}>
        {turns.map((t) => (
          <View key={t.id} style={{ gap: 6 }}>
            {t.question ? <Text style={styles.question}>{t.question}</Text> : null}
            {t.error ? <Text style={styles.error}>⚠️ {t.error}</Text> : null}
            {!t.reply && !t.error ? (
              <View style={styles.row}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={styles.muted}>{t.question ? "Thinking…" : "Checking weather, air, alerts and civic info here…"}</Text>
              </View>
            ) : null}
            {t.reply ? (
              <>
                <Text style={styles.answer}>{plain(t.reply.answer)}</Text>
                <Steps steps={t.reply.plan} />
                <View style={styles.row}>
                  <Tap feedback="dim" hitSlop={8} onPress={() => (voice.speakingId === t.id ? voice.stopSpeaking() : voice.speak(t.id, plain(t.reply!.answer)))}
                    accessibilityLabel="Read aloud">
                    <Ionicons name={voice.speakingId === t.id ? "stop-circle-outline" : "play-circle-outline"} size={20} color={colors.accentBlue} />
                  </Tap>
                  {t.confirmed ? <Text style={styles.muted}>{t.confirmed}</Text> : null}
                </View>
                {t.reply.pendingAction && !t.confirmed ? (
                  <PendingActionCard
                    pending={t.reply.pendingAction}
                    onDone={(o) => setTurns((all) => all.map((x) => (x.id === t.id ? { ...x, confirmed: o } : x)))}
                    compact
                  />
                ) : null}
              </>
            ) : null}
          </View>
        ))}
      </ScrollView>

      <View style={styles.inputRow}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Ask about this place… (traffic, report an issue)"
          placeholderTextColor="#8A8A95"
          style={styles.input}
          onSubmitEditing={send}
          returnKeyType="send"
          maxLength={500}
          editable={!busy}
        />
        <Tap feedback="dim" onPress={send} disabled={!draft.trim() || busy} hitSlop={8} accessibilityLabel="Ask City Sense">
          <Ionicons name="send" size={20} color={draft.trim() && !busy ? colors.accentBlue : "#B8C7E8"} />
        </Tap>
      </View>
    </FadeIn>
  );
}

function Steps({ steps }: { steps?: PlanStep[] | null }) {
  if (!steps?.length) return null;
  return (
    <View style={styles.steps}>
      {steps.map((s) => (
        <Text key={s.id} style={styles.step}>
          {s.status === "completed" ? "✓" : s.status === "failed" ? "✕" : "•"} {EXECUTOR[s.executor] ?? s.executor}: {s.action}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    position: "absolute",
    left: 10,
    right: 10,
    bottom: 96,
    maxHeight: "58%",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingTop: 12,
    paddingHorizontal: 14,
    paddingBottom: 10,
    elevation: 8,
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 4 },
    gap: 8,
  },
  header: { flexDirection: "row", alignItems: "center", gap: 10 },
  badge: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.accentBlue, alignItems: "center", justifyContent: "center" },
  kicker: { fontFamily: fonts.medium, fontSize: 11, color: colors.textMuted },
  title: { fontFamily: fonts.bold, fontSize: 16, color: colors.text },
  body: { flexGrow: 0 },
  question: { alignSelf: "flex-end", backgroundColor: colors.primary, color: "#fff", fontFamily: fonts.medium, fontSize: 13,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, overflow: "hidden", maxWidth: "88%" },
  answer: { fontFamily: fonts.regular, fontSize: 14, lineHeight: 20, color: colors.text },
  error: { fontFamily: fonts.medium, fontSize: 13, color: colors.danger },
  muted: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  steps: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 6, gap: 1 },
  step: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: colors.surfaceAlt, borderRadius: radius.md,
    paddingHorizontal: 12, height: 44 },
  input: { flex: 1, fontFamily: fonts.regular, fontSize: 14, color: colors.text },
});

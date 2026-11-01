import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useEffect, useRef } from "react";
import { Animated, BackHandler, ScrollView, StyleSheet, Text, View } from "react-native";
import type { Avatar } from "../api/types";
import { BobbingAvatar } from "../assistant/AssistantLayer";
import { absoluteUrl } from "../config";
import type { MainAvatar } from "../content/mainAvatars";
import { useReducedMotion } from "../motion";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";

/** Skill tiles shown in the gallery after the local places. */
const SKILLS: { icon: keyof typeof Ionicons.glyphMap; label: string; prompt: string; bg: string }[] = [
  { icon: "megaphone", label: "Report issues", prompt: "I want to report a civic issue near me", bg: "#9A2143" },
  { icon: "calendar", label: "Events", prompt: "What's happening in Dehradun this month?", bg: "#E59E0B" },
  { icon: "cafe", label: "Local picks", prompt: "Recommend a good place to eat nearby", bg: "#2E9E5B" },
  { icon: "newspaper", label: "Notices", prompt: "Latest notices", bg: "#1D2B4F" },
];

/**
 * The guide's card (opened from the name pill), laid out like the design's profile card: back button,
 * card with the guide, verified name pill, description, stats + action, a picture gallery (places the
 * guide knows), and a row of round buttons under the card.
 */
export function GuideCard({
  avatar,
  visible,
  topInset,
  places,
  onClose,
  onAsk,
  onChangeGuide,
  messageCount,
  lang,
  onToggleLanguage,
  autoPlay,
  onToggleVoice,
}: {
  avatar: MainAvatar;
  visible: boolean;
  topInset: number;
  places: Avatar[];
  onClose: () => void;
  onAsk: (prompt: string) => void;
  onChangeGuide: () => void;
  messageCount: number;
  lang: "hi" | "en";
  onToggleLanguage: () => void;
  autoPlay: boolean;
  onToggleVoice: () => void;
}) {
  const reduced = useReducedMotion();
  const enter = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!visible) return;
    enter.setValue(reduced ? 1 : 0);
    if (!reduced) Animated.spring(enter, { toValue: 1, friction: 9, tension: 70, useNativeDriver: true }).start();
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      close();
      return true;
    });
    return () => sub.remove();
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => {
    if (reduced) return onClose();
    Animated.timing(enter, { toValue: 0, duration: 170, useNativeDriver: true }).start(onClose);
  };
  if (!visible) return null;

  const ask = (prompt: string) => {
    onClose();
    onAsk(prompt);
  };

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.page, { paddingTop: topInset + 10, opacity: enter }]}>
      <Tap feedback="scale" style={styles.back} onPress={close} accessibilityLabel="Back">
        <Ionicons name="return-up-back" size={22} color="#fff" />
      </Tap>

      <Animated.View
        style={[
          styles.card,
          {
            transform: [
              { translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [-60, 0] }) },
              { scale: enter.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] }) },
            ],
          },
        ]}
      >
        <View style={styles.portrait}>
          <BobbingAvatar avatar={avatar} size={190} variant="portrait" />
        </View>
        <View style={styles.nameRow}>
          <Ionicons name="checkmark-circle" size={24} color={colors.success} />
          <View style={styles.namePill}>
            <Text style={styles.name}>{avatar.name}</Text>
          </View>
        </View>
        <Text style={styles.desc}>
          Your City Sense guide for Dehradun. {avatar.tagline}. Ask about complaints, notices, events, places and the map.
        </Text>

        <View style={styles.statsRow}>
          <View style={styles.stat} accessibilityLabel="4 specialist desks">
            <Ionicons name="person-outline" size={16} color={colors.textMuted} />
            <Text style={styles.statValue}>4</Text>
            <Text style={styles.statLabel}>desks</Text>
          </View>
          <View style={styles.stat} accessibilityLabel={`${messageCount} messages`}>
            <Ionicons name="copy-outline" size={16} color={colors.textMuted} />
            <Text style={styles.statValue}>{messageCount}</Text>
            <Text style={styles.statLabel}>messages</Text>
          </View>
          <Tap style={styles.changeBtn} onPress={onChangeGuide} accessibilityLabel="Change guide">
            <Text style={styles.changeText}>Change</Text>
            <Ionicons name="add" size={18} color={colors.text} />
          </Tap>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.gallery} style={styles.galleryWrap}>
          {places.slice(0, 6).map((p, i) => (
            <FadeIn key={p.id} index={i} from="below">
              <Tap
                style={styles.tile}
                onPress={() => {
                  onClose();
                  router.push({ pathname: "/avatar/[id]", params: { id: p.id } });
                }}
                accessibilityLabel={`${p.name}, ${p.title}`}
              >
                <Image source={{ uri: absoluteUrl(p.heroImageUrl || p.pinImageUrl) }} style={StyleSheet.absoluteFill} contentFit="cover" />
                <View style={styles.tileShade}>
                  <Text style={styles.tileText} numberOfLines={1}>
                    {p.name}
                  </Text>
                </View>
              </Tap>
            </FadeIn>
          ))}
          {SKILLS.map((s, i) => (
            <FadeIn key={s.label} index={places.length + i} from="below">
              <Tap style={[styles.tile, { backgroundColor: s.bg, padding: 10, justifyContent: "space-between" }]} onPress={() => ask(s.prompt)} accessibilityLabel={s.label}>
                <Ionicons name={s.icon} size={28} color="#fff" />
                <Text style={styles.tileText}>{s.label}</Text>
              </Tap>
            </FadeIn>
          ))}
        </ScrollView>
      </Animated.View>

      {/* Round buttons under the card */}
      <FadeIn from="below" delay={160} style={styles.actions}>
        <RoundAction icon={autoPlay ? "volume-high" : "volume-mute"} bg={colors.navy} onPress={onToggleVoice} a11y={autoPlay ? "Mute voice" : "Unmute voice"} />
        <Tap style={[styles.round, { backgroundColor: colors.primary }]} onPress={onToggleLanguage} accessibilityLabel="Switch language">
          <Text style={styles.roundText}>{lang === "hi" ? "EN" : "हि"}</Text>
        </Tap>
        <RoundAction icon="chatbubble-ellipses" bg={colors.success} onPress={() => ask("Introduce yourself")} a11y="Ask the guide to introduce themselves" />
        <RoundAction icon="map" bg={colors.warning} onPress={() => ask("Show Clock Tower on the map")} a11y="Show the map" />
        <Tap feedback="dim" onPress={onChangeGuide} accessibilityLabel="Change guide" hitSlop={8}>
          <Ionicons name="add-circle-outline" size={32} color={colors.text} />
        </Tap>
      </FadeIn>
    </Animated.View>
  );
}

function RoundAction({ icon, bg, onPress, a11y }: { icon: keyof typeof Ionicons.glyphMap; bg: string; onPress: () => void; a11y: string }) {
  return (
    <Tap style={[styles.round, { backgroundColor: bg }]} onPress={onPress} accessibilityLabel={a11y}>
      <Ionicons name={icon} size={24} color="#fff" />
    </Tap>
  );
}

const styles = StyleSheet.create({
  page: { backgroundColor: colors.surface, paddingHorizontal: 22, zIndex: 20 },
  back: { width: 44, height: 40, borderRadius: 10, backgroundColor: "#9E9E9E", alignItems: "center", justifyContent: "center", marginBottom: 6 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 32,
    paddingTop: 14,
    paddingBottom: 18,
    paddingHorizontal: 18,
    borderWidth: 1,
    borderColor: "#ECECF1",
    elevation: 10,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 6 },
  },
  portrait: { alignItems: "center", height: 200, justifyContent: "center" },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 6 },
  namePill: { flex: 1, backgroundColor: colors.navy, borderRadius: radius.pill, paddingVertical: 6, alignItems: "center", marginRight: 30 },
  name: { fontFamily: fonts.bold, fontSize: 18, color: "#fff" },
  desc: { marginTop: 10, fontFamily: fonts.regular, fontSize: 14, lineHeight: 20, color: colors.textMuted },
  statsRow: { flexDirection: "row", alignItems: "center", gap: 18, marginTop: 14 },
  stat: { flexDirection: "row", alignItems: "center", gap: 6 },
  statValue: { fontFamily: fonts.bold, fontSize: 15, color: colors.text },
  statLabel: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  changeBtn: {
    marginLeft: "auto",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#EFEFF2",
    borderRadius: radius.pill,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  changeText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.text },
  galleryWrap: { marginTop: 16, marginHorizontal: -18 },
  gallery: { gap: 10, paddingHorizontal: 18 },
  tile: { width: 112, height: 112, borderRadius: 12, overflow: "hidden", backgroundColor: colors.surfaceAlt },
  tileShade: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 8, paddingVertical: 5, backgroundColor: "rgba(0,0,0,0.35)" },
  tileText: { fontFamily: fonts.bold, fontSize: 12, color: "#fff" },
  actions: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 10, marginTop: 18 },
  round: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  roundText: { fontFamily: fonts.bold, fontSize: 17, color: "#fff" },
});

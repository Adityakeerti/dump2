import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Alert, Animated, ScrollView, StyleSheet, Text, View } from "react-native";
import { useAssistant } from "../../assistant/AssistantContext";
import { AvatarChooser, BobbingAvatar } from "../../assistant/AssistantLayer";
import { useAuth } from "../../auth/AuthContext";
import { mainAvatarById } from "../../content/mainAvatars";
import { Card } from "../../components/Card";
import { ScreenHeader } from "../../components/ScreenHeader";
import { config } from "../../config";
import { images } from "../../content/onboarding";
import { duration, timing, useReducedMotion } from "../../motion";
import { FadeIn } from "../../motion/FadeIn";
import { Tap } from "../../motion/Tap";
import { colors, fonts, radius } from "../../theme";

/** Chat reply languages the core agent supports. */
const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिन्दी" },
];

export default function Settings() {
  const { user, language, setLanguage, signOut } = useAuth();
  const { avatarId, chooseAvatar } = useAssistant();
  const [choosing, setChoosing] = useState(false);
  if (!user) return null;
  const guide = mainAvatarById(avatarId);

  const logout = () =>
    Alert.alert("Log out?", "You'll need to sign in again.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Log out",
        style: "destructive",
        onPress: async () => {
          await signOut();
          router.replace("/welcome");
        },
      },
    ]);

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Settings" />
      <ScrollView contentContainerStyle={styles.content}>
        <FadeIn index={0}>
        <Card style={styles.profile}>
          <Image source={images.faceBoy} style={styles.photo} contentFit="cover" />
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{user.fullName}</Text>
            <Text style={styles.email}>{user.email}</Text>
            <View style={styles.badges}>
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{user.role.toLowerCase()}</Text>
              </View>
              {user.emailVerified ? (
                <View style={[styles.badge, { backgroundColor: "#E5F6EC" }]}>
                  <Ionicons name="checkmark-circle" size={12} color={colors.success} />
                  <Text style={[styles.badgeText, { color: colors.success }]}>verified</Text>
                </View>
              ) : null}
            </View>
          </View>
        </Card>
        </FadeIn>

        <Text style={styles.section}>City Sense guide</Text>
        <FadeIn index={1}>
        <Tap style={styles.guideRow} onPress={() => setChoosing(true)} accessibilityLabel={`City Sense guide: ${guide.name}. Change`}>
          <BobbingAvatar avatar={guide} size={44} />
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{guide.name}</Text>
            <Text style={styles.email}>{guide.tagline}</Text>
          </View>
          <Text style={styles.guideChange}>Change</Text>
        </Tap>
        </FadeIn>

        <Text style={styles.section}>Chat language</Text>
        <Segmented options={LANGUAGES} value={language} onChange={setLanguage} />

        <Text style={styles.section}>About</Text>
        <Card style={{ padding: 0 }}>
          <Row icon="server-outline" label="Server" value={config.apiBaseUrl} />
          <Row icon="map-outline" label="Map data" value="© OpenStreetMap contributors · OpenFreeMap" />
        </Card>

        <Tap style={styles.logout} onPress={logout} accessibilityLabel="Log out">
          <Ionicons name="log-out-outline" size={20} color={colors.danger} />
          <Text style={styles.logoutText}>Log out</Text>
        </Tap>
      </ScrollView>
      {choosing ? (
        <AvatarChooser
          onChoose={(id) => {
            void chooseAvatar(id);
            setChoosing(false);
          }}
          onCancel={() => setChoosing(false)}
        />
      ) : null}
    </View>
  );
}

/** Two-way switch whose thumb slides to the chosen option, like a native segmented control. */
function Segmented({ options, value, onChange }: { options: { code: string; label: string }[]; value: string; onChange: (code: string) => void }) {
  const reduced = useReducedMotion();
  const [width, setWidth] = useState(0);
  const x = useRef(new Animated.Value(0)).current;
  const placed = useRef(false);
  const segW = width > 0 ? (width - SEG_PAD * 2) / options.length : 0;
  const index = Math.max(0, options.findIndex((o) => o.code === value));

  useEffect(() => {
    if (!segW) return;
    const to = index * segW;
    // First placement (and reduce motion) snaps; later changes slide.
    if (!placed.current || reduced) {
      x.setValue(to);
      placed.current = true;
    } else {
      timing(x, to, { duration: duration.fast, curve: "move" }).start();
    }
  }, [index, segW, reduced, x]);

  return (
    <View style={styles.segment} onLayout={(e) => setWidth(e.nativeEvent.layout.width)} accessibilityRole="radiogroup">
      {segW > 0 ? <Animated.View style={[styles.segThumb, { width: segW, transform: [{ translateX: x }] }]} /> : null}
      {options.map((o) => (
        <Tap
          key={o.code}
          feedback="dim"
          style={styles.segBtn}
          onPress={() => onChange(o.code)}
          accessibilityRole="radio"
          accessibilityState={{ selected: value === o.code }}
          accessibilityLabel={o.label}
        >
          <Text style={[styles.segText, value === o.code && styles.segTextActive]}>{o.label}</Text>
        </Tap>
      ))}
    </View>
  );
}

function Row({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={18} color={colors.textMuted} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const SEG_PAD = 4;

const styles = StyleSheet.create({
  guideRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 12,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  guideChange: { fontFamily: fonts.bold, fontSize: 13, color: colors.accentBlue },
  fill: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 20, paddingBottom: 40, gap: 12 },
  profile: { flexDirection: "row", alignItems: "center", gap: 16 },
  photo: { width: 64, height: 64, borderRadius: 32, backgroundColor: "#E2A4F0" },
  name: { fontFamily: fonts.bold, fontSize: 18, color: colors.text },
  email: { fontFamily: fonts.regular, fontSize: 13, color: colors.textMuted },
  badges: { flexDirection: "row", gap: 6, marginTop: 6 },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.surfaceAlt, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontFamily: fonts.semibold, fontSize: 11, color: colors.textMuted },
  section: { fontFamily: fonts.bold, fontSize: 15, color: colors.text, marginTop: 8 },
  segment: { flexDirection: "row", backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: SEG_PAD },
  segBtn: { flex: 1, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.sm },
  segThumb: {
    position: "absolute",
    top: SEG_PAD,
    left: SEG_PAD,
    bottom: SEG_PAD,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    elevation: 1,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 4,
  },
  segText: { fontFamily: fonts.medium, color: colors.textMuted },
  segTextActive: { color: colors.primary, fontFamily: fonts.bold },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 14 },
  rowLabel: { fontFamily: fonts.medium, color: colors.text },
  rowValue: { flex: 1, textAlign: "right", fontFamily: fonts.regular, color: colors.textMuted, fontSize: 13 },
  logout: { flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", marginTop: 16, height: 48, borderRadius: radius.sm, borderWidth: 1, borderColor: "#F3C9C9" },
  logoutText: { fontFamily: fonts.bold, color: colors.danger },
});

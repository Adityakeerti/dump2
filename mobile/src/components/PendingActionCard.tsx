import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { errorMessage } from "../api/client";
import { agentApi } from "../api/endpoints";
import type { PendingAgentAction } from "../api/types";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";

type PhotoState = "none" | "uploading" | "attached" | "error";

/**
 * A complaint the agent drafted, waiting for the citizen: optional camera photo (stored in the
 * database and sent with the complaint), then Confirm or Cancel. The agent never files on its own.
 */
export function PendingActionCard({
  pending,
  onDone,
  compact = false,
}: {
  pending: PendingAgentAction;
  /** Called with a one-line outcome ("Filed · CMP-…", "Discarded", "⚠️ …"). */
  onDone: (outcome: string) => void;
  compact?: boolean;
}) {
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [photo, setPhoto] = useState<PhotoState>("none");
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);

  const takePhoto = async () => {
    setPhotoError(null);
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      setPhotoError("Camera permission is needed to add a photo.");
      return;
    }
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.6, exif: false });
    if (shot.canceled || !shot.assets?.[0]) return;
    const uri = shot.assets[0].uri;
    setPhotoUri(uri);
    setPhoto("uploading");
    try {
      await agentApi.attachPhoto(pending.token, uri);
      setPhoto("attached");
    } catch (e) {
      setPhoto("error");
      setPhotoError(errorMessage(e));
    }
  };

  const decide = async (confirm: boolean) => {
    setBusy(confirm ? "confirm" : "cancel");
    try {
      const r = confirm ? await agentApi.confirm(pending.token) : await agentApi.cancel(pending.token);
      if (r.status === "executed") {
        const worker = r.result?.assignedWorker ? ` · ${r.result.assignedWorker}` : "";
        const pic = r.result?.photoAttached ? " · photo attached" : "";
        onDone(`✅ Filed · ${r.result?.trackingId ?? ""}${worker}${pic}`);
      } else if (r.status === "cancelled") onDone("Draft discarded.");
      else onDone(`⚠️ ${r.detail ?? r.status}`);
    } catch (e) {
      setBusy(null);
      setPhotoError(errorMessage(e));
    }
  };

  return (
    <FadeIn from="below" style={[styles.card, compact && { padding: 8 }]}>
      <View style={styles.titleRow}>
        <Ionicons name="document-text-outline" size={15} color={colors.navy} />
        <Text style={styles.title}>Complaint draft</Text>
      </View>
      <Text style={styles.summary} numberOfLines={compact ? 3 : 5}>
        {pending.summary}
      </Text>

      {photoUri ? (
        <View style={styles.photoRow}>
          <Image source={{ uri: photoUri }} style={styles.thumb} contentFit="cover" />
          <Text style={styles.photoText}>
            {photo === "uploading" ? "Uploading photo…" : photo === "attached" ? "Photo attached ✓" : "Photo not uploaded"}
          </Text>
          {photo === "uploading" ? <ActivityIndicator size="small" color={colors.primary} /> : null}
          {photo !== "uploading" ? (
            <Tap feedback="dim" hitSlop={8} onPress={takePhoto} accessibilityLabel="Retake photo">
              <Text style={styles.link}>Retake</Text>
            </Tap>
          ) : null}
        </View>
      ) : (
        <Tap
          style={[styles.photoBtn, pending.photoSuggested && styles.photoBtnSuggested]}
          onPress={takePhoto}
          disabled={busy !== null}
          accessibilityLabel="Take a photo of the issue"
        >
          <Ionicons name="camera" size={16} color={pending.photoSuggested ? "#fff" : colors.navy} />
          <Text style={[styles.photoBtnText, pending.photoSuggested && { color: "#fff" }]}>
            {pending.photoSuggested ? "Add a photo (recommended)" : "Add a photo"}
          </Text>
        </Tap>
      )}
      {photoError ? <Text style={styles.error}>{photoError}</Text> : null}

      <View style={styles.actions}>
        <Tap
          style={[styles.btn, { backgroundColor: colors.success }]}
          onPress={() => decide(true)}
          disabled={busy !== null || photo === "uploading"}
          accessibilityLabel="Confirm and file complaint"
        >
          {busy === "confirm" ? <ActivityIndicator size="small" color="#fff" /> : <Text style={styles.btnText}>Confirm & file</Text>}
        </Tap>
        <Tap style={[styles.btn, { backgroundColor: "#9A9AA3" }]} onPress={() => decide(false)} disabled={busy !== null} accessibilityLabel="Discard draft">
          <Text style={styles.btnText}>Cancel</Text>
        </Tap>
      </View>
    </FadeIn>
  );
}

const styles = StyleSheet.create({
  card: { marginTop: 8, padding: 10, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, gap: 8 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  title: { fontFamily: fonts.bold, fontSize: 13, color: colors.navy },
  summary: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted, lineHeight: 17 },
  photoBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    alignSelf: "flex-start",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.navy,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  photoBtnSuggested: { backgroundColor: colors.navy },
  photoBtnText: { fontFamily: fonts.semibold, fontSize: 12, color: colors.navy },
  photoRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  thumb: { width: 54, height: 54, borderRadius: 10, backgroundColor: colors.surfaceAlt },
  photoText: { flex: 1, fontFamily: fonts.medium, fontSize: 12, color: colors.text },
  link: { fontFamily: fonts.bold, fontSize: 12, color: colors.accentBlue },
  error: { fontFamily: fonts.medium, fontSize: 12, color: colors.danger },
  actions: { flexDirection: "row", gap: 8 },
  btn: { flex: 1, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  btnText: { fontFamily: fonts.bold, fontSize: 13, color: "#fff" },
});

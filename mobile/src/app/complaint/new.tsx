import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { errorMessage } from "../../api/client";
import { civicApi, geoApi } from "../../api/endpoints";
import { AuthHeader } from "../../components/AuthHeader";
import { Button } from "../../components/Button";
import { LinkText } from "../../components/LinkText";
import { ErrorBanner } from "../../components/StateViews";
import { TextField } from "../../components/TextField";
import { useKeyboardHeight } from "../../hooks/useKeyboardHeight";
import { useUserLocation } from "../../hooks/useUserLocation";
import { FadeIn } from "../../motion/FadeIn";
import { Tap } from "../../motion/Tap";
import { colors, fonts, radius } from "../../theme";

/** Issues a field crew needs to see: suggest a photo for these. */
const PHOTO_HELPS = /sewage|sewer|drain|overflow|garbage|trash|waste|dump|pothole|pot hole|water ?logging|leak|broken|damaged|fallen|streetlight|street light|nala|naali|kooda|गड्ढा|कूड़ा|नाली|सीवर/i;

export default function NewComplaint() {
  const keyboard = useKeyboardHeight();
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const { coords, status, refresh } = useUserLocation();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [address, setAddress] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!coords) return;
    geoApi
      .reverse(coords.latitude, coords.longitude)
      .then((p) => setAddress(p.displayName))
      .catch(() => setAddress(null));
  }, [coords]);

  const submit = async () => {
    if (!title.trim() || !description.trim()) return setError("Add a title and a short description");
    if (!coords) return setError("We need your location to route the complaint to the right ward");
    setBusy(true);
    setError(null);
    try {
      const c = await civicApi.file({
        title: title.trim(),
        description: description.trim(),
        latitude: coords.latitude,
        longitude: coords.longitude,
        address: address ?? undefined,
        photoUri: photoUri ?? undefined,
      });
      router.replace({ pathname: "/complaint/[trackingId]", params: { trackingId: c.trackingId } });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const takePhoto = async () => {
    setError(null);
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return setError("Camera permission is needed to add a photo.");
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.6, exif: false });
    if (!shot.canceled && shot.assets?.[0]) setPhotoUri(shot.assets[0].uri);
  };
  const photoSuggested = PHOTO_HELPS.test(`${title} ${description}`);

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: 32 + keyboard }]} keyboardShouldPersistTaps="handled">
          <AuthHeader title="Report an issue" fallback="/townhall" />
          <TextField label="What's wrong?" placeholder="e.g. Deep pothole near the bus stop" value={title} onChangeText={setTitle} maxLength={255} />
          <TextField
            label="Details"
            placeholder="Describe the problem and any landmark"
            value={description}
            onChangeText={setDescription}
            multiline
            style={{ height: 110, paddingTop: 12, textAlignVertical: "top" }}
          />

          <Text style={styles.label}>Photo {photoSuggested && !photoUri ? <Text style={styles.recommended}>· recommended for this issue</Text> : null}</Text>
          {photoUri ? (
            <FadeIn from="below" style={styles.photoRow}>
              <Image source={{ uri: photoUri }} style={styles.thumb} contentFit="cover" />
              <View style={{ flex: 1, gap: 6 }}>
                <Text style={styles.locationText}>Photo attached. It is stored with your complaint.</Text>
                <View style={{ flexDirection: "row", gap: 16 }}>
                  <LinkText style={styles.retry} onPress={() => void takePhoto()}>
                    Retake
                  </LinkText>
                  <LinkText style={[styles.retry, { color: colors.textMuted }]} onPress={() => setPhotoUri(null)}>
                    Remove
                  </LinkText>
                </View>
              </View>
            </FadeIn>
          ) : (
            <Tap style={[styles.photoBtn, photoSuggested && styles.photoBtnOn]} onPress={takePhoto} accessibilityLabel="Take a photo of the issue">
              <Ionicons name="camera" size={20} color={photoSuggested ? "#fff" : colors.navy} />
              <Text style={[styles.photoText, photoSuggested && { color: "#fff" }]}>Click a photo</Text>
            </Tap>
          )}

          <Text style={[styles.label, { marginTop: 16 }]}>Location</Text>
          <View style={styles.location}>
            <Ionicons name="location" size={18} color={colors.primary} />
            <Text style={styles.locationText} numberOfLines={2}>
              {coords
                ? (address ?? `${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`)
                : status === "pending"
                  ? "Finding your location…"
                  : "Location unavailable"}
            </Text>
            {!coords && status !== "pending" ? (
              <LinkText style={styles.retry} onPress={() => void refresh()}>
                Retry
              </LinkText>
            ) : null}
          </View>
          <Text style={styles.hint}>The department and priority are picked automatically from your description.</Text>

          {error ? <ErrorBanner message={error} /> : null}
          <Button title="Submit complaint" onPress={submit} loading={busy} style={{ marginTop: 12 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 24, paddingBottom: 32 },
  label: { fontFamily: fonts.medium, fontSize: 14, color: colors.text, marginBottom: 8 },
  location: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt },
  locationText: { flex: 1, fontFamily: fonts.regular, color: colors.text, fontSize: 13 },
  retry: { fontFamily: fonts.bold, color: colors.primary },
  recommended: { fontFamily: fonts.medium, fontSize: 12, color: colors.primary },
  photoBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    height: 52,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.navy,
  },
  photoBtnOn: { backgroundColor: colors.navy, borderStyle: "solid" },
  photoText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.navy },
  photoRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 10, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt },
  thumb: { width: 72, height: 72, borderRadius: 10, backgroundColor: colors.border },
  hint: { fontFamily: fonts.regular, color: colors.textMuted, fontSize: 12, marginTop: 8, marginBottom: 8 },
});

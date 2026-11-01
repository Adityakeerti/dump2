import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { Tap } from "../motion/Tap";
import { colors, fonts } from "../theme";

/** `fallback` is where Back goes when there is no history (e.g. the screen was opened from a cold start). */
export function AuthHeader({ title, back = true, fallback = "/welcome" }: { title: string; back?: boolean; fallback?: string }) {
  const goBack = () => (router.canGoBack() ? router.back() : router.replace(fallback as never));
  return (
    <View style={styles.row}>
      {back ? (
        <Tap feedback="dim" onPress={goBack} hitSlop={12} accessibilityLabel="Back" style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Tap>
      ) : null}
      <Text style={styles.title} accessibilityRole="header">
        {title}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { alignItems: "center", justifyContent: "center", marginTop: 48, marginBottom: 32 },
  back: { position: "absolute", left: 0 },
  title: { fontFamily: fonts.bold, fontSize: 26, color: colors.text },
});

import { DMSerifDisplay_400Regular } from "@expo-google-fonts/dm-serif-display";
import {
  Urbanist_400Regular,
  Urbanist_500Medium,
  Urbanist_600SemiBold,
  Urbanist_700Bold,
} from "@expo-google-fonts/urbanist";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { config, isConfigured } from "../config";
import { duration, useMotion } from "../motion";
import { splashHiding } from "../motion/splash";
import { colors } from "../theme";

SplashScreen.preventAutoHideAsync().catch(() => {});
// Dissolve into the first screen instead of cutting (Android fades by default; this matches iOS and the timing).
SplashScreen.setOptions({ fade: true, duration: duration.base });

function RootStack() {
  const { ready } = useAuth();
  const [fontsLoaded] = useFonts({
    DMSerifDisplay_400Regular,
    Urbanist_400Regular,
    Urbanist_500Medium,
    Urbanist_600SemiBold,
    Urbanist_700Bold,
  });
  const loaded = ready && fontsLoaded;
  // Native push transitions stay as they are; reduce motion swaps the slide for a cross-fade.
  const { stackAnimation } = useMotion();

  useEffect(() => {
    if (!loaded) return;
    splashHiding(duration.base);
    SplashScreen.hideAsync().catch(() => {});
  }, [loaded]);

  if (!loaded) return null;
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface }, animation: stackAnimation }}>
      <Stack.Screen name="(tabs)" options={{ animation: "fade" }} />
      {/* Welcome's kite takeoff hands over to Login with a cross-fade; every other way into Login keeps the default. */}
      <Stack.Screen
        name="login"
        options={({ route }) => ((route.params as { via?: string } | undefined)?.via === "kite" ? { animation: "fade" } : {})}
      />
    </Stack>
  );
}

export default function RootLayout() {
  if (!isConfigured) {
    // Misconfigured build: fail loudly instead of calling a guessed URL.
    return (
      <View style={styles.misconfig}>
        <Text style={styles.title}>App not configured</Text>
        <Text style={styles.body}>
          EXPO_PUBLIC_API_BASE_URL is missing or invalid ("{config.apiBaseUrl}"). Set it in mobile/.env and rebuild.
        </Text>
      </View>
    );
  }
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <StatusBar style="dark" />
        <RootStack />
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  misconfig: { flex: 1, justifyContent: "center", padding: 32, backgroundColor: "#fff" },
  title: { fontSize: 20, fontWeight: "700", marginBottom: 8 },
  body: { fontSize: 15, color: "#555" },
});

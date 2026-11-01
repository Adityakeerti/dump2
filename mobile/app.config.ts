import type { ConfigContext, ExpoConfig } from "expo/config";

/**
 * All environment-specific values come from env vars (see .env.example).
 * EXPO_PUBLIC_API_BASE_URL is inlined into the JS bundle at build time; the app talks only to
 * CitySense core, which proxies every third-party API (maps, geocoding, routing).
 */
const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? "";
const androidPackage = process.env.ANDROID_PACKAGE ?? "com.citysense.mobile";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "CitySense",
  slug: "citysense",
  scheme: "citysense",
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "light",
  ios: { supportsTablet: false, bundleIdentifier: androidPackage },
  android: {
    package: androidPackage,
    adaptiveIcon: {
      backgroundColor: "#FFFFFF",
      foregroundImage: "./assets/android-icon-foreground.png",
    },
    permissions: ["ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION", "RECORD_AUDIO"],
    predictiveBackGestureEnabled: false,
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    "expo-image",
    "expo-font",
    ["expo-splash-screen", { image: "./assets/splash-icon.png", imageWidth: 200, backgroundColor: "#FFFFFF" }],
    [
      "expo-location",
      { locationWhenInUsePermission: "CitySense uses your location to show city avatars and services around you." },
    ],
    [
      "expo-build-properties",
      // Release builds block plain HTTP; allow it only when the configured backend is http://.
      { android: { usesCleartextTraffic: apiBaseUrl.startsWith("http://") } },
    ],
    "@maplibre/maplibre-react-native",
    ["expo-audio", { microphonePermission: "CitySense uses the microphone so you can talk to the city assistant." }],
    [
      "expo-image-picker",
      { cameraPermission: "CitySense uses the camera so you can attach a photo of a civic issue to your complaint.", photosPermission: false },
    ],
  ],
  experiments: { typedRoutes: false },
});

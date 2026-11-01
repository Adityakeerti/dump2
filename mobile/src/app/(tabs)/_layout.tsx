import { Redirect } from "expo-router";
import { View } from "react-native";
import { AssistantProvider } from "../../assistant/AssistantContext";
import { AssistantLayer } from "../../assistant/AssistantLayer";
import { Tabs } from "expo-router/js-tabs";
import { useAuth } from "../../auth/AuthContext";
import { TabBar } from "../../components/TabBar";
import { TABS } from "../../content/tabs";
import { duration, easing, useReducedMotion } from "../../motion";

// Tabs shift slightly sideways while cross-fading (native driver); reduce motion keeps the plain dissolve.
const tabTransition = (reduced: boolean) =>
  ({
    animation: reduced ? "fade" : "shift",
    transitionSpec: { animation: "timing", config: { duration: reduced ? duration.fast : duration.base, easing: easing.move } },
  }) as const;

export default function TabsLayout() {
  const { token, user } = useAuth();
  const reduced = useReducedMotion();
  if (!token || !user) return <Redirect href="/welcome" />;
  if (!user.emailVerified) return <Redirect href="/verify" />;

  // The main agent (City Sense) floats over every tab: island -> half-screen panel, first-run guide chooser.
  return (
    <AssistantProvider>
    <View style={{ flex: 1 }}>
    <Tabs
      screenOptions={{ headerShown: false, ...tabTransition(reduced) }}
      tabBar={({ state, navigateToTab }) => {
        const active = state.routes[state.index]?.name ?? "explore";
        const select = (name: string) => {
          const route = state.routes.find((r) => r.name === name);
          if (route) navigateToTab(route.key);
        };
        return <TabBar items={TABS} activeName={active} onSelect={select} />;
      }}
    >
      {TABS.map((t) => (
        // The map renders into a GLSurfaceView on Android, which ignores view opacity: fading it would flicker.
        <Tabs.Screen key={t.name} name={t.name} options={t.name === "explore" ? { animation: "none" } : undefined} />
      ))}
    </Tabs>
    <AssistantLayer />
    </View>
    </AssistantProvider>
  );
}


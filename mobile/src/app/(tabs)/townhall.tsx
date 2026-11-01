import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { Animated, type LayoutChangeEvent, ScrollView, type ScrollViewInstance, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { errorMessage } from "../../api/client";
import { avatarApi, businessApi, civicApi, noticesApi } from "../../api/endpoints";
import { useAssistant } from "../../assistant/AssistantContext";
import { AvatarChooser, tabBarHeight } from "../../assistant/AssistantLayer";
import { useAssistantChat } from "../../assistant/useAssistantChat";
import { useAuth } from "../../auth/AuthContext";
import { mainAvatarById } from "../../content/mainAvatars";
import { useKeyboardHeight } from "../../hooks/useKeyboardHeight";
import { useUserLocation } from "../../hooks/useUserLocation";
import { useReducedMotion } from "../../motion";
import { FadeIn } from "../../motion/FadeIn";
import { Tap } from "../../motion/Tap";
import { colors, fonts } from "../../theme";
import { CityFeed, type FeedData } from "../../townhall/CityFeed";
import { GuideCard } from "../../townhall/GuideCard";
import { GuideStage } from "../../townhall/GuideStage";
import { HimalayaArt } from "../../townhall/HimalayaArt";
import { WeatherPage } from "../../townhall/WeatherPage";

/** Dehradun city centre, for nearby lists before a GPS fix. */
const CITY = { lat: 30.3243, lng: 78.0418 };

/** Height of the three-tab bar at the top of Townhall (below the status bar). */
const TABS_H = 62;
const TOWN_TABS = [
  { key: "guide", label: "Guide", icon: "person-circle-outline" },
  { key: "town", label: "Town", icon: "business-outline" },
  { key: "weather", label: "Weather", icon: "partly-sunny-outline" },
] as const;

/**
 * Townhall: three simple tabs (tap the bar or swipe sideways).
 *   Guide    the main guide in full view; chat docked above the tab bar; name pill -> guide card
 *   Town     the Dehradun card, then the city feed: businesses, events, places, notices, complaints
 *   Weather  live Dehradun weather, next hours, the week, air quality, flood risk
 */
export default function Townhall() {
  const insets = useSafeAreaInsets();
  const reduced = useReducedMotion();
  const { avatarId, chooseAvatar, openPanel, requestMapFocus } = useAssistant();
  const { language, setLanguage } = useAuth();
  const avatar = mainAvatarById(avatarId);
  // Navigating elsewhere from here continues the same conversation in the hovering panel.
  const chat = useAssistantChat({ onLeaveTab: () => openPanel({ anchor: "bottom", focus: false }) });
  const keyboard = useKeyboardHeight();
  const { coords } = useUserLocation();

  const [size, setSize] = useState({ width: 0, height: 0 });
  const [tab, setTab] = useState(0);
  const [card, setCard] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const pager = useRef<ScrollViewInstance>(null);
  const x = useRef(new Animated.Value(0)).current;

  const [data, setData] = useState<FeedData>({ businesses: null, events: null, places: null, notices: null, complaints: null });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const near = coords ? { lat: coords.latitude, lng: coords.longitude } : CITY;
    const [b, e, p, n, c] = await Promise.allSettled([
      businessApi.list(near, 12),
      civicApi.events(),
      avatarApi.nearby(near.lat, near.lng, 15000),
      noticesApi.latest(5),
      civicApi.mine(),
    ]);
    const pick = <T,>(r: PromiseSettledResult<T>, prev: T | null): T | null => (r.status === "fulfilled" ? r.value : prev);
    setData((d) => ({
      businesses: pick(b, d.businesses) ?? [],
      events: pick(e, d.events) ?? [],
      places: pick(p, d.places) ?? [],
      notices: pick(n, d.notices) ?? [],
      complaints: pick(c, d.complaints) ?? [],
    }));
    const failed = [b, e, p, c].find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
    if (failed) setError(errorMessage(failed.reason));
  }, [coords]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const goTo = (i: number) => {
    pager.current?.scrollTo({ x: i * size.width, animated: !reduced });
    setTab(i);
  };
  const ask = (prompt: string) => {
    goTo(0);
    void chat.send(prompt);
  };

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    if (width !== size.width || height !== size.height) setSize({ width, height });
  };
  const keyboardLift = Math.max(0, keyboard - tabBarHeight(insets.bottom));
  const { width: W, height: H } = size;
  const pageTop = insets.top + TABS_H;
  const upcoming = (data.events ?? []).filter((e) => Date.parse(e.endsAt ?? e.startsAt) >= Date.now()).length;

  return (
    <View style={styles.fill} onLayout={onLayout}>
      {W > 0 && H > 0 ? (
        <Animated.ScrollView
          ref={pager}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          scrollEnabled={keyboard === 0}
          keyboardShouldPersistTaps="handled"
          scrollEventThrottle={16}
          onScroll={Animated.event([{ nativeEvent: { contentOffset: { x } } }], { useNativeDriver: true })}
          onMomentumScrollEnd={(e) => setTab(Math.round(e.nativeEvent.contentOffset.x / W))}
        >
          <GuideStage
            avatar={avatar}
            chat={chat}
            width={W}
            height={H}
            topInset={pageTop - 6}
            keyboardLift={keyboardLift}
            pageIndex={tab}
            onOpenCard={() => setCard(true)}
            onNext={() => goTo(1)}
            onChangeGuide={() => setChoosing(true)}
          />
          <CityFeed
            data={data}
            error={error}
            width={W}
            height={H}
            topInset={pageTop}
            guideName={avatar.name}
            top={
              <CityCard
                width={W}
                counts={{ businesses: data.businesses?.length ?? 0, events: upcoming, places: data.places?.length ?? 0 }}
                onWeather={() => goTo(2)}
              />
            }
            onAsk={ask}
            onShowOnMap={(latitude, longitude, label) => {
              // Explore consumes the focus once its map is ready.
              requestMapFocus({ latitude, longitude, label });
              router.navigate("/explore");
            }}
            onRefresh={load}
          />
          <WeatherPage width={W} height={H} topInset={pageTop} coords={coords} onAsk={ask} />
        </Animated.ScrollView>
      ) : null}

      {/* Three-tab bar */}
      {W > 0 ? (
        <View style={[styles.tabsWrap, { paddingTop: insets.top + 8 }]} pointerEvents="box-none">
          <View style={styles.tabs}>
            <Animated.View
              style={[
                styles.tabThumb,
                {
                  width: (W - 32) / 3 - 8,
                  transform: [{ translateX: x.interpolate({ inputRange: [0, W * 2], outputRange: [4, 4 + ((W - 32) / 3) * 2], extrapolate: "clamp" }) }],
                },
              ]}
            />
            {TOWN_TABS.map((t, i) => (
              <Tap key={t.key} feedback="dim" style={styles.tabItem} onPress={() => goTo(i)} accessibilityRole="tab" accessibilityState={{ selected: tab === i }} accessibilityLabel={t.label}>
                <Ionicons name={t.icon} size={19} color="#fff" />
                <Text style={[styles.tabText, tab === i && styles.tabTextOn]}>{t.label}</Text>
              </Tap>
            ))}
          </View>
        </View>
      ) : null}

      <GuideCard
        avatar={avatar}
        visible={card}
        topInset={insets.top}
        places={data.places ?? []}
        onClose={() => setCard(false)}
        onAsk={ask}
        onChangeGuide={() => {
          setCard(false);
          setChoosing(true);
        }}
        messageCount={chat.messages.length}
        lang={chat.lang}
        onToggleLanguage={() => void setLanguage(language === "hi" ? "en" : "hi")}
        autoPlay={chat.voice.autoPlay}
        onToggleVoice={chat.voice.toggleAutoPlay}
      />
      {choosing ? (
        <AvatarChooser
          onChoose={async (id) => {
            await chooseAvatar(id);
            setChoosing(false);
          }}
          onCancel={() => setChoosing(false)}
        />
      ) : null}
    </View>
  );
}

/** Top of the Town tab: the Dehradun card and this month's summary. */
function CityCard({
  width,
  counts,
  onWeather,
}: {
  width: number;
  counts: { businesses: number; events: number; places: number };
  onWeather: () => void;
}) {
  const heroW = width - 32;
  const heroH = Math.round(heroW * 0.72);
  return (
    <View style={{ paddingHorizontal: 16, gap: 12, paddingTop: 4 }}>
      <FadeIn from="none" style={[styles.hero, { height: heroH }]}>
        <HimalayaArt width={heroW} height={heroH} />
        <View style={styles.heroInfo}>
          <View style={{ flex: 1, gap: 6 }}>
            <Text style={styles.heroCity}>Dehradun</Text>
            <View style={styles.heroRow}>
              <Ionicons name="location-outline" size={18} color="rgba(255,255,255,0.9)" />
              <Text style={styles.heroCountry}>India</Text>
            </View>
          </View>
          <Text style={styles.heroCode}>UK</Text>
        </View>
      </FadeIn>
      <FadeIn from="below" delay={120}>
        <Tap style={styles.plan} onPress={onWeather} accessibilityLabel="This month in town. Open weather">
          <View style={styles.planRow}>
            <Text style={styles.planTitle}>This month in town</Text>
            <Text style={styles.planValue}>{counts.events} events</Text>
          </View>
          <View style={styles.planLine}>
            <Ionicons name="checkmark-circle-outline" size={20} color="#fff" />
            <Text style={styles.planText}>
              {counts.businesses} popular spots and {counts.places} local agents near you. Scroll down for the city feed.
            </Text>
          </View>
        </Tap>
      </FadeIn>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.surface },
  tabsWrap: { position: "absolute", top: 0, left: 0, right: 0, paddingHorizontal: 16, paddingBottom: 6, backgroundColor: colors.surface },
  tabs: { height: 48, borderRadius: 14, backgroundColor: "#2F3238", flexDirection: "row", alignItems: "center" },
  tabThumb: { position: "absolute", top: 4, bottom: 4, borderRadius: 10, backgroundColor: "#5B5F68" },
  tabItem: { flex: 1, height: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  tabText: { fontFamily: fonts.medium, fontSize: 13, color: "#C9CCD3" },
  tabTextOn: { fontFamily: fonts.bold, color: "#fff" },
  hero: { borderRadius: 26, overflow: "hidden", backgroundColor: colors.navy },
  heroInfo: {
    position: "absolute",
    left: 22,
    right: 22,
    bottom: 18,
    flexDirection: "row",
    alignItems: "flex-start",
    paddingHorizontal: 18,
    paddingVertical: 16,
    borderRadius: 16,
    backgroundColor: "rgba(20,32,52,0.62)",
  },
  heroCity: { fontFamily: fonts.bold, fontSize: 24, color: "#fff" },
  heroRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  heroCountry: { fontFamily: fonts.medium, fontSize: 15, color: "rgba(255,255,255,0.9)" },
  heroCode: { fontFamily: fonts.medium, fontSize: 15, color: "rgba(255,255,255,0.9)" },
  plan: { borderRadius: 16, backgroundColor: "#1E3A40", paddingHorizontal: 18, paddingVertical: 16, gap: 8 },
  planRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  planTitle: { fontFamily: fonts.bold, fontSize: 17, color: "#fff" },
  planValue: { fontFamily: fonts.bold, fontSize: 17, color: "#fff" },
  planLine: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  planText: { flex: 1, fontFamily: fonts.medium, fontSize: 13, lineHeight: 18, color: "rgba(255,255,255,0.9)" },
});

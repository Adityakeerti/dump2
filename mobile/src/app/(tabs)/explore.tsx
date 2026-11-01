import { Ionicons } from "@expo/vector-icons";
import { ExploreMap, MAP_PITCH } from "../../components/ExploreMap";
import { PlaceSheet } from "../../components/PlaceSheet";
import { useAssistantOptional } from "../../assistant/AssistantContext";
import { AssistantBar } from "../../assistant/AssistantLayer";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { errorMessage } from "../../api/client";
import { avatarApi, geoApi } from "../../api/endpoints";
import type { Avatar, Place } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ErrorBanner, Loading } from "../../components/StateViews";
import { absoluteUrl } from "../../config";
import { useMapConfig } from "../../hooks/useMapConfig";
import { type LatLng, useUserLocation } from "../../hooks/useUserLocation";
import { useMotion } from "../../motion";
import { FadeIn } from "../../motion/FadeIn";
import { Tap } from "../../motion/Tap";
import { colors, fonts, radius } from "../../theme";
import { boundsAround, circlePolygon, formatDistance } from "../../utils/geo";

type Result = { kind: "avatar"; avatar: Avatar } | { kind: "place"; place: Place };

export default function Explore() {
  const insets = useSafeAreaInsets();
  const { mapDuration } = useMotion();
  const camera = useRef<any>(null);
  const { config, error: configError, reload } = useMapConfig();
  const { coords, status: locStatus, refresh: refreshLocation } = useUserLocation();
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [searching, setSearching] = useState(false);
  const [placePin, setPlacePin] = useState<Place | null>(null);
  // Spot the main agent is briefing about (tap anywhere on the map).
  const [tapped, setTapped] = useState<LatLng | null>(null);
  const { language } = useAuth();
  const assistant = useAssistantOptional();
  // Camera commands sent before the native map finishes loading are dropped.
  const [mapReady, setMapReady] = useState(false);

  // Geofence centre: the user's position, or the city default from core when location is unavailable.
  const origin: LatLng | null = useMemo(() => {
    if (coords) return coords;
    if (config && locStatus !== "pending") return { latitude: config.defaultLatitude, longitude: config.defaultLongitude };
    return null;
  }, [coords, config, locStatus]);

  const loadNearby = useCallback(async () => {
    if (!origin || !config) return;
    setLoadError(null);
    try {
      setAvatars(await avatarApi.nearby(origin.latitude, origin.longitude, config.geofenceRadiusMeters));
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, [origin, config]);

  useEffect(() => {
    void loadNearby();
  }, [loadNearby]);

  // Frame the whole geofence (as in the mockup) rather than a fixed zoom, whatever radius core sets.
  // One camera timing for every move; under reduce motion the camera jumps instead of flying.
  const frameGeofence = useCallback(
    (center: LatLng) => {
      if (!config) return;
      camera.current?.fitBounds(boundsAround(center.latitude, center.longitude, config.geofenceRadiusMeters), {
        padding: { top: 140, bottom: 90, left: 24, right: 24 },
        pitch: MAP_PITCH,
        duration: mapDuration,
      });
    },
    [config, mapDuration],
  );

  useEffect(() => {
    if (origin && mapReady) frameGeofence(origin);
  }, [origin?.latitude, origin?.longitude, mapReady]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced search over avatars (core DB) and places (core's geocoding proxy).
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    const near = origin ? { lat: origin.latitude, lng: origin.longitude } : undefined;
    const t = setTimeout(async () => {
      const [a, p] = await Promise.allSettled([avatarApi.search(q, near), geoApi.geocode(q, near)]);
      const list: Result[] = [];
      if (a.status === "fulfilled") list.push(...a.value.map((avatar) => ({ kind: "avatar" as const, avatar })));
      if (p.status === "fulfilled") list.push(...p.value.places.map((place) => ({ kind: "place" as const, place })));
      setResults(list);
      setSearching(false);
    }, 400);
    return () => clearTimeout(t);
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  const geofence = useMemo(
    () => (origin && config ? circlePolygon(origin.latitude, origin.longitude, config.geofenceRadiusMeters) : null),
    [origin, config],
  );

  const openAvatar = (a: Avatar) => {
    setQuery("");
    router.push({ pathname: "/avatar/[id]", params: { id: a.id } });
  };

  // "Show Clock Tower on the map" from the main agent: fly there and drop a pin.
  useEffect(() => {
    const f = assistant?.mapFocus;
    if (!f || !mapReady) return;
    setQuery("");
    setPlacePin({ name: f.label ?? "Here", displayName: f.label ?? "", latitude: f.latitude, longitude: f.longitude, type: "agent" });
    camera.current?.flyTo({ center: [f.longitude, f.latitude], zoom: 16.3, pitch: 60, duration: mapDuration });
  }, [assistant?.mapFocus?.nonce, mapReady]); // eslint-disable-line react-hooks/exhaustive-deps

  // Tap empty map -> fly in low and tilted (3D buildings show from ~z15) and ask the main agent.
  const onMapPress = (point: LatLng) => {
    setQuery("");
    setTapped(point);
    camera.current?.flyTo({ center: [point.longitude, point.latitude], zoom: 16.3, pitch: 60, duration: mapDuration });
  };

  const goToPlace = (p: Place) => {
    setQuery("");
    setPlacePin(p);
    camera.current?.flyTo({ center: [p.longitude, p.latitude], zoom: 16, pitch: 60, duration: mapDuration });
  };

  const recenter = async () => {
    const pos = (await refreshLocation()) ?? origin;
    if (pos) frameGeofence(pos);
  };

  if (configError) {
    return (
      <View style={[styles.fill, styles.pad, { paddingTop: insets.top + 24 }]}>
        <ErrorBanner message={`Map unavailable: ${configError}`} onRetry={reload} />
      </View>
    );
  }
  if (!config) return <Loading />;

  return (
    <View style={styles.fill}>
      <ExploreMap
        config={config}
        cameraRef={camera}
        geofence={geofence}
        avatars={avatars}
        placePin={placePin}
        coords={coords}
        onOpenAvatar={openAvatar}
        onMapReady={() => setMapReady(true)}
        onMapPress={onMapPress}
        tappedPoint={tapped}
      />

      <View style={[styles.searchWrap, { top: insets.top + 10 }]}>
        <View style={styles.search}>
          <Ionicons name="search" size={18} color={colors.textMuted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search avatars & places · tap the map to ask"
            placeholderTextColor="#7A7A85"
            style={styles.searchInput}
            returnKeyType="search"
            accessibilityLabel="Search avatars and places"
          />
          {searching ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : query ? (
            <Tap feedback="dim" onPress={() => setQuery("")} hitSlop={10} accessibilityLabel="Clear search">
              <Ionicons name="close-circle" size={18} color={colors.textMuted} />
            </Tap>
          ) : null}
        </View>
        {/* The main agent (City Sense) sits right under the search box; it steps aside while searching. */}
        {assistant?.avatarId && query.trim().length < 2 ? <AssistantBar anchor="top" /> : null}
        {/* Previous results stay up while the next search runs (the bar shows the spinner), so the panel
            doesn't blink on every pause in typing. It drops down from the bar once, when it first opens. */}
        {query.trim().length >= 2 && (results.length > 0 || !searching) && (
          <FadeIn from="above" style={styles.results}>
            {results.length === 0 ? (
              <Text style={styles.noResults}>No avatars or places match “{query.trim()}”</Text>
            ) : (
              <FlatList
                data={results}
                keyboardShouldPersistTaps="handled"
                keyExtractor={(r, i) => (r.kind === "avatar" ? r.avatar.id : `p${i}`)}
                renderItem={({ item }) =>
                  item.kind === "avatar" ? (
                    <Tap feedback="highlight" style={styles.resultRow} onPress={() => openAvatar(item.avatar)} accessibilityLabel={`${item.avatar.name}, ${item.avatar.title}`}>
                      <Image source={{ uri: absoluteUrl(item.avatar.pinImageUrl) }} style={styles.resultImg} contentFit="contain" />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.resultTitle}>{item.avatar.name}</Text>
                        <Text style={styles.resultSub} numberOfLines={1}>
                          {item.avatar.title}
                          {item.avatar.distanceMeters != null ? ` · ${formatDistance(item.avatar.distanceMeters)}` : ""}
                        </Text>
                      </View>
                    </Tap>
                  ) : (
                    <Tap feedback="highlight" style={styles.resultRow} onPress={() => goToPlace(item.place)} accessibilityLabel={item.place.displayName}>
                      <View style={[styles.resultImg, styles.placeIcon]}>
                        <Ionicons name="map-outline" size={18} color={colors.primary} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.resultTitle}>{item.place.name}</Text>
                        <Text style={styles.resultSub} numberOfLines={1}>
                          {item.place.displayName}
                        </Text>
                      </View>
                    </Tap>
                  )
                }
              />
            )}
          </FadeIn>
        )}
        {loadError ? <ErrorBanner message={loadError} onRetry={loadNearby} /> : null}
        {!coords && locStatus !== "pending" && !query ? (
          <FadeIn style={{ alignSelf: "flex-start" }}>
            <Text style={styles.notice}>
              {locStatus === "denied" ? "Location permission is off" : "Can't get your location"} — showing avatars around the city centre.
            </Text>
          </FadeIn>
        ) : null}
      </View>

      {tapped ? <PlaceSheet point={tapped} language={language ?? "en"} onClose={() => setTapped(null)} /> : null}

      <View style={styles.bottomRow} pointerEvents="box-none">
        <View style={styles.countChip}>
          <Text style={styles.countText}>
            {avatars.length} avatar{avatars.length === 1 ? "" : "s"} within {formatDistance(config.geofenceRadiusMeters)}
          </Text>
        </View>
        <Tap style={styles.fab} onPress={recenter} accessibilityLabel="Centre on my location">
          <Ionicons name="locate" size={22} color={colors.navy} />
        </Tap>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.surface },
  pad: { paddingHorizontal: 16 },
  searchWrap: { position: "absolute", left: 14, right: 14, gap: 8 },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    height: 48,
    paddingHorizontal: 16,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 4,
  },
  searchInput: { flex: 1, fontFamily: fonts.medium, fontSize: 15, color: colors.text },
  results: {
    maxHeight: 320,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    paddingVertical: 4,
    elevation: 4,
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowRadius: 10,
  },
  noResults: { padding: 14, fontFamily: fonts.regular, color: colors.textMuted },
  resultRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 10 },
  resultImg: { width: 36, height: 36 },
  placeIcon: { borderRadius: 18, backgroundColor: "#F8E8ED", alignItems: "center", justifyContent: "center" },
  resultTitle: { fontFamily: fonts.semibold, fontSize: 15, color: colors.text },
  resultSub: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted },
  notice: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.92)",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    fontFamily: fonts.medium,
    fontSize: 12,
    color: colors.textMuted,
  },
  pinWrap: { alignItems: "center" },
  pinImage: { width: 52, height: 64 },
  pinIcon: { marginTop: -6 },
  meHalo: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "rgba(59,130,246,0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  meDot: { width: 16, height: 16, borderRadius: 8, backgroundColor: colors.accentBlue, borderWidth: 2.5, borderColor: "#fff" },
  bottomRow: {
    position: "absolute",
    left: 14,
    right: 14,
    bottom: 34,
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
  },
  countChip: { backgroundColor: "rgba(29,43,79,0.9)", paddingHorizontal: 12, paddingVertical: 7, borderRadius: radius.pill },
  countText: { color: "#fff", fontFamily: fonts.semibold, fontSize: 12 },
  fab: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    elevation: 4,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
  },
});

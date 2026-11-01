import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { router } from "expo-router";
import { useMemo, useRef, useState } from "react";
import {
  type LayoutChangeEvent,
  Linking,
  RefreshControl,
  ScrollView,
  type ScrollViewInstance,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { Avatar, Business, CityEvent, Complaint, Notice } from "../api/types";
import { ErrorBanner } from "../components/StateViews";
import { StatusBadge } from "../components/StatusBadge";
import { absoluteUrl } from "../config";
import { useKeyboardHeight } from "../hooks/useKeyboardHeight";
import { animateNextLayout, useReducedMotion } from "../motion";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";
import { formatDistance, timeAgo } from "../utils/geo";
import { sameDay, startOfDay, startOfWeek, WeekCalendar } from "./WeekCalendar";

export interface FeedData {
  businesses: Business[] | null;
  events: CityEvent[] | null;
  places: Avatar[] | null;
  notices: Notice[] | null;
  complaints: Complaint[] | null;
}

const CATEGORY: Record<string, { icon: keyof typeof Ionicons.glyphMap; bg: string; label: string }> = {
  restaurant: { icon: "restaurant", bg: "#FDECEF", label: "Restaurant" },
  cafe: { icon: "cafe", bg: "#FFF3DF", label: "Cafe" },
  sweets: { icon: "ice-cream", bg: "#FCE8F3", label: "Sweets" },
  bakery: { icon: "storefront", bg: "#FFF0E3", label: "Bakery" },
  bookstore: { icon: "book", bg: "#E8F0FF", label: "Books" },
  shopping: { icon: "bag-handle", bg: "#E9F7EF", label: "Shopping" },
};
const categoryOf = (c: string) => CATEGORY[c.toLowerCase()] ?? { icon: "storefront" as const, bg: colors.surfaceAlt, label: c };

const EVENT_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  culture: "musical-notes",
  festival: "sparkles",
  civic: "flag",
  literature: "book",
  sports: "walk",
};

type SectionKey = "business" | "events" | "places" | "civic";

/** Event still relevant on/after `day` (multi-day festivals count on every day they run). */
const runsOn = (e: CityEvent, day: Date) => {
  const s = startOfDay(new Date(e.startsAt)).getTime();
  const end = startOfDay(new Date(e.endsAt ?? e.startsAt)).getTime();
  const d = startOfDay(day).getTime();
  return d >= s && d <= end;
};

/**
 * Townhall feed (swipe right from the city card): popular businesses, upcoming events on a week
 * calendar, places with a local agent, notices and the citizen's own complaints.
 */
export function CityFeed({
  data,
  error,
  width,
  height,
  topInset,
  guideName,
  top,
  onAsk,
  onShowOnMap,
  onRefresh,
}: {
  data: FeedData;
  error: string | null;
  width: number;
  height: number;
  topInset: number;
  guideName: string;
  /** Shown above the feed (the Dehradun card). */
  top?: React.ReactNode;
  onAsk: (prompt: string) => void;
  onShowOnMap: (latitude: number, longitude: number, label: string) => void;
  onRefresh: () => Promise<void>;
}) {
  const reduced = useReducedMotion();
  const keyboard = useKeyboardHeight();
  const scroll = useRef<ScrollViewInstance>(null);
  const offsets = useRef<Partial<Record<SectionKey, number>>>({});
  const trackY = useRef(0);
  const [refreshing, setRefreshing] = useState(false);
  const [trackId, setTrackId] = useState("");

  // Calendar: this week, nothing selected = every upcoming event.
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [selected, setSelected] = useState<Date | null>(null);
  const upcoming = useMemo(() => {
    const today = startOfDay(new Date()).getTime();
    return (data.events ?? [])
      .filter((e) => startOfDay(new Date(e.endsAt ?? e.startsAt)).getTime() >= today)
      .sort((a, b) => Date.parse(a.startsAt) - Date.parse(b.startsAt));
  }, [data.events]);
  const marked = useMemo(() => {
    const set = new Set<number>();
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart.getTime() + i * 86_400_000);
      if (upcoming.some((e) => runsOn(e, d))) set.add(startOfDay(d).getTime());
    }
    return set;
  }, [upcoming, weekStart]);
  const shownEvents = selected ? upcoming.filter((e) => runsOn(e, selected)) : upcoming;

  const mark = (key: SectionKey) => (e: LayoutChangeEvent) => {
    offsets.current[key] = e.nativeEvent.layout.y;
  };
  const track = () => {
    const id = trackId.trim().toUpperCase();
    if (id) router.push({ pathname: "/complaint/[trackingId]", params: { trackingId: id } });
  };

  return (
    <View style={{ width, height, backgroundColor: colors.surface }}>
      <ScrollView
        ref={scroll}
        nestedScrollEnabled
        contentContainerStyle={[styles.content, { paddingTop: topInset, paddingBottom: 40 + keyboard }]}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await onRefresh();
              setRefreshing(false);
            }}
          />
        }
      >
        {top}
        {error ? <ErrorBanner message={error} onRetry={onRefresh} /> : null}

        {/* Popular businesses: picture, name, two lines, "Learn More", and a button hanging off the card */}
        <View onLayout={mark("business")} style={styles.section}>
          <SectionTitle icon="checkmark-circle-outline" title="Popular Businesses" />
          <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow}>
            {(data.businesses ?? [])
              .map((b, i) => {
                const cat = categoryOf(b.category);
                return (
                  <FadeIn key={b.id} index={i} from="below" style={styles.bizSlot}>
                    <View style={styles.bizCard}>
                      <View style={[styles.bizArt, { backgroundColor: cat.bg }]}>
                        <Ionicons name={cat.icon} size={30} color={colors.navy} />
                        <Text style={styles.bizCat}>
                          {cat.label}
                          {b.distanceMeters != null ? ` · ${formatDistance(b.distanceMeters)}` : ""}
                        </Text>
                      </View>
                      <View style={styles.bizBody}>
                        <Text style={styles.bizName} numberOfLines={1}>
                          {b.name}
                        </Text>
                        <Text style={styles.bizDesc} numberOfLines={2}>
                          {b.description}
                        </Text>
                        <Tap feedback="dim" hitSlop={6} onPress={() => onAsk(`Tell me about ${b.name} in ${b.locality.split(" / ")[0]}`)} accessibilityLabel={`Ask ${guideName} about ${b.name}`}>
                          <Text style={styles.learn}>Learn More</Text>
                        </Tap>
                      </View>
                    </View>
                    <Tap style={styles.hangBtn} onPress={() => onShowOnMap(b.latitude, b.longitude, b.name)} accessibilityLabel={`Show ${b.name} on the map`}>
                      <Text style={styles.hangText}>Map</Text>
                      <Ionicons name="add" size={14} color="#fff" />
                    </Tap>
                  </FadeIn>
                );
              })}
            {data.businesses?.length === 0 ? <Text style={styles.empty}>No businesses listed yet.</Text> : null}
          </ScrollView>
          {data.businesses && data.businesses.length > 0 ? (
            <Text style={styles.note}>From public city guides; check a listing is still open before you go.</Text>
          ) : null}
        </View>

        {/* Events: week calendar, "View all", then big tiles */}
        <View onLayout={mark("events")} style={styles.section}>
          <SectionTitle icon="checkmark-circle-outline" title="Upcoming Events near you" />
          <View style={styles.calendarWrap}>
            <WeekCalendar
              weekStart={weekStart}
              selected={selected}
              marked={marked}
              onSelect={(d) => {
                animateNextLayout();
                setSelected((cur) => (cur && sameDay(cur, d) ? null : d));
              }}
              onShiftWeek={(n) => {
                animateNextLayout();
                setWeekStart((w) => new Date(w.getTime() + n * 7 * 86_400_000));
                setSelected(null);
              }}
            />
          </View>
          <Tap feedback="dim" style={styles.viewAll} onPress={() => setSelected(null)} accessibilityLabel="View all upcoming events">
            <Text style={styles.viewAllText}>{selected ? "View all ›" : `All upcoming (${upcoming.length}) ›`}</Text>
          </Tap>
          {data.events === null ? null : shownEvents.length === 0 ? (
            <Text style={styles.empty}>{selected ? "Nothing listed on this day." : "No upcoming events listed."}</Text>
          ) : (
            <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow}>
              {shownEvents
                .map((e, i) => {
                  const start = new Date(e.startsAt);
                  const end = e.endsAt ? new Date(e.endsAt) : null;
                  const range =
                    end && !sameDay(start, end)
                      ? `${start.toLocaleDateString("en-IN", { day: "numeric", month: "short" })} – ${end.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}`
                      : start.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
                  return (
                    <FadeIn key={e.id} index={i} from="below">
                      <Tap style={styles.eventTile} onPress={() => onAsk(`Tell me about ${e.title}`)} accessibilityLabel={`${e.title}, ${range}. Ask ${guideName}`}>
                        <View style={styles.eventArt}>
                          <Ionicons name={EVENT_ICON[e.category.toLowerCase()] ?? "sparkles"} size={44} color="#B7BAC4" />
                          <View style={styles.dateChip}>
                            <Text style={styles.dateDay}>{start.getDate()}</Text>
                            <Text style={styles.dateMon}>{start.toLocaleDateString("en-IN", { month: "short" })}</Text>
                          </View>
                        </View>
                        <View style={styles.eventBody}>
                          <Text style={styles.eventCat} numberOfLines={1}>
                            {e.category.toLowerCase()} · {range}
                          </Text>
                          <Text style={styles.eventTitle} numberOfLines={2}>
                            {e.title}
                          </Text>
                          {e.venue ? (
                            <Text style={styles.eventSub} numberOfLines={1}>
                              📍 {e.venue}
                            </Text>
                          ) : null}
                        </View>
                      </Tap>
                      {/* Sibling, not nested: the source link must not sit inside the tile's own button. */}
                      {e.sourceUrl ? (
                        <Tap feedback="dim" hitSlop={8} style={styles.sourceBtn} onPress={() => Linking.openURL(e.sourceUrl!)} accessibilityLabel="Open the event's source">
                          <Ionicons name="open-outline" size={15} color={colors.navy} />
                        </Tap>
                      ) : null}
                    </FadeIn>
                  );
                })}
            </ScrollView>
          )}
        </View>

        {/* Places with a local agent */}
        <View onLayout={mark("places")} style={styles.section}>
          <SectionTitle icon="location-outline" title="Places & local agents" />
          <View style={styles.grid}>
            {(data.places ?? []).slice(0, 6).map((a, i) => (
              <FadeIn key={a.id} index={i} from="below" style={styles.gridCell}>
                <Tap style={styles.place} onPress={() => router.push({ pathname: "/avatar/[id]", params: { id: a.id } })} accessibilityLabel={`${a.name}, ${a.title}`}>
                  <View style={styles.placeArt}>
                    <Image source={{ uri: absoluteUrl(a.pinImageUrl) }} style={{ width: 84, height: 84 }} contentFit="contain" />
                  </View>
                  <Text style={styles.placeName} numberOfLines={1}>
                    {a.name}
                  </Text>
                  <Text style={styles.placeSub} numberOfLines={2}>
                    {a.title}
                  </Text>
                  {a.distanceMeters != null ? <Text style={styles.placeDist}>{formatDistance(a.distanceMeters)}</Text> : null}
                </Tap>
              </FadeIn>
            ))}
          </View>
          {data.places?.length === 0 ? <Text style={styles.empty}>No local agents near you yet.</Text> : null}
        </View>

        {/* Civic: notices, report, track, my complaints */}
        <View onLayout={mark("civic")} style={styles.section}>
          <SectionTitle icon="newspaper-outline" title="Latest notices" />
          {(data.notices ?? []).slice(0, 3).map((n, i) => (
            <FadeIn key={n.id} index={i}>
              <Tap feedback="highlight" style={styles.row} onPress={() => router.navigate("/updates")} accessibilityLabel={n.title}>
                <Ionicons name={n.isPinned ? "pin" : "document-text-outline"} size={18} color={colors.navy} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={2}>
                    {n.title}
                  </Text>
                  <Text style={styles.rowSub}>
                    {n.department}
                    {n.publishDate ? ` · ${timeAgo(n.publishDate)}` : ""}
                  </Text>
                </View>
              </Tap>
            </FadeIn>
          ))}
          {data.notices?.length === 0 ? <Text style={styles.empty}>No active notices.</Text> : null}

          <Tap style={styles.report} onPress={() => router.push("/complaint/new")} accessibilityLabel="Report an issue">
            <View style={styles.reportIcon}>
              <Ionicons name="megaphone" size={20} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.reportTitle}>Report an issue</Text>
              <Text style={styles.reportSub}>Potholes, garbage, sewage, streetlights… add a photo</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#fff" />
          </Tap>

          <View style={styles.trackRow} onLayout={(e) => (trackY.current = e.nativeEvent.layout.y)}>
            <TextInput
              // Bring the field just under the header, clear of the keyboard.
              onFocus={() => setTimeout(() => scroll.current?.scrollTo({ y: (offsets.current.civic ?? 0) + trackY.current - 80, animated: !reduced }), 300)}
              value={trackId}
              onChangeText={setTrackId}
              placeholder="Track: CMP-…"
              placeholderTextColor="#A6A6B0"
              autoCapitalize="characters"
              style={styles.trackInput}
              onSubmitEditing={track}
              returnKeyType="search"
            />
            <Tap style={styles.trackBtn} onPress={track} accessibilityLabel="Track complaint">
              <Ionicons name="search" size={18} color="#fff" />
            </Tap>
          </View>

          <SectionTitle icon="list-outline" title="My complaints" />
          {data.complaints === null ? null : data.complaints.length === 0 ? (
            <Text style={styles.empty}>You haven't filed anything yet.</Text>
          ) : (
            data.complaints.slice(0, 6).map((c, i) => (
              <FadeIn key={c.id} index={i}>
                <Tap
                  feedback="highlight"
                  style={styles.row}
                  onPress={() => router.push({ pathname: "/complaint/[trackingId]", params: { trackingId: c.trackingId } })}
                  accessibilityLabel={`${c.title}, ${c.status.replace(/_/g, " ").toLowerCase()}`}
                >
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={styles.rowTitle} numberOfLines={1}>
                      {c.title}
                    </Text>
                    <Text style={styles.rowSub}>
                      {c.trackingId} · {timeAgo(c.createdAt)}
                    </Text>
                  </View>
                  <StatusBadge value={c.status} />
                </Tap>
              </FadeIn>
            ))
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function SectionTitle({ icon, title }: { icon: keyof typeof Ionicons.glyphMap; title: string }) {
  return (
    <View style={styles.sectionTitle}>
      <Ionicons name={icon} size={18} color={colors.text} />
      <Text style={styles.sectionText}>{title}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: 40, gap: 6 },
  section: { gap: 10, paddingTop: 14 },
  sectionTitle: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 18 },
  sectionText: { fontFamily: fonts.medium, fontSize: 16, color: colors.text },
  hRow: { gap: 10, paddingHorizontal: 16, paddingTop: 2, paddingBottom: 16 },
  bizSlot: { width: 168, alignItems: "center" },
  bizCard: {
    width: 168,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: "#E2E2E8",
    overflow: "hidden",
    elevation: 2,
    shadowColor: "#000",
    shadowOpacity: 0.07,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
  },
  bizArt: { height: 78, alignItems: "center", justifyContent: "center", gap: 2 },
  bizCat: { fontFamily: fonts.semibold, fontSize: 10, color: colors.navy },
  bizBody: { paddingHorizontal: 10, paddingTop: 8, paddingBottom: 20, gap: 3 },
  bizName: { fontFamily: fonts.bold, fontSize: 13, color: colors.text },
  bizDesc: { fontFamily: fonts.regular, fontSize: 11, lineHeight: 15, color: colors.textMuted, minHeight: 30 },
  learn: { fontFamily: fonts.semibold, fontSize: 11, color: colors.text, textDecorationLine: "underline", marginTop: 2 },
  hangBtn: {
    marginTop: -14,
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "#2F3238",
    borderRadius: radius.pill,
    paddingHorizontal: 16,
    paddingVertical: 6,
    elevation: 3,
  },
  hangText: { fontFamily: fonts.semibold, fontSize: 12, color: "#fff" },
  note: { paddingHorizontal: 18, marginTop: -8, fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  calendarWrap: { marginHorizontal: 16 },
  viewAll: { alignSelf: "center", paddingVertical: 4 },
  viewAllText: { fontFamily: fonts.medium, fontSize: 13, color: colors.text },
  eventTile: { width: 168, borderRadius: 10, backgroundColor: colors.surface, overflow: "hidden", borderWidth: 1, borderColor: "#E6E6EB" },
  eventArt: { height: 150, backgroundColor: "#E7E8EC", alignItems: "center", justifyContent: "center" },
  dateChip: { position: "absolute", top: 8, left: 8, width: 44, paddingVertical: 4, borderRadius: 10, backgroundColor: colors.navy, alignItems: "center" },
  dateDay: { fontFamily: fonts.bold, fontSize: 16, color: "#fff" },
  dateMon: { fontFamily: fonts.medium, fontSize: 10, color: "rgba(255,255,255,0.85)" },
  sourceBtn: { position: "absolute", top: 8, right: 8, width: 28, height: 28, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.9)", alignItems: "center", justifyContent: "center" },
  eventBody: { padding: 10, gap: 3 },
  eventCat: { fontFamily: fonts.medium, fontSize: 10, color: colors.primary },
  eventTitle: { fontFamily: fonts.bold, fontSize: 13, color: colors.text, minHeight: 34 },
  eventSub: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  link: { fontFamily: fonts.bold, fontSize: 12, color: colors.accentBlue },
  grid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 12 },
  gridCell: { width: "50%", padding: 4 },
  place: { borderRadius: 16, backgroundColor: colors.surfaceAlt, padding: 10, alignItems: "center", gap: 2 },
  placeArt: { width: 92, height: 92, borderRadius: 46, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", marginBottom: 4 },
  placeName: { fontFamily: fonts.bold, fontSize: 14, color: colors.text },
  placeSub: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted, textAlign: "center" },
  placeDist: { fontFamily: fonts.semibold, fontSize: 11, color: colors.primary },
  row: { marginHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  rowTitle: { fontFamily: fonts.semibold, fontSize: 14, color: colors.text },
  rowSub: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  report: { marginHorizontal: 16, marginTop: 6, flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: colors.primary, borderRadius: radius.lg, padding: 14 },
  reportIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  reportTitle: { color: "#fff", fontFamily: fonts.bold, fontSize: 16 },
  reportSub: { color: "rgba(255,255,255,0.85)", fontFamily: fonts.regular, fontSize: 12 },
  trackRow: { marginHorizontal: 16, flexDirection: "row", gap: 8 },
  trackInput: {
    flex: 1,
    height: 44,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    fontFamily: fonts.medium,
    color: colors.text,
  },
  trackBtn: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.navy, alignItems: "center", justifyContent: "center" },
  empty: { paddingHorizontal: 16, fontFamily: fonts.regular, color: colors.textMuted, fontSize: 13 },
});

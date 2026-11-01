import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { errorMessage } from "../../api/client";
import { incidentApi, noticesApi } from "../../api/endpoints";
import type { Incident, LiveMessage, Notice } from "../../api/types";
import { ScreenHeader } from "../../components/ScreenHeader";
import { Empty, ErrorBanner, Loading } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useLiveEvents } from "../../hooks/useLiveEvents";
import { animateNextLayout } from "../../motion";
import { FadeIn, useFirstBatch } from "../../motion/FadeIn";
import { colors, fonts, radius } from "../../theme";
import { timeAgo } from "../../utils/geo";

const MAX_LIVE = 10;
const MAX_NOTICES = 5;
// Notices are the govt portal's published JSON (no push channel): poll while visible so a redeploy shows up.
const NOTICE_POLL_MS = 30_000;
// Citizens see incident and complaint changes; internal pipeline events (observations, actions) stay on the dashboard.
const CITIZEN_EVENT = /^(INCIDENT|COMPLAINT)_/;

function describe(m: LiveMessage): { title: string; body: string } {
  const d = (m.data ?? {}) as Record<string, unknown>;
  const title = (d.title as string) ?? (d.trackingId as string) ?? m.type.replace(/_/g, " ").toLowerCase();
  return { title, body: m.type.replace(/_/g, " ").toLowerCase() };
}

function noticeTone(priority: string): string {
  const p = priority.toLowerCase();
  if (p === "urgent" || p === "critical") return colors.danger;
  if (p === "important" || p === "high") return colors.warning;
  return colors.accentBlue;
}

export default function Updates() {
  // null until the first response, so "All clear" never flashes before data arrives.
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [notices, setNotices] = useState<Notice[] | null>(null);
  const [openNotice, setOpenNotice] = useState<string | null>(null);
  const [live, setLive] = useState<LiveMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const firstBatch = useFirstBatch(incidents !== null);

  const load = useCallback(async (opts?: { live?: boolean }) => {
    setError(null);
    // Incidents (core) and notices (govt portal) are separate services: one failing keeps the other.
    const [i, n] = await Promise.allSettled([incidentApi.list(), noticesApi.latest(MAX_NOTICES)]);
    // A live change may add or drop rows; let the list settle smoothly instead of jumping.
    if (opts?.live) animateNextLayout();
    setIncidents((prev) => (i.status === "fulfilled" ? i.value : (prev ?? [])));
    setNotices((prev) => (n.status === "fulfilled" ? n.value : (prev ?? [])));
    const failed = [i, n].find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
    if (failed) setError(errorMessage(failed.reason));
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
      const timer = setInterval(() => void load({ live: true }), NOTICE_POLL_MS);
      return () => clearInterval(timer);
    }, [load]),
  );

  const connected = useLiveEvents((m) => {
    if (!CITIZEN_EVENT.test(m.type)) return;
    // One row per entity: the newest event replaces older ones. Existing rows glide down to make room.
    animateNextLayout();
    setLive((prev) => [m, ...prev.filter((p) => p.entityId !== m.entityId)].slice(0, MAX_LIVE));
    if (m.type.startsWith("INCIDENT")) void load({ live: true });
  });

  return (
    <View style={styles.fill}>
      <ScreenHeader
        title="Updates"
        subtitle="Government notices, live alerts and incidents"
        right={
          <View style={styles.liveChip} accessibilityLabel={connected ? "Live updates connected" : "Live updates offline"}>
            <View style={[styles.liveDot, { backgroundColor: connected ? colors.success : colors.textMuted }]} />
            <Text style={styles.liveText}>{connected ? "Live" : "Offline"}</Text>
          </View>
        }
      />
      {error ? (
        <View style={{ paddingHorizontal: 20 }}>
          <ErrorBanner message={error} onRetry={() => void load()} />
        </View>
      ) : null}
      <FlatList
        data={incidents ?? []}
        keyExtractor={(i) => i.id}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await load();
              setRefreshing(false);
            }}
          />
        }
        ListHeaderComponent={
          <View style={{ gap: 8, marginBottom: 12 }}>
            <Text style={styles.section}>Government notices</Text>
            {notices === null ? null : notices.length === 0 ? (
              <Text style={styles.itemSub}>No notices published right now.</Text>
            ) : (
              notices.map((n) => {
                const open = openNotice === n.id;
                return (
                  <FadeIn key={n.id}>
                    <Pressable
                      onPress={() => {
                        animateNextLayout();
                        setOpenNotice(open ? null : n.id);
                      }}
                      style={[styles.notice, { borderLeftColor: noticeTone(n.priority) }]}
                      accessibilityRole="button"
                      accessibilityState={{ expanded: open }}
                      accessibilityHint={open ? "Collapse notice" : "Read the full notice"}
                    >
                      <View style={styles.noticeTop}>
                        <Ionicons name={n.isPinned ? "pin" : "megaphone-outline"} size={14} color={colors.textMuted} />
                        <Text style={styles.noticeMeta} numberOfLines={1}>
                          {n.department}
                          {n.publishDate ? ` · ${timeAgo(n.publishDate)}` : ""}
                        </Text>
                        <StatusBadge value={n.priority} />
                      </View>
                      <Text style={styles.itemTitle}>{n.title}</Text>
                      {n.summary ? (
                        <Text style={styles.itemSub} numberOfLines={open ? undefined : 2}>
                          {n.summary}
                        </Text>
                      ) : null}
                      {open && n.body ? <Text style={styles.noticeBody}>{n.body}</Text> : null}
                      {open ? (
                        <Text style={styles.noticeRef}>
                          Ref {n.referenceNumber} · {n.signatory}
                        </Text>
                      ) : null}
                    </Pressable>
                  </FadeIn>
                );
              })
            )}
            {live.length > 0 ? (
              <>
                <Text style={[styles.section, { marginTop: 8 }]}>Just now</Text>
                {live.map((m) => {
                  const { title, body } = describe(m);
                  return (
                    // Keyed by entity (one row each), so an update re-orders the row instead of remounting the list.
                    <FadeIn key={m.entityId} style={styles.liveItem}>
                      <Ionicons name="flash" size={16} color={colors.primary} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle} numberOfLines={1}>
                          {title}
                        </Text>
                        <Text style={styles.itemSub}>
                          {body} · {timeAgo(m.timestamp)}
                        </Text>
                      </View>
                    </FadeIn>
                  );
                })}
              </>
            ) : null}
            <Text style={[styles.section, { marginTop: 8 }]}>Active incidents</Text>
          </View>
        }
        ListEmptyComponent={
          incidents === null ? <Loading /> : <Empty title="All clear" body="No active incidents reported near the city right now." />
        }
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        renderItem={({ item, index }) => (
          <FadeIn animate={firstBatch()} index={index} style={styles.item}>
            <View style={[styles.sev, { backgroundColor: item.severity >= 4 ? colors.danger : item.severity >= 3 ? colors.warning : colors.accentBlue }]}>
              <Text style={styles.sevText}>{item.severity}</Text>
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={styles.itemTitle}>{item.title}</Text>
              {item.summary ? (
                <Text style={styles.itemSub} numberOfLines={2}>
                  {item.summary}
                </Text>
              ) : null}
              <Text style={styles.itemSub}>
                {item.type.toLowerCase()} · {item.observationCount} report{item.observationCount === 1 ? "" : "s"} · {timeAgo(item.updatedAt)}
              </Text>
            </View>
            <StatusBadge value={item.status} />
          </FadeIn>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 20, paddingBottom: 32, flexGrow: 1 },
  liveChip: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surfaceAlt, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 },
  liveDot: { width: 8, height: 8, borderRadius: 4 },
  liveText: { fontFamily: fonts.semibold, fontSize: 12, color: colors.text },
  section: { fontFamily: fonts.bold, fontSize: 16, color: colors.text },
  liveItem: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: radius.md, backgroundColor: "#FBEFF2" },
  item: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: radius.md, backgroundColor: colors.surfaceAlt },
  sev: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  sevText: { color: "#fff", fontFamily: fonts.bold },
  itemTitle: { fontFamily: fonts.semibold, fontSize: 15, color: colors.text },
  itemSub: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted },
  notice: { gap: 4, padding: 14, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderLeftWidth: 4 },
  noticeTop: { flexDirection: "row", alignItems: "center", gap: 6 },
  noticeMeta: { flex: 1, fontFamily: fonts.medium, fontSize: 12, color: colors.textMuted },
  noticeBody: { fontFamily: fonts.regular, fontSize: 13, lineHeight: 19, color: colors.text, marginTop: 4 },
  noticeRef: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted, marginTop: 4 },
});

import { Image } from "expo-image";
import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { errorMessage } from "../../api/client";
import { civicApi } from "../../api/endpoints";
import type { Complaint } from "../../api/types";
import { AuthHeader } from "../../components/AuthHeader";
import { Card } from "../../components/Card";
import { ErrorBanner, Loading } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { FadeIn } from "../../motion/FadeIn";
import { config } from "../../config";
import { colors, fonts } from "../../theme";
import { timeAgo } from "../../utils/geo";

export default function TrackComplaint() {
  const { trackingId } = useLocalSearchParams<{ trackingId: string }>();
  const [complaint, setComplaint] = useState<Complaint | null>(null);
  const [ladder, setLadder] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [c, meta] = await Promise.all([civicApi.track(trackingId), civicApi.meta()]);
      setComplaint(c);
      setLadder(meta.escalationLadder);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [trackingId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
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
      >
        <AuthHeader title={trackingId} fallback="/townhall" />
        {error ? <ErrorBanner message={error} onRetry={load} /> : null}
        {!complaint && !error ? <Loading /> : null}
        {complaint ? (
          <FadeIn style={styles.loaded}>
            <Card style={{ gap: 6 }}>
              <StatusBadge value={complaint.status} />
              <Text style={styles.title}>{complaint.title}</Text>
              <Text style={styles.body}>{complaint.description}</Text>
              {complaint.photoUrl ? (
                <Image
                  source={{ uri: `${config.complaintServiceUrl}${complaint.photoUrl}` }}
                  style={{ width: "100%", aspectRatio: 4 / 3, borderRadius: 12, backgroundColor: colors.surfaceAlt, marginVertical: 4 }}
                  contentFit="cover"
                  transition={250}
                  accessibilityLabel="Photo attached to this complaint"
                />
              ) : null}
              <Text style={styles.meta}>
                {complaint.department.replace(/_/g, " ")} · {complaint.priority.toLowerCase()} priority · filed {timeAgo(complaint.createdAt)}
              </Text>
              {complaint.assignedWorker ? <Text style={styles.meta}>Assigned to {complaint.assignedWorker}</Text> : null}
              {complaint.resolutionNotes ? <Text style={styles.body}>Resolution: {complaint.resolutionNotes}</Text> : null}
            </Card>

            <Text style={styles.section}>Escalation ladder</Text>
            <View style={styles.ladder}>
              {ladder.map((step, i) => {
                const done = i < complaint.escalationLevel || (i === 0 && complaint.escalationLevel >= 0);
                const current = i === complaint.escalationLevel;
                return (
                  <View key={step} style={styles.step}>
                    <View style={styles.rail}>
                      <View style={[styles.node, done && styles.nodeDone, current && styles.nodeCurrent]} />
                      {i < ladder.length - 1 ? <View style={[styles.line, i < complaint.escalationLevel && styles.lineDone]} /> : null}
                    </View>
                    <Text style={[styles.stepText, current && styles.stepCurrent, !done && !current && styles.stepTodo]}>{step}</Text>
                  </View>
                );
              })}
            </View>
          </FadeIn>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 24, paddingBottom: 32, gap: 12 },
  loaded: { gap: 12 },
  title: { fontFamily: fonts.bold, fontSize: 18, color: colors.text },
  body: { fontFamily: fonts.regular, fontSize: 14, color: colors.text },
  meta: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted },
  section: { fontFamily: fonts.bold, fontSize: 16, color: colors.text, marginTop: 8 },
  ladder: { paddingLeft: 4 },
  step: { flexDirection: "row", gap: 12, minHeight: 40 },
  rail: { alignItems: "center", width: 16 },
  node: { width: 14, height: 14, borderRadius: 7, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface },
  nodeDone: { backgroundColor: colors.primary, borderColor: colors.primary },
  nodeCurrent: { borderColor: colors.primary, backgroundColor: "#fff", borderWidth: 4 },
  line: { flex: 1, width: 2, backgroundColor: colors.border },
  lineDone: { backgroundColor: colors.primary },
  stepText: { fontFamily: fonts.medium, color: colors.text, marginTop: -2 },
  stepCurrent: { fontFamily: fonts.bold, color: colors.primary },
  stepTodo: { color: colors.textMuted },
});

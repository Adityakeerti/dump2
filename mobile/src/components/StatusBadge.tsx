import { StyleSheet, Text, View } from "react-native";
import { colors, fonts } from "../theme";

const tone: Record<string, string> = {
  FILED: colors.accentBlue,
  ASSIGNED: colors.warning,
  IN_PROGRESS: colors.warning,
  ESCALATED: colors.danger,
  RESOLVED: colors.success,
  REJECTED: colors.textMuted,
  OPEN: colors.danger,
  CRITICAL: colors.danger,
  ALERT: colors.danger,
  WARNING: colors.warning,
  INFO: colors.accentBlue,
};

/** Complaint-module ladder statuses: WORKER_ASSIGNED, WARNING_1..5, ESCALATED_<authority>. */
function ladderTone(v: string): string | undefined {
  if (v === "WORKER_ASSIGNED") return colors.warning;
  if (v.startsWith("WARNING_")) return colors.warning;
  if (v.startsWith("ESCALATED_")) return colors.danger;
  return undefined;
}

export function StatusBadge({ value }: { value: string }) {
  const key = value.toUpperCase();
  const c = tone[key] ?? ladderTone(key) ?? colors.textMuted;
  return (
    <View style={[styles.badge, { backgroundColor: `${c}1A` }]}>
      <Text style={[styles.text, { color: c }]}>{value.replace(/_/g, " ")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: "flex-start" },
  text: { fontFamily: fonts.bold, fontSize: 11, letterSpacing: 0.3 },
});

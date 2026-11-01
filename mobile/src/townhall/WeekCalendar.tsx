import { Ionicons } from "@expo/vector-icons";
import { useEffect, useRef } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { useReducedMotion } from "../motion";
import { Tap } from "../motion/Tap";
import { colors, fonts } from "../theme";

const DAY = 86_400_000;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
export const startOfWeek = (d: Date) => new Date(startOfDay(d).getTime() - d.getDay() * DAY);
export const sameDay = (a: Date, b: Date) => startOfDay(a).getTime() === startOfDay(b).getTime();

/**
 * Week strip like a pocket calendar: month header with arrows, seven days, a dot under days that
 * have events, the selected day in a navy circle that springs into place.
 */
export function WeekCalendar({
  weekStart,
  selected,
  marked,
  onSelect,
  onShiftWeek,
}: {
  weekStart: Date;
  selected: Date | null;
  /** Days (start-of-day ms) that have at least one event. */
  marked: Set<number>;
  onSelect: (d: Date) => void;
  onShiftWeek: (delta: number) => void;
}) {
  const days = Array.from({ length: 7 }, (_, i) => new Date(weekStart.getTime() + i * DAY));
  const today = startOfDay(new Date());
  const label = (selected ?? days[3]).toLocaleDateString("en-IN", { month: "long", day: "numeric", year: "numeric" });

  return (
    <View style={styles.wrap}>
      <View style={styles.header}>
        <Tap feedback="dim" hitSlop={10} onPress={() => onShiftWeek(-1)} accessibilityLabel="Previous week">
          <Ionicons name="chevron-back" size={20} color={colors.text} />
        </Tap>
        <Text style={styles.month}>{label}</Text>
        <Tap feedback="dim" hitSlop={10} onPress={() => onShiftWeek(1)} accessibilityLabel="Next week">
          <Ionicons name="chevron-forward" size={20} color={colors.text} />
        </Tap>
      </View>
      <View style={styles.row}>
        {days.map((d) => (
          <DayCell
            key={d.getTime()}
            date={d}
            on={!!selected && sameDay(d, selected)}
            today={sameDay(d, today)}
            marked={marked.has(startOfDay(d).getTime())}
            onPress={() => onSelect(d)}
          />
        ))}
      </View>
    </View>
  );
}

function DayCell({ date, on, today, marked, onPress }: { date: Date; on: boolean; today: boolean; marked: boolean; onPress: () => void }) {
  const reduced = useReducedMotion();
  const v = useRef(new Animated.Value(on ? 1 : 0)).current;
  useEffect(() => {
    if (reduced) v.setValue(on ? 1 : 0);
    else Animated.spring(v, { toValue: on ? 1 : 0, friction: 6, tension: 140, useNativeDriver: true }).start();
  }, [on, reduced, v]);
  return (
    <Tap
      feedback="dim"
      style={styles.cell}
      onPress={onPress}
      accessibilityLabel={`${date.toDateString()}${marked ? ", has events" : ""}`}
      accessibilityState={{ selected: on }}
    >
      <Text style={styles.weekday}>{WEEKDAYS[date.getDay()]}</Text>
      <View style={styles.dayBox}>
        <Animated.View style={[styles.circle, { opacity: v, transform: [{ scale: v.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] }) }] }]} />
        <Text style={[styles.day, today && !on && { color: colors.primary }, on && { color: "#fff" }]}>{date.getDate()}</Text>
      </View>
      <View style={[styles.dot, { opacity: marked ? 1 : 0 }]} />
    </Tap>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 4 },
  month: { fontFamily: fonts.semibold, fontSize: 14, color: colors.text },
  row: { flexDirection: "row", justifyContent: "space-between" },
  cell: { alignItems: "center", gap: 6, width: 42, paddingVertical: 2 },
  weekday: { fontFamily: fonts.medium, fontSize: 12, color: colors.textMuted },
  dayBox: { width: 34, height: 34, alignItems: "center", justifyContent: "center" },
  circle: { position: "absolute", width: 34, height: 34, borderRadius: 17, backgroundColor: colors.navy },
  day: { fontFamily: fonts.semibold, fontSize: 14, color: colors.text },
  dot: { width: 5, height: 5, borderRadius: 2.5, backgroundColor: colors.primary },
});

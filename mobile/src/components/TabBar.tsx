import { Ionicons } from "@expo/vector-icons";
import { useEffect, useMemo, useRef } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { duration, timing, useMotion } from "../motion";
import { Tap } from "../motion/Tap";
import { colors, fonts } from "../theme";

export interface TabItem {
  name: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconActive: keyof typeof Ionicons.glyphMap;
}

/** Bottom bar from the mockup: icon + label, active tab gets a soft blue pill behind the icon. */
export function TabBar({
  items,
  activeName,
  onSelect,
}: {
  items: TabItem[];
  activeName: string;
  onSelect: (name: string) => void;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
      {items.map((t) => (
        <Tab key={t.name} item={t} active={t.name === activeName} onPress={() => onSelect(t.name)} />
      ))}
    </View>
  );
}

function Tab({ item, active, onPress }: { item: TabItem; active: boolean; onPress: () => void }) {
  const { pillFrom } = useMotion();
  // `on`: the selected pill grows out from the icon. `press`: a faint pill shows under the finger before release.
  const on = useRef(new Animated.Value(active ? 1 : 0)).current;
  const press = useRef(new Animated.Value(0)).current;
  // The icon gives a small springy hop when its tab becomes active.
  const hop = useRef(new Animated.Value(0)).current;
  const { reduced } = useMotion();

  useEffect(() => {
    timing(on, active ? 1 : 0, { duration: duration.fast, curve: "move" }).start();
    if (active && !reduced) {
      hop.setValue(0);
      Animated.sequence([
        Animated.timing(hop, { toValue: 1, duration: 120, useNativeDriver: true }),
        Animated.spring(hop, { toValue: 0, friction: 4, tension: 160, useNativeDriver: true }),
      ]).start();
    }
  }, [active, on, hop, reduced]);

  const pillStyle = useMemo(
    () => ({ opacity: on, transform: [{ scaleX: on.interpolate({ inputRange: [0, 1], outputRange: [pillFrom, 1] }) }] }),
    [on, pillFrom],
  );

  return (
    <Tap
      feedback="none"
      style={styles.item}
      onPress={onPress}
      onPressIn={() => timing(press, 1, { duration: duration.pressIn }).start()}
      onPressOut={() => timing(press, 0, { duration: duration.pressOut }).start()}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      accessibilityLabel={item.label}
    >
      <View style={styles.pill}>
        <Animated.View style={[StyleSheet.absoluteFill, styles.pillPress, { opacity: press }]} />
        <Animated.View style={[StyleSheet.absoluteFill, styles.pillActive, pillStyle]} />
        <Animated.View
          style={{
            transform: [
              { translateY: hop.interpolate({ inputRange: [0, 1], outputRange: [0, -4] }) },
              { scale: hop.interpolate({ inputRange: [0, 1], outputRange: [1, 1.15] }) },
            ],
          }}
        >
          <Ionicons name={active ? item.iconActive : item.icon} size={20} color={active ? colors.tabActive : "#4A4A55"} />
        </Animated.View>
      </View>
      <Text style={[styles.label, active && styles.labelActive]}>{item.label}</Text>
    </Tap>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    backgroundColor: "#F7F8FC",
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  item: { flex: 1, alignItems: "center", gap: 2 },
  pill: { width: 52, height: 28, alignItems: "center", justifyContent: "center" },
  pillPress: { borderRadius: 14, backgroundColor: "rgba(15, 23, 42, 0.06)" },
  pillActive: { borderRadius: 14, backgroundColor: colors.tabActiveBg },
  label: { fontFamily: fonts.medium, fontSize: 11, color: "#4A4A55" },
  labelActive: { color: colors.tabActive, fontFamily: fonts.bold },
});

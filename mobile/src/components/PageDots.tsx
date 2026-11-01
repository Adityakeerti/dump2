import { useEffect, useRef } from "react";
import { Animated, StyleSheet, View } from "react-native";
import { duration, easing, useReducedMotion } from "../motion";
import { colors } from "../theme";

export function PageDots({ count, index }: { count: number; index: number }) {
  return (
    <View style={styles.row} accessibilityLabel={`Page ${index + 1} of ${count}`}>
      {Array.from({ length: count }, (_, i) => (
        <Dot key={i} active={i === index} />
      ))}
    </View>
  );
}

/**
 * The active dot stretches into a bar. Width affects layout, so this one runs on the JS driver:
 * three tiny views animating only when the page changes.
 */
function Dot({ active }: { active: boolean }) {
  const reduced = useReducedMotion();
  const on = useRef(new Animated.Value(active ? 1 : 0)).current;

  useEffect(() => {
    const to = active ? 1 : 0;
    if (reduced) on.setValue(to);
    else Animated.timing(on, { toValue: to, duration: duration.fast, easing: easing.move, useNativeDriver: false }).start();
  }, [active, reduced, on]);

  return (
    <Animated.View
      style={[
        styles.dot,
        {
          width: on.interpolate({ inputRange: [0, 1], outputRange: [8, 14] }),
          backgroundColor: on.interpolate({ inputRange: [0, 1], outputRange: [colors.dotInactive, colors.dot] }),
        },
      ]}
    />
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 4, alignItems: "center" },
  dot: { height: 4, borderRadius: 2 },
});

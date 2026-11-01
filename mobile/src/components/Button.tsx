import { ActivityIndicator, StyleSheet, Text, type ViewStyle } from "react-native";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";

interface Props {
  title: string;
  onPress: () => void;
  variant?: "primary" | "outline";
  loading?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
  compact?: boolean;
}

export function Button({ title, onPress, variant = "primary", loading, disabled, style, compact }: Props) {
  const outline = variant === "outline";
  return (
    <Tap
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      accessibilityLabel={title}
      onPress={onPress}
      disabled={disabled || loading}
      style={[styles.base, compact && styles.compact, outline ? styles.outline : styles.primary, (disabled || loading) && styles.disabled, style]}
    >
      {loading ? (
        <ActivityIndicator color={outline ? colors.primary : "#fff"} />
      ) : (
        <Text style={[styles.label, outline && { color: colors.primary }]}>{title}</Text>
      )}
    </Tap>
  );
}

const styles = StyleSheet.create({
  base: { height: 48, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", paddingHorizontal: 20 },
  compact: { height: 40 },
  primary: { backgroundColor: colors.primary },
  outline: { borderWidth: 1.5, borderColor: colors.primary, backgroundColor: colors.surface },
  disabled: { opacity: 0.55 },
  label: { color: "#fff", fontFamily: fonts.semibold, fontSize: 15 },
});

import type { ReactNode } from "react";
import { type StyleProp, Text, type TextStyle, type ViewStyle } from "react-native";
import { Tap } from "../motion/Tap";

/** Tappable text that dims on touch, like every other control. Not pressable when `onPress` is absent. */
export function LinkText({
  children,
  onPress,
  style,
  containerStyle,
  accessibilityRole = "button",
  accessibilityLabel,
}: {
  children: ReactNode;
  onPress?: () => void;
  style?: StyleProp<TextStyle>;
  containerStyle?: StyleProp<ViewStyle>;
  accessibilityRole?: "button" | "link";
  accessibilityLabel?: string;
}) {
  return (
    <Tap
      feedback="dim"
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={accessibilityRole}
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: !onPress }}
      hitSlop={8}
      style={containerStyle}
    >
      <Text style={style}>{children}</Text>
    </Tap>
  );
}

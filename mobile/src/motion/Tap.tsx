import { type ReactNode, useEffect, useMemo, useRef } from "react";
import {
  Animated,
  type GestureResponderEvent,
  Pressable,
  type PressableProps,
  type StyleProp,
  StyleSheet,
  type ViewStyle,
} from "react-native";
import { duration, opacity, timing, useMotion } from "./index";

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

/**
 * - `scale`: buttons, cards, chips, floating buttons; shrink slightly (a light dim under reduce motion).
 * - `highlight`: full-width rows and tab items; a soft tint fades in behind the content.
 * - `dim`: icon-only buttons and text links; fade to half opacity.
 * - `none`: no visual response (emergency controls render their own pressed state with zero delay).
 */
export type Feedback = "scale" | "highlight" | "dim" | "none";

export interface TapProps extends Omit<PressableProps, "style" | "children"> {
  feedback?: Feedback;
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
  highlightColor?: string;
}

/**
 * The one pressable used across the app, so every touch responds the same way.
 * Feedback starts on touch-down on the native driver; `onPress` is never delayed by it.
 */
export function Tap({
  feedback = "scale",
  style,
  children,
  highlightColor = "rgba(15, 23, 42, 0.06)",
  onPressIn,
  onPressOut,
  disabled,
  accessibilityRole = "button",
  ...rest
}: TapProps) {
  const { pressScale, pressOpacity } = useMotion();
  const pressed = useRef(new Animated.Value(0)).current;
  const live = feedback !== "none" && !disabled;

  // A control that becomes disabled mid-press (e.g. a button switching to loading) must not stay pressed.
  useEffect(() => {
    if (disabled) timing(pressed, 0, { duration: duration.pressOut }).start();
  }, [disabled, pressed]);

  const handleIn = (e: GestureResponderEvent) => {
    if (live) timing(pressed, 1, { duration: duration.pressIn }).start();
    onPressIn?.(e);
  };
  const handleOut = (e: GestureResponderEvent) => {
    timing(pressed, 0, { duration: duration.pressOut }).start();
    onPressOut?.(e);
  };

  const flat = StyleSheet.flatten(style) ?? {};
  // Feedback scales the caller's own opacity (e.g. a disabled button's) rather than replacing it.
  const base = typeof flat.opacity === "number" ? flat.opacity : 1;

  // Built once per input change, not per render, so list re-renders don't re-attach native nodes.
  const feedbackStyle = useMemo((): Animated.WithAnimatedValue<ViewStyle> | null => {
    const fade = (to: number) => pressed.interpolate({ inputRange: [0, 1], outputRange: [base, base * to] });
    if (feedback === "scale") {
      return {
        transform: [{ scale: pressed.interpolate({ inputRange: [0, 1], outputRange: [1, pressScale] }) }],
        opacity: fade(pressOpacity),
      };
    }
    if (feedback === "dim") return { opacity: fade(opacity.dim) };
    return null;
  }, [feedback, base, pressScale, pressOpacity, pressed]);

  const radius = feedback === "highlight" ? flat.borderRadius : undefined;

  return (
    <AnimatedPressable
      {...rest}
      disabled={disabled}
      accessibilityRole={accessibilityRole}
      onPressIn={handleIn}
      onPressOut={handleOut}
      style={[style, feedbackStyle]}
    >
      {feedback === "highlight" ? (
        <Animated.View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, { backgroundColor: highlightColor, opacity: pressed, borderRadius: radius }]}
        />
      ) : null}
      {children}
    </AnimatedPressable>
  );
}

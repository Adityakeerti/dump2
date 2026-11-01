import { useEffect, useState } from "react";
import { Keyboard, Platform } from "react-native";

/**
 * Current on-screen keyboard height (0 when hidden). Works regardless of Android's window resize mode
 * (edge-to-edge apps don't get adjustResize), so floating inputs can lift themselves above it.
 */
export function useKeyboardHeight() {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    const show = Keyboard.addListener(Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow", (e) =>
      setHeight(e.endCoordinates.height),
    );
    const hide = Keyboard.addListener(Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide", () => setHeight(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return height;
}

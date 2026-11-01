import { Ionicons } from "@expo/vector-icons";
import { StyleSheet } from "react-native";
import { Tap } from "../motion/Tap";

export function NextArrow({ onPress, label = "Next" }: { onPress: () => void; label?: string }) {
  return (
    <Tap accessibilityLabel={label} onPress={onPress} style={styles.btn} hitSlop={10}>
      <Ionicons name="chevron-forward" size={20} color="#fff" />
    </Tap>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#111",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer" as any,
  },
});

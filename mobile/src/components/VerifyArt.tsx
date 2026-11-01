import { Ionicons } from "@expo/vector-icons";
import { StyleSheet, View } from "react-native";
import { colors } from "../theme";

/**
 * Stand-in for the mockup's "person at laptop" illustration, which is not among the provided
 * assets. Swap for the real artwork once it is exported.
 */
export function VerifyArt() {
  return (
    <View style={styles.wrap} accessibilityElementsHidden>
      <View style={styles.window}>
        <View style={styles.bar} />
        <View style={styles.row}>
          {[0, 1, 2, 3].map((i) => (
            <View key={i} style={styles.cell} />
          ))}
        </View>
        <Ionicons name="mail-open-outline" size={44} color="#2F9E8F" style={{ marginTop: 10 }} />
      </View>
      <View style={styles.shield}>
        <Ionicons name="shield-checkmark" size={40} color="#2F9E8F" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { height: 170, alignItems: "center", justifyContent: "center", marginVertical: 8 },
  window: {
    width: 230,
    height: 140,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#FAFAFC",
    alignItems: "center",
    paddingTop: 0,
    overflow: "hidden",
  },
  bar: { height: 10, alignSelf: "stretch", backgroundColor: "#4A4A55" },
  row: { flexDirection: "row", gap: 8, marginTop: 18 },
  cell: { width: 26, height: 26, borderRadius: 6, borderWidth: 1, borderColor: "#C9C9D2", backgroundColor: "#fff" },
  shield: {
    position: "absolute",
    right: 40,
    top: 0,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: "#E3F5F2",
    alignItems: "center",
    justifyContent: "center",
  },
});

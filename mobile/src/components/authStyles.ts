import { StyleSheet } from "react-native";
import { colors, fonts } from "../theme";

export const authStyles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 28, paddingBottom: 32 },
  link: { fontFamily: fonts.medium, color: colors.text, textDecorationLine: "underline", marginTop: 16, fontSize: 14 },
  switch: { textAlign: "center", marginTop: 24, fontFamily: fonts.regular, color: colors.textMuted },
  switchRow: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", alignItems: "center", marginTop: 24 },
  switchText: { fontFamily: fonts.regular, color: colors.textMuted },
  switchLink: { color: colors.primary, fontFamily: fonts.bold },
});

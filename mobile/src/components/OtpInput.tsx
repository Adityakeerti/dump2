import { useRef } from "react";
import { Pressable, StyleSheet, Text, TextInput, type TextInputInstance, View } from "react-native";
import { colors, fonts, radius } from "../theme";

/** N separate boxes backed by one hidden input, so paste and autofill work. */
export function OtpInput({ length, value, onChange }: { length: number; value: string; onChange: (v: string) => void }) {
  const ref = useRef<TextInputInstance>(null);
  return (
    <Pressable style={styles.row} onPress={() => ref.current?.focus()} accessibilityLabel="Verification code">
      {Array.from({ length }, (_, i) => {
        const focused = i === Math.min(value.length, length - 1);
        return (
          <View key={i} style={[styles.box, focused && styles.focused]}>
            <Text style={styles.digit}>{value[i] ?? ""}</Text>
          </View>
        );
      })}
      <TextInput
        ref={ref}
        value={value}
        onChangeText={(t) => onChange(t.replace(/\D/g, "").slice(0, length))}
        keyboardType="number-pad"
        textContentType="oneTimeCode"
        autoComplete="sms-otp"
        maxLength={length}
        autoFocus
        style={styles.hidden}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  box: {
    flex: 1,
    aspectRatio: 1,
    maxWidth: 64,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  focused: { borderColor: colors.primary },
  digit: { fontFamily: fonts.bold, fontSize: 22, color: colors.text },
  hidden: { position: "absolute", opacity: 0, width: 1, height: 1 },
});

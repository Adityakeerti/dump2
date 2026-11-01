import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { errorMessage } from "../api/client";
import { authApi } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { AuthHeader } from "../components/AuthHeader";
import { Button } from "../components/Button";
import { OtpInput } from "../components/OtpInput";
import { LinkText } from "../components/LinkText";
import { ErrorBanner } from "../components/StateViews";
import { VerifyArt } from "../components/VerifyArt";
import { mmss, useCountdown } from "../hooks/useCountdown";
import { colors, fonts } from "../theme";

export default function Verify() {
  const { user, signIn, signOut } = useAuth();
  const email = user?.email ?? "";
  const [length, setLength] = useState(4);
  const [cooldown, setCooldown] = useState({ seconds: 0, n: 0 });
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const left = useCountdown(cooldown.seconds, cooldown.n);

  const send = useCallback(async () => {
    if (!email) return;
    setError(null);
    try {
      // Server enforces the cooldown; it reports how long until another send is allowed.
      const res = await authApi.sendOtp(email);
      setLength(res.codeLength);
      setCooldown((c) => ({ seconds: res.resendAfterSeconds, n: c.n + 1 }));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [email]);

  useEffect(() => {
    if (!user) router.replace("/welcome");
    else if (user.emailVerified) router.replace("/explore");
    else void send();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async () => {
    if (code.length !== length) return setError(`Enter the ${length}-digit code`);
    setBusy(true);
    setError(null);
    try {
      const res = await authApi.verifyOtp(email, code);
      await signIn(res);
      router.replace("/verified");
    } catch (e) {
      setError(errorMessage(e));
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AuthHeader title="Verify" back={false} />
        <VerifyArt />
        <Text style={styles.heading}>Enter OTP</Text>
        <Text style={styles.sub}>
          A {length} digit OTP has been sent to your registered email{email ? `\n${email}` : ""}
        </Text>
        <OtpInput length={length} value={code} onChange={setCode} />
        {error ? <ErrorBanner message={error} /> : null}
        <Button title="Verify" onPress={submit} loading={busy} style={{ marginTop: 28 }} />
        <LinkText
          style={[styles.resend, left > 0 && styles.resendDisabled]}
          containerStyle={styles.centered}
          onPress={left > 0 ? undefined : send}
        >
          Resend OTP {left > 0 ? <Text style={styles.timer}>({mmss(left)})</Text> : null}
        </LinkText>
        <LinkText style={styles.switch} containerStyle={styles.centered} onPress={() => void signOut().then(() => router.replace("/welcome"))}>
          Use a different account
        </LinkText>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: 28, paddingBottom: 32, gap: 12 },
  heading: { fontFamily: fonts.bold, fontSize: 20, textAlign: "center", color: colors.text, marginTop: 4 },
  sub: { fontFamily: fonts.regular, fontSize: 14, textAlign: "center", color: colors.textMuted, marginBottom: 16 },
  resend: { textAlign: "center", fontFamily: fonts.semibold, color: colors.text, marginTop: 12 },
  resendDisabled: { color: colors.textMuted },
  timer: { fontFamily: fonts.regular, color: colors.textMuted },
  switch: { textAlign: "center", fontFamily: fonts.regular, color: colors.primary, marginTop: 8 },
  centered: { alignSelf: "center" },
});

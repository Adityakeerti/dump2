import { router } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { errorMessage } from "../api/client";
import { authApi } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { authStyles as styles } from "../components/authStyles";
import { AuthHeader } from "../components/AuthHeader";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { OtpInput } from "../components/OtpInput";
import { LinkText } from "../components/LinkText";
import { ErrorBanner } from "../components/StateViews";
import { TextField } from "../components/TextField";
import { mmss, useCountdown } from "../hooks/useCountdown";
import { FadeIn } from "../motion/FadeIn";
import { colors } from "../theme";

/** Two steps on one screen: request a reset code, then set a new password with it. */
export default function Forgot() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<{ length: number; cooldown: number; n: number } | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const left = useCountdown(sent?.cooldown ?? 0, sent?.n ?? 0);

  const request = async () => {
    if (!email.trim()) return setError("Enter your email");
    setBusy(true);
    setError(null);
    try {
      const res = await authApi.forgotPassword(email.trim());
      setSent((s) => ({ length: res.codeLength, cooldown: res.resendAfterSeconds, n: (s?.n ?? 0) + 1 }));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!sent || code.length !== sent.length) return setError(`Enter the ${sent?.length ?? 4}-digit code`);
    if (password.length < 8) return setError("Password must be at least 8 characters");
    setBusy(true);
    setError(null);
    try {
      const res = await authApi.resetPassword(email.trim(), code, password);
      await signIn(res);
      router.replace("/explore");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <AuthHeader title="Reset password" />
          <Card>
            <TextField
              label="Email"
              placeholder="Enter your registered email"
              value={email}
              onChangeText={setEmail}
              editable={!sent}
              autoCapitalize="none"
              keyboardType="email-address"
            />
            {sent ? (
              // Second step arrives in place of the send button; it eases in so the change reads as progress.
              <FadeIn>
                <Text style={[styles.switch, { marginTop: 0, marginBottom: 12, textAlign: "left" }]}>
                  If that email has an account, a {sent.length}-digit code is on its way.
                </Text>
                <OtpInput length={sent.length} value={code} onChange={setCode} />
                <TextField
                  label="New password"
                  placeholder="At least 8 characters"
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  style={{ marginTop: 0 }}
                />
                {error ? <ErrorBanner message={error} /> : null}
                <Button title="Set new password" onPress={reset} loading={busy} style={{ marginTop: 8 }} compact />
                <LinkText style={[styles.link, left > 0 && { color: colors.textMuted }]} containerStyle={{ alignSelf: "flex-start" }} onPress={left > 0 ? undefined : request}>
                  Resend code {left > 0 ? `(${mmss(left)})` : ""}
                </LinkText>
              </FadeIn>
            ) : (
              <>
                {error ? <ErrorBanner message={error} /> : null}
                <Button title="Send reset code" onPress={request} loading={busy} style={{ marginTop: 8 }} compact />
              </>
            )}
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

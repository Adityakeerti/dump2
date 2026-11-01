import { router } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { errorMessage } from "../api/client";
import { authApi } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { AuthHeader } from "../components/AuthHeader";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LinkText } from "../components/LinkText";
import { ErrorBanner } from "../components/StateViews";
import { TextField } from "../components/TextField";
import { authStyles as styles } from "../components/authStyles";

export default function SignUp() {
  const { signIn } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!fullName.trim() || !email.trim()) return setError("Enter your name and email");
    if (password.length < 8) return setError("Password must be at least 8 characters");
    setBusy(true);
    setError(null);
    try {
      // Core creates an unverified account and emails a code; the token works only after /verify.
      const res = await authApi.register({ fullName: fullName.trim(), email: email.trim(), password });
      await signIn(res);
      router.replace("/verify");
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
          <AuthHeader title="Sign Up" />
          <Card>
            <TextField label="Full name" placeholder="Enter your name" value={fullName} onChangeText={setFullName} autoComplete="name" />
            <TextField
              label="Email"
              placeholder="Enter your email"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
            <TextField
              label="Password"
              placeholder="At least 8 characters"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="new-password"
              onSubmitEditing={submit}
            />
            {error ? <ErrorBanner message={error} /> : null}
            <Button title="Create account" onPress={submit} loading={busy} style={{ marginTop: 8 }} compact />
          </Card>
          <View style={styles.switchRow}>
            <Text style={styles.switchText}>Already have an account? </Text>
            <LinkText style={styles.switchLink} onPress={() => router.replace("/login")}>
              Login
            </LinkText>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

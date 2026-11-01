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

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!email.trim() || !password) {
      setError("Enter your email and password");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await authApi.login(email.trim(), password);
      await signIn(res);
      router.replace(res.user.emailVerified ? "/explore" : "/verify");
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
          <AuthHeader title="Login" />
          <Card>
            <TextField
              label="Avatar ID"
              placeholder="Enter your registered email"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
            />
            <TextField
              label="Password"
              placeholder="Enter Password"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="password"
              onSubmitEditing={submit}
            />
            {error ? <ErrorBanner message={error} /> : null}
            <Button title="Sign In" onPress={submit} loading={busy} style={{ marginTop: 8 }} compact />
            <LinkText style={styles.link} containerStyle={{ alignSelf: "flex-start" }} onPress={() => router.push("/forgot")}>
              Forgot password?
            </LinkText>
          </Card>
          <View style={styles.switchRow}>
            <Text style={styles.switchText}>New here? </Text>
            <LinkText style={styles.switchLink} onPress={() => router.replace("/signup")}>
              Create an account
            </LinkText>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

import { Image } from "expo-image";
import { router } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Button } from "../components/Button";
import { images } from "../content/onboarding";
import { colors, fonts } from "../theme";

export default function Verified() {
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.content}>
        <Image source={images.verified} style={styles.art} contentFit="contain" />
        <Text style={styles.title}>Your account{"\n"}was successfully verified !</Text>
        <Text style={styles.sub}>Proceed to your profile</Text>
        <Button title="Profile" onPress={() => router.replace("/settings")} style={styles.btn} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  content: { flex: 1, justifyContent: "center", paddingHorizontal: 28, marginTop: -80 },
  art: { width: 200, height: 140, alignSelf: "center" },
  title: { fontFamily: fonts.semibold, fontSize: 19, textAlign: "center", color: colors.text, marginTop: 16, lineHeight: 26 },
  sub: { fontFamily: fonts.regular, fontSize: 13, textAlign: "center", color: colors.textMuted, marginTop: 18 },
  btn: { marginTop: 16 },
});

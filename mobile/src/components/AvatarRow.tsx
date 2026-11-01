import { Image } from "expo-image";
import { StyleSheet, Text, View } from "react-native";
import { Tap } from "../motion/Tap";
import type { Avatar } from "../api/types";
import { absoluteUrl } from "../config";
import { colors, fonts } from "../theme";
import { Ionicons } from "@expo/vector-icons";

export function AvatarRow({ avatar, onPress, right }: { avatar: Avatar; onPress: () => void; right?: React.ReactNode }) {
  return (
    <Tap feedback="highlight" style={styles.row} onPress={onPress} accessibilityLabel={`${avatar.name}, ${avatar.title}`}>
      <View style={styles.imgWrap}>
        <Image source={{ uri: absoluteUrl(avatar.pinImageUrl) }} style={styles.img} contentFit="contain" />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.name}>{avatar.name}</Text>
        <Text style={styles.sub} numberOfLines={1}>
          {avatar.title}
        </Text>
        <View style={styles.meta}>
          <Ionicons name="star" size={12} color={colors.star} />
          <Text style={styles.metaText}>
            {Number(avatar.rating).toFixed(2)} · {avatar.category.toLowerCase()}
          </Text>
        </View>
      </View>
      {right}
    </Tap>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 12, paddingHorizontal: 20 },
  imgWrap: { width: 56, height: 56, borderRadius: 28, backgroundColor: "#FDEFE6", alignItems: "center", justifyContent: "center", overflow: "hidden" },
  img: { width: 48, height: 52 },
  name: { fontFamily: fonts.bold, fontSize: 16, color: colors.text },
  sub: { fontFamily: fonts.regular, fontSize: 13, color: colors.textMuted },
  meta: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  metaText: { fontFamily: fonts.medium, fontSize: 12, color: colors.textMuted },
});

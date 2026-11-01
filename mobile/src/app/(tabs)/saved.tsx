import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";
import { errorMessage } from "../../api/client";
import { avatarApi } from "../../api/endpoints";
import type { Avatar } from "../../api/types";
import { AvatarRow } from "../../components/AvatarRow";
import { ScreenHeader } from "../../components/ScreenHeader";
import { Empty, ErrorBanner, Loading } from "../../components/StateViews";
import { animateNextLayout } from "../../motion";
import { FadeIn, useFirstBatch } from "../../motion/FadeIn";
import { Tap } from "../../motion/Tap";
import { colors } from "../../theme";

export default function Saved() {
  const [items, setItems] = useState<Avatar[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const firstBatch = useFirstBatch(items !== null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await avatarApi.saved());
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  // Refresh whenever the tab gains focus so saves made elsewhere show up.
  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const unsave = async (a: Avatar) => {
    // Rows below close the gap smoothly instead of jumping up.
    animateNextLayout();
    setItems((list) => list?.filter((x) => x.id !== a.id) ?? null);
    try {
      await avatarApi.setSaved(a.id, false);
    } catch (e) {
      setError(errorMessage(e));
      void load();
    }
  };

  return (
    <View style={styles.fill}>
      <ScreenHeader title="Saved" subtitle="Avatars you bookmarked" />
      {error ? (
        <View style={{ paddingHorizontal: 20 }}>
          <ErrorBanner message={error} onRetry={load} />
        </View>
      ) : null}
      {items === null && !error ? (
        <Loading />
      ) : (
        <FlatList
          data={items ?? []}
          keyExtractor={(a) => a.id}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
            />
          }
          ItemSeparatorComponent={() => <View style={styles.sep} />}
          contentContainerStyle={items?.length ? undefined : { flex: 1 }}
          ListEmptyComponent={
            <Empty
              title="Nothing saved yet"
              body="Tap the bookmark on an avatar's profile to keep it here."
              action={{ label: "Explore the map", onPress: () => router.navigate("/explore") }}
            />
          }
          renderItem={({ item, index }) => (
            <FadeIn animate={firstBatch()} index={index}>
              <AvatarRow
                avatar={item}
                onPress={() => router.push({ pathname: "/avatar/[id]", params: { id: item.id } })}
                right={
                  <Tap feedback="dim" onPress={() => unsave(item)} hitSlop={10} accessibilityLabel={`Remove ${item.name} from saved`}>
                    <Ionicons name="bookmark" size={22} color={colors.primary} />
                  </Tap>
                }
              />
            </FadeIn>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.surface },
  sep: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginLeft: 90 },
});

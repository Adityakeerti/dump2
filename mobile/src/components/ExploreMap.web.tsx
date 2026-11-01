import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import React, { createElement, useEffect, useImperativeHandle, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { Avatar, MapConfig, Place } from "../api/types";
import { absoluteUrl } from "../config";
import type { LatLng } from "../hooks/useUserLocation";
import { colors, fonts, radius } from "../theme";
import type { ExploreMapProps } from "./ExploreMap";

export function ExploreMap({
  config,
  cameraRef,
  geofence,
  avatars,
  placePin,
  coords,
  onOpenAvatar,
  onMapReady,
}: ExploreMapProps) {
  const [center, setCenter] = useState({
    lat: config.defaultLatitude,
    lng: config.defaultLongitude,
  });

  useImperativeHandle(
    cameraRef,
    () =>
      ({
        fitBounds: (_bounds: any, _options?: any) => {},
        flyTo: (options: { center: [number, number]; zoom?: number }) => {
          if (options?.center) {
            setCenter({ lng: options.center[0], lat: options.center[1] });
          }
        },
        jumpTo: () => {},
        easeTo: () => {},
        zoomTo: () => {},
        setStop: () => {},
      }) as any,
  );

  useEffect(() => {
    onMapReady();
  }, [onMapReady]);

  // OpenStreetMap embed bbox around center
  const delta = 0.04;
  const bbox = `${center.lng - delta}%2C${center.lat - delta}%2C${center.lng + delta}%2C${center.lat + delta}`;
  const osmUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${center.lat}%2C${center.lng}`;

  return (
    <View style={styles.fill}>
      {/* Background OSM Web Map */}
      <View style={StyleSheet.absoluteFill}>
        {createElement("iframe", {
          src: osmUrl,
          style: {
            width: "100%",
            height: "100%",
            border: "none",
            pointerEvents: "auto",
          },
          title: "OpenStreetMap",
        })}
      </View>

      {/* Interactive Avatar Pins Overlay on Web */}
      <View style={styles.webPinsContainer} pointerEvents="box-none">
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.avatarPillsScroll}
          pointerEvents="box-none"
        >
          {avatars.map((a) => (
            <Pressable
              key={a.id}
              style={styles.avatarPill}
              onPress={() => onOpenAvatar(a)}
              accessibilityLabel={`${a.name}, ${a.title}`}
            >
              <Image source={{ uri: absoluteUrl(a.pinImageUrl) }} style={styles.pillImage} contentFit="contain" />
              <View style={styles.pillTextWrap}>
                <Text style={styles.pillName}>{a.name}</Text>
                <Text style={styles.pillTitle} numberOfLines={1}>
                  {a.title}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
            </Pressable>
          ))}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: "#E5E3DF" },
  webPinsContainer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 86,
    paddingHorizontal: 12,
  },
  avatarPillsScroll: {
    gap: 10,
    paddingVertical: 6,
  },
  avatarPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(255, 255, 255, 0.95)",
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: radius.pill,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
    borderWidth: 1,
    borderColor: "rgba(0,0,0,0.06)",
  },
  pillImage: { width: 32, height: 38 },
  pillTextWrap: { maxWidth: 140 },
  pillName: { fontFamily: fonts.semibold, fontSize: 13, color: colors.text },
  pillTitle: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
});

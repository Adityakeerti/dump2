import { Ionicons } from "@expo/vector-icons";
import { Camera, type CameraRef, GeoJSONSource, Layer, Map, Marker } from "@maplibre/maplibre-react-native";
import { Image } from "expo-image";
import type React from "react";
import { useRef } from "react";
import { StyleSheet, View } from "react-native";
import type { Avatar, MapConfig, Place } from "../api/types";
import { absoluteUrl } from "../config";
import type { LatLng } from "../hooks/useUserLocation";
import { colors } from "../theme";

export type ExploreMapProps = {
  config: MapConfig;
  cameraRef: React.RefObject<CameraRef | null>;
  geofence: any;
  avatars: Avatar[];
  placePin: Place | null;
  coords: LatLng | null;
  onOpenAvatar: (a: Avatar) => void;
  onMapReady: () => void;
  /** Tap on empty map: the main agent briefs the citizen about that spot. */
  onMapPress?: (point: { latitude: number; longitude: number }) => void;
  /** The spot currently being described by the main agent. */
  tappedPoint?: { latitude: number; longitude: number } | null;
};

/** Initial tilt: with the vector style's 3D buildings this gives a street-level, city-model feel. */
export const MAP_PITCH = 50;

export function ExploreMap({
  config,
  cameraRef,
  geofence,
  avatars,
  placePin,
  coords,
  onOpenAvatar,
  onMapReady,
  onMapPress,
  tappedPoint,
}: ExploreMapProps) {
  // A tap on an avatar pin can also reach the map's own press handler; don't treat it as a map tap.
  const lastPinPress = useRef(0);
  return (
    <Map
      style={styles.fill}
      mapStyle={absoluteUrl(config.styleUrl)}
      logo={false}
      compass={false}
      attribution
      attributionPosition={{ bottom: 8, left: 8 }}
      onDidFinishLoadingMap={onMapReady}
      // Low sun from the south-east so extruded buildings get readable shading.
      light={{ anchor: "viewport", position: [1.4, 135, 40], color: "#ffffff", intensity: 0.45 }}
      onPress={(e) => {
        if (Date.now() - lastPinPress.current < 600) return;
        const [lng, lat] = e.nativeEvent.lngLat;
        onMapPress?.({ latitude: lat, longitude: lng });
      }}
    >
      <Camera
        ref={cameraRef}
        minZoom={config.minZoom}
        maxZoom={config.maxZoom}
        initialViewState={{
          center: [config.defaultLongitude, config.defaultLatitude],
          zoom: config.defaultZoom,
          pitch: MAP_PITCH,
        }}
      />
      {geofence && (
        <GeoJSONSource id="geofence" data={geofence}>
          <Layer id="geofence-fill" type="fill" paint={{ "fill-color": colors.geofenceFill }} />
          <Layer id="geofence-line" type="line" paint={{ "line-color": colors.geofenceLine, "line-width": 1.5 }} />
        </GeoJSONSource>
      )}
      {avatars.map((a) => (
        <Marker key={a.id} id={a.id} lngLat={[a.longitude, a.latitude]} anchor="bottom" onPress={() => {
          lastPinPress.current = Date.now();
          onOpenAvatar(a);
        }}>
          <View pointerEvents="none" accessible accessibilityLabel={`${a.name}, ${a.title}`} style={styles.pinWrap}>
            <Image source={{ uri: absoluteUrl(a.pinImageUrl) }} style={styles.pinImage} contentFit="contain" />
            <Ionicons name="location" size={22} color={colors.pinGreen} style={styles.pinIcon} />
          </View>
        </Marker>
      ))}
      {placePin && (
        <Marker id="place" lngLat={[placePin.longitude, placePin.latitude]} anchor="bottom">
          <Ionicons pointerEvents="none" name="location-sharp" size={34} color={colors.primary} />
        </Marker>
      )}
      {tappedPoint && (
        <Marker id="tapped" lngLat={[tappedPoint.longitude, tappedPoint.latitude]} anchor="bottom">
          <Ionicons pointerEvents="none" name="sparkles" size={30} color={colors.accentBlue} />
        </Marker>
      )}
      {coords && (
        <Marker id="me" lngLat={[coords.longitude, coords.latitude]} anchor="center">
          <View style={styles.meHalo} pointerEvents="none">
            <View style={styles.meDot} />
          </View>
        </Marker>
      )}
    </Map>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.surface },
  pinWrap: { alignItems: "center" },
  pinImage: { width: 52, height: 64 },
  pinIcon: { marginTop: -6 },
  meHalo: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "rgba(59,130,246,0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  meDot: { width: 16, height: 16, borderRadius: 8, backgroundColor: colors.accentBlue, borderWidth: 2.5, borderColor: "#fff" },
});

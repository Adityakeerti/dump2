import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { errorMessage } from "../api/client";
import { weatherApi } from "../api/endpoints";
import type { AirQuality, CityWeather, WeatherForecast } from "../api/types";
import { ErrorBanner } from "../components/StateViews";
import { FadeIn } from "../motion/FadeIn";
import { Tap } from "../motion/Tap";
import { colors, fonts, radius } from "../theme";

/** WMO weather code -> label + icon (https://open-meteo.com/en/docs, "WMO Weather interpretation codes"). */
function wmo(code: number): { label: string; icon: keyof typeof Ionicons.glyphMap } {
  if (code === 0) return { label: "Clear sky", icon: "sunny" };
  if (code <= 2) return { label: "Partly cloudy", icon: "partly-sunny" };
  if (code === 3) return { label: "Overcast", icon: "cloudy" };
  if (code === 45 || code === 48) return { label: "Fog", icon: "cloudy" };
  if (code >= 51 && code <= 57) return { label: "Drizzle", icon: "rainy" };
  if (code >= 61 && code <= 67) return { label: "Rain", icon: "rainy" };
  if (code >= 71 && code <= 77) return { label: "Snow", icon: "snow" };
  if (code >= 80 && code <= 82) return { label: "Rain showers", icon: "rainy" };
  if (code >= 85 && code <= 86) return { label: "Snow showers", icon: "snow" };
  if (code >= 95) return { label: "Thunderstorm", icon: "thunderstorm" };
  return { label: "—", icon: "cloud-outline" };
}

/** US AQI bands (EPA). */
function aqiBand(aqi: number): { label: string; color: string } {
  if (aqi <= 50) return { label: "Good", color: "#2E9E5B" };
  if (aqi <= 100) return { label: "Moderate", color: "#E59E0B" };
  if (aqi <= 150) return { label: "Unhealthy for sensitive groups", color: "#F07B22" };
  if (aqi <= 200) return { label: "Unhealthy", color: "#D93A3A" };
  if (aqi <= 300) return { label: "Very unhealthy", color: "#8E3BB0" };
  return { label: "Hazardous", color: "#7A1F2B" };
}

const hhmm = (iso: string) => iso.slice(11, 16);
const dayName = (iso: string, i: number) =>
  i === 0 ? "Today" : new Date(`${iso}T12:00:00`).toLocaleDateString("en-IN", { weekday: "short" });

/** Townhall tab 3: live Dehradun weather, the next hours, the week, air quality and flood risk. */
export function WeatherPage({
  width,
  height,
  topInset,
  coords,
  onAsk,
}: {
  width: number;
  height: number;
  topInset: number;
  coords: { latitude: number; longitude: number } | null;
  onAsk: (prompt: string) => void;
}) {
  const [now, setNow] = useState<CityWeather | null>(null);
  const [fc, setFc] = useState<WeatherForecast | null>(null);
  const [air, setAir] = useState<AirQuality | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const lat = coords?.latitude ?? 30.3165;
  const lng = coords?.longitude ?? 78.0322;
  const load = useCallback(async () => {
    setError(null);
    const [n, f, a] = await Promise.allSettled([weatherApi.current(lat, lng), weatherApi.forecast(lat, lng), weatherApi.air(lat, lng)]);
    if (n.status === "fulfilled") setNow(n.value);
    if (f.status === "fulfilled") setFc(f.value);
    if (a.status === "fulfilled") setAir(a.value);
    const failed = [n, f].find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
    if (failed) setError(errorMessage(failed.reason));
  }, [lat, lng]);

  useEffect(() => {
    void load();
  }, [load]);

  const code = fc?.current.weather_code ?? 0;
  const sky = wmo(code);
  const temp = fc?.current.temperature_2m ?? now?.temperatureC;
  const aqi = air?.current.us_aqi;
  const band = aqi != null ? aqiBand(aqi) : null;
  const risk = now?.riskLevel ?? "NORMAL";

  return (
    <ScrollView
      style={{ width, height }}
      contentContainerStyle={[styles.content, { paddingTop: topInset + 8 }]}
      nestedScrollEnabled
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
    >
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}

      <FadeIn from="below">
        <LinearGradient colors={code >= 51 ? ["#4B6584", "#7A8FA8"] : ["#3B7BC8", "#8CC3F0"]} style={styles.hero}>
          <View style={{ flex: 1 }}>
            <Text style={styles.city}>Dehradun</Text>
            <Text style={styles.temp}>{temp != null ? `${Math.round(temp)}°` : "—"}</Text>
            <Text style={styles.cond}>{fc ? sky.label : (now?.conditionText ?? "")}</Text>
            {fc ? (
              <Text style={styles.feels}>
                Feels like {Math.round(fc.current.apparent_temperature)}° · H {Math.round(fc.daily.temperature_2m_max[0])}° L{" "}
                {Math.round(fc.daily.temperature_2m_min[0])}°
              </Text>
            ) : null}
          </View>
          <Ionicons name={sky.icon} size={84} color="rgba(255,255,255,0.95)" />
        </LinearGradient>
      </FadeIn>

      {/* Next hours */}
      {fc ? (
        <FadeIn from="below" index={1} style={styles.card}>
          <Text style={styles.cardTitle}>Next 12 hours</Text>
          <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 18 }}>
            {fc.hourly.time.map((t, i) => (
              <View key={t} style={styles.hour}>
                <Text style={styles.hourTime}>{i === 0 ? "Now" : hhmm(t)}</Text>
                <Ionicons name={wmo(fc.hourly.weather_code[i]).icon} size={22} color={colors.navy} />
                <Text style={styles.hourTemp}>{Math.round(fc.hourly.temperature_2m[i])}°</Text>
                <Text style={styles.hourRain}>{fc.hourly.precipitation_probability[i] ?? 0}%</Text>
              </View>
            ))}
          </ScrollView>
        </FadeIn>
      ) : null}

      {/* Tiles */}
      <View style={styles.tiles}>
        <Tile
          index={2}
          icon="leaf"
          title="Air quality"
          value={aqi != null ? String(Math.round(aqi)) : "—"}
          sub={band ? `${band.label} · PM2.5 ${Math.round(air!.current.pm2_5)}` : "US AQI"}
          tint={band?.color}
        />
        <Tile
          index={3}
          icon="water"
          title="Flood risk"
          value={risk === "NORMAL" ? "Normal" : risk.charAt(0) + risk.slice(1).toLowerCase()}
          sub={now ? `${now.floodDepthCm} cm water · rain ${now.rainMm} mm` : ""}
          tint={risk === "NORMAL" ? colors.success : colors.danger}
        />
        <Tile index={4} icon="speedometer" title="Wind" value={fc ? `${Math.round(fc.current.wind_speed_10m)} km/h` : "—"} sub="at 10 m" />
        <Tile index={5} icon="water-outline" title="Humidity" value={fc ? `${fc.current.relative_humidity_2m}%` : now ? `${now.relativeHumidity}%` : "—"} sub="relative" />
      </View>

      {/* Week */}
      {fc ? (
        <FadeIn from="below" index={6} style={styles.card}>
          <Text style={styles.cardTitle}>This week</Text>
          {fc.daily.time.map((d, i) => (
            <View key={d} style={styles.day}>
              <Text style={styles.dayName}>{dayName(d, i)}</Text>
              <Ionicons name={wmo(fc.daily.weather_code[i]).icon} size={20} color={colors.navy} style={{ width: 28 }} />
              <Text style={styles.dayRain}>{fc.daily.precipitation_probability_max[i] ?? 0}%</Text>
              <Text style={styles.dayRange}>
                {Math.round(fc.daily.temperature_2m_min[i])}° / {Math.round(fc.daily.temperature_2m_max[i])}°
              </Text>
            </View>
          ))}
          <View style={styles.sunRow}>
            <Ionicons name="sunny-outline" size={15} color={colors.textMuted} />
            <Text style={styles.sunText}>
              Sunrise {hhmm(fc.daily.sunrise[0])} · Sunset {hhmm(fc.daily.sunset[0])}
            </Text>
          </View>
        </FadeIn>
      ) : null}

      <Tap style={styles.ask} onPress={() => onAsk("Is it a good day to go out in Dehradun? Check the weather and air quality.")} accessibilityLabel="Ask your guide about the weather">
        <Ionicons name="chatbubble-ellipses-outline" size={18} color="#fff" />
        <Text style={styles.askText}>Ask your guide: good day to go out?</Text>
      </Tap>
      <Text style={styles.source}>Data: Open-Meteo (weather, air quality), CitySense flood estimate. Pull to refresh.</Text>
    </ScrollView>
  );
}

function Tile({
  icon,
  title,
  value,
  sub,
  tint,
  index,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  value: string;
  sub: string;
  tint?: string;
  index: number;
}) {
  return (
    <FadeIn from="below" index={index} style={styles.tile}>
      <View style={styles.tileHead}>
        <Ionicons name={icon} size={16} color={tint ?? colors.navy} />
        <Text style={styles.tileTitle}>{title}</Text>
      </View>
      <Text style={[styles.tileValue, tint ? { color: tint } : null]}>{value}</Text>
      <Text style={styles.tileSub} numberOfLines={2}>
        {sub}
      </Text>
    </FadeIn>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingBottom: 32, gap: 12 },
  hero: { borderRadius: 24, padding: 20, flexDirection: "row", alignItems: "center", minHeight: 170 },
  city: { fontFamily: fonts.semibold, fontSize: 16, color: "rgba(255,255,255,0.9)" },
  temp: { fontFamily: fonts.bold, fontSize: 58, color: "#fff", lineHeight: 66 },
  cond: { fontFamily: fonts.semibold, fontSize: 16, color: "#fff" },
  feels: { fontFamily: fonts.regular, fontSize: 13, color: "rgba(255,255,255,0.85)", marginTop: 4 },
  card: { borderRadius: 18, backgroundColor: colors.surfaceAlt, padding: 14, gap: 10 },
  cardTitle: { fontFamily: fonts.bold, fontSize: 14, color: colors.text },
  hour: { alignItems: "center", gap: 4 },
  hourTime: { fontFamily: fonts.medium, fontSize: 12, color: colors.textMuted },
  hourTemp: { fontFamily: fonts.bold, fontSize: 14, color: colors.text },
  hourRain: { fontFamily: fonts.medium, fontSize: 11, color: colors.accentBlue },
  tiles: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  tile: { width: "48.5%", borderRadius: 16, backgroundColor: colors.surfaceAlt, padding: 12, gap: 4 },
  tileHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  tileTitle: { fontFamily: fonts.semibold, fontSize: 12, color: colors.textMuted },
  tileValue: { fontFamily: fonts.bold, fontSize: 22, color: colors.text },
  tileSub: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted },
  day: { flexDirection: "row", alignItems: "center", gap: 10 },
  dayName: { width: 56, fontFamily: fonts.semibold, fontSize: 14, color: colors.text },
  dayRain: { width: 44, fontFamily: fonts.medium, fontSize: 12, color: colors.accentBlue },
  dayRange: { flex: 1, textAlign: "right", fontFamily: fonts.semibold, fontSize: 14, color: colors.text },
  sunRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  sunText: { fontFamily: fonts.regular, fontSize: 12, color: colors.textMuted },
  ask: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 50, borderRadius: radius.pill, backgroundColor: colors.navy },
  askText: { fontFamily: fonts.bold, fontSize: 14, color: "#fff" },
  source: { fontFamily: fonts.regular, fontSize: 11, color: colors.textMuted, textAlign: "center" },
});

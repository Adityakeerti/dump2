/** Design tokens sampled from the CitySense mockup (UI.jpeg) and its asset files. */
export const colors = {
  primary: "#9A2143",
  navy: "#1D2B4F",
  text: "#1F1F24",
  textMuted: "#6B6B76",
  border: "#E3E3E8",
  surface: "#FFFFFF",
  surfaceAlt: "#F5F5F8",
  chip: "#F1F1F4",
  accentBlue: "#3B82F6",
  tabActiveBg: "#DCE8FF",
  tabActive: "#1A56DB",
  success: "#2E9E5B",
  warning: "#E59E0B",
  danger: "#D93A3A",
  geofenceFill: "rgba(245, 97, 81, 0.35)",
  geofenceLine: "rgba(245, 97, 81, 0.6)",
  pinGreen: "#22A35A",
  star: "#F5B301",
  dot: "#E85A6B",
  dotInactive: "#F6C3CA",
} as const;

export const fonts = {
  display: "DMSerifDisplay_400Regular",
  regular: "Urbanist_400Regular",
  medium: "Urbanist_500Medium",
  semibold: "Urbanist_600SemiBold",
  bold: "Urbanist_700Bold",
} as const;

export const radius = { sm: 8, md: 12, lg: 18, pill: 999 } as const;
export const space = (n: number) => n * 4;

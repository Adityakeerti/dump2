import type { TabItem } from "../components/TabBar";

/** Bottom navigation from the mockup. */
export const TABS: TabItem[] = [
  { name: "explore", label: "Explore", icon: "location-outline", iconActive: "location" },
  { name: "townhall", label: "Townhall", icon: "business-outline", iconActive: "business" },
  { name: "saved", label: "Saved", icon: "bookmark-outline", iconActive: "bookmark" },
  { name: "updates", label: "Updates", icon: "notifications-outline", iconActive: "notifications" },
  { name: "settings", label: "Settings", icon: "settings-outline", iconActive: "settings" },
];

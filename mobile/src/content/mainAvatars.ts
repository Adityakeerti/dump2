/**
 * Looks for the main agent (City Sense). The citizen picks one on first launch; it appears in the
 * assistant island, the half-screen panel and Settings.
 *
 * Art: assets/main-avatars/<id>.png is a 512x512 face-centred crop for the circular mask;
 * <id>-portrait.png is the whole sticker for the chooser. Both are generated from the originals in
 * Project/assets/{female_main,male_main} (see scripts in the commit that added them).
 */
export interface MainAvatar {
  id: string;
  name: string;
  tagline: string;
  /** `require()` of the face-centred bust (circular mask). */
  bust: number;
  /** `require()` of the full sticker portrait (chooser). */
  portrait: number;
  /** Ring colour around the masked avatar. */
  ring: string;
  /** Short lines the avatar "says" in idle bubbles, per app language. */
  phrases: { en: string[]; hi: string[] };
}

export const MAIN_AVATARS: MainAvatar[] = [
  {
    id: "mira",
    name: "Mira",
    tagline: "Warm and clear · answers in Hindi or English",
    bust: require("../../assets/main-avatars/mira.png"),
    portrait: require("../../assets/main-avatars/mira-portrait.png"),
    ring: "#9A2143",
    phrases: {
      en: ["Namaste! 🙏", "Need help in the city?", "Try: show notices", "Spotted a pothole?", "Ask me anything ✨"],
      hi: ["नमस्ते! 🙏", "शहर में मदद चाहिए?", "बोलिए: नोटिस दिखाओ", "कोई गड्ढा दिखा?", "कुछ भी पूछिए ✨"],
    },
  },
  {
    id: "arjun",
    name: "Arjun",
    tagline: "Calm and quick · great for on-the-go help",
    bust: require("../../assets/main-avatars/arjun.png"),
    portrait: require("../../assets/main-avatars/arjun-portrait.png"),
    ring: "#1D2B4F",
    phrases: {
      en: ["Hey there! 👋", "Where to today?", "Try: my complaints", "Traffic check? 🚦", "I can open the map 🗺️"],
      hi: ["नमस्ते! 👋", "आज कहाँ जाना है?", "बोलिए: मेरी शिकायतें", "ट्रैफिक देखें? 🚦", "मैं नक्शा खोल दूँ? 🗺️"],
    },
  },
];

export const mainAvatarById = (id: string | null | undefined): MainAvatar =>
  MAIN_AVATARS.find((a) => a.id === id) ?? MAIN_AVATARS[0];

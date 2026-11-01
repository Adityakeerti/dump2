/** Copy and artwork for the three intro slides (from the CitySense mockup). */
export interface Slide {
  key: string;
  title: string;
  arch: number;
  archTint?: string;
  variant: "emblem" | "avatar" | "grid";
}

export const slides: Slide[] = [
  { key: "built-for", title: "Saarthi 26", arch: require("../../assets/images/arch-orange.png"), variant: "emblem" },
  { key: "platform", title: "Avatar Platform", arch: require("../../assets/images/arch-salmon.png"), variant: "avatar" },
  { key: "explore", title: "Ready to explore ?", arch: require("../../assets/images/arch-blue.png"), variant: "grid" },
];

export const images = {
  emblem: require("../../assets/images/emblem.png"),
  sikhMan: require("../../assets/images/sikh-man.png"),
  cow: require("../../assets/images/cow.png"),
  kite: require("../../assets/images/kite.png"),
  archGreen: require("../../assets/images/arch-green.png"),
  faceBoy: require("../../assets/images/face-boy.png"),
  faceSikh: require("../../assets/images/face-sikh.png"),
  faceHijab: require("../../assets/images/face-hijab.png"),
  faces: [
    require("../../assets/images/face-1.png"),
    require("../../assets/images/face-5.png"),
    require("../../assets/images/face-2.png"),
    require("../../assets/images/face-3.png"),
    require("../../assets/images/face-4.png"),
  ],
  verified: require("../../assets/images/verified.png"),
  bot: require("../../assets/images/bot.png"),
};

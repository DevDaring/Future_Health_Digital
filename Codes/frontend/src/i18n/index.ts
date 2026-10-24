import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import bn from "./locales/bn.json";
import en from "./locales/en.json";
import hi from "./locales/hi.json";
import ml from "./locales/ml.json";
import tl from "./locales/tl.json";
import ur from "./locales/ur.json";

// Patient-facing strings in 7 languages (demo fixture translations, not clinically validated).
export const LOCALES = { en, ar, hi, ur, ml, bn, tl } as const;
export type Lang = keyof typeof LOCALES;

void i18n.use(initReactI18next).init({
  resources: Object.fromEntries(Object.entries(LOCALES).map(([k, v]) => [k, { translation: v }])),
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export const SPEECH_LANG: Record<string, string> = {
  en: "en-US", ar: "ar-AE", hi: "hi-IN", ur: "ur-PK", ml: "ml-IN", bn: "bn-BD", tl: "fil-PH",
};

export default i18n;

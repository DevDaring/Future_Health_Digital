// Copies the patient-chat phrases (backend fixtures) into src/i18n/locales/*.json.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
const fx = new URL("../../backend/app/fixtures/", import.meta.url);
const en = JSON.parse(readFileSync(new URL("phrases_en.json", fx)));
for (const lang of ["en", "ar", "hi", "ur", "ml", "bn", "tl"]) {
  const p = new URL(`phrases/${lang}.json`, fx);
  const tr = lang === "en" || !existsSync(p) ? {} : JSON.parse(readFileSync(p));
  const out = { ui: { ...en.ui, ...(tr.ui ?? {}) }, quick: { ...en.quick, ...(tr.quick ?? {}) } };
  writeFileSync(new URL(`../src/i18n/locales/${lang}.json`, import.meta.url), JSON.stringify(out, null, 1) + "\n");
}
console.log("i18n synced");

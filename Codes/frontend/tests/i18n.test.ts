import { describe, expect, it } from "vitest";
import { LOCALES } from "../src/i18n";

describe("patient chat locales", () => {
  it("ships all 7 languages with the same keys as English", () => {
    const en = LOCALES.en;
    expect(Object.keys(LOCALES).sort()).toEqual(["ar", "bn", "en", "hi", "ml", "tl", "ur"]);
    for (const [lang, loc] of Object.entries(LOCALES)) {
      expect(Object.keys(loc.ui).sort(), lang).toEqual(Object.keys(en.ui).sort());
      expect(Object.keys(loc.quick).sort(), lang).toEqual(Object.keys(en.quick).sort());
    }
  });
  it("actually translates (non-English differs from English)", () => {
    expect(LOCALES.ml.quick.qr_night).not.toBe(LOCALES.en.quick.qr_night);
    expect(LOCALES.ar.ui.talk_to_human).not.toBe(LOCALES.en.ui.talk_to_human);
  });
});

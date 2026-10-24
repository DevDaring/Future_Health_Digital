import { describe, expect, it } from "vitest";
import { bestBy, fillTemplate, isRtl, pct, resultLabel, signed, slaTone } from "../src/lib/format";

describe("format helpers", () => {
  it("formats percentages and handles nulls", () => {
    expect(pct(0.4321)).toBe("43%");
    expect(pct(0.4321, 1)).toBe("43.2%");
    expect(pct(null)).toBe("—");
  });
  it("fills tour templates from live values", () => {
    expect(fillTemplate("{a} of {b}", { a: 3, b: "5" })).toBe("3 of 5");
    expect(fillTemplate("{missing}", {})).toBe("…");
  });
  it("knows RTL languages", () => {
    expect(isRtl("ar")).toBe(true);
    expect(isRtl("ur")).toBe(true);
    expect(isRtl("ml")).toBe(false);
  });
  it("labels screening results", () => {
    expect(resultLabel("HBA1C", 6.1, null)).toBe("HbA1c 6.1%");
    expect(resultLabel("BIRADS", 4, "BI-RADS 4")).toBe("BI-RADS 4");
    expect(resultLabel("FIT", null, "positive")).toBe("FIT positive");
  });
  it("picks the best item", () => {
    const rows = [{ v: 2 }, { v: 5 }, { v: null }, { v: 1 }];
    expect(bestBy(rows, (r) => r.v)?.v).toBe(5);
    expect(bestBy(rows, (r) => r.v, "min")?.v).toBe(1);
  });
  it("signs and tones", () => {
    expect(signed(0.25)).toBe("+0.25");
    expect(signed(-0.5, 1)).toBe("−0.5");
    expect(slaTone(-1)).toBe("bad");
    expect(slaTone(3)).toBe("warn");
    expect(slaTone(30)).toBe("ok");
  });
});

// Small pure helpers (unit-tested in tests/format.test.ts).

export const LANG_NAMES: Record<string, string> = {
  en: "English", ar: "العربية", hi: "हिन्दी", ur: "اردو", ml: "മലയാളം", bn: "বাংলা", tl: "Tagalog",
};
export const LANG_EN: Record<string, string> = {
  en: "English", ar: "Arabic", hi: "Hindi", ur: "Urdu", ml: "Malayalam", bn: "Bengali", tl: "Tagalog",
};
export const RTL_LANGS = new Set(["ar", "ur"]);
export const isRtl = (lang: string) => RTL_LANGS.has(lang);

export const pct = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(digits)}%`;

export const num = (x: number | null | undefined, digits = 0) =>
  x === null || x === undefined ? "—" : x.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const signed = (x: number, digits = 2) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(digits)}`;

export const aed = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `AED ${num(x, 0)}`);

export function resultLabel(test: string, value: number | null, text: string | null): string {
  if (test === "HBA1C" && value !== null) return `HbA1c ${value.toFixed(1)}%`;
  if (test === "BIRADS") return text ?? `BI-RADS ${value ?? "?"}`;
  if (test === "FIT") return `FIT ${text ?? "positive"}`;
  return text ?? String(value ?? "");
}

export function relTime(iso: string, now: Date = new Date()): string {
  const s = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (Math.abs(s) < 60) return "just now";
  const m = s / 60;
  if (Math.abs(m) < 60) return `${Math.round(m)} min ago`;
  const h = m / 60;
  if (Math.abs(h) < 24) return `${Math.round(h)} h ago`;
  const d = h / 24;
  return d >= 0 ? `${Math.round(d)} d ago` : `in ${Math.round(-d)} d`;
}

/** Fill `{name}` placeholders from a values object (used by the Judge Mode tour). */
export function fillTemplate(tpl: string, values: Record<string, string | number | null | undefined>): string {
  return tpl.replace(/\{(\w+)\}/g, (_, k: string) => {
    const v = values[k];
    return v === null || v === undefined ? "…" : String(v);
  });
}

export const STATE_LABEL: Record<string, string> = {
  RESULT_RECEIVED: "Result received", NOTIFIED: "Notified", ENGAGED: "Engaged", UNDERSTOOD: "Understood",
  BOOKED: "Booked", ATTENDED: "Attended", CLOSED: "Closed", UNREACHABLE: "Unreachable", DECLINED: "Declined",
  NO_SHOW: "No-show", ESCALATED: "Escalated", BREACHED: "SLA breached",
};

export const PROGRAM_LABEL: Record<string, string> = { DIABETES: "Diabetes", COLORECTAL: "Colorectal", BREAST: "Breast" };

export function slaTone(daysLeft: number): "bad" | "warn" | "ok" {
  if (daysLeft < 0) return "bad";
  if (daysLeft < 5) return "warn";
  return "ok";
}

export function bestBy<T>(items: T[], key: (t: T) => number | null | undefined, mode: "max" | "min" = "max"): T | undefined {
  let best: T | undefined;
  let bestV: number | undefined;
  for (const it of items) {
    const v = key(it);
    if (v === null || v === undefined) continue;
    if (bestV === undefined || (mode === "max" ? v > bestV : v < bestV)) {
      best = it;
      bestV = v;
    }
  }
  return best;
}

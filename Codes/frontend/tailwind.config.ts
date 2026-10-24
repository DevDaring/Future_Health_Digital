import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        card: v("card"),
        line: v("line"),
        ink: { DEFAULT: v("ink"), 2: v("ink-2"), 3: v("ink-3") },
        night: { DEFAULT: v("night"), 2: v("night-2"), 3: v("night-3") },
        teal: { DEFAULT: v("teal"), soft: v("teal-soft"), ink: v("teal-ink") },
        indigo: { DEFAULT: v("indigo"), soft: v("indigo-soft"), ink: v("indigo-ink") },
        sand: { DEFAULT: v("sand"), soft: v("sand-soft"), ink: v("sand-ink") },
        ok: { DEFAULT: v("ok"), soft: v("ok-soft") },
        warn: { DEFAULT: v("warn"), soft: v("warn-soft") },
        bad: { DEFAULT: v("bad"), soft: v("bad-soft") },
        info: { DEFAULT: v("info"), soft: v("info-soft") },
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans Variable"', "system-ui", "sans-serif"],
        arabic: ['"Noto Naskh Arabic"', "serif"],
        urdu: ['"Noto Nastaliq Urdu"', "serif"],
      },
      borderRadius: { "4xl": "2rem" },
      boxShadow: {
        soft: "0 1px 2px rgb(var(--shadow) / 0.05), 0 8px 28px -12px rgb(var(--shadow) / 0.18)",
        lift: "0 2px 6px rgb(var(--shadow) / 0.06), 0 24px 48px -20px rgb(var(--shadow) / 0.35)",
        glow: "0 0 0 1px rgb(var(--teal) / 0.35), 0 12px 40px -12px rgb(var(--teal) / 0.55)",
      },
      keyframes: {
        shimmer: { from: { backgroundPosition: "-200% 0" }, to: { backgroundPosition: "200% 0" } },
        pulseRing: { "0%": { transform: "scale(0.7)", opacity: "0.7" }, "100%": { transform: "scale(2.2)", opacity: "0" } },
        floaty: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        dash: { to: { strokeDashoffset: "0" } },
        spinSlow: { to: { transform: "rotate(360deg)" } },
      },
      animation: {
        shimmer: "shimmer 1.6s linear infinite",
        pulseRing: "pulseRing 2.2s cubic-bezier(0.2,0.6,0.3,1) infinite",
        floaty: "floaty 5s ease-in-out infinite",
        spinSlow: "spinSlow 24s linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;

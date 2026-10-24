import clsx from "clsx";
import { AlertTriangle, CheckCircle2, CircleDashed, Inbox, Loader2, ShieldCheck, ShieldAlert, X } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import type { QaMeta } from "../api/types";
import { LANG_EN, STATE_LABEL, pct } from "../lib/format";

export function Logo({ size = 36, light = false }: { size?: number; light?: boolean }) {
  // Two arcs that meet: the loop that WASL closes. "وصل" means connection.
  return (
    <div className="flex items-center gap-2.5">
      <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
        <defs>
          <linearGradient id="wg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgb(45 212 191)" />
            <stop offset="100%" stopColor="rgb(129 140 248)" />
          </linearGradient>
        </defs>
        <circle cx="24" cy="24" r="22" fill={light ? "rgba(255,255,255,0.06)" : "rgb(var(--night))"} />
        <path d="M13 28a11 11 0 0 1 17.5-12.6" stroke="url(#wg)" strokeWidth="4.2" strokeLinecap="round" fill="none" />
        <path d="M35 20a11 11 0 0 1-17.5 12.6" stroke="url(#wg)" strokeWidth="4.2" strokeLinecap="round" fill="none" />
        <circle cx="31" cy="15.6" r="2.6" fill="rgb(234 179 88)" />
        <circle cx="17" cy="32.4" r="2.6" fill="rgb(234 179 88)" />
      </svg>
      <div className="leading-none">
        <div className={clsx("text-lg font-extrabold tracking-tight", light ? "text-white" : "text-ink")}>
          WASL <span className="font-arabic text-base font-semibold text-sand" lang="ar">وصل</span>
        </div>
        <div className={clsx("mt-0.5 text-[10px] font-semibold uppercase tracking-[0.18em]", light ? "text-white/50" : "text-ink-3")}>
          Screening → Care
        </div>
      </div>
    </div>
  );
}

const TONES = {
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  info: "bg-info-soft text-info",
  teal: "bg-teal-soft text-teal-ink",
  indigo: "bg-indigo-soft text-indigo-ink",
  sand: "bg-sand-soft text-sand-ink",
  neutral: "bg-line/60 text-ink-2",
} as const;
export type Tone = keyof typeof TONES;

export function Chip({ tone = "neutral", children, className, icon }: { tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span className={clsx("chip", TONES[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

const STATE_TONE: Record<string, Tone> = {
  RESULT_RECEIVED: "neutral", NOTIFIED: "info", ENGAGED: "indigo", UNDERSTOOD: "teal", BOOKED: "teal", ATTENDED: "ok",
  CLOSED: "ok", UNREACHABLE: "warn", DECLINED: "neutral", NO_SHOW: "warn", ESCALATED: "bad", BREACHED: "bad",
};
export function StateBadge({ state, understood }: { state: string; understood?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Chip tone={STATE_TONE[state] ?? "neutral"}>
        {state === "ESCALATED" || state === "BREACHED" ? <AlertTriangle size={11} /> : <CircleDashed size={11} />}
        {STATE_LABEL[state] ?? state}
      </Chip>
      {understood && state !== "UNDERSTOOD" && (
        <Chip tone="teal" icon={<CheckCircle2 size={11} />}>
          Understood
        </Chip>
      )}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: Tone = severity === "urgent" ? "bad" : severity === "high" ? "warn" : "info";
  const dots = severity === "urgent" ? 3 : severity === "high" ? 2 : 1;
  return (
    <Chip tone={tone}>
      <span aria-hidden className="tracking-tighter">{"●".repeat(dots)}</span>
      {severity}
    </Chip>
  );
}

export function LangChip({ lang }: { lang: string }) {
  return (
    <span className="chip bg-night/5 text-ink-2 dark:bg-white/10" title={LANG_EN[lang]}>
      <span className="text-[10px] font-black uppercase">{lang}</span>
      <span className="hidden sm:inline">{LANG_EN[lang]}</span>
    </span>
  );
}

export function QaChip({ qa, onClick }: { qa?: QaMeta; onClick?: () => void }) {
  if (!qa) return null;
  const ok = qa.passed;
  const label = ok ? `Translation QA ✓ ${qa.score.toFixed(2)}` : qa.source === "approved_translation" ? `QA ✗ ${qa.score.toFixed(2)} → approved translation` : `QA ✗ → English + interpreter`;
  return (
    <button type="button" onClick={onClick} className={clsx("chip", ok ? TONES.ok : TONES.warn, onClick && "hover:brightness-95")}>
      {ok ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
      {label}
    </button>
  );
}

export function Card({ title, subtitle, action, children, className, tour, icon }: {
  title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; tour?: string; icon?: ReactNode;
}) {
  return (
    <section className={clsx("card p-5", className)} data-tour={tour}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            {icon && <div className="mt-0.5 grid h-8 w-8 place-items-center rounded-xl bg-teal-soft text-teal-ink">{icon}</div>}
            <div>
              {title && <h2 className="text-[15px] font-bold tracking-tight text-ink">{title}</h2>}
              {subtitle && <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>}
            </div>
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Meter({ value, tone = "teal", max = 1, label }: { value: number | null; tone?: "teal" | "indigo" | "bad" | "sand" | "warn"; max?: number; label?: string }) {
  const v = Math.max(0, Math.min(1, (value ?? 0) / max));
  const color = { teal: "bg-teal", indigo: "bg-indigo", bad: "bg-bad", sand: "bg-sand", warn: "bg-warn" }[tone];
  return (
    <div className="flex items-center gap-2" aria-label={label}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-line">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${v * 100}%` }} />
      </div>
      <span className="tabular w-10 text-xs font-semibold text-ink-2">{value === null ? "—" : pct(value)}</span>
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: {
  value: T; options: { value: T; label: ReactNode; hint?: string }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" className="inline-flex rounded-xl border border-line bg-bg p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          title={o.hint}
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded-lg font-semibold transition",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
            value === o.value ? "bg-card text-ink shadow-soft" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line px-6 py-10 text-center">
      <div className="grid h-11 w-11 place-items-center rounded-2xl bg-bg text-ink-3">{icon ?? <Inbox size={20} />}</div>
      <div className="text-sm font-semibold text-ink">{title}</div>
      {hint && <div className="max-w-sm text-xs text-ink-2">{hint}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-bad/30 bg-bad-soft/60 p-4 text-sm text-bad">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <div className="font-semibold">Something went wrong</div>
        <div className="text-xs opacity-80">{msg}</div>
      </div>
      {retry && (
        <button className="btn-ghost !py-1 text-xs" onClick={retry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("animate-spin", className)} size={16} aria-hidden />;
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-night/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={clsx("card max-h-[90vh] w-full overflow-auto p-6 scrollbar-thin", wide ? "max-w-4xl" : "max-w-lg")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-4">
          <h3 className="text-lg font-bold tracking-tight">{title}</h3>
          <button aria-label="Close" className="rounded-lg p-1 text-ink-3 hover:bg-bg hover:text-ink" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Illustrative({ children = "ILLUSTRATIVE" }: { children?: ReactNode }) {
  return (
    <span className="chip border border-sand/40 bg-sand-soft text-[10px] uppercase tracking-wider text-sand-ink" title="Configurable assumption — not a clinical or real-world estimate">
      {children}
    </span>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "ok" | "bad" | "warn" }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={clsx("tabular mt-1 text-2xl font-extrabold tracking-tight", tone === "ok" && "text-ok", tone === "bad" && "text-bad", tone === "warn" && "text-warn")}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="label mb-1.5 text-teal">{eyebrow}</div>}
        <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

import clsx from "clsx";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, Hash, Link2, ShieldCheck, ShieldAlert, TrendingDown, TrendingUp } from "lucide-react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChatMessage, Counterfactual, PatientTwin, ShapItem, TimelineEvent, TranslationCheck } from "../api/types";
import { STATE_LABEL, isRtl, pct, relTime } from "../lib/format";
import { Chip, EmptyState, Illustrative, QaChip } from "./ui";

export function WhyBars({ items }: { items: ShapItem[] }) {
  const max = Math.max(...items.map((i) => Math.abs(i.shap)), 0.01);
  return (
    <div className="space-y-2.5">
      {items.map((it) => {
        const up = it.shap > 0;
        const w = (Math.abs(it.shap) / max) * 100;
        return (
          <div key={it.feature} className="grid grid-cols-[1fr_120px] items-center gap-3">
            <div className="flex items-center gap-2 text-sm">
              {up ? <TrendingUp size={14} className="shrink-0 text-bad" /> : <TrendingDown size={14} className="shrink-0 text-ok" />}
              <span className="font-medium">{it.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg">
                <motion.div initial={{ width: 0 }} animate={{ width: `${w}%` }} className={clsx("h-full rounded-full", up ? "bg-bad" : "bg-ok")} />
              </div>
              <span className="tabular w-11 text-right text-[11px] font-semibold text-ink-2">{up ? "+" : "−"}{Math.abs(it.shap).toFixed(2)}</span>
            </div>
          </div>
        );
      })}
      <p className="pt-1 text-[11px] text-ink-3">SHAP contributions to drop-off risk (log-odds). Red raises risk, green lowers it.</p>
    </div>
  );
}

export function WhatWouldHelp({ items }: { items: Counterfactual[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {items.map((cf, i) => (
        <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
          className={clsx("relative overflow-hidden rounded-2xl border p-4", i === 0 ? "border-teal/50 bg-gradient-to-br from-teal-soft/70 to-card" : "border-line bg-bg/40")}>
          {i === 0 && <span className="chip absolute right-3 top-3 bg-teal text-white">best</span>}
          <ul className="space-y-1 text-sm font-semibold">
            {cf.actions.map((a) => (
              <li key={a} className="flex items-start gap-1.5"><CheckCircle2 size={14} className="mt-0.5 shrink-0 text-teal" />{a}</li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap items-end gap-x-2 gap-y-1">
            <div>
              <div className="label">Now</div>
              <div className="tabular text-xl font-extrabold text-ink-2">{cf.p_baseline.toFixed(2)}</div>
            </div>
            <ArrowRight size={18} className="mb-1.5 text-teal" />
            <div>
              <div className="label">With this</div>
              <div className="tabular text-2xl font-extrabold text-teal">{cf.p_return.toFixed(2)}</div>
            </div>
            <span className="chip mb-1 bg-ok-soft text-ok">+{cf.delta.toFixed(2)}</span>
          </div>
          <div className="mt-2 text-[11px] text-ink-3">Estimated probability of returning for follow-up</div>
        </motion.div>
      ))}
    </div>
  );
}

export function Timeline({ events, valid }: { events: TimelineEvent[]; valid: boolean }) {
  return (
    <div>
      <div className={clsx("mb-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold", valid ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad")}>
        {valid ? <ShieldCheck size={13} /> : <ShieldAlert size={13} />} {valid ? `Hash chain verified (${events.length} events)` : "Chain broken — record altered"}
      </div>
      <ol className="relative space-y-3 border-l-2 border-line pl-5">
        {events.map((e) => (
          <li key={e.id} className="relative">
            <span className={clsx("absolute -left-[27px] top-1 grid h-4 w-4 place-items-center rounded-full ring-4 ring-card",
              e.from_state === e.to_state ? "bg-sand" : "bg-teal")} />
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-bold">{e.from_state === e.to_state ? e.reason.split(":")[0] : STATE_LABEL[e.to_state] ?? e.to_state}</span>
              <span className="text-[11px] text-ink-3">{new Date(e.created_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}</span>
              <span className="text-[11px] text-ink-3">· {e.actor}</span>
            </div>
            <div className="text-xs text-ink-2">{e.from_state === e.to_state ? e.reason.split(":").slice(1).join(":") : e.reason}</div>
            <div className="mt-0.5 flex items-center gap-1 font-mono text-[10px] text-ink-3" title={`prev ${e.prev_hash}\nhash ${e.hash}`}>
              <Hash size={10} />{e.prev_hash.slice(0, 8)} <Link2 size={10} className="text-teal" /> {e.hash.slice(0, 8)}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Transcript({ messages, onCheck, lang }: { messages: ChatMessage[]; onCheck?: (id: string) => void; lang: string }) {
  if (!messages.length) return <EmptyState title="No conversation yet" hint="Start outreach to send the patient a secure link." />;
  return (
    <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1 scrollbar-thin">
      {messages.map((m) => {
        const mine = m.sender === "patient";
        return (
          <div key={m.id} className={clsx("flex flex-col", mine ? "items-end" : "items-start")}>
            <div className={clsx("max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm",
              m.kind === "emergency" ? "border border-bad bg-bad-soft text-bad" : mine ? "bg-indigo text-white" : m.sender === "system" ? "bg-sand-soft text-sand-ink" : "bg-bg")}
              lang={m.sender === "system" ? "en" : lang} dir="auto">
              {m.text}
              {m.text_en && m.text_en !== m.text && (
                <div className={clsx("mt-1.5 border-t pt-1.5 text-[11px] opacity-75", mine ? "border-white/20" : "border-line")} lang="en" dir="ltr">
                  EN: {m.text_en}
                </div>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] text-ink-3">{m.sender.replace("_", " ")} · {relTime(m.created_at)}</span>
              {m.meta.qa && <QaChip qa={m.meta.qa} onClick={m.translation_check_id && onCheck ? () => onCheck(m.translation_check_id!) : undefined} />}
              {m.meta.teach_back === "passed" && <Chip tone="ok" icon={<CheckCircle2 size={11} />}>Teach-back passed</Chip>}
              {m.meta.teach_back === "failed" && <Chip tone="warn">Teach-back → human</Chip>}
              {m.red_flag && <Chip tone="bad">red flag</Chip>}
              {m.meta.barrier && m.meta.barrier !== "none" && <Chip tone="indigo">barrier: {m.meta.barrier}</Chip>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function CheckDetail({ c }: { c: TranslationCheck }) {
  const rows: [string, string, string][] = [
    ["1 · Approved English", c.source_en, "en"],
    ["2 · Simplified (literacy-adapted)", c.simplified_en, "en"],
    ["3 · Machine translation", c.translated, c.language],
    ["4 · Back-translation to English", c.back_translated, "en"],
  ];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={c.passed ? "ok" : "warn"}>{c.passed ? "Passed" : "Failed"}</Chip>
        <Chip tone="neutral">judge score {c.judge_score.toFixed(2)} (≥ 0.85)</Chip>
        <Chip tone={c.entity_match ? "ok" : "bad"}>numbers & test names {c.entity_match ? "match" : "MISMATCH"}</Chip>
        <Chip tone="neutral">{c.provider}</Chip>
      </div>
      {rows.map(([label, text, lang]) => (
        <div key={label} className="rounded-xl border border-line p-3">
          <div className="label mb-1">{label}</div>
          <div className="text-sm" lang={lang} dir={isRtl(lang) ? "rtl" : "ltr"}>{text}</div>
        </div>
      ))}
      {c.discrepancies.length > 0 && (
        <div className="rounded-xl border border-warn/40 bg-warn-soft/50 p-3 text-sm text-warn">
          <div className="label mb-1 !text-warn">Discrepancies</div>
          <ul className="list-disc pl-5">{c.discrepancies.map((d) => <li key={d}>{d}</li>)}</ul>
        </div>
      )}
      <div className="rounded-xl border border-teal/40 bg-teal-soft/40 p-3">
        <div className="label mb-1">5 · Sent to the patient {c.fell_back && "(safe fallback: clinician-approved translation)"}</div>
        <div className="text-sm" lang={c.language} dir={isRtl(c.language) ? "rtl" : "ltr"}>{c.final_text}</div>
      </div>
    </div>
  );
}

const DELAY_COLORS = ["rgb(var(--teal))", "rgb(var(--info))", "rgb(var(--warn))", "rgb(var(--bad))"];

export function PatientTwinChart({ twin }: { twin: PatientTwin }) {
  const months = twin.delays[0].trajectory.month;
  const data = months.map((m, i) => {
    const row: Record<string, number> = { month: m };
    twin.delays.forEach((d) => {
      row[`p${d.delay_months}`] = +(d.trajectory.p[i] * 100).toFixed(2);
      row[`band${d.delay_months}`] = [+(d.trajectory.lo[i] * 100).toFixed(2), +(d.trajectory.hi[i] * 100).toFixed(2)] as unknown as number;
    });
    return row;
  });
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Illustrative>Illustrative — not for clinical decisions</Illustrative>
        <span className="text-xs text-ink-2">P({twin.outcome_label}) over {twin.horizon_months / 12} years if follow-up is delayed</span>
      </div>
      <div className="h-64">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ left: -10, right: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} tickFormatter={(m) => `${m}m`} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} />
            <Tooltip formatter={(v: unknown) => (Array.isArray(v) ? `${v[0]}–${v[1]}%` : `${v}%`)} contentStyle={{ borderRadius: 12, background: "rgb(var(--card))", border: "1px solid rgb(var(--line))" }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {twin.delays.map((d, i) => (
              <Area key={`b${d.delay_months}`} dataKey={`band${d.delay_months}`} stroke="none" fill={DELAY_COLORS[i]} fillOpacity={0.08} legendType="none" isAnimationActive={false} />
            ))}
            {twin.delays.map((d, i) => (
              <Line key={d.delay_months} dataKey={`p${d.delay_months}`} name={d.delay_months ? `Delay ${d.delay_months} mo` : "Follow-up now"} stroke={DELAY_COLORS[i]} strokeWidth={2.5} dot={false} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {twin.delays.map((d, i) => (
          <div key={d.delay_months} className="rounded-xl bg-bg p-2.5">
            <div className="text-[11px] font-semibold" style={{ color: DELAY_COLORS[i] }}>{d.delay_months ? `+${d.delay_months} months` : "Now"}</div>
            <div className="tabular text-lg font-extrabold">{pct(d.p_outcome_5y, 1)}</div>
            <div className="text-[10px] text-ink-3">90% band {pct(d.lo, 1)}–{pct(d.hi, 1)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

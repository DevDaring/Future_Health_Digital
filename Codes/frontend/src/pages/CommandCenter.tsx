import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertOctagon, BellRing, CalendarClock, CheckCircle2, FastForward, Hourglass, Link2, Radio, Siren, TimerOff } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { post } from "../api/client";
import { useAdvanceClock, useBreaches, useEscalations, useFeed, useFunnel, useInvalidate, useKpis } from "../api/hooks";
import { Card, EmptyState, ErrorState, Illustrative, LoadingBlock, PageHeader, Segmented, Skeleton, Spinner } from "../components/ui";
import { PROGRAM_LABEL, STATE_LABEL, num, pct, relTime } from "../lib/format";
import { useAuth } from "../store/auth";

function Kpi({ label, value, sub, icon, tone, tour }: { label: string; value: ReactNode; sub?: ReactNode; icon: ReactNode; tone: string; tour?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card relative overflow-hidden p-5" data-tour={tour}>
      <div className={clsx("absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-20 blur-2xl", tone)} />
      <div className="flex items-start justify-between">
        <div className="label">{label}</div>
        <div className={clsx("grid h-9 w-9 place-items-center rounded-xl text-white", tone)}>{icon}</div>
      </div>
      <div className="tabular mt-3 text-[32px] font-extrabold leading-none tracking-tight">{value}</div>
      {sub && <div className="mt-2 text-xs text-ink-2">{sub}</div>}
    </motion.div>
  );
}

function FunnelChart({ program }: { program?: string }) {
  const f = useFunnel(program);
  if (f.isLoading) return <LoadingBlock rows={7} />;
  if (f.error) return <ErrorState error={f.error} retry={() => void f.refetch()} />;
  const steps = f.data!.steps;
  const max = steps[0]?.count || 1;
  const biggest = f.data!.biggest_drop?.state;
  return (
    <div className="space-y-2.5">
      {steps.map((s, i) => {
        const w = (s.count / max) * 100;
        const isBig = s.state === biggest;
        return (
          <div key={s.state} className="grid grid-cols-[120px_1fr_70px] items-center gap-3 sm:grid-cols-[150px_1fr_90px]">
            <div className="text-right text-xs font-semibold text-ink-2">
              {STATE_LABEL[s.state]}
              {s.state === "UNDERSTOOD" && <div className="text-[10px] font-normal text-ink-3">WASL teach-back</div>}
            </div>
            <div className="relative h-9 rounded-xl bg-bg">
              <motion.div
                initial={{ width: 0 }} animate={{ width: `${w}%` }} transition={{ duration: 0.8, delay: i * 0.06 }}
                className={clsx("flex h-full items-center rounded-xl px-3 text-xs font-bold text-white",
                  i < 2 ? "bg-gradient-to-r from-indigo to-indigo/80" : "bg-gradient-to-r from-teal to-teal/80")}
              >
                <span className="tabular">{num(s.count)}</span>
              </motion.div>
            </div>
            <div className="text-xs">
              {i > 0 && (
                <span className={clsx("chip", isBig ? "bg-bad-soft text-bad" : "bg-bg text-ink-2")}>
                  {isBig && <AlertOctagon size={11} />}−{s.dropoff_pct}%
                </span>
              )}
            </div>
          </div>
        );
      })}
      {biggest && (
        <p className="pt-2 text-xs text-ink-2" data-tour="funnel-insight">
          <strong className="text-bad">Biggest drop: before {STATE_LABEL[biggest]}.</strong> People are notified but don't engage or book —
          the gap is understanding and access, not detection.
        </p>
      )}
    </div>
  );
}

function EscalationFeed() {
  const e = useEscalations("open");
  const inv = useInvalidate();
  const user = useAuth((s) => s.user);
  const [busy, setBusy] = useState<string | null>(null);
  if (e.isLoading) return <LoadingBlock rows={5} />;
  if (e.error) return <ErrorState error={e.error} />;
  const items = e.data!.items.slice(0, 8);
  if (!items.length) return <EmptyState title="No open escalations" hint="Red flags and SLA breaches appear here within 5 seconds." icon={<CheckCircle2 size={20} />} />;
  return (
    <ul className="space-y-2">
      {items.map((x) => (
        <motion.li layout key={x.id}
          className={clsx("flex items-center gap-3 rounded-xl border p-3", x.reason === "red_flag" ? "border-bad/40 bg-bad-soft/50" : "border-line bg-bg/60")}>
          <div className={clsx("grid h-9 w-9 shrink-0 place-items-center rounded-xl", x.reason === "red_flag" ? "bg-bad text-white" : "bg-warn-soft text-warn")}>
            {x.reason === "red_flag" ? <Siren size={16} /> : x.reason === "sla_breach" ? <TimerOff size={16} /> : <BellRing size={16} />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Link to={`/loops/${x.loop_id}`} className="hover:underline">{x.display_name}</Link>
              <span className="text-[11px] font-normal text-ink-3">{x.patient_code}</span>
            </div>
            <div className="truncate text-xs text-ink-2">
              {x.reason.replace("_", " ")} · {PROGRAM_LABEL[x.program]} · {x.notes || "—"}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-ink-3">{relTime(x.created_at)}</div>
            {user?.role !== "navigator" || x.reason === "red_flag" ? (
              <button className="mt-1 text-xs font-bold text-teal hover:underline" disabled={busy === x.id}
                onClick={async () => { setBusy(x.id); await post(`/escalations/${x.id}/ack`, { notes: "Acknowledged from Command Center" }); inv("escalations", "kpis", "loop"); setBusy(null); }}>
                {busy === x.id ? <Spinner /> : "Acknowledge"}
              </button>
            ) : null}
          </div>
        </motion.li>
      ))}
    </ul>
  );
}

function ActivityTicker() {
  const f = useFeed();
  if (f.isLoading) return <Skeleton className="h-40" />;
  const ev = f.data?.events ?? [];
  return (
    <ul className="space-y-1.5 font-mono text-[11px]">
      {ev.map((e) => (
        <li key={e.id} className="flex items-center gap-2 text-ink-2">
          <span className="text-ink-3">#{e.seq}</span>
          <Link2 size={10} className="text-teal" />
          <span className="text-teal">{e.hash}</span>
          <Link to={`/loops/${e.loop_id}`} className="font-semibold text-ink hover:underline">{e.persona ? e.persona : e.patient_code}</Link>
          <span>{e.from_state ? `${e.from_state}→` : ""}{e.to_state}</span>
          <span className="ml-auto truncate text-ink-3">{relTime(e.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export default function CommandCenter() {
  const k = useKpis();
  const b = useBreaches();
  const adv = useAdvanceClock();
  const [program, setProgram] = useState<string>("");
  const d = k.data;
  return (
    <div>
      <PageHeader
        eyebrow="Command Center"
        title="Every abnormal result, followed to care"
        subtitle="Live state of every screening-to-care loop, with SLA timers and a hash-chained audit trail."
        actions={
          <button className="btn-ghost" onClick={() => adv.mutate(7)} disabled={adv.isPending} data-tour="advance-clock">
            {adv.isPending ? <Spinner /> : <FastForward size={16} />} Advance clock +7 days
          </button>
        }
      />
      {adv.data && (
        <div className="mb-4 rounded-xl bg-info-soft px-4 py-2 text-sm text-info">
          Clock moved to +{adv.data.offset_days} days: {adv.data.new_breaches} new SLA breaches, {adv.data.reminders_sent} reminders sent.
        </div>
      )}
      {k.error && <ErrorState error={k.error} retry={() => void k.refetch()} />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5" data-tour="kpis">
        {d ? (
          <>
            <Kpi label="Abnormal results" value={num(d.total_loops)} sub={`${num(d.open_loops)} loops still open`} icon={<Radio size={16} />} tone="bg-indigo" />
            <Kpi label="30-day closure" value={pct(d.closure_rate_30d)} sub={<><strong className="text-bad">{pct(d.never_completed_share)}</strong> never completed follow-up</>} icon={<CheckCircle2 size={16} />} tone="bg-teal" tour="kpi-closure" />
            <Kpi label="Median days to care" value={d.median_days_to_followup ?? "—"} sub="result → attended" icon={<CalendarClock size={16} />} tone="bg-sand" />
            <Kpi label="SLA breaches" value={num(d.sla_breaches)} sub={<span className="inline-flex items-center gap-1">SLAs 7/21/60 d <Illustrative /></span>} icon={<Hourglass size={16} />} tone="bg-warn" />
            <Kpi label="Open escalations" value={num(d.open_escalations)} sub={d.open_red_flags ? <strong className="text-bad">{d.open_red_flags} red flag(s)!</strong> : "no red flags"} icon={<Siren size={16} />} tone="bg-bad" />
          </>
        ) : (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-36" />)
        )}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <Card
          title="Screening-to-care funnel"
          subtitle="Loops that reached each step (from the audit log). Simulated as-is baseline, before WASL."
          tour="funnel"
          action={
            <Segmented size="sm" value={program} onChange={setProgram}
              options={[{ value: "", label: "All" }, { value: "DIABETES", label: "Diabetes" }, { value: "COLORECTAL", label: "Colorectal" }, { value: "BREAST", label: "Breast" }]} />
          }
        >
          <FunnelChart program={program || undefined} />
        </Card>
        <Card title="Live escalations" subtitle="Polled every 5 s · red flags first" tour="escalations" icon={<Siren size={16} />}>
          <EscalationFeed />
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card title="Open SLA breaches by program" subtitle="Still actionable — every breach opens an escalation">
          {b.isLoading ? <Skeleton className="h-56" /> : b.data && b.data.by_program.length ? (
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={b.data.by_program.map((r) => ({ ...r, program: PROGRAM_LABEL[r.program] }))} margin={{ left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                  <XAxis dataKey="program" tick={{ fontSize: 12, fill: "rgb(var(--ink-2))" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid rgb(var(--line))", background: "rgb(var(--card))" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="routine" stackId="a" fill="rgb(var(--info))" radius={[0, 0, 6, 6]} />
                  <Bar dataKey="high" stackId="a" fill="rgb(var(--warn))" />
                  <Bar dataKey="urgent" stackId="a" fill="rgb(var(--bad))" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <EmptyState title="No open breaches" />}
        </Card>
        <Card title="Audit chain activity" subtitle="Every event is SHA-256 chained to the one before it">
          <ActivityTicker />
        </Card>
      </div>
    </div>
  );
}

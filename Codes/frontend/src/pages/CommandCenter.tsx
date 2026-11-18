import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertOctagon, BellRing, CalendarClock, CheckCircle2, ClipboardCheck, FastForward, FilePlus2, Hourglass, Link2, Radio, Siren, TimerOff, UserCheck } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { post } from "../api/client";
import { type Scope, useAdvanceClock, useBreaches, useEscalations, useFeed, useFunnel, useInvalidate, useKpis } from "../api/hooks";
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

function FunnelChart({ program, scope }: { program?: string; scope: Scope }) {
  const f = useFunnel(program, scope);
  if (f.isLoading) return <LoadingBlock rows={7} />;
  if (f.error) return <ErrorState error={f.error} retry={() => void f.refetch()} />;
  const steps = f.data!.steps;
  if (!f.data!.total) {
    return <EmptyState title="No added results yet" hint="Add a result or upload a CSV on the Add Results page, then watch it move through the funnel here." icon={<FilePlus2 size={20} />} />;
  }
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
      {biggest && scope === "all" && (
        <p className="pt-2 text-xs text-ink-2" data-tour="funnel-insight">
          <strong className="text-bad">Biggest drop: before {STATE_LABEL[biggest]}.</strong> People are notified but don't engage or book —
          the gap is understanding and access, not detection.
        </p>
      )}
    </div>
  );
}

const ESC_ICON: Record<string, JSX.Element> = { red_flag: <Siren size={16} />, urgent_result: <Siren size={16} />, sla_breach: <TimerOff size={16} /> };

function EscalationFeed({ scope }: { scope: Scope }) {
  const e = useEscalations("open", undefined, scope);
  const inv = useInvalidate();
  const user = useAuth((s) => s.user);
  const [busy, setBusy] = useState<string | null>(null);
  if (e.isLoading) return <LoadingBlock rows={5} />;
  if (e.error) return <ErrorState error={e.error} />;
  const items = e.data!.items.slice(0, 8);
  if (!items.length) return <EmptyState title="No open escalations" hint="Red flags, urgent results and SLA breaches appear here within 5 seconds." icon={<CheckCircle2 size={20} />} />;
  return (
    <ul className="space-y-2">
      {items.map((x) => (
        <motion.li layout key={x.id}
          className={clsx("flex items-center gap-3 rounded-xl border p-3", ["red_flag", "urgent_result"].includes(x.reason) ? "border-bad/40 bg-bad-soft/50" : "border-line bg-bg/60")}>
          <div className={clsx("grid h-9 w-9 shrink-0 place-items-center rounded-xl", ["red_flag", "urgent_result"].includes(x.reason) ? "bg-bad text-white" : "bg-warn-soft text-warn")}>
            {ESC_ICON[x.reason] ?? <BellRing size={16} />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Link to={`/loops/${x.loop_id}`} className="hover:underline">{x.display_name}</Link>
              <span className="text-[11px] font-normal text-ink-3">{x.patient_code}</span>
            </div>
            <div className="truncate text-xs text-ink-2">
              {x.reason.replace("_", " ")} · {PROGRAM_LABEL[x.program]} · {x.notes || "—"}
            </div>
            {x.owner && <div className="text-[11px] text-ink-3">Owner: <strong className="text-ink-2">{x.owner}</strong></div>}
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

function ActivityTicker({ scope }: { scope: Scope }) {
  const f = useFeed(scope);
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
  const [params, setParams] = useSearchParams();
  const scope: Scope = params.get("scope") === "added" ? "added" : "all";
  const setScope = (v: Scope) => setParams(v === "added" ? { scope: "added" } : {}, { replace: true });
  const k = useKpis(scope);
  const b = useBreaches(scope);
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
          <>
            <Segmented<Scope> value={scope} onChange={setScope}
              options={[{ value: "all", label: "All results (simulated)" }, { value: "added", label: "Results you added" }]} />
            <button className="btn-ghost" onClick={() => adv.mutate(7)} disabled={adv.isPending} data-tour="advance-clock">
              {adv.isPending ? <Spinner /> : <FastForward size={16} />} Advance clock +7 days
            </button>
          </>
        }
      />
      {scope === "added" && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-teal-soft/60 px-4 py-2.5 text-sm text-teal-ink">
          <span>Showing only results added on the <strong>Add Results</strong> page (or imported by FHIR). Updates every few seconds.</span>
          <Link to="/intake" className="inline-flex items-center gap-1.5 font-bold hover:underline"><FilePlus2 size={14} /> Add results</Link>
        </div>
      )}
      {adv.data && (
        <div className="mb-4 rounded-xl bg-info-soft px-4 py-2 text-sm text-info">
          Clock moved to +{adv.data.offset_days} days: {adv.data.new_breaches} new SLA breaches, {adv.data.reminders_sent} reminders sent.
        </div>
      )}
      {k.error && <ErrorState error={k.error} retry={() => void k.refetch()} />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5" data-tour="kpis">
        {d ? (
          <>
            <Kpi label={scope === "added" ? "Results you added" : "Abnormal results"} value={num(d.total_loops)} sub={`${num(d.open_loops)} loops still open`} icon={<Radio size={16} />} tone="bg-indigo" />
            {scope === "added" ? (
              <Kpi label="Seen so far" value={pct(d.closure_rate_30d)} sub="visit attended or loop closed" icon={<CheckCircle2 size={16} />} tone="bg-teal" tour="kpi-closure" />
            ) : (
              <Kpi label="30-day closure" value={pct(d.closure_rate_30d)} sub={<><strong className="text-bad">{pct(d.never_completed_share)}</strong> never completed follow-up</>} icon={<CheckCircle2 size={16} />} tone="bg-teal" tour="kpi-closure" />
            )}
            <Kpi label="Median days to care" value={d.median_days_to_followup ?? "—"} sub="result → attended" icon={<CalendarClock size={16} />} tone="bg-sand" />
            <Kpi label="SLA breaches" value={num(d.sla_breaches)} sub={<span className="inline-flex items-center gap-1">SLAs 7/21/60 d <Illustrative /></span>} icon={<Hourglass size={16} />} tone="bg-warn" />
            <Kpi label="Open escalations" value={num(d.open_escalations)}
              sub={d.open_red_flags || d.open_urgent_results ? <strong className="text-bad">{[d.open_red_flags && `${d.open_red_flags} red flag(s)`, d.open_urgent_results && `${d.open_urgent_results} urgent result(s)`].filter(Boolean).join(" · ")}</strong> : "no red flags"}
              icon={<Siren size={16} />} tone="bg-bad" />
          </>
        ) : (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-36" />)
        )}
      </div>

      {d && (
        <div className="mt-4 grid gap-3 sm:grid-cols-3" data-tour="accountability">
          <div className="card flex items-center gap-3 p-4">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-teal-soft text-teal-ink"><UserCheck size={16} /></div>
            <div><div className="text-sm font-bold">{d.unowned_open_loops === 0 ? "Every open case has a named owner" : `${num(d.unowned_open_loops)} open case(s) without an owner`}</div>
              <div className="text-xs text-ink-2">Owner is set the moment a result arrives; changes are audited.</div></div>
          </div>
          <div className="card flex items-center gap-3 p-4">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-warn-soft text-warn"><ClipboardCheck size={16} /></div>
            <div><div className="text-sm font-bold">{num(d.awaiting_closure)} seen, closure note due</div>
              <div className="text-xs text-ink-2">Visit attended; the owner must document the outcome.</div></div>
          </div>
          <div className="card flex items-center gap-3 p-4">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-ok-soft text-ok"><CheckCircle2 size={16} /></div>
            <div><div className="text-sm font-bold">{num(d.closed_documented)} / {num(d.closed_loops)} closed with a documented outcome</div>
              <div className="text-xs text-ink-2">A loop can only close with who saw the patient, the result and the next step.</div></div>
          </div>
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <Card
          title="Screening-to-care funnel"
          subtitle={scope === "added" ? "Your results: cases that reached each step, from the audit log." : "Loops that reached each step (from the audit log). Simulated as-is baseline, before WASL."}
          tour="funnel"
          action={
            <Segmented size="sm" value={program} onChange={setProgram}
              options={[{ value: "", label: "All" }, { value: "DIABETES", label: "Diabetes" }, { value: "COLORECTAL", label: "Colorectal" }, { value: "BREAST", label: "Breast" }]} />
          }
        >
          <FunnelChart program={program || undefined} scope={scope} />
        </Card>
        <Card title="Live escalations" subtitle="Polled every 5 s · red flags first" tour="escalations" icon={<Siren size={16} />}>
          <EscalationFeed scope={scope} />
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
          <ActivityTicker scope={scope} />
        </Card>
      </div>
    </div>
  );
}

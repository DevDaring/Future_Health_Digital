import clsx from "clsx";
import { Award, BadgeCheck, ChevronDown, FlaskConical, Play, ShieldQuestion, Sigma } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { post } from "../api/client";
import { useInvalidate, useTwinRun, useTwinRuns } from "../api/hooks";
import type { TwinPolicy, TwinPolicyResult, TwinRun } from "../api/types";
import { Card, Chip, EmptyState, ErrorState, Illustrative, LoadingBlock, PageHeader, Spinner } from "../components/ui";
import { LANG_EN, aed, bestBy, num, pct } from "../lib/format";

const POLICIES: { id: TwinPolicy; label: string; color: string }[] = [
  { id: "no_outreach", label: "No outreach", color: "rgb(var(--ink-3))" },
  { id: "sms_everyone", label: "SMS everyone", color: "rgb(var(--info))" },
  { id: "risk_ranked", label: "Risk-ranked calls", color: "rgb(var(--warn))" },
  { id: "wasl_uplift", label: "WASL uplift", color: "rgb(var(--teal))" },
  { id: "wasl_uplift_fair", label: "WASL uplift + fairness", color: "rgb(var(--indigo))" },
];
const COLOR = Object.fromEntries(POLICIES.map((p) => [p.id, p.color]));
const SHORT: Record<string, string> = { no_outreach: "None", sms_everyone: "SMS", risk_ranked: "Risk", wasl_uplift: "WASL", wasl_uplift_fair: "WASL+fair" };

interface Params {
  horizon_days: number; n_patients: number; navigators: number; daily_budget: number; clinic_capacity_multiplier: number;
  extra_evening_friday: boolean; extra_language: string | null; cost_sms: number; cost_call: number; cost_visit: number; seed: number;
}
const DEFAULTS: Params = {
  horizon_days: 180, n_patients: 5000, navigators: 1, daily_budget: 20, clinic_capacity_multiplier: 1, extra_evening_friday: false,
  extra_language: null, cost_sms: 0.5, cost_call: 25, cost_visit: 150, seed: 42,
};

function Slider({ label, value, min, max, step = 1, onChange, fmt }: { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; fmt?: (v: number) => string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs"><span className="font-semibold text-ink-2">{label}</span><span className="tabular font-bold">{fmt ? fmt(value) : value}</span></div>
      <input type="range" className="w-full accent-[rgb(var(--teal))]" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} aria-label={label} />
    </div>
  );
}

const tooltipStyle = { borderRadius: 12, background: "rgb(var(--card))", border: "1px solid rgb(var(--line))", fontSize: 12 };

function Results({ run }: { run: TwinRun }) {
  const res = run.results?.results ?? {};
  const rows = POLICIES.filter((p) => res[p.id]).map((p) => res[p.id] as TwinPolicyResult);
  const bestClosure = bestBy(rows, (r) => r.closure_rate)?.policy;
  const bestCost = bestBy(rows.filter((r) => r.policy !== "no_outreach" && r.policy !== "sms_everyone"), (r) => r.incremental_cost_per_extra_loop, "min")?.policy;
  const bestGap = bestBy(rows, (r) => r.fairness_gap, "min")?.policy;
  const bestAlloc = bestBy(rows.filter((r) => r.allocation_gap !== null), (r) => r.allocation_gap, "min")?.policy;
  const series = rows[0]?.series.day.map((d, i) => Object.fromEntries([["day", d], ...rows.map((r) => [r.policy, r.series.cumulative_closed[i]])])) ?? [];
  const queue = rows[0]?.series.day.map((d, i) => Object.fromEntries([["day", d], ...rows.map((r) => [r.policy, r.series.clinic_queue[i]])])) ?? [];
  const langs = Object.keys(rows[0]?.by_group.language ?? {});
  const fairData = langs.map((g) => Object.fromEntries([["group", LANG_EN[g] ?? g], ...rows.map((r) => [r.policy, +(r.by_group.language[g] * 100).toFixed(1)])]));

  return (
    <div className="space-y-6" data-tour="twin-results">
      {run.results?.calibration && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-ok/30 bg-ok-soft/50 px-4 py-2.5 text-sm text-ok">
          <BadgeCheck size={16} /> {run.results.calibration.statement}
          <span className="text-xs text-ink-2">· paired comparison with common random numbers · seed {run.seed}</span>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {rows.map((r) => (
          <div key={r.policy} className={clsx("card relative overflow-hidden p-4", r.policy.startsWith("wasl") && "ring-1 ring-teal/40")}>
            <div className="absolute inset-x-0 top-0 h-1" style={{ background: COLOR[r.policy] }} />
            <div className="text-sm font-bold">{r.label}</div>
            <div className="tabular mt-2 text-3xl font-extrabold tracking-tight">{pct(r.closure_rate, 1)}</div>
            <div className="text-[11px] text-ink-3">loops closed within 60 days</div>
            <dl className="mt-3 space-y-1 text-[11px] [&_dd]:whitespace-nowrap">
              <div className="flex justify-between"><dt className="text-ink-2">Median days</dt><dd className="tabular font-semibold">{r.median_days_to_followup ?? "—"}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-2">Extra closed</dt><dd className="tabular font-semibold">+{num(r.extra_closed_vs_no_outreach)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-2">Cost / extra loop</dt><dd className="tabular font-semibold">{r.incremental_cost_per_extra_loop ? aed(r.incremental_cost_per_extra_loop) : "—"}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-2">Closure gap</dt><dd className="tabular font-semibold">{pct(r.fairness_gap, 1)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-2">Allocation gap</dt><dd className="tabular font-semibold">{r.allocation_gap === null ? "—" : pct(r.allocation_gap, 1)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-2">Navigator use</dt><dd className="tabular font-semibold">{pct(r.navigator_utilisation)}</dd></div>
            </dl>
            <div className="mt-3 flex flex-wrap gap-1">
              {r.policy === bestClosure && <Chip tone="teal" icon={<Award size={11} />}>most loops closed</Chip>}
              {r.policy === bestCost && <Chip tone="sand" icon={<Award size={11} />}>lowest cost / extra loop</Chip>}
              {r.policy === bestGap && <Chip tone="indigo" icon={<Award size={11} />}>smallest closure gap</Chip>}
              {r.policy === bestAlloc && <Chip tone="ok" icon={<Award size={11} />}>fairest allocation</Chip>}
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Loop-closure rate" subtitle="Share of abnormal results followed up within 60 days">
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={rows.map((r) => ({ name: SHORT[r.policy], v: +(r.closure_rate * 100).toFixed(1), p: r.policy }))} margin={{ left: -15 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "rgb(var(--ink-2))" }} interval={0} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} domain={[40, 100]} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v}%`} />
                <Bar dataKey="v" radius={[8, 8, 0, 0]}>{rows.map((r) => <Cell key={r.policy} fill={COLOR[r.policy]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Outreach cost per extra closed loop" subtitle={<span className="inline-flex items-center gap-1">vs. no outreach · AED <Illustrative /></span>}>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={rows.filter((r) => r.incremental_cost_per_extra_loop).map((r) => ({ name: SHORT[r.policy], v: r.incremental_cost_per_extra_loop, p: r.policy }))} margin={{ left: -5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: "rgb(var(--ink-2))" }} interval={0} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => aed(v as number)} />
                <Bar dataKey="v" radius={[8, 8, 0, 0]}>{rows.filter((r) => r.incremental_cost_per_extra_loop).map((r) => <Cell key={r.policy} fill={COLOR[r.policy]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Cumulative closed loops over time">
          <div className="h-64">
            <ResponsiveContainer>
              <LineChart data={series} margin={{ left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} tickFormatter={(d) => `d${d}`} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {rows.map((r) => <Line key={r.policy} dataKey={r.policy} name={r.label} stroke={COLOR[r.policy]} strokeWidth={r.policy.startsWith("wasl") ? 3 : 1.8} dot={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Clinic queue" subtitle="People waiting for a follow-up slot (all clinics)">
          <div className="h-64">
            <ResponsiveContainer>
              <AreaChart data={queue} margin={{ left: -15 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} tickFormatter={(d) => `d${d}`} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                {rows.map((r) => <Area key={r.policy} dataKey={r.policy} name={r.label} stroke={COLOR[r.policy]} fill={COLOR[r.policy]} fillOpacity={0.08} strokeWidth={1.8} />)}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card title="Closure rate by language group" subtitle="Fairness gap = best group − worst group. Uplift targeting narrows it; the fairness floor equalises budget share vs need share.">
        <div className="h-72">
          <ResponsiveContainer>
            <BarChart data={fairData} margin={{ left: -15 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
              <XAxis dataKey="group" tick={{ fontSize: 11, fill: "rgb(var(--ink-2))" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v}%`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {rows.map((r) => <Bar key={r.policy} dataKey={r.policy} name={r.label} fill={COLOR[r.policy]} radius={[4, 4, 0, 0]} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}

function Sensitivity({ run }: { run: TwinRun }) {
  const r = run.results;
  if (!r?.closure_by_scale) return null;
  const pols = POLICIES.filter((p) => r.closure_by_scale![p.id]);
  return (
    <div data-tour="sensitivity">
      <div className={clsx("mb-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-bold", r.robust ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn")}>
        {r.robust ? <BadgeCheck size={15} /> : <ShieldQuestion size={15} />}
        {r.robust ? "Robust: WASL beats every baseline at ×0.5, ×1.0 and ×1.5 outreach effect" : "Not robust at every scale"}
      </div>
      <table className="w-full text-sm">
        <thead><tr className="text-left"><th className="label py-1">Policy</th>{r.scales!.map((s) => <th key={s} className="label py-1 text-right">effect ×{s}</th>)}</tr></thead>
        <tbody>
          {pols.map((p) => (
            <tr key={p.id} className="border-t border-line">
              <td className="py-1.5 font-semibold"><span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />{p.label}</td>
              {r.scales!.map((s) => <td key={s} className="tabular py-1.5 text-right">{pct(r.closure_by_scale![p.id][String(s)], 1)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PolicyTwin() {
  const [params, setParams] = useState<Params>(DEFAULTS);
  const [selected, setSelected] = useState<TwinPolicy[]>(POLICIES.map((p) => p.id));
  const [runId, setRunId] = useState<string | null>(null);
  const [sensId, setSensId] = useState<string | null>(null);
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const history = useTwinRuns("compare");
  const sensHistory = useTwinRuns("sensitivity");
  const run = useTwinRun(runId);
  const sens = useTwinRun(sensId);
  const inv = useInvalidate();
  const set = <K extends keyof Params>(k: K, v: Params[K]) => setParams((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    if (!runId && history.data?.items.length) setRunId(history.data.items.find((r) => r.status === "done")?.id ?? null);
  }, [history.data, runId]);
  useEffect(() => {
    if (!sensId && sensHistory.data?.items.length) setSensId(sensHistory.data.items.find((r) => r.status === "done")?.id ?? null);
  }, [sensHistory.data, sensId]);
  useEffect(() => {
    if (run.data?.status === "done") inv("twinruns");
  }, [run.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  async function start(kind: "runs" | "sensitivity") {
    setErr(null);
    try {
      const r = await post<TwinRun>(`/twin/${kind}`, { policies: selected, params });
      if (kind === "runs") setRunId(r.id);
      else setSensId(r.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }
  const running = run.data && (run.data.status === "queued" || run.data.status === "running");
  const sensRunning = sens.data && (sens.data.status === "queued" || sens.data.status === "running");
  const assumptions = useMemo(
    () => [
      ["Ground-truth behaviour model", "backend/app/synth/config.yaml"], ["Navigator call ≈ 15 min, 7 h day", "TwinParams.call_minutes"],
      ["8 visits / clinic / day", "TwinParams.visits_per_clinic_per_day"], ["Native navigator languages: ar, en, hi, ur (others via interpreter, 60% effect)", "system_twin.NATIVE_NAVIGATOR_LANGS"],
      ["Evening/Friday slots available 60% of the time (100% with extra sessions)", "system_twin.simulate"], ["Closed = attended within 60 days", "SLA_WINDOW_DAYS"],
      ["Costs: SMS 0.5, tailored contact 25, visit 150 AED", "TwinParams.cost_*"], ["Severity weights 1 / 1.25 / 1.5", "ml/prioritise.py"], ["Fairness slack ε = 0.1", "TwinParams.fairness_epsilon"],
    ],
    [],
  );

  return (
    <div>
      <PageHeader eyebrow="Care-pathway digital twin" title="Test outreach policies before they touch real people"
        subtitle="A SimPy simulation of 5,000 abnormal results. Policies rank people with the trained models; outcomes come from the hidden ground truth." />
      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <Card title="Scenario" icon={<Sigma size={16} />} className="h-fit xl:sticky xl:top-20" tour="twin-params">
          <div className="space-y-4">
            <Slider label="Horizon" value={params.horizon_days} min={60} max={365} step={10} onChange={(v) => set("horizon_days", v)} fmt={(v) => `${v} days`} />
            <Slider label="Navigators" value={params.navigators} min={1} max={10} onChange={(v) => set("navigators", v)} />
            <Slider label="Daily contact budget" value={params.daily_budget} min={5} max={100} onChange={(v) => set("daily_budget", v)} />
            <Slider label="Clinic capacity" value={params.clinic_capacity_multiplier} min={0.5} max={2} step={0.1} onChange={(v) => set("clinic_capacity_multiplier", v)} fmt={(v) => `×${v.toFixed(1)}`} />
            <label className="flex items-center justify-between text-xs font-semibold text-ink-2">
              Extra evening / Friday sessions
              <input type="checkbox" checked={params.extra_evening_friday} onChange={(e) => set("extra_evening_friday", e.target.checked)} />
            </label>
            <label className="block text-xs font-semibold text-ink-2">
              Extra-language navigator
              <select className="input mt-1" value={params.extra_language ?? ""} onChange={(e) => set("extra_language", e.target.value || null)}>
                <option value="">None</option>
                {["ml", "bn", "tl"].map((l) => <option key={l} value={l}>{LANG_EN[l]}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(["cost_sms", "cost_call", "cost_visit"] as const).map((k) => (
                <label key={k} className="text-[11px] font-semibold text-ink-2">{k.replace("cost_", "")} AED
                  <input type="number" className="input mt-1 !px-2" value={params[k]} onChange={(e) => set(k, +e.target.value)} />
                </label>
              ))}
            </div>
            <label className="block text-[11px] font-semibold text-ink-2">Seed<input type="number" className="input mt-1" value={params.seed} onChange={(e) => set("seed", +e.target.value)} /></label>
            <div>
              <div className="label mb-1.5">Policies</div>
              <div className="flex flex-wrap gap-1.5">
                {POLICIES.map((p) => {
                  const on = selected.includes(p.id);
                  return (
                    <button key={p.id} type="button" onClick={() => setSelected(on ? selected.filter((x) => x !== p.id) : [...selected, p.id])}
                      className={clsx("chip border", on ? "border-transparent text-white" : "border-line bg-card text-ink-2")} style={on ? { background: p.color } : undefined}>
                      {p.label}
                    </button>
                  );
                })}
              </div>
            </div>
            <button className="btn-primary w-full" disabled={!selected.length || !!running} onClick={() => void start("runs")} data-tour="twin-run">
              {running ? <Spinner /> : <Play size={16} />} Run twin
            </button>
            <button className="btn-ghost w-full" disabled={!!sensRunning} onClick={() => void start("sensitivity")}>
              {sensRunning ? <Spinner /> : <FlaskConical size={16} />} Sensitivity ±50%
            </button>
            {err && <div className="rounded-xl bg-bad-soft p-2 text-xs text-bad">{err}</div>}
          </div>
        </Card>

        <div className="space-y-6">
          {running && (
            <div className="card flex items-center gap-3 p-5"><Spinner /> Simulating {num(params.n_patients)} patients × {selected.length} policies…</div>
          )}
          {run.error && <ErrorState error={run.error} />}
          {run.data?.status === "error" && <ErrorState error={run.data.error} />}
          {run.data?.status === "done" ? <Results run={run.data} /> : !running && (history.isLoading ? <LoadingBlock rows={6} /> : <EmptyState title="No twin run yet" hint="Press Run twin — it takes a few seconds." />)}
          <Card title="Sensitivity analysis" subtitle="Outreach effect scaled ×0.5 / ×1.0 / ×1.5 — does WASL still win?">
            {sens.data?.status === "done" ? <Sensitivity run={sens.data} /> : sensRunning ? <div className="flex items-center gap-2 text-sm"><Spinner /> Running 15 simulations…</div> : <EmptyState title="Not run yet" hint="Press Sensitivity ±50%." />}
          </Card>
          <div className="card p-5">
            <button className="flex w-full items-center justify-between text-left" onClick={() => setShowAssumptions(!showAssumptions)} aria-expanded={showAssumptions}>
              <span className="flex items-center gap-2 font-bold">ILLUSTRATIVE ASSUMPTIONS <Illustrative /></span>
              <ChevronDown size={18} className={clsx("transition", showAssumptions && "rotate-180")} />
            </button>
            {showAssumptions && (
              <ul className="mt-3 divide-y divide-line text-sm">
                {assumptions.map(([a, w]) => <li key={a} className="flex justify-between gap-4 py-2"><span>{a}</span><code className="text-[11px] text-ink-3">{w}</code></li>)}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

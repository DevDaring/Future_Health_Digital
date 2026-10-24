import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Download, FileBadge2, Fingerprint, Hammer, Scale, Search, ShieldCheck, ShieldX, Undo2, UserCheck } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { download, get, post } from "../api/client";
import { useFairness, useInvalidate } from "../api/hooks";
import { Card, Chip, EmptyState, ErrorState, Illustrative, LoadingBlock, PageHeader, Segmented, Spinner } from "../components/ui";
import { LANG_EN, num, pct, relTime } from "../lib/format";
import { useAuth } from "../store/auth";

type Tab = "fairness" | "model" | "audit" | "consent" | "review";
const tooltipStyle = { borderRadius: 12, background: "rgb(var(--card))", border: "1px solid rgb(var(--line))", fontSize: 12 };
const label = (g: string, by: string) => (by === "language" ? LANG_EN[g] ?? g : g);

function FairnessTab() {
  const [by, setBy] = useState("language");
  const f = useFairness(by);
  if (f.isLoading) return <LoadingBlock rows={6} />;
  if (f.error) return <ErrorState error={f.error} />;
  const d = f.data!;
  const best = d.best_rate ?? 0;
  const closure = d.groups.map((g) => ({ group: label(g.group, by), rate: g.closure_rate !== null ? +(g.closure_rate * 100).toFixed(1) : 0, disparity: g.disparity }));
  const share = d.groups.map((g) => ({ group: label(g.group, by), need: +(g.need_share * 100).toFixed(1), risk: +(g.budget_share.risk_only * 100).toFixed(1), uplift: +(g.budget_share.uplift * 100).toFixed(1), fair: +(g.budget_share.uplift_fair * 100).toFixed(1) }));
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={by} onChange={setBy} options={[{ value: "language", label: "Language" }, { value: "nationality_group", label: "Nationality" }, { value: "insurance_tier", label: "Insurance" }, { value: "sex", label: "Sex" }]} />
        <span className="text-xs text-ink-2">Disparity = closure below 80% of the best group (four-fifths rule, a heuristic).</span>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Loop-closure rate by group" subtitle="Live loops with results ≥ 30 days old (as-is baseline)" tour="fairness-closure">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={closure} margin={{ left: -15 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="group" tick={{ fontSize: 11, fill: "rgb(var(--ink-2))" }} interval={0} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v}%`} />
                <ReferenceLine y={best * 80} stroke="rgb(var(--bad))" strokeDasharray="5 4" label={{ value: "80% of best", fill: "rgb(var(--bad))", fontSize: 11, position: "insideTopRight" }} />
                <Bar dataKey="rate" radius={[8, 8, 0, 0]} fill="rgb(var(--teal))" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {d.groups.filter((g) => g.disparity).map((g) => <Chip key={g.group} tone="bad" icon={<AlertTriangle size={11} />}>{label(g.group, by)} below 80%</Chip>)}
          </div>
        </Card>
        <Card title="Share of today's outreach budget vs share of need" subtitle="Need = open high/urgent loops. The fairness floor guarantees ≥ need × (1 − ε).">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={share} margin={{ left: -15 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="group" tick={{ fontSize: 11, fill: "rgb(var(--ink-2))" }} interval={0} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v}%`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="need" name="Need share" fill="rgb(var(--ink-3))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="risk" name="Risk policy" fill="rgb(var(--warn))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="uplift" name="Uplift" fill="rgb(var(--teal))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="fair" name="Uplift + fair" fill="rgb(var(--indigo))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Card title="Model performance by group" subtitle={`Held-out test set · model ${d.model_version ?? "—"}`}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px] text-sm">
            <thead><tr className="text-left">{["Group", "Live loops", "Closure", "vs best", "AUROC", "Brier (calibration)", "TPR of high-risk flag"].map((h) => <th key={h} className="label py-2">{h}</th>)}</tr></thead>
            <tbody>
              {d.groups.map((g) => (
                <tr key={g.group} className="border-t border-line">
                  <td className="py-2 font-semibold">{label(g.group, by)}</td>
                  <td className="tabular">{num(g.n_loops)}</td>
                  <td className="tabular">{pct(g.closure_rate, 1)}</td>
                  <td>{g.ratio_to_best !== null && <Chip tone={g.disparity ? "bad" : "ok"}>{(g.ratio_to_best * 100).toFixed(0)}%</Chip>}</td>
                  <td className="tabular">{g.auroc?.toFixed(3) ?? "—"}</td>
                  <td className="tabular">{g.brier?.toFixed(3) ?? "—"}</td>
                  <td className="tabular">{pct(g.tpr_high_risk)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

interface ModelCard {
  name: string; version: string; owner: string; intended_use: string; out_of_scope: string[]; training_data: string; features_excluded: string[]; limitations: string[];
  risk: { auroc: number; auprc: number; brier: number; n: number; base_rate: number };
  uplift: { auuc_true: Record<string, number>; qini_auuc_observed: Record<string, number>; corr_with_true_tau: number; true_gain_curves: Record<string, { frac: number[]; gain: number[] }> };
  data: Record<string, number>; feature_importance: { feature: string; gain_share: number }[]; llm_provider: string;
}

function ModelTab() {
  const mc = useQuery({ queryKey: ["modelcard"], queryFn: () => get<ModelCard>("/governance/model-card") });
  const cal = useQuery({ queryKey: ["calibration"], queryFn: () => get<{ bins: { pred: number; obs: number; n: number }[]; brier: number }>("/governance/calibration") });
  if (mc.isLoading) return <LoadingBlock rows={8} />;
  if (mc.error) return <ErrorState error={mc.error} />;
  const m = mc.data!;
  const curves = m.uplift.true_gain_curves;
  const gain = curves.uplift.frac.map((f, i) => ({ frac: Math.round(f * 100), uplift: +(curves.uplift.gain[i] * 100).toFixed(1), risk: +(curves.risk.gain[i] * 100).toFixed(1), random: +(curves.random.gain[i] * 100).toFixed(1) }));
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Model card" subtitle={`${m.name} · ${m.version}`} icon={<FileBadge2 size={16} />} className="xl:col-span-2">
          <div className="grid gap-4 text-sm md:grid-cols-2">
            <div><div className="label mb-1">Intended use</div><p className="text-ink-2">{m.intended_use}</p></div>
            <div><div className="label mb-1">Training data</div><p className="text-ink-2">{m.training_data}</p></div>
            <div><div className="label mb-1">Out of scope</div><ul className="list-disc pl-5 text-ink-2">{m.out_of_scope.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><div className="label mb-1">Limitations</div><ul className="list-disc pl-5 text-ink-2">{m.limitations.map((x) => <li key={x}>{x}</li>)}</ul></div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <Chip tone="teal">owner: {m.owner}</Chip><Chip tone="neutral">excluded: {m.features_excluded.join("; ")}</Chip><Chip tone="indigo">LLM: {m.llm_provider}</Chip>
          </div>
        </Card>
        <Card title="Headline metrics" subtitle="Synthetic test set">
          <div className="grid grid-cols-2 gap-4">
            {[["AUROC", m.risk.auroc.toFixed(3)], ["AUPRC", m.risk.auprc.toFixed(3)], ["Brier", m.risk.brier.toFixed(3)], ["Uplift corr.", m.uplift.corr_with_true_tau.toFixed(2)]].map(([k, v]) => (
              <div key={k} className="rounded-xl bg-bg p-3"><div className="label">{k}</div><div className="tabular mt-1 text-2xl font-extrabold">{v}</div></div>
            ))}
          </div>
          <div className="mt-4 space-y-1.5 text-sm">
            <div className="label">AUUC vs true effect (random ≈ 0)</div>
            {(["uplift", "risk", "random"] as const).map((k) => (
              <div key={k} className="flex items-center justify-between"><span className="capitalize">{k === "uplift" ? "WASL uplift" : k}</span><span className="tabular font-bold">{m.uplift.auuc_true[k].toFixed(3)}</span></div>
            ))}
          </div>
        </Card>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Uplift gain curve (known true effect)" subtitle="Contact the top x% ranked by each score: share of all achievable gain captured">
          <div className="h-72">
            <ResponsiveContainer>
              <LineChart data={gain} margin={{ left: -15 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="frac" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v}%`} labelFormatter={(l) => `top ${l}% contacted`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line dataKey="uplift" name="WASL uplift" stroke="rgb(var(--teal))" strokeWidth={3} dot={false} />
                <Line dataKey="risk" name="Risk ranking" stroke="rgb(var(--warn))" strokeWidth={2} dot={false} />
                <Line dataKey="random" name="Random" stroke="rgb(var(--ink-3))" strokeDasharray="5 4" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Calibration (drop-off risk)" subtitle={`Isotonic-calibrated · Brier ${cal.data?.brier.toFixed(3) ?? "—"}`}>
          <div className="h-72">
            {cal.data && (
              <ResponsiveContainer>
                <ScatterChart margin={{ left: -15 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" />
                  <XAxis type="number" dataKey="pred" name="Predicted" domain={[0, 1]} tickFormatter={(v) => pct(v)} tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} />
                  <YAxis type="number" dataKey="obs" name="Observed" domain={[0, 1]} tickFormatter={(v) => pct(v)} tick={{ fontSize: 11, fill: "rgb(var(--ink-3))" }} />
                  <ZAxis dataKey="n" range={[40, 260]} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => pct(v, 1)} />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="rgb(var(--ink-3))" strokeDasharray="4 4" />
                  <Scatter data={cal.data.bins} fill="rgb(var(--indigo))" />
                </ScatterChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>
      <Card title="What drives drop-off risk" subtitle="Share of total split gain in the risk model">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {m.feature_importance.slice(0, 9).map((f) => (
            <div key={f.feature} className="flex items-center gap-2 text-sm">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg"><div className="h-full rounded-full bg-indigo" style={{ width: `${f.gain_share * 300}%` }} /></div>
              <span className="w-52 truncate text-xs text-ink-2">{f.feature}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function AuditTab() {
  const user = useAuth((s) => s.user);
  const [res, setRes] = useState<{ valid: boolean; broken_at: string | null; broken_seq?: number | null; checked: number; verified_at?: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  async function run(kind: "verify" | "tamper" | "untamper") {
    setBusy(kind);
    try {
      if (kind === "verify") setRes(await get("/governance/audit/verify"));
      else setRes((await post<{ verify: typeof res }>(`/demo/${kind}`)).verify);
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
      <Card title="Tamper-evident audit chain" subtitle="hash = SHA-256(prev_hash ‖ canonical JSON(event) ‖ created_at), per loop and globally" icon={<Fingerprint size={16} />} tour="verify-chain">
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" onClick={() => void run("verify")} disabled={!!busy}>{busy === "verify" ? <Spinner /> : <ShieldCheck size={16} />} Verify chain</button>
          <button className="btn-ghost" onClick={() => void download("/governance/audit/export.csv", "wasl_audit_log.csv")}><Download size={16} /> Export CSV</button>
        </div>
        {res && (
          <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} key={`${res.valid}-${res.checked}`}
            className={clsx("mt-5 flex items-center gap-4 rounded-2xl p-5", res.valid ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad")}>
            {res.valid ? <ShieldCheck size={40} /> : <ShieldX size={40} />}
            <div>
              <div className="text-lg font-extrabold">{res.valid ? "Chain intact" : "Tampering detected"}</div>
              <div className="text-sm">{res.valid ? `${num(res.checked)} events re-hashed — no record was altered.` : `Broken at event #${res.broken_seq} (${res.broken_at?.slice(0, 8)}…). Every later hash no longer matches.`}</div>
            </div>
          </motion.div>
        )}
      </Card>
      {user?.role === "admin" && (
        <Card title="Try to cheat (demo)" subtitle="Edit one stored audit row directly in the database, without re-hashing — exactly what an attacker would do." icon={<Hammer size={16} />}>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost border-bad/50 text-bad" onClick={() => void run("tamper")} disabled={!!busy}>{busy === "tamper" ? <Spinner /> : <Hammer size={16} />} Tamper one record</button>
            <button className="btn-ghost" onClick={() => void run("untamper")} disabled={!!busy}>{busy === "untamper" ? <Spinner /> : <Undo2 size={16} />} Repair</button>
          </div>
        </Card>
      )}
    </div>
  );
}

function ConsentTab() {
  const [q, setQ] = useState("");
  const [pid, setPid] = useState<string | null>(null);
  const inv = useInvalidate();
  const search = useQuery({
    queryKey: ["consent-search", q],
    queryFn: () => get<{ items: { patient_id: string; display_name: string; patient_code: string; persona: string | null }[] }>(`/worklist?budget=2000&size=8&show_all=true&q=${encodeURIComponent(q)}`),
    enabled: q.length >= 2,
  });
  const c = useQuery({
    queryKey: ["consent", pid],
    queryFn: () => get<{ current: Record<string, { granted: boolean; granted_at: string | null; revoked_at: string | null }>; history: { scope: string; granted: boolean; created_at: string; note: string | null }[] }>(`/consents/${pid}`),
    enabled: !!pid,
  });
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
      <Card title="Find a patient" icon={<Search size={16} />}>
        <input className="input" placeholder="Type a name or WASL-P code (e.g. Ramesh)" value={q} onChange={(e) => setQ(e.target.value)} />
        <ul className="mt-3 space-y-1.5">
          {search.data?.items.map((p) => (
            <li key={p.patient_id}>
              <button className={clsx("w-full rounded-xl border px-3 py-2 text-left text-sm", pid === p.patient_id ? "border-teal bg-teal-soft/40" : "border-line hover:bg-bg")} onClick={() => setPid(p.patient_id)}>
                <span className="font-semibold">{p.display_name}</span> <span className="text-xs text-ink-3">{p.patient_code}</span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Consent center" subtitle="Revoking outreach consent immediately stops all navigator messages." icon={<UserCheck size={16} />}>
        {!pid ? <EmptyState title="Pick a patient" /> : c.isLoading ? <LoadingBlock rows={3} /> : c.data && (
          <div className="space-y-3">
            {(["outreach", "data_for_model", "share_with_clinic"] as const).map((scope) => {
              const cur = c.data!.current[scope];
              return (
                <div key={scope} className="flex items-center justify-between rounded-xl border border-line p-3">
                  <div>
                    <div className="font-semibold capitalize">{scope.replace(/_/g, " ")}</div>
                    <div className="text-xs text-ink-2">{cur?.granted ? "granted" : "not granted / revoked"}</div>
                  </div>
                  <button className={clsx("btn !py-1.5 text-xs", cur?.granted ? "bg-bad-soft text-bad" : "bg-ok-soft text-ok")}
                    onClick={async () => { await post(`/consents/${pid}`, { scope, granted: !cur?.granted }); void c.refetch(); inv("loop"); }}>
                    {cur?.granted ? "Revoke" : "Grant"}
                  </button>
                </div>
              );
            })}
            <div className="label pt-2">History</div>
            <ul className="space-y-1 text-xs text-ink-2">{c.data.history.slice(-6).reverse().map((h, i) => <li key={i}>{relTime(h.created_at)} · {h.scope} {h.granted ? "granted" : "revoked"} {h.note ? `· ${h.note}` : ""}</li>)}</ul>
          </div>
        )}
      </Card>
    </div>
  );
}

function ReviewTab() {
  const user = useAuth((s) => s.user);
  const r = useQuery({ queryKey: ["review"], queryFn: () => get<{ items: { id: string; item_type: string; loop_id: string | null; reason: string; patient_code: string | null; persona: string | null; created_at: string }[]; total: number }>("/review-queue?size=50"), refetchInterval: 8000 });
  const canDecide = user?.role === "admin" || user?.role === "clinician";
  if (r.isLoading) return <LoadingBlock rows={5} />;
  if (!r.data?.items.length) return <EmptyState title="Review queue is empty" hint="Translation failures, teach-back failures, refusals and LLM refusals land here for a human." icon={<ClipboardCheck size={20} />} />;
  return (
    <Card title={`Human oversight queue (${r.data.total})`} subtitle="Nothing the AI could not verify reaches a patient without a human able to see it." icon={<ClipboardCheck size={16} />}>
      <ul className="space-y-2">
        {r.data.items.map((it) => (
          <li key={it.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3">
            <Chip tone={it.item_type === "translation_check" ? "warn" : it.item_type === "refusal" ? "neutral" : "indigo"}>{it.item_type.replace("_", " ")}</Chip>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">{it.persona ? `${it.persona} · ` : ""}{it.patient_code}</div>
              <div className="truncate text-xs text-ink-2">{it.reason}</div>
            </div>
            <span className="text-[11px] text-ink-3">{relTime(it.created_at)}</span>
            {it.loop_id && <a href={`/loops/${it.loop_id}`} className="text-xs font-bold text-teal hover:underline">Open loop</a>}
            {canDecide && (
              <div className="flex gap-1.5">
                <button className="btn !py-1 text-xs bg-ok-soft text-ok" onClick={async () => { await post(`/review-queue/${it.id}/decide`, { decision: "approved", note: "Reviewed" }); void r.refetch(); }}><CheckCircle2 size={12} /> Approve</button>
                <button className="btn !py-1 text-xs bg-bad-soft text-bad" onClick={async () => { await post(`/review-queue/${it.id}/decide`, { decision: "rejected", note: "Needs correction" }); void r.refetch(); }}>Reject</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

const TABS: Tab[] = ["fairness", "model", "audit", "consent", "review"];

export default function Fairness() {
  const [params, setParams] = useSearchParams();
  const initial = params.get("tab") as Tab | null;
  const [tab, setTabState] = useState<Tab>(initial && TABS.includes(initial) ? initial : "fairness");
  const setTab = (t: Tab) => {
    setTabState(t);
    setParams({ tab: t }, { replace: true });
  };
  return (
    <div>
      <PageHeader eyebrow="Trust & governance" title="Fair, explainable, auditable"
        subtitle="Fairness by group, the model card, a hash-chained audit trail, consent and human oversight — in one place."
        actions={<Illustrative>Synthetic data</Illustrative>} />
      <div className="mb-6 overflow-x-auto">
        <Segmented<Tab> value={tab} onChange={setTab} options={[
          { value: "fairness", label: <span className="inline-flex items-center gap-1.5"><Scale size={14} />Fairness</span> },
          { value: "model", label: <span className="inline-flex items-center gap-1.5"><FileBadge2 size={14} />Model card</span> },
          { value: "audit", label: <span className="inline-flex items-center gap-1.5"><Fingerprint size={14} />Audit</span> },
          { value: "consent", label: <span className="inline-flex items-center gap-1.5"><UserCheck size={14} />Consent</span> },
          { value: "review", label: <span className="inline-flex items-center gap-1.5"><ClipboardCheck size={14} />Review queue</span> },
        ]} />
      </div>
      {tab === "fairness" && <FairnessTab />}
      {tab === "model" && <ModelTab />}
      {tab === "audit" && <AuditTab />}
      {tab === "consent" && <ConsentTab />}
      {tab === "review" && <ReviewTab />}
    </div>
  );
}

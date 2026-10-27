import clsx from "clsx";
import { ArrowDownUp, ChevronLeft, ChevronRight, Lightbulb, Search, Send, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { post } from "../api/client";
import { useInvalidate, useWorklist } from "../api/hooks";
import type { Policy } from "../api/types";
import { Card, EmptyState, ErrorState, Illustrative, LangChip, LoadingBlock, Meter, PageHeader, Segmented, SeverityBadge, Spinner, StateBadge } from "../components/ui";
import { LANG_EN, PROGRAM_LABEL, num, pct, resultLabel, slaTone } from "../lib/format";

const PERSONA_NAMES: Record<string, string> = { ramesh: "Ramesh", fatima: "Fatima", joy: "Joy", imran: "Imran", sara: "Sara" };

export default function Worklist() {
  const [policy, setPolicy] = useState<Policy>("uplift");
  const [budget, setBudget] = useState(200);
  const [page, setPage] = useState(1);
  const [program, setProgram] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<string | null>(null);
  const w = useWorklist(policy, budget, page, program || undefined, q || undefined);
  const inv = useInvalidate();
  const nav = useNavigate();
  const d = w.data;

  async function startBulk() {
    setBulk("…");
    const r = await post<{ started: string[]; skipped: unknown[] }>("/loops/outreach/bulk", [...sel]);
    setBulk(`Started outreach for ${r.started.length} (skipped ${r.skipped.length}). Patients receive a secure magic link.`);
    setSel(new Set());
    inv("worklist", "kpis", "feed");
  }

  return (
    <div>
      <PageHeader
        eyebrow="Worklist"
        title="Who to call today"
        subtitle="Ranked by how much outreach changes the outcome (uplift), not just who is at risk — under a daily call budget."
      />
      <div className="card mb-5 flex flex-wrap items-center gap-x-6 gap-y-4 p-4" data-tour="policy-switch">
        <div>
          <div className="label mb-1.5">Prioritisation policy</div>
          <Segmented<Policy>
            value={policy}
            onChange={(v) => { setPolicy(v); setPage(1); }}
            options={[
              { value: "risk_only", label: "Risk", hint: "severity × P(drop-off)" },
              { value: "uplift", label: "Uplift (WASL)", hint: "severity × uplift" },
              { value: "uplift_fair", label: "Uplift + Fair", hint: "uplift with per-language minimum share of budget" },
            ]}
          />
        </div>
        <div className="min-w-[220px] flex-1">
          <div className="label mb-1.5 flex items-center justify-between">
            <span>Daily outreach budget</span>
            <span className="tabular text-ink">{budget} contacts</span>
          </div>
          <input type="range" min={20} max={500} step={10} value={budget} onChange={(e) => { setBudget(+e.target.value); setPage(1); }}
            className="w-full accent-[rgb(var(--teal))]" aria-label="Daily outreach budget" />
        </div>
        <div className="flex items-center gap-2">
          <select className="input !w-auto" value={program} onChange={(e) => { setProgram(e.target.value); setPage(1); }} aria-label="Program">
            <option value="">All programs</option>
            <option value="DIABETES">Diabetes</option>
            <option value="COLORECTAL">Colorectal</option>
            <option value="BREAST">Breast</option>
          </select>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
            <input className="input !w-44 pl-8" placeholder="Name or code" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search" />
          </div>
        </div>
      </div>

      {d && (
        <div className="mb-5 grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <Card className="!p-4" tour="persona-tracker">
            <div className="label mb-2 flex items-center gap-2"><UserRound size={12} /> Demo personas — rank under this policy</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(d.personas).map(([k, p]) => (
                <Link key={k} to={`/loops/${p.loop_id}`}
                  className={clsx("flex items-center gap-2 rounded-xl border px-3 py-1.5 text-sm transition hover:shadow-soft",
                    p.in_budget ? "border-teal/50 bg-teal-soft/40" : "border-line bg-bg")}>
                  <span className="font-bold">{PERSONA_NAMES[k] ?? k}</span>
                  <span className="tabular text-xs text-ink-2">{p.rank ? `#${p.rank}` : "booked"}</span>
                  {p.in_budget ? <span className="chip bg-teal text-white">today</span> : <span className="chip bg-line text-ink-3">later</span>}
                </Link>
              ))}
            </div>
          </Card>
          <Card className="!p-4" tour="uplift-insight">
            <div className="label mb-2 flex items-center gap-2"><Lightbulb size={12} /> Versus risk-only ranking</div>
            {policy === "risk_only" ? (
              <p className="text-sm text-ink-2">Switch to <strong>Uplift</strong> to see who changes.</p>
            ) : (
              <p className="text-sm leading-relaxed text-ink-2">
                <strong className="text-ink">{d.vs_risk_only.swapped_out}</strong> people leave today's list — they average{" "}
                <strong className="text-ink">{num(d.vs_risk_only.avg_prior_no_shows_out, 1)}</strong> past no-shows and a call barely moves them
                (uplift {pct(d.vs_risk_only.avg_uplift_out)}). <strong className="text-ink">{d.vs_risk_only.swapped_in}</strong> people come in for whom outreach
                matters more (uplift {pct(d.vs_risk_only.avg_uplift_in)}): about <strong className="text-teal">+{num(d.vs_risk_only.expected_extra_returns, 1)}</strong> extra
                expected returns from the same {d.budget} calls.
              </p>
            )}
          </Card>
        </div>
      )}

      <Card
        title={d ? `${num(d.total)} loops in today's budget` : "Ranked loops"}
        subtitle={d ? `${num(d.eligible)} open loops eligible · expected returns caused by outreach ≈ ${num(d.expected_returns_from_outreach, 0)}` : undefined}
        action={
          <button className="btn-primary" disabled={!sel.size || bulk === "…"} onClick={() => void startBulk()}>
            {bulk === "…" ? <Spinner /> : <Send size={15} />} Start outreach ({sel.size})
          </button>
        }
      >
        {bulk && bulk !== "…" && <div className="mb-3 rounded-xl bg-ok-soft px-3 py-2 text-sm text-ok">{bulk}</div>}
        {w.isLoading ? <LoadingBlock rows={8} /> : w.error ? <ErrorState error={w.error} retry={() => void w.refetch()} /> : !d!.items.length ? (
          <EmptyState title="Nothing to show" hint="No open loops match these filters." />
        ) : (
          <div className="-mx-5 overflow-x-auto scrollbar-thin">
            <table className="w-full min-w-[1180px] text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  {["", "#", "Patient", "Result", "Severity", "State", "SLA", "P(drop-off)", "Uplift", "Top reason"].map((h) => (
                    <th key={h} className="label px-3 py-2 first:pl-5">{h === "Uplift" ? <span className="inline-flex items-center gap-1">Uplift <ArrowDownUp size={10} /></span> : h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d!.items.map((r) => (
                  <tr key={r.id} className={clsx("cursor-pointer border-b border-line/60 transition hover:bg-bg", r.persona && "bg-sand-soft/30")}
                    onClick={() => nav(`/loops/${r.id}`)} data-tour={r.persona ? `row-${r.persona}` : undefined}>
                    <td className="py-2.5 pl-5 pr-2" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" aria-label={`Select ${r.display_name}`} checked={sel.has(r.id)}
                        onChange={(e) => { const s = new Set(sel); if (e.target.checked) s.add(r.id); else s.delete(r.id); setSel(s); }} />
                    </td>
                    <td className="tabular px-3 font-bold text-ink-3">{r.rank}</td>
                    <td className="px-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{r.display_name}</span>
                        {r.persona && <span className="chip bg-sand text-white">persona</span>}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 whitespace-nowrap text-[11px] text-ink-3">{r.patient_code} <LangChip lang={r.language} /></div>
                    </td>
                    <td className="px-3">
                      <div className="font-medium">{resultLabel(r.test_code, r.value, r.value_text)}</div>
                      <div className="whitespace-nowrap text-[11px] text-ink-3">{PROGRAM_LABEL[r.program]} · {r.category}</div>
                    </td>
                    <td className="px-3"><SeverityBadge severity={r.severity} /></td>
                    <td className="px-3"><StateBadge state={r.state} understood={r.understood} /></td>
                    <td className="px-3">
                      <span className={clsx("tabular whitespace-nowrap text-xs font-bold", { bad: "text-bad", warn: "text-warn", ok: "text-ink-2" }[slaTone(r.sla_days_left)])}>
                        {r.sla_days_left < 0 ? `${Math.abs(r.sla_days_left).toFixed(0)} d over` : `${r.sla_days_left.toFixed(0)} d left`}
                      </span>
                    </td>
                    <td className="px-3"><Meter value={r.p_dropoff} tone="bad" label="Drop-off risk" /></td>
                    <td className="px-3"><Meter value={r.uplift} tone="teal" max={0.7} label="Uplift" /></td>
                    <td className="max-w-[240px] px-3 pr-5">
                      {r.top_reason ? <span className="chip max-w-full truncate whitespace-nowrap bg-indigo-soft text-indigo-ink" title={r.top_reason}>{r.top_reason}</span> : <span className="text-ink-3">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {d && d.total > d.size && (
          <div className="mt-4 flex items-center justify-between text-xs text-ink-2">
            <span>Page {d.page} of {Math.ceil(d.total / d.size)}</span>
            <div className="flex gap-2">
              <button className="btn-ghost !px-2 !py-1" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={14} /></button>
              <button className="btn-ghost !px-2 !py-1" disabled={page * d.size >= d.total} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={14} /></button>
            </div>
          </div>
        )}
        {d && policy === "uplift_fair" && (
          <div className="mt-5 rounded-xl border border-line p-4">
            <div className="label mb-2 flex items-center gap-2">Fairness floors (ε = 0.1) <Illustrative /></div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {Object.entries(d.allocation).map(([g, a]) => (
                <div key={g} className="rounded-lg bg-bg p-2 text-xs">
                  <div className="font-bold">{LANG_EN[g] ?? g}</div>
                  <div className="text-ink-2">need {pct(a.need_share)} · got {pct(a.budget_share)}</div>
                  <div className="text-ink-3">floor {a.floor ?? 0}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

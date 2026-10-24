import { useQuery } from "@tanstack/react-query";
import { Building2, Calculator, Coins, HeartPulse, Printer, Rocket, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { Card, EmptyState, ErrorState, Illustrative, LoadingBlock, PageHeader, Segmented } from "../components/ui";
import { aed, num, pct } from "../lib/format";

interface Roi {
  run_id: string; policy: string; policy_label: string; closure_baseline: number; closure_policy: number; extra_loops_per_1000: number;
  extra_loops_per_year: number; loops_closed_per_year: number; outreach_cost_per_year: number; extra_visit_cost_per_year: number;
  cost_per_closed_loop: number; outreach_cost_per_extra_loop: number | null; late_stage_avoided: { low: number; high: number };
  net_benefit: { low: number; high: number }; late_stage_risk_assumptions: Record<string, { low: number; high: number }>; label: string;
}

export default function RoiPage() {
  const [inputs, setInputs] = useState({ abnormal_per_year: 20000, cost_sms: 0.5, cost_call: 25, cost_visit: 150, late_stage_cost: 150000 });
  const [policy, setPolicy] = useState("wasl_uplift_fair");
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, String(v)])), policy }).toString();
  const r = useQuery({ queryKey: ["roi", qs], queryFn: () => get<Roi>(`/roi?${qs}`), retry: false });
  const d = r.data;

  return (
    <div>
      <PageHeader eyebrow="Impact & ROI" title="The payer case, with its assumptions on the table"
        subtitle="Driven by the latest Policy Twin run and scaled to your volume. Every rate is a range, every cost is editable."
        actions={<button className="btn-ghost no-print" onClick={() => window.print()}><Printer size={16} /> Download PDF</button>} />
      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        <Card title="Inputs" icon={<Calculator size={16} />} className="no-print h-fit">
          <div className="space-y-3">
            {([
              ["abnormal_per_year", "Abnormal results / year"], ["cost_sms", "SMS cost (AED)"], ["cost_call", "Tailored contact (AED)"],
              ["cost_visit", "Follow-up visit (AED)"], ["late_stage_cost", "Cost of a late-stage case (AED)"],
            ] as const).map(([k, l]) => (
              <label key={k} className="block text-xs font-semibold text-ink-2">{l}
                <input type="number" className="input mt-1" value={inputs[k]} onChange={(e) => setInputs({ ...inputs, [k]: +e.target.value })} />
              </label>
            ))}
            <div>
              <div className="label mb-1.5">Policy</div>
              <Segmented size="sm" value={policy} onChange={setPolicy} options={[{ value: "wasl_uplift", label: "WASL" }, { value: "wasl_uplift_fair", label: "WASL + fair" }, { value: "risk_ranked", label: "Risk" }]} />
            </div>
            <Illustrative>All values illustrative</Illustrative>
          </div>
        </Card>
        <div className="space-y-6" data-tour="roi">
          {r.isLoading ? <LoadingBlock rows={6} /> : r.error ? (
            (r.error as { status?: number }).status === 404 ? <EmptyState title="Run the Policy Twin first" hint="ROI is computed from the latest twin comparison." icon={<Rocket size={20} />} /> : <ErrorState error={r.error} />
          ) : d && (
            <>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  { l: "Extra loops closed / 1,000", v: `+${num(d.extra_loops_per_1000, 0)}`, s: `${pct(d.closure_baseline, 1)} → ${pct(d.closure_policy, 1)}`, i: <TrendingUp size={16} />, c: "bg-teal" },
                  { l: "Extra loops / year", v: `+${num(d.extra_loops_per_year)}`, s: `${num(d.loops_closed_per_year)} closed in total`, i: <HeartPulse size={16} />, c: "bg-indigo" },
                  { l: "Outreach cost / extra loop", v: aed(d.outreach_cost_per_extra_loop), s: `${aed(d.outreach_cost_per_year)} outreach / year`, i: <Coins size={16} />, c: "bg-sand" },
                  { l: "Late-stage cases avoided", v: `${num(d.late_stage_avoided.low, 0)}–${num(d.late_stage_avoided.high, 0)}`, s: "per year (range)", i: <Building2 size={16} />, c: "bg-ok" },
                ].map((k) => (
                  <div key={k.l} className="card relative overflow-hidden p-5">
                    <div className={`absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-20 blur-2xl ${k.c}`} />
                    <div className="flex items-start justify-between"><div className="label">{k.l}</div><div className={`grid h-8 w-8 place-items-center rounded-xl text-white ${k.c}`}>{k.i}</div></div>
                    <div className="tabular mt-3 text-[28px] font-extrabold leading-none">{k.v}</div>
                    <div className="mt-2 text-xs text-ink-2">{k.s}</div>
                  </div>
                ))}
              </div>
              <Card title="Net benefit (illustrative)" subtitle={`${d.policy_label} vs no outreach · late-stage cases avoided × cost − outreach − extra visits`}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl bg-gradient-to-br from-ok-soft to-card p-5">
                    <div className="label">Low assumptions</div>
                    <div className="tabular mt-1 text-3xl font-extrabold text-ok">{aed(d.net_benefit.low)}</div>
                  </div>
                  <div className="rounded-2xl bg-gradient-to-br from-teal-soft to-card p-5">
                    <div className="label">High assumptions</div>
                    <div className="tabular mt-1 text-3xl font-extrabold text-teal">{aed(d.net_benefit.high)}</div>
                  </div>
                </div>
                <div className="mt-4 text-sm text-ink-2">
                  Cost per closed loop (outreach + visit): <strong className="text-ink">{aed(d.cost_per_closed_loop)}</strong> · extra visit capacity needed: <strong className="text-ink">{aed(d.extra_visit_cost_per_year)}</strong>/year.
                </div>
              </Card>
              <Card title="Assumptions" subtitle="P(late-stage disease or complication | follow-up missed), per program">
                <table className="w-full text-sm">
                  <thead><tr className="text-left"><th className="label py-1">Program</th><th className="label py-1 text-right">Low</th><th className="label py-1 text-right">High</th></tr></thead>
                  <tbody>{Object.entries(d.late_stage_risk_assumptions).map(([p, v]) => (
                    <tr key={p} className="border-t border-line"><td className="py-1.5 font-semibold">{p}</td><td className="tabular text-right">{pct(v.low)}</td><td className="tabular text-right">{pct(v.high)}</td></tr>
                  ))}</tbody>
                </table>
                <p className="mt-3 text-xs text-ink-3">{d.label}. Twin run {d.run_id.slice(0, 8)} — <Link to="/twin" className="font-semibold text-teal">change the scenario</Link>.</p>
              </Card>
              <Card title="Pilot plan" icon={<Rocket size={16} />}>
                <ol className="grid gap-3 text-sm md:grid-cols-3">
                  {[["Weeks 0–4", "One clinic, diabetes program. FHIR feed from the HIE (e.g. Malaffi), clinician sign-off of templates and translations, ethics + DoH data approvals."],
                    ["Weeks 5–10", "Randomised rollout (stepped wedge) of uplift-ranked outreach vs usual care — this also re-trains the uplift model on real data."],
                    ["Weeks 11–13", "Evaluate loop closure, days to follow-up, fairness by language, cost per closed loop. Go / no-go for program 2."]].map(([w, t]) => (
                    <li key={w} className="rounded-xl border border-line p-3"><div className="font-bold text-teal">{w}</div><div className="mt-1 text-ink-2">{t}</div></li>
                  ))}
                </ol>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

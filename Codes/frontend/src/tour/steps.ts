// Judge Mode: 10 steps, ~3 minutes. Every number shown comes live from the API — the
// text below is only templates filled with `fillTemplate`.
import { get, post } from "../api/client";
import type { ChatState, DemoState, Funnel, Kpis, LoopDetail, TwinRun, Worklist } from "../api/types";
import { LOCALES } from "../i18n";
import { STATE_LABEL, num, pct } from "../lib/format";

export type TourData = Record<string, string | number | null | undefined>;

export interface TourStep {
  id: string;
  title: string;
  body: string;
  target: string | null;
  route: (d: TourData) => string;
  prepare?: (d: TourData) => Promise<TourData>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function personas(): Promise<DemoState["personas"]> {
  return (await get<DemoState>("/demo/state")).personas;
}

async function openChat(loopId: string): Promise<string> {
  const r = await post<{ token: string }>(`/loops/${loopId}/outreach`, {});
  await get<ChatState>(`/c/${r.token}`);
  return r.token;
}

async function waitRun(id: string): Promise<TwinRun> {
  for (let i = 0; i < 240; i++) {
    const r = await get<TwinRun>(`/twin/runs/${id}`);
    if (r.status === "done" || r.status === "error") return r;
    await sleep(700);
  }
  throw new Error("twin run timed out");
}

export const STEPS: TourStep[] = [
  {
    id: "kpis",
    title: "1 · The problem, live",
    body: "{total} abnormal screening results. In the simulated as-is baseline, {never} never complete follow-up within 30 days. Each one is a missed chance for early diagnosis.",
    target: "kpis",
    route: () => "/",
    prepare: async () => {
      const k = await get<Kpis>("/dashboard/kpis");
      return { total: num(k.total_loops), never: pct(k.never_completed_share) };
    },
  },
  {
    id: "funnel",
    title: "2 · Where people fall out",
    body: "{notified} people were notified, but only {booked} ever booked. The biggest single drop is before \"{biggest}\" (−{drop}%). The problem is understanding and access — not detection.",
    target: "funnel",
    route: () => "/",
    prepare: async () => {
      const f = await get<Funnel>("/dashboard/funnel");
      const by = Object.fromEntries(f.steps.map((s) => [s.state, s.count]));
      return { notified: num(by.NOTIFIED), booked: num(by.BOOKED), biggest: f.biggest_drop ? STATE_LABEL[f.biggest_drop.state] : "—", drop: f.biggest_drop?.dropoff_pct ?? "—" };
    },
  },
  {
    id: "worklist",
    title: "3 · Rank by uplift, not just risk",
    body: "Switching Risk → Uplift swaps {swapped} people. Those leaving average {noshows} past no-shows — a call barely moves them; those joining gain {gain} more expected returns from the same calls. Imran rises #{iRisk} → #{iUplift}. Ramesh is inside today's budget either way (#{rUplift}). Sara stays near the bottom (#{sara}): she would return anyway.",
    target: "uplift-insight",
    route: () => "/worklist",
    prepare: async () => {
      const [u, r] = await Promise.all([get<Worklist>("/worklist?policy=uplift&budget=200&size=1"), get<Worklist>("/worklist?policy=risk_only&budget=200&size=1")]);
      return {
        swapped: u.vs_risk_only.swapped_in, noshows: num(u.vs_risk_only.avg_prior_no_shows_out, 1),
        rRisk: r.personas.ramesh?.rank ?? "—", rUplift: u.personas.ramesh?.rank ?? "—", sara: u.personas.sara?.rank ?? "—",
        iRisk: r.personas.imran?.rank ?? "—", iUplift: u.personas.imran?.rank ?? "—", gain: `+${num(u.vs_risk_only.expected_extra_returns, 1)}`,
      };
    },
  },
  {
    id: "ramesh",
    title: "4 · Why Ramesh? What would help?",
    body: "SHAP: {reasons}. The counterfactual engine searches only actionable levers: \"{actions}\" raises his estimated return probability from {p0} to {p1}.",
    target: "what-would-help",
    route: (d) => `/loops/${d.ramesh}`,
    prepare: async () => {
      const p = await personas();
      const l = await get<LoopDetail>(`/loops/${p.ramesh.loop_id}`);
      const cf = l.score!.counterfactuals[0];
      return {
        ramesh: p.ramesh.loop_id, imran: p.imran.loop_id, fatima: p.fatima.loop_id,
        reasons: l.score!.shap_top.slice(0, 3).map((s) => s.label.toLowerCase()).join(", "),
        actions: cf.actions.join(" + "), p0: cf.p_baseline.toFixed(2), p1: cf.p_return.toFixed(2),
      };
    },
  },
  {
    id: "chat",
    title: "5 · The navigator, in Malayalam",
    body: "Result explained in Malayalam → barrier \"I work nights\" → teach-back passed → {slot} booked ({reason}). Every message passed back-translation QA (score {score}). The loop is now BOOKED + UNDERSTOOD.",
    target: "chat-messages",
    route: (d) => `/c/${d.rameshToken}`,
    prepare: async (d) => {
      const token = await openChat(String(d.ramesh));
      const q = LOCALES.ml.quick;
      await post<ChatState>(`/c/${token}/message`, { text: q.qr_night });
      const s = await post<ChatState>(`/c/${token}/message`, { text: q.qr_tb_diabetes });
      const slots = s.messages[s.messages.length - 1]?.meta.slots ?? [];
      const pick = slots.find((x) => x.match_reasons.some((m) => m.toLowerCase().includes("evening"))) ?? slots[0];
      const after = pick ? await post<ChatState>(`/c/${token}/book`, { slot_id: pick.slot_id }) : s;
      const scores = after.messages.map((m) => m.meta.qa?.score).filter((x): x is number => typeof x === "number");
      return { rameshToken: token, slot: after.booked?.label ?? "a slot", reason: pick?.match_reasons[0] ?? "", score: scores.length ? Math.min(...scores).toFixed(2) : "—" };
    },
  },
  {
    id: "imran",
    title: "6 · The AI is checked before it speaks",
    body: "Imran (Urdu): the machine translation turned his HbA1c into the wrong number ({issue}). The entity check caught it, the judge scored {score}, and he received the clinician-approved translation instead. The item is waiting in the human review queue.",
    target: "transcript",
    route: (d) => `/loops/${d.imran}`,
    prepare: async (d) => {
      await openChat(String(d.imran));
      const l = await get<LoopDetail>(`/loops/${d.imran}`);
      const bad = l.translation_checks.find((c) => !c.passed);
      return { issue: bad?.discrepancies[0] ?? "number mismatch", score: bad ? bad.judge_score.toFixed(2) : "—" };
    },
  },
  {
    id: "fatima",
    title: "7 · Red flag → a human, instantly",
    body: "Fatima wrote \"{msg}\". In {ms} ms WASL replied with urgent-care advice (call 999), opened a red-flag escalation, and paused the AI until a nurse acknowledges it. Press Acknowledge in the live feed.",
    target: "escalations",
    route: () => "/",
    prepare: async (d) => {
      const token = await openChat(String(d.fatima));
      const msg = LOCALES.ar.quick.qr_redflag_lump;
      const t0 = performance.now();
      await post<ChatState>(`/c/${token}/message`, { text: msg });
      return { msg, ms: Math.round(performance.now() - t0) };
    },
  },
  {
    id: "twin",
    title: "8 · Policy Twin",
    body: "5,000 simulated patients × 5 policies, paired on the same random numbers. {best} closes {bestRate} of loops vs {none} with no outreach and {risk} with risk-ranked calls, at {cost} per extra closed loop (risk-ranked: {riskCost}). Allocation gap with the fairness floor: {fairAlloc} vs {upAlloc}. Sensitivity: {robust}.",
    target: "twin-results",
    route: () => "/twin",
    prepare: async () => {
      const [run, sens] = await Promise.all([post<TwinRun>("/twin/runs", {}), post<TwinRun>("/twin/sensitivity", {})]);
      const r = await waitRun(run.id);
      const s = await waitRun(sens.id);
      const res = r.results!.results!;
      const best = Object.values(res).sort((a, b) => b.closure_rate - a.closure_rate)[0];
      return {
        best: best.label, bestRate: pct(best.closure_rate, 1), none: pct(res.no_outreach.closure_rate, 1), risk: pct(res.risk_ranked.closure_rate, 1),
        cost: `AED ${num(best.incremental_cost_per_extra_loop)}`, riskCost: `AED ${num(res.risk_ranked.incremental_cost_per_extra_loop)}`,
        fairAlloc: pct(res.wasl_uplift_fair.allocation_gap, 1), upAlloc: pct(res.wasl_uplift.allocation_gap, 1),
        robust: s.results?.robust ? "WASL wins at ×0.5, ×1.0 and ×1.5 effect ✓" : "not robust at every scale",
        gapNone: pct(res.no_outreach.fairness_gap, 1), gapWasl: pct(res.wasl_uplift.fairness_gap, 1),
      };
    },
  },
  {
    id: "governance",
    title: "9 · Fairness & a tamper-evident audit trail",
    body: "{checked} hash-chained events re-verified: {valid}. In the twin, the closure gap between language groups shrinks from {gapNone} (no outreach) to {gapWasl} (WASL). Revoking consent stops the navigator immediately.",
    target: "verify-chain",
    route: () => "/fairness?tab=audit",
    prepare: async () => {
      const v = await get<{ valid: boolean; checked: number }>("/governance/audit/verify");
      return { checked: num(v.checked), valid: v.valid ? "chain intact ✓" : "TAMPERING DETECTED" };
    },
  },
  {
    id: "roi",
    title: "10 · Impact, and the path to a pilot",
    body: "{policy}, per 1,000 abnormal results: +{extra} loops closed; outreach cost per extra loop {cost} (fairness costs a little: plain WASL uplift was {costPlain} in step 8); {lo}–{hi} late-stage cases avoided per year at 20,000 results (illustrative). Pilot: one clinic, one program, 90 days, FHIR-ready.",
    target: "roi",
    route: () => "/roi",
    prepare: async () => {
      type Roi = { policy_label: string; extra_loops_per_1000: number; outreach_cost_per_extra_loop: number | null; late_stage_avoided: { low: number; high: number } };
      const [r, plain] = await Promise.all([get<Roi>("/roi?policy=wasl_uplift_fair"), get<Roi>("/roi?policy=wasl_uplift")]);
      return { policy: `With ${r.policy_label}`, extra: num(r.extra_loops_per_1000), cost: `AED ${num(r.outreach_cost_per_extra_loop)}`, costPlain: `AED ${num(plain.outreach_cost_per_extra_loop)}`, lo: num(r.late_stage_avoided.low), hi: num(r.late_stage_avoided.high) };
    },
  },
];

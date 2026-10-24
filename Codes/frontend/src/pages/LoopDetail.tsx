import clsx from "clsx";
import {
  ArrowLeft, BrainCircuit, CalendarCheck, ExternalLink, HeartHandshake, MessagesSquare, QrCode, Send, ShieldCheck, Sparkles, UserCheck, Workflow,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { post } from "../api/client";
import { useInvalidate, useLoop, usePatientTwin } from "../api/hooks";
import type { TranslationCheck } from "../api/types";
import { CheckDetail, PatientTwinChart, Timeline, Transcript, WhatWouldHelp, WhyBars } from "../components/loop";
import { Card, Chip, EmptyState, ErrorState, LangChip, LoadingBlock, Modal, SeverityBadge, Spinner, StateBadge } from "../components/ui";
import { PROGRAM_LABEL, STATE_LABEL, pct, resultLabel } from "../lib/format";
import { useAuth } from "../store/auth";

const STEPS = ["RESULT_RECEIVED", "NOTIFIED", "ENGAGED", "UNDERSTOOD", "BOOKED", "ATTENDED", "CLOSED"];

export default function LoopDetail() {
  const { id } = useParams();
  const q = useLoop(id);
  const user = useAuth((s) => s.user);
  const twin = usePatientTwin(id, !!q.data?.can_view_twin);
  const inv = useInvalidate();
  const [outreach, setOutreach] = useState<{ link: string; token: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [check, setCheck] = useState<TranslationCheck | null>(null);

  if (q.isLoading) return <LoadingBlock rows={10} />;
  if (q.error) return <ErrorState error={q.error} retry={() => void q.refetch()} />;
  const d = q.data!;
  const L = d.loop;
  const p = d.patient;
  const reached = new Set(d.timeline.map((e) => e.to_state));
  const currentIdx = STEPS.indexOf(L.state);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      inv("loop", "worklist", "kpis", "feed", "escalations");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const startOutreach = () =>
    act("outreach", async () => {
      const r = await post<{ link: string; token: string }>(`/loops/${L.id}/outreach`, {});
      const local = `${window.location.origin}/c/${r.token}`;
      setOutreach({ link: local, token: r.token });
    });

  return (
    <div>
      <Link to="/worklist" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-ink-2 hover:text-ink">
        <ArrowLeft size={14} /> Worklist
      </Link>

      <div className="card relative mb-6 overflow-hidden p-6">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-teal/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-extrabold tracking-tight">{d.identity.display_name}</h1>
              {p.persona && <Chip tone="sand">demo persona · {p.persona}</Chip>}
              <LangChip lang={p.language} />
              <StateBadge state={L.state} understood={L.understood} />
              {L.navigator_paused && <Chip tone="bad">AI paused — awaiting nurse</Chip>}
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
              <span>{p.code}</span>
              <span>{p.age} y · {p.sex}</span>
              <span className="font-semibold text-ink">{resultLabel(L.test_code, L.value, L.value_text)}</span>
              <span>{PROGRAM_LABEL[L.program]} · {L.category}</span>
              <SeverityBadge severity={L.severity} />
              <span className={clsx("font-semibold", L.sla_days_left < 0 ? "text-bad" : "text-ink-2")}>
                SLA {L.sla_days_left < 0 ? `${Math.abs(L.sla_days_left).toFixed(0)} d overdue` : `${L.sla_days_left.toFixed(0)} d left`}
              </span>
            </div>
            <div className="mt-1 text-xs text-ink-3">
              PII view: {d.identity.pii_level}
              {d.identity.phone ? ` · ${d.identity.phone}` : ""}
              {d.identity.emirates_id ? ` · EID ${d.identity.emirates_id}` : ""}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {["RESULT_RECEIVED", "NOTIFIED", "BREACHED", "UNREACHABLE", "NO_SHOW", "ENGAGED"].includes(L.state) && (
              <button className="btn-primary" onClick={() => void startOutreach()} disabled={busy === "outreach"} data-tour="start-outreach">
                {busy === "outreach" ? <Spinner /> : <Send size={15} />} Start outreach
              </button>
            )}
            {d.conversations.length > 0 && !outreach && (
              <span className="chip self-center bg-info-soft text-info"><MessagesSquare size={12} /> conversation active ({d.conversations[0].language})</span>
            )}
            {user?.role !== "navigator" && (
              <button className="btn-ghost" onClick={() => void act("assign", () => post(`/loops/${L.id}/assign`, {}))}>
                <UserCheck size={15} /> Assign to me
              </button>
            )}
            <select className="input !w-auto" value="" aria-label="Transition"
              onChange={(e) => {
                const to = e.target.value;
                if (!to) return;
                const reason = to === "DECLINED" ? "Informed refusal: risk explained by staff in patient's language" : `Set by ${user?.display_name}`;
                void act("t", () => post(`/loops/${L.id}/transition`, { to_state: to, reason }));
              }}>
              <option value="">Move to…</option>
              {d.allowed_transitions.map((s) => <option key={s} value={s}>{STATE_LABEL[s]}</option>)}
            </select>
          </div>
        </div>
        {err && <div className="relative mt-3 rounded-xl bg-bad-soft px-3 py-2 text-sm text-bad">{err}</div>}

        <ol className="relative mt-6 grid grid-cols-7 gap-1" aria-label="Loop progress">
          {STEPS.map((s, i) => {
            const done = reached.has(s) || (currentIdx >= 0 && i <= currentIdx);
            return (
              <li key={s} className="flex flex-col items-center gap-1.5 text-center">
                <div className={clsx("h-1.5 w-full rounded-full", done ? "bg-gradient-to-r from-teal to-indigo" : "bg-line")} />
                <span className={clsx("text-[10px] font-semibold sm:text-[11px]", done ? "text-ink" : "text-ink-3")}>{STATE_LABEL[s]}</span>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <div className="space-y-6">
          {d.score ? (
            <>
              <Card title="Why this patient?" subtitle={`Drop-off risk ${pct(d.score.p_dropoff)} · model ${d.score.model_version}`} icon={<BrainCircuit size={16} />} tour="why-card">
                <WhyBars items={d.score.shap_top} />
              </Card>
              <Card title="What would help" subtitle="Counterfactuals over actionable levers only — channel, language, slot type, cost info" icon={<Sparkles size={16} />} tour="what-would-help">
                <WhatWouldHelp items={d.score.counterfactuals} />
              </Card>
            </>
          ) : (
            <Card title="Scores"><EmptyState title="Not scored" hint="Closed loops are not re-scored." /></Card>
          )}
          <Card title="Conversation" subtitle="Every outgoing message: approved template → PII firewall → LLM → back-translation QA" icon={<MessagesSquare size={16} />} tour="transcript">
            <Transcript messages={d.messages} lang={p.language} onCheck={(cid) => setCheck(d.translation_checks.find((c) => c.id === cid) ?? null)} />
            {d.teach_back.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {d.teach_back.map((t, i) => (
                  <Chip key={t.id} tone={t.passed ? "ok" : "warn"}>Teach-back #{i + 1}: {t.passed ? "passed" : "not yet"} — {t.feedback}</Chip>
                ))}
              </div>
            )}
          </Card>
          {d.can_view_twin && (
            <Card title="Patient twin" subtitle="Markov progression if follow-up is delayed · clinician/coordinator only" icon={<Workflow size={16} />} tour="patient-twin">
              {twin.data ? <PatientTwinChart twin={twin.data} /> : twin.error ? <ErrorState error={twin.error} /> : <LoadingBlock rows={4} />}
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card title="Profile" subtitle="Pseudonymous — identity lives in a separate table" icon={<HeartHandshake size={16} />}>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {[
                ["Language", p.language_name], ["Literacy", `${p.literacy_level} / 3`], ["Occupation", p.occupation_type],
                ["Shift", p.shift_pattern], ["Free days", p.preferred_days.join(", ")], ["Home", `${p.home_area} · ${p.distance_km} km`],
                ["Insurance", p.insurance_tier], ["Prior no-shows", String(p.prior_no_shows)], ["Channel", p.preferred_channel],
                ["Nationality group", p.nationality_group],
              ].map(([k, v]) => (
                <div key={k}><dt className="label">{k}</dt><dd className="mt-0.5 font-medium capitalize">{v}</dd></div>
              ))}
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(d.consents).map(([scope, c]) => (
                <button key={scope} className={clsx("chip", c.granted ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad")} title="Click to toggle consent"
                  onClick={() => void act("consent", () => post(`/consents/${L.patient_id}`, { scope, granted: !c.granted }))}>
                  <ShieldCheck size={11} /> {scope.replace(/_/g, " ")}: {c.granted ? "granted" : "revoked"}
                </button>
              ))}
            </div>
          </Card>

          {d.appointments.length > 0 && (
            <Card title="Appointment" icon={<CalendarCheck size={16} />}>
              {d.appointments.map((a) => (
                <div key={a.id} className="rounded-xl border border-teal/40 bg-teal-soft/40 p-3">
                  <div className="font-bold">{a.slot_label} · {a.clinic_name}</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">{a.match_reasons.map((r) => <Chip key={r} tone="teal">{r}</Chip>)}</div>
                  <div className="mt-1 text-xs capitalize text-ink-2">status: {a.status}</div>
                </div>
              ))}
            </Card>
          )}

          {d.slots.length > 0 && (
            <Card title="Smart slots" subtitle="Matched to shift, preferred day, distance and clinician language" icon={<CalendarCheck size={16} />} tour="smart-slots">
              <div className="space-y-2.5">
                {d.slots.map((s) => (
                  <div key={s.slot_id} className="rounded-xl border border-line p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="font-bold">{s.local_label}</div>
                        <div className="text-xs text-ink-2">{s.clinic_name}</div>
                      </div>
                      <button className="btn-ghost !py-1 text-xs" disabled={!!busy} onClick={() => void act("book", () => post(`/loops/${L.id}/book`, { slot_id: s.slot_id }))}>
                        Book
                      </button>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">{s.match_reasons.map((r) => <Chip key={r} tone="teal">{r}</Chip>)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {d.escalations.length > 0 && (
            <Card title="Escalations">
              <ul className="space-y-2">
                {d.escalations.map((e) => (
                  <li key={e.id} className="flex items-center justify-between gap-2 rounded-xl bg-bg p-2.5 text-sm">
                    <div>
                      <div className="font-semibold capitalize">{e.reason.replace("_", " ")}</div>
                      <div className="text-xs text-ink-2">{e.notes}</div>
                    </div>
                    {e.status === "open" ? (
                      <button className="btn-ghost !py-1 text-xs" onClick={() => void act("ack", () => post(`/escalations/${e.id}/ack`, { notes: `Acknowledged by ${user?.display_name}` }))}>Acknowledge</button>
                    ) : <Chip tone="ok">{e.status}</Chip>}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card title="Audit trail" subtitle="SHA-256 hash chain — tamper-evident" icon={<ShieldCheck size={16} />} tour="timeline">
            <Timeline events={d.timeline} valid={d.chain.valid} />
          </Card>
        </div>
      </div>

      <Modal open={!!outreach} onClose={() => setOutreach(null)} title="Secure link sent">
        {outreach && (
          <div className="text-center">
            <p className="text-sm text-ink-2">The patient receives a one-tap magic link (hashed in the database, expires in 14 days). Scan it on a phone, or open it here.</p>
            <div className="mx-auto mt-4 w-fit rounded-2xl bg-white p-4 shadow-soft">
              <QRCodeSVG value={outreach.link} size={180} fgColor="#0b1324" />
            </div>
            <div className="mt-3 break-all rounded-xl bg-bg p-2 font-mono text-[11px] text-ink-2"><QrCode size={11} className="mr-1 inline" />{outreach.link}</div>
            <a href={`/c/${outreach.token}`} target="_blank" rel="noreferrer" className="btn-primary mt-4" data-tour="open-patient-view">
              <ExternalLink size={15} /> Open patient view
            </a>
          </div>
        )}
      </Modal>
      <Modal open={!!check} onClose={() => setCheck(null)} title="Translation QA — back-translation verification" wide>
        {check && <CheckDetail c={check} />}
      </Modal>
    </div>
  );
}

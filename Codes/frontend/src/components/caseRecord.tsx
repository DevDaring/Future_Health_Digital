import clsx from "clsx";
import {
  BadgeCheck, CalendarCheck, CheckCircle2, ClipboardCheck, FileText, Hand, Link2, MessageCircleQuestion, Siren, TimerOff, UserCheck, UserX, XCircle,
} from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { post } from "../api/client";
import { useStaff } from "../api/hooks";
import type { CaseRecordEntry, Closure, LoopDetail } from "../api/types";
import { relTime } from "../lib/format";
import { Chip, Spinner } from "./ui";

const KIND: Record<string, { icon: ReactNode; tone: string }> = {
  result: { icon: <FileText size={14} />, tone: "bg-indigo-soft text-indigo-ink" },
  owner: { icon: <UserCheck size={14} />, tone: "bg-bg text-ink-2" },
  barrier: { icon: <MessageCircleQuestion size={14} />, tone: "bg-sand-soft text-sand-ink" },
  teach_back: { icon: <BadgeCheck size={14} />, tone: "bg-teal-soft text-teal-ink" },
  booked: { icon: <CalendarCheck size={14} />, tone: "bg-teal-soft text-teal-ink" },
  red_flag: { icon: <Siren size={14} />, tone: "bg-bad text-white" },
  urgent: { icon: <Siren size={14} />, tone: "bg-bad-soft text-bad" },
  escalation: { icon: <Siren size={14} />, tone: "bg-bad-soft text-bad" },
  ack: { icon: <Hand size={14} />, tone: "bg-ok-soft text-ok" },
  human: { icon: <Hand size={14} />, tone: "bg-info-soft text-info" },
  declined: { icon: <XCircle size={14} />, tone: "bg-line text-ink-2" },
  attended: { icon: <CheckCircle2 size={14} />, tone: "bg-ok-soft text-ok" },
  no_show: { icon: <UserX size={14} />, tone: "bg-warn-soft text-warn" },
  breach: { icon: <TimerOff size={14} />, tone: "bg-warn-soft text-warn" },
  closed: { icon: <ClipboardCheck size={14} />, tone: "bg-ok text-white" },
};

const SOURCE: Record<CaseRecordEntry["source"], { label: string; tone: "teal" | "neutral" | "indigo" }> = {
  patient_chat: { label: "from patient chat", tone: "teal" },
  staff: { label: "staff", tone: "indigo" },
  system: { label: "system", tone: "neutral" },
};

export function CaseRecord({ items }: { items: CaseRecordEntry[] }) {
  return (
    <ol className="relative space-y-3 border-l border-line pl-5">
      {items.map((c) => (
        <li key={`${c.seq}-${c.kind}`} className="relative">
          <span className={clsx("absolute -left-[31px] top-0 grid h-6 w-6 place-items-center rounded-full ring-4 ring-card", KIND[c.kind]?.tone ?? "bg-bg text-ink-2")}>
            {KIND[c.kind]?.icon ?? <FileText size={14} />}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold">{c.label}</span>
            <Chip tone={SOURCE[c.source].tone}>{SOURCE[c.source].label}</Chip>
            <span className="ml-auto text-[11px] text-ink-3">{relTime(c.at)}</span>
          </div>
          {c.detail && <div className="mt-0.5 text-xs text-ink-2">{c.detail}</div>}
          <div className="mt-0.5 flex items-center gap-1 font-mono text-[10px] text-ink-3"><Link2 size={9} /> audit #{c.seq} · {c.hash}</div>
        </li>
      ))}
    </ol>
  );
}

export function OwnerPanel({ d, onChanged }: { d: LoopDetail; onChanged: () => void }) {
  const staff = useStaff();
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const owner = d.loop.owner;
  async function save() {
    if (!to) return;
    setBusy(true);
    setErr(null);
    try {
      await post(`/loops/${d.loop.id}/assign`, { user_id: to, note });
      setTo("");
      setNote("");
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-full bg-teal-soft text-sm font-extrabold text-teal-ink">
          {owner ? owner.name.split(" ").filter((w) => !w.endsWith(".")).map((w) => w[0]).slice(0, 2).join("") : "?"}
        </div>
        <div>
          <div className="font-bold">{owner ? owner.name : "No owner"}</div>
          <div className="text-xs text-ink-2">{owner ? <><span className="capitalize">{owner.role}</span> · accountable until the loop is closed</> : "assign someone now"}</div>
        </div>
      </div>
      <div className="mt-3 rounded-xl bg-bg p-3 text-sm">
        <div className="label">Next action</div>
        <div className="mt-0.5 font-semibold">{d.next_action}</div>
      </div>
      {!["CLOSED", "DECLINED"].includes(d.loop.state) && <div className="mt-3 flex flex-wrap gap-2">
        <select className="input !w-auto flex-1" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Change owner">
          <option value="">Change owner…</option>
          {staff.data?.items.filter((u) => u.id !== owner?.id).map((u) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
        </select>
        {to && <input className="input !w-auto flex-1" placeholder="Reason (optional)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />}
        {to && <button className="btn-primary !py-1.5" disabled={busy} onClick={() => void save()}>{busy ? <Spinner /> : "Hand over"}</button>}
      </div>}
      {err && <div className="mt-2 text-xs text-bad">{err}</div>}
    </div>
  );
}

function localDate(d: Date) {
  const tz = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - tz).toISOString().slice(0, 10);
}

export function ClosureForm({ d, onDone }: { d: LoopDetail; onDone: () => void }) {
  const appt = d.appointments.find((a) => a.status !== "no_show");
  const visited = d.loop.state === "ATTENDED" || d.loop.state === "BOOKED";
  const [f, setF] = useState({
    outcome: visited ? "referral_completed" : "seen_elsewhere",
    seen_by: appt?.clinic_name ?? "",
    visit_date: localDate(appt && new Date(appt.start_at) < new Date() ? new Date(appt.start_at) : new Date()),
    summary: "",
    next_step: "",
    report_shared_with: d.screening_facility ?? "",
    patient_informed: false,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const today = localDate(new Date());
    const visit = f.visit_date === today ? new Date(Date.now() - 60_000).toISOString() : `${f.visit_date}T12:00:00+04:00`;
    try {
      await post(`/loops/${d.loop.id}/close`, { ...f, visit_date: visit });
      onDone();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : String(e2));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3 text-sm">
      {!visited && (
        <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn">
          No visit is on record yet. You can close only if the patient was seen at another provider and you have the outcome.
        </p>
      )}
      <label className="block"><span className="label">Outcome</span>
        <select className="input mt-1" value={f.outcome} onChange={(e) => set("outcome", e.target.value)}>
          {Object.entries(d.closure_outcomes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block"><span className="label">Seen by (provider)</span>
          <input className="input mt-1" required minLength={2} value={f.seen_by} onChange={(e) => set("seen_by", e.target.value)} placeholder="Clinic or doctor" />
        </label>
        <label className="block"><span className="label">Visit date</span>
          <input className="input mt-1" type="date" required value={f.visit_date} max={localDate(new Date())} onChange={(e) => set("visit_date", e.target.value)} />
        </label>
      </div>
      <label className="block"><span className="label">What happened</span>
        <textarea className="input mt-1 min-h-[70px]" required minLength={10} value={f.summary} onChange={(e) => set("summary", e.target.value)}
          placeholder="e.g. Repeat HbA1c 7.6%; diagnosed type 2 diabetes; started metformin and diet plan" />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block"><span className="label">Next step</span>
          <input className="input mt-1" value={f.next_step} onChange={(e) => set("next_step", e.target.value)} placeholder="e.g. Diabetes clinic review in 3 months" />
        </label>
        <label className="block"><span className="label">Report sent to</span>
          <input className="input mt-1" required minLength={2} value={f.report_shared_with} onChange={(e) => set("report_shared_with", e.target.value)} placeholder="Screening provider / family doctor" />
        </label>
      </div>
      <label className="flex items-start gap-2 rounded-xl border border-line p-3">
        <input type="checkbox" className="mt-0.5" checked={f.patient_informed} onChange={(e) => set("patient_informed", e.target.checked)} />
        <span><strong>The patient has been told the outcome</strong> and knows the next step. Required to close.</span>
      </label>
      {err && <div className="rounded-xl bg-bad-soft px-3 py-2 text-xs text-bad">{err}</div>}
      <button className="btn-primary w-full justify-center" type="submit" disabled={busy || !f.patient_informed} data-tour="close-submit">
        {busy ? <Spinner /> : <ClipboardCheck size={15} />} Close the loop with this outcome
      </button>
    </form>
  );
}

export function ClosureView({ c }: { c: Closure }) {
  const rows: [string, ReactNode][] = [
    ["Outcome", c.outcome_label], ["Seen by", c.seen_by], ["Visit", c.visit_date ? new Date(c.visit_date).toLocaleDateString("en-GB") : "—"],
    ["What happened", c.summary], ["Next step", c.next_step || "—"], ["Report sent to", c.report_shared_with],
    ["Patient informed", c.patient_informed ? "Yes" : "No"], ["Closed by", `${c.closed_by_name} · ${new Date(c.closed_at).toLocaleDateString("en-GB")}`],
  ];
  return (
    <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents"><dt className="label pt-0.5">{k}</dt><dd className="font-medium">{v}</dd></div>
      ))}
    </dl>
  );
}

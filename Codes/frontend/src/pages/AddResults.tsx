import clsx from "clsx";
import { AlertTriangle, CheckCircle2, CircleSlash, Download, FilePlus2, FileUp, Info, LayoutDashboard, Siren, TimerOff, Upload, UserRound } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { download, get, post } from "../api/client";
import { useIntakeRecent, useInvalidate, useKpis } from "../api/hooks";
import type { IntakeResult } from "../api/types";
import { Card, Chip, EmptyState, ErrorState, LangChip, LoadingBlock, PageHeader, SeverityBadge, Spinner, StateBadge } from "../components/ui";
import { LANG_EN, PROGRAM_LABEL, num, relTime, resultLabel } from "../lib/format";

type Test = "HbA1c" | "FIT" | "Mammogram";

const PRESETS: { label: string; test: Test; value: string; name: string; language: string; sex: "M" | "F"; age: number; shift: string }[] = [
  { label: "Urgent HbA1c 10.4%", test: "HbA1c", value: "10.4", name: "Sanjay Pillai", language: "ml", sex: "M", age: 52, shift: "night" },
  { label: "Positive stool test", test: "FIT", value: "positive", name: "Maria Reyes", language: "tl", sex: "F", age: 56, shift: "day" },
  { label: "Mammogram BI-RADS 4", test: "Mammogram", value: "BI-RADS 4", name: "Noura Al Ameri", language: "ar", sex: "F", age: 48, shift: "day" },
  { label: "Normal HbA1c 5.3%", test: "HbA1c", value: "5.3", name: "Ali Khan", language: "ur", sex: "M", age: 41, shift: "rotating" },
];

const FLAG: Record<string, { label: string; tone: "bad" | "warn"; icon: JSX.Element }> = {
  urgent_result: { label: "Urgent: clinician flag", tone: "bad", icon: <Siren size={11} /> },
  red_flag: { label: "Red flag", tone: "bad", icon: <Siren size={11} /> },
  sla_breach: { label: "SLA already passed", tone: "warn", icon: <TimerOff size={11} /> },
};

function OutcomeList({ items }: { items: IntakeResult[] }) {
  return (
    <ul className="space-y-2">
      {items.map((r, i) => (
        <li key={`${r.row}-${i}`} className={clsx("flex flex-wrap items-center gap-3 rounded-xl border p-3 text-sm",
          r.status === "loop_created" ? "border-teal/40 bg-teal-soft/30" : r.status === "normal" ? "border-line bg-bg" : "border-bad/30 bg-bad-soft/40")}>
          {r.status === "loop_created" ? <CheckCircle2 size={16} className="text-teal" /> : r.status === "normal" ? <CircleSlash size={16} className="text-ink-3" /> : <AlertTriangle size={16} className="text-bad" />}
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{r.name ?? `Row ${r.row}`} {r.result && <span className="font-normal text-ink-2">· {r.result}</span>}</div>
            <div className="text-xs text-ink-2">{r.message}{r.owner ? ` · owner: ${r.owner}` : ""}</div>
          </div>
          {(r.flags ?? []).map((f) => <Chip key={f} tone={FLAG[f]?.tone ?? "warn"} icon={FLAG[f]?.icon}>{FLAG[f]?.label ?? f}</Chip>)}
          {r.loop_id && <Link to={`/loops/${r.loop_id}`} className="text-xs font-bold text-teal hover:underline">Open case →</Link>}
        </li>
      ))}
    </ul>
  );
}

export default function AddResults() {
  const inv = useInvalidate();
  const recent = useIntakeRecent();
  const k = useKpis("added");
  const fileRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({ name: "", test: "HbA1c" as Test, value: "7.8", language: "ml", sex: "M", age: 47, result_date: "", facility: "Mussafah Mobile Screening Van", shift: "night" });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [last, setLast] = useState<{ title: string; items: IntakeResult[] } | null>(null);
  const set = <K extends keyof typeof form>(key: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: v }));

  async function run(key: string, title: string, fn: () => Promise<{ results: IntakeResult[] }>) {
    setBusy(key);
    setErr(null);
    try {
      const r = await fn();
      setLast({ title, items: r.results });
      inv("intake-recent", "kpis", "funnel", "breaches", "escalations", "feed", "worklist");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const row = { ...form, name: form.name.trim() || "Reviewer Patient", age: Number(form.age), result_date: form.result_date || null };
    void run("one", "Result added", () => post("/intake/results", { results: [row] }));
  };
  const uploadText = (csv: string, title: string) => run("csv", title, () => post("/intake/csv", { csv }));
  const onFile = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 200_000) return setErr("The file is larger than 200 KB (at most 200 rows)");
    await uploadText(await f.text(), `Uploaded ${f.name}`);
    if (fileRef.current) fileRef.current.value = "";
  };

  const valueInput =
    form.test === "FIT" ? (
      <select className="input" value={form.value} onChange={(e) => set("value", e.target.value)} aria-label="FIT result">
        <option value="positive">Positive</option>
        <option value="negative">Negative</option>
      </select>
    ) : form.test === "Mammogram" ? (
      <select className="input" value={form.value} onChange={(e) => set("value", e.target.value)} aria-label="BI-RADS category">
        {[0, 1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={`BI-RADS ${n}`}>BI-RADS {n}</option>)}
      </select>
    ) : (
      <input className="input" inputMode="decimal" value={form.value} onChange={(e) => set("value", e.target.value)} aria-label="HbA1c percent" placeholder="e.g. 7.8" />
    );

  const d = k.data;
  return (
    <div>
      <PageHeader
        eyebrow="Add results"
        title="Add your own screening results"
        subtitle="Type a result or upload a CSV. Each abnormal result opens a care case with a named owner and a deadline, and appears in the Command Center at once. Normal results are reported back and do not open a case."
        actions={
          <Link to="/?scope=added" className="btn-primary" data-tour="watch-added">
            <LayoutDashboard size={15} /> Watch them in the Command Center
          </Link>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5" data-tour="added-kpis">
        {[
          ["Cases from your results", d ? num(d.total_loops) : "…", "abnormal results only"],
          ["Open urgent flags", d ? num(d.open_urgent_results + d.open_red_flags) : "…", "waiting for a clinician"],
          ["SLA breaches", d ? num(d.sla_breaches) : "…", "deadline passed, still open"],
          ["Seen, closure due", d ? num(d.awaiting_closure) : "…", "outcome not yet documented"],
          ["Closed with outcome", d ? `${num(d.closed_documented)} / ${num(d.closed_loops)}` : "…", "documented closure"],
        ].map(([label, value, sub]) => (
          <div key={label} className="card p-4">
            <div className="label">{label}</div>
            <div className="tabular mt-2 text-2xl font-extrabold">{value}</div>
            <div className="mt-1 text-xs text-ink-3">{sub}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_1fr]">
        <Card title="One result" subtitle="Thresholds come from the clinician-editable screening rules (HbA1c ≥ 5.7%, FIT positive, BI-RADS 0, 4, 5)." icon={<FilePlus2 size={16} />} tour="intake-form">
          <div className="mb-3 flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button key={p.label} type="button" className="chip bg-bg text-ink-2 hover:bg-teal-soft hover:text-teal-ink"
                onClick={() => setForm((f) => ({ ...f, name: p.name, test: p.test, value: p.value, language: p.language, sex: p.sex, age: p.age, shift: p.shift }))}>
                {p.label}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <label className="col-span-2 sm:col-span-1"><span className="label">Patient name</span>
              <input className="input mt-1" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Anil Menon" maxLength={80} />
            </label>
            <label><span className="label">Test</span>
              <select className="input mt-1" value={form.test} aria-label="Test"
                onChange={(e) => { const t = e.target.value as Test; setForm((f) => ({ ...f, test: t, value: t === "FIT" ? "positive" : t === "Mammogram" ? "BI-RADS 4" : "7.8" })); }}>
                <option value="HbA1c">HbA1c (diabetes)</option>
                <option value="FIT">FIT stool test (bowel)</option>
                <option value="Mammogram">Mammogram (breast)</option>
              </select>
            </label>
            <label><span className="label">Result {form.test === "HbA1c" ? "(%)" : ""}</span><div className="mt-1">{valueInput}</div></label>
            <label><span className="label">Language</span>
              <select className="input mt-1" value={form.language} onChange={(e) => set("language", e.target.value)}>
                {Object.entries(LANG_EN).map(([c, n]) => <option key={c} value={c}>{n}</option>)}
              </select>
            </label>
            <label><span className="label">Sex</span>
              <select className="input mt-1" value={form.sex} onChange={(e) => set("sex", e.target.value)}><option value="F">Female</option><option value="M">Male</option></select>
            </label>
            <label><span className="label">Age</span>
              <input className="input mt-1" type="number" min={18} max={100} value={form.age} onChange={(e) => set("age", Number(e.target.value))} />
            </label>
            <label><span className="label">Work shift</span>
              <select className="input mt-1" value={form.shift} onChange={(e) => set("shift", e.target.value)}>
                <option value="day">Day</option><option value="night">Night</option><option value="rotating">Rotating</option>
              </select>
            </label>
            <label><span className="label">Result date</span>
              <input className="input mt-1" type="date" value={form.result_date} onChange={(e) => set("result_date", e.target.value)} />
            </label>
            <label className="col-span-2 sm:col-span-1"><span className="label">Screening provider</span>
              <input className="input mt-1" value={form.facility} onChange={(e) => set("facility", e.target.value)} maxLength={120} />
            </label>
            <div className="col-span-2 flex items-center gap-3 sm:col-span-3">
              <button className="btn-primary shrink-0 whitespace-nowrap" type="submit" disabled={!!busy} data-tour="intake-submit">
                {busy === "one" ? <Spinner /> : <FilePlus2 size={15} />} Add result
              </button>
              <span className="text-xs text-ink-3">Leave the date empty for today. An older date can already be past its deadline.</span>
            </div>
          </form>
        </Card>

        <Card title="Upload a CSV" subtitle="Up to 200 rows. Columns: name, language, sex, age, test, value, result_date, facility, phone, shift." icon={<FileUp size={16} />}>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost" onClick={() => void download("/intake/template.csv", "wasl_results_template.csv")}><Download size={15} /> Download template</button>
            <button className="btn-ghost" disabled={!!busy} onClick={() => void run("csv", "Sample file uploaded (8 rows)", async () => post("/intake/csv", { csv: await get<string>("/intake/template.csv") }))}>
              {busy === "csv" ? <Spinner /> : <Upload size={15} />} Upload the sample file
            </button>
          </div>
          <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line p-6 text-center text-sm text-ink-2 hover:border-teal hover:bg-teal-soft/20">
            <FileUp size={22} className="text-teal" />
            <span><strong className="text-ink">Choose a CSV file</strong> from your computer</span>
            <span className="text-xs text-ink-3">Test: HbA1c, FIT or Mammogram · Value: 7.2 / positive / BI-RADS 4 · Language: en, ar, hi, ur, ml, bn, tl</span>
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => void onFile(e.target.files?.[0])} />
          </label>
          <p className="mt-3 flex items-start gap-2 text-xs text-ink-3">
            <Info size={13} className="mt-0.5 shrink-0" /> Use made-up people only. Results are stored in the demo database; a demo reset (Judge Mode) removes them.
          </p>
        </Card>
      </div>

      {err && <div className="mt-4 rounded-xl bg-bad-soft px-4 py-2 text-sm text-bad">{err}</div>}
      {last && (
        <Card className="mt-6" title={last.title}
          subtitle={`${last.items.filter((r) => r.status === "loop_created").length} case(s) opened · ${last.items.filter((r) => r.status === "normal").length} normal · ${last.items.filter((r) => r.status === "error").length} row error(s)`}>
          <OutcomeList items={last.items} />
        </Card>
      )}

      <Card className="mt-6" title="Your results, live" subtitle="Updates every few seconds as outreach, chat, booking, flags and closure happen." icon={<UserRound size={16} />} tour="added-table">
        {recent.isLoading ? <LoadingBlock rows={4} /> : recent.error ? <ErrorState error={recent.error} /> : !recent.data?.items.length ? (
          <EmptyState title="No added results yet" hint="Add one above, or upload the sample file." />
        ) : (
          <div className="-mx-5 overflow-x-auto scrollbar-thin">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  {["Patient", "Result", "Severity", "State", "Owner", "Next action", "Flags / outcome", "Result date"].map((h) => <th key={h} className="label px-3 py-2 first:pl-5">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {recent.data.items.map((r) => (
                  <tr key={r.id} className="border-b border-line/60 hover:bg-bg">
                    <td className="py-2.5 pl-5 pr-3">
                      <Link to={`/loops/${r.id}`} className="font-semibold hover:underline">{r.display_name}</Link>
                      <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-3">{r.patient_code} <LangChip lang={r.language} /></div>
                    </td>
                    <td className="px-3">
                      <div className="font-medium">{resultLabel(r.test_code, r.value, r.value_text)}</div>
                      <div className="text-[11px] text-ink-3">{PROGRAM_LABEL[r.program]} · {r.facility}</div>
                    </td>
                    <td className="px-3"><SeverityBadge severity={r.severity} /></td>
                    <td className="px-3"><StateBadge state={r.state} understood={r.understood} /></td>
                    <td className="px-3 text-xs">{r.owner ? <><div className="font-semibold">{r.owner.name}</div><div className="capitalize text-ink-3">{r.owner.role}</div></> : <Chip tone="bad">unowned</Chip>}</td>
                    <td className="max-w-[200px] px-3 text-xs text-ink-2">{r.next_action}</td>
                    <td className="px-3">
                      <div className="flex flex-wrap gap-1">
                        {r.open_flags.map((f) => <Chip key={f} tone={FLAG[f]?.tone ?? "warn"} icon={FLAG[f]?.icon}>{FLAG[f]?.label ?? f.replace("_", " ")}</Chip>)}
                        {r.closure && <Chip tone="ok" icon={<CheckCircle2 size={11} />}>{r.closure.outcome_label}</Chip>}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 pr-5 text-xs text-ink-3">{relTime(r.resulted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

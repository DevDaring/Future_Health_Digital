import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { BadgeCheck, EyeOff, FilePlus2, FileText, Languages, Play, ShieldAlert, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { get, post } from "../api/client";
import type { TranslationCheck } from "../api/types";
import { CheckDetail } from "../components/loop";
import { Card, Chip, EmptyState, ErrorState, LoadingBlock, Modal, PageHeader, Segmented, Spinner } from "../components/ui";
import { LANG_EN, LANG_NAMES, PROGRAM_LABEL, isRtl, relTime } from "../lib/format";
import { useAuth } from "../store/auth";

interface Template { id: string; program: string; severity: string; key: string; body: string; approved_by: string | null; approved_at: string | null; version: number; status: string; translations: string[] }

function Preview({ templates }: { templates: Template[] }) {
  const [tid, setTid] = useState(templates.find((t) => t.key === "result_explain" && t.program === "DIABETES" && t.severity === "routine")?.id ?? templates[0]?.id);
  const [lang, setLang] = useState("ml");
  const [lit, setLit] = useState(2);
  const [persona, setPersona] = useState("ramesh");
  const [out, setOut] = useState<null | { result: { source_en: string; simplified_en: string; translated: string; back_translated: string; judge_score: number; entity_match: boolean; discrepancies: string[]; passed: boolean; fell_back: boolean; final_text: string; final_source: string; provider: string }; redacted_payloads: string[]; fallbacks: string[] }>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setOut(await post("/content/preview", { template_id: tid, language: lang, literacy: lit, persona }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const check: TranslationCheck | null = out
    ? { id: "preview", template_key: "", language: lang, created_at: "", ...out.result }
    : null;
  return (
    <Card title="Preview through the full QA pipeline" subtitle="Approved EN → PII firewall → simplify → translate → back-translate → entity check + LLM judge" icon={<Play size={16} />} tour="content-preview">
      <div className="grid gap-3 md:grid-cols-4">
        <select className="input md:col-span-2" value={tid} onChange={(e) => setTid(e.target.value)} aria-label="Template">
          {templates.filter((t) => t.status === "approved").map((t) => <option key={t.id} value={t.id}>{t.program}/{t.severity} · {t.key}</option>)}
        </select>
        <select className="input" value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {Object.keys(LANG_NAMES).map((l) => <option key={l} value={l}>{LANG_EN[l]} · {LANG_NAMES[l]}</option>)}
        </select>
        <select className="input" value={persona} onChange={(e) => setPersona(e.target.value)} aria-label="Persona">
          {["ramesh", "fatima", "joy", "imran", "sara"].map((p) => <option key={p} value={p}>Persona: {p}</option>)}
        </select>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-ink-2">Literacy</span>
        <Segmented size="sm" value={String(lit)} onChange={(v) => setLit(+v)} options={[{ value: "1", label: "1 · basic" }, { value: "2", label: "2" }, { value: "3", label: "3" }]} />
        <button className="btn-primary ml-auto" onClick={() => void run()} disabled={busy}>{busy ? <Spinner /> : <Play size={15} />} Run pipeline</button>
      </div>
      {err && <div className="mt-3"><ErrorState error={err} /></div>}
      {out && check && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <CheckDetail c={check} />
          <div>
            <div className="label mb-2 flex items-center gap-1.5"><EyeOff size={12} /> What the LLM actually saw (PII firewall)</div>
            {out.redacted_payloads.length ? out.redacted_payloads.map((p, i) => (
              <pre key={i} className="mb-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl bg-night p-3 font-mono text-[11px] text-teal-200 scrollbar-thin">{p}</pre>
            )) : <p className="text-xs text-ink-2">Mock provider: no network call was made (fixture translation used).</p>}
            {out.fallbacks.length > 0 && <Chip tone="warn">LLM errors → mock fallback: {out.fallbacks.join(", ")}</Chip>}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function ContentStudio() {
  const user = useAuth((s) => s.user);
  const t = useQuery({ queryKey: ["templates"], queryFn: () => get<{ items: Template[] }>("/content/templates") });
  const [failedOnly, setFailedOnly] = useState(false);
  const checks = useQuery({ queryKey: ["checks", failedOnly], queryFn: () => get<{ items: TranslationCheck[]; stats: { total: number; failed: number } }>(`/content/translation-checks?size=40${failedOnly ? "&failed=true" : ""}`), refetchInterval: 8000 });
  const [program, setProgram] = useState("ALL");
  const [open, setOpen] = useState<TranslationCheck | null>(null);
  const [draft, setDraft] = useState<Template | null>(null);
  const [body, setBody] = useState("");
  const canApprove = user?.role === "admin" || user?.role === "clinician";
  const grouped = useMemo(() => (t.data?.items ?? []).filter((x) => program === "ALL" || x.program === program), [t.data, program]);

  return (
    <div>
      <PageHeader eyebrow="Content Studio" title="Clinicians own the words"
        subtitle="All patient-facing medical content comes from approved templates. The AI only simplifies, personalises and translates — and is checked before it speaks." />
      {t.error && <ErrorState error={t.error} />}
      {t.data && <Preview templates={t.data.items} />}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <Card title="Approved templates" subtitle={`${t.data?.items.length ?? "…"} templates · English masters with 6 approved translations each`} icon={<FileText size={16} />}
          action={<Segmented size="sm" value={program} onChange={setProgram} options={[{ value: "ALL", label: "All" }, { value: "ANY", label: "Generic" }, { value: "DIABETES", label: "DM" }, { value: "COLORECTAL", label: "CRC" }, { value: "BREAST", label: "Breast" }]} />}>
          {t.isLoading ? <LoadingBlock rows={6} /> : (
            <ul className="max-h-[560px] space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {grouped.map((x) => (
                <li key={x.id} className="rounded-xl border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold">{x.key}</span>
                    <Chip tone="neutral">{x.program === "ANY" ? "generic" : PROGRAM_LABEL[x.program]}{x.severity !== "any" ? ` · ${x.severity}` : ""}</Chip>
                    <Chip tone={x.status === "approved" ? "ok" : x.status === "draft" ? "warn" : "neutral"} icon={x.status === "approved" ? <BadgeCheck size={11} /> : undefined}>{x.status} v{x.version}</Chip>
                    <span className="ml-auto flex items-center gap-1 text-[11px] text-ink-3"><Languages size={11} />{x.translations.length}/6</span>
                  </div>
                  <p className="mt-1.5 text-sm text-ink-2">{x.body}</p>
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-3">
                    {x.approved_by && <span>approved by {x.approved_by}</span>}
                    <button className="font-bold text-teal hover:underline" onClick={() => { setDraft(x); setBody(x.body); }}><FilePlus2 size={11} className="inline" /> new version</button>
                    {x.status === "draft" && canApprove && (
                      <button className="font-bold text-ok hover:underline" onClick={async () => { await post(`/content/templates/${x.id}/approve`); void t.refetch(); }}>Approve</button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Translation-check log" subtitle={checks.data ? `${checks.data.stats.total} checks · ${checks.data.stats.failed} failed → safe fallback + human review` : undefined}
          icon={<ShieldCheck size={16} />} action={<label className="flex items-center gap-1.5 text-xs font-semibold"><input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} /> failed only</label>}>
          {checks.isLoading ? <LoadingBlock rows={6} /> : !checks.data?.items.length ? <EmptyState title="No checks yet" hint="Start outreach for a non-English persona to see checks appear." /> : (
            <ul className="max-h-[560px] space-y-2 overflow-y-auto pr-1 scrollbar-thin">
              {checks.data.items.map((c) => (
                <li key={c.id}>
                  <button onClick={() => setOpen(c)} className={clsx("w-full rounded-xl border p-3 text-left transition hover:shadow-soft", c.passed ? "border-line" : "border-warn/50 bg-warn-soft/40")}>
                    <div className="flex items-center gap-2 text-xs">
                      {c.passed ? <ShieldCheck size={13} className="text-ok" /> : <ShieldAlert size={13} className="text-warn" />}
                      <span className="font-mono font-bold">{c.template_key}</span>
                      <span className="chip bg-bg text-ink-2">{LANG_EN[c.language]}</span>
                      <span className="tabular ml-auto font-bold">{c.judge_score.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm" lang={c.language} dir={isRtl(c.language) ? "rtl" : "ltr"}>{c.final_text}</p>
                    <div className="mt-1 text-[11px] text-ink-3">{relTime(c.created_at)} · {c.provider}{c.fell_back && " · fell back to approved translation"}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title="Translation check" wide>{open && <CheckDetail c={open} />}</Modal>
      <Modal open={!!draft} onClose={() => setDraft(null)} title={`New version · ${draft?.key}`}>
        <p className="mb-2 text-xs text-ink-2">Saved as a draft. A clinician must approve it before any patient sees it; translations must be re-approved.</p>
        <textarea className="input min-h-[140px]" value={body} onChange={(e) => setBody(e.target.value)} />
        <button className="btn-primary mt-3" onClick={async () => { if (!draft) return; await post("/content/templates", { program: draft.program, severity: draft.severity, key: draft.key, body }); setDraft(null); void t.refetch(); }}>Save draft</button>
      </Modal>
    </div>
  );
}

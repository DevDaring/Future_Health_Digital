import { useQueryClient } from "@tanstack/react-query";
import { Gavel, Play, RotateCcw } from "lucide-react";
import { useState } from "react";
import { post } from "../api/client";
import { Modal, Spinner } from "../components/ui";
import { useAuth, useUi } from "../store/auth";
import { useTourData } from "./Tour";

export function JudgeModeButton() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const user = useAuth((s) => s.user);
  const setTour = useUi((s) => s.setTour);
  const resetData = useTourData((s) => s.reset);
  const qc = useQueryClient();
  const isAdmin = user?.role === "admin";

  async function start(reset: boolean) {
    setErr(null);
    setBusy(true);
    try {
      if (reset) await post("/demo/reset");
      resetData();
      await qc.invalidateQueries();
      setOpen(false);
      setTour(true, 0);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="btn bg-gradient-to-r from-sand to-amber-500 text-white shadow-soft hover:brightness-110" onClick={() => setOpen(true)} data-tour="judge-mode">
        <Gavel size={16} /> <span className="hidden sm:inline">Judge Mode</span>
      </button>
      <Modal open={open} onClose={() => !busy && setOpen(false)} title="Judge Mode — a 3-minute guided tour">
        <p className="text-sm text-ink-2">
          One click resets the demo data (same seed → identical numbers), then walks through all ten screens. Each step runs the real action — a Malayalam
          conversation, a red-flag escalation, a 5-policy twin run — and fills the narration with live numbers from the API.
        </p>
        <ol className="mt-4 grid grid-cols-2 gap-1.5 text-xs text-ink-2">
          {["Command Center", "Funnel", "Uplift worklist", "Why + What would help", "Malayalam chat + teach-back", "Translation QA catch", "Red flag → nurse", "Policy Twin", "Fairness + audit", "ROI + pilot"].map((s, i) => (
            <li key={s} className="rounded-lg bg-bg px-2 py-1.5"><strong className="text-ink">{i + 1}.</strong> {s}</li>
          ))}
        </ol>
        {err && <div className="mt-3 rounded-xl bg-bad-soft p-2 text-sm text-bad">{err}</div>}
        <div className="mt-5 flex flex-wrap gap-2">
          {isAdmin && (
            <button className="btn-primary" disabled={busy} onClick={() => void start(true)}>
              {busy ? <Spinner /> : <RotateCcw size={16} />} {busy ? "Resetting demo data (~20 s)…" : "Reset & start tour"}
            </button>
          )}
          <button className="btn-ghost" disabled={busy} onClick={() => void start(false)}>
            <Play size={16} /> Start without reset
          </button>
        </div>
      </Modal>
    </>
  );
}

import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Gavel, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { create } from "zustand";
import { Spinner } from "../components/ui";
import { fillTemplate } from "../lib/format";
import { useUi } from "../store/auth";
import { STEPS, type TourData } from "./steps";

interface TourStore {
  data: TourData;
  merge: (d: TourData) => void;
  reset: () => void;
}
export const useTourData = create<TourStore>()((set) => ({
  data: {},
  merge: (d) => set((s) => ({ data: { ...s.data, ...d } })),
  reset: () => set({ data: {} }),
}));

function useRect(selector: string | null, deps: unknown[]) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  useLayoutEffect(() => {
    if (!selector) {
      setRect(null);
      return;
    }
    let scrolled = false;
    const tick = () => {
      const el = document.querySelector(`[data-tour="${selector}"]`);
      if (el) {
        if (!scrolled) {
          el.scrollIntoView({ block: "center", behavior: "smooth" });
          scrolled = true;
        }
        setRect(el.getBoundingClientRect());
      } else setRect(null);
    };
    tick();
    const id = window.setInterval(tick, 300);
    window.addEventListener("resize", tick);
    window.addEventListener("scroll", tick, true);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("resize", tick);
      window.removeEventListener("scroll", tick, true);
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return rect;
}

export function TourOverlay() {
  const { tourActive, tourStep, setTour } = useUi();
  const { data, merge } = useTourData();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prepared = useRef<Set<string>>(new Set());
  const step = STEPS[tourStep];

  useEffect(() => {
    if (!tourActive) {
      prepared.current = new Set();
      return;
    }
    let alive = true;
    (async () => {
      setError(null);
      try {
        if (step.prepare && !prepared.current.has(step.id)) {
          setPreparing(true);
          const extra = await step.prepare(useTourData.getState().data);
          if (!alive) return;
          merge(extra);
          prepared.current.add(step.id);
          await qc.invalidateQueries();
        }
        nav(step.route({ ...useTourData.getState().data }));
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setPreparing(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [tourActive, tourStep]); // eslint-disable-line react-hooks/exhaustive-deps

  const rect = useRect(tourActive && !preparing ? step.target : null, [tourActive, tourStep, preparing]);
  if (!tourActive) return null;

  const pad = 8;
  const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const cardW = Math.min(420, vw - 24);
  // Place the card where it fits: below the target, else above it, else pinned bottom-right.
  // Anchoring with `bottom` keeps the buttons on screen however long the narration is.
  const CARD_H = 330;
  let pos: { top?: number; bottom?: number; left: number } = { bottom: 24, left: vw - cardW - 24 };
  if (rect) {
    const left = Math.min(Math.max(12, rect.left), vw - cardW - 12);
    if (vh - rect.bottom - pad - 16 >= CARD_H) pos = { top: rect.bottom + pad + 12, left };
    else if (rect.top - pad - 16 >= CARD_H) pos = { bottom: vh - rect.top + pad + 12, left };
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-[60]" aria-live="polite">
      {rect ? (
        <motion.div
          className="pointer-events-none fixed rounded-2xl ring-4 ring-sand"
          animate={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }}
          transition={{ type: "spring", stiffness: 260, damping: 30 }}
          style={{ boxShadow: "0 0 0 9999px rgba(6,10,20,0.55)" }}
        />
      ) : (
        <div className="pointer-events-none fixed inset-0 bg-night/40" />
      )}
      <AnimatePresence mode="wait">
        <motion.div
          key={step.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="pointer-events-auto fixed z-[61] rounded-2xl border border-sand/50 bg-card p-5 shadow-lift"
          style={{ width: cardW, maxHeight: vh - 24, overflowY: "auto", ...pos }}
          role="dialog"
          aria-label="Judge Mode tour"
        >
          <div className="flex items-center justify-between">
            <span className="chip bg-sand-soft text-sand-ink"><Gavel size={12} /> Judge Mode · {tourStep + 1}/{STEPS.length}</span>
            <button className="rounded-lg p-1 text-ink-3 hover:bg-bg hover:text-ink" aria-label="End tour" onClick={() => setTour(false)}><X size={16} /></button>
          </div>
          <h3 className="mt-3 text-lg font-extrabold tracking-tight">{step.title}</h3>
          {preparing ? (
            <div className="mt-2 flex items-center gap-2 text-sm text-ink-2"><Spinner /> Running it live…</div>
          ) : error ? (
            <div className="mt-2 rounded-xl bg-bad-soft p-2 text-sm text-bad">{error}</div>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-ink-2">{fillTemplate(step.body, data)}</p>
          )}
          <div className="mt-4 flex items-center justify-between">
            <div className="flex gap-1">
              {STEPS.map((s, i) => <span key={s.id} className={`h-1.5 rounded-full transition-all ${i === tourStep ? "w-5 bg-sand" : i < tourStep ? "w-1.5 bg-teal" : "w-1.5 bg-line"}`} />)}
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost !px-3 !py-1.5" disabled={tourStep === 0 || preparing} onClick={() => setTour(true, tourStep - 1)}><ChevronLeft size={15} /> Back</button>
              {tourStep < STEPS.length - 1 ? (
                <button className="btn-primary !px-3 !py-1.5" disabled={preparing} onClick={() => setTour(true, tourStep + 1)}>Next <ChevronRight size={15} /></button>
              ) : (
                <button className="btn-primary !px-3 !py-1.5" onClick={() => setTour(false)}>Finish</button>
              )}
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarCheck2, CheckCircle2, Globe2, Headset, Lock, MapPin, Mic, MicOff, PhoneCall, SendHorizontal, ShieldCheck, Siren, Volume2 } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { ApiError, get, post } from "../api/client";
import type { ChatMessage, ChatState, Slot } from "../api/types";
import { Logo, Spinner } from "../components/ui";
import i18n, { SPEECH_LANG } from "../i18n";
import { LANG_NAMES } from "../lib/format";

type SpeechRec = { lang: string; interimResults: boolean; onresult: (e: { results: { 0: { transcript: string } }[] }) => void; onend: () => void; start: () => void; stop: () => void };

function getRecognition(): SpeechRec | null {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const C = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return C ? new C() : null;
}

function speak(text: string, lang: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = SPEECH_LANG[lang] ?? "en-US";
  u.rate = 0.92;
  window.speechSynthesis.speak(u);
}

function SlotCards({ slots, onBook, busy, booked, t }: { slots: Slot[]; onBook: (s: Slot) => void; busy: string | null; booked: boolean; t: (k: string) => string }) {
  return (
    <div className="mt-2 space-y-2">
      {slots.map((s, i) => (
        <motion.div key={s.slot_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
          className="rounded-2xl border border-line bg-card p-3 shadow-soft">
          <div className="flex items-start justify-between gap-2">
            <div dir="ltr" lang="en">
              <div className="text-base font-extrabold">{s.local_label}</div>
              <div className="flex items-center gap-1 text-xs text-ink-2"><MapPin size={11} />{s.clinic_name} · {s.distance_km} km</div>
            </div>
            {i === 0 && <span className="chip bg-teal text-white">★</span>}
          </div>
          <div className="mt-2 flex flex-wrap gap-1" dir="ltr" lang="en">
            {s.match_reasons.map((r) => <span key={r} className="chip bg-teal-soft text-teal-ink">{r}</span>)}
          </div>
          <button className="btn-primary mt-3 w-full !py-2.5 text-base" disabled={!!busy || booked} onClick={() => onBook(s)}>
            {busy === s.slot_id ? <Spinner /> : <CalendarCheck2 size={18} />} {t("ui.book")}
          </button>
        </motion.div>
      ))}
    </div>
  );
}

function Bubble({ m, lang, rtl, t, onBook, busy, booked }: { m: ChatMessage; lang: string; rtl: boolean; t: (k: string) => string; onBook: (s: Slot) => void; busy: string | null; booked: boolean }) {
  const mine = m.sender === "patient";
  if (m.kind === "consent" || m.sender === "system") {
    return <div className="mx-auto max-w-[85%] rounded-xl bg-sand-soft px-3 py-2 text-center text-sm text-sand-ink" lang="en" dir="ltr">{m.text}</div>;
  }
  return (
    <motion.div initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className={clsx("flex flex-col", mine ? "items-end" : "items-start")}>
      <div className={clsx("relative max-w-[88%] rounded-3xl px-4 py-3 text-[17px] leading-relaxed shadow-soft",
        m.kind === "emergency" ? "border-2 border-bad bg-bad-soft font-semibold text-bad" : mine ? "rounded-br-lg bg-gradient-to-br from-indigo to-indigo/85 text-white" : "rounded-bl-lg bg-card text-ink",
        rtl && (mine ? "rounded-br-3xl rounded-bl-lg" : "rounded-bl-3xl rounded-br-lg"))}
        lang={lang} dir="auto">
        {m.text}
        {!mine && (
          <button className="ms-2 inline-flex translate-y-0.5 text-ink-3 hover:text-teal" aria-label={t("ui.listen")} onClick={() => speak(m.text, lang)}>
            <Volume2 size={16} />
          </button>
        )}
      </div>
      {!mine && m.meta.qa && lang !== "en" && (
        <span className={clsx("mt-1 inline-flex items-center gap-1 text-[11px] font-semibold", m.meta.qa.passed ? "text-ok" : "text-sand-ink")}>
          <ShieldCheck size={11} /> {m.meta.qa.passed ? t("ui.checked_translation") : t("ui.approved_translation")}
        </span>
      )}
      {m.meta.teach_back === "passed" && <span className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-ok"><CheckCircle2 size={11} /> ✓</span>}
      {m.kind === "slots" && m.meta.slots && <div className="w-full max-w-[92%]"><SlotCards slots={m.meta.slots} onBook={onBook} busy={busy} booked={booked} t={t} /></div>}
    </motion.div>
  );
}

export default function PatientChat() {
  const { token } = useParams();
  const { t } = useTranslation();
  const [st, setSt] = useState<ChatState | null>(null);
  const [err, setErr] = useState<{ status: number; msg: string } | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [busySlot, setBusySlot] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const recRef = useRef<SpeechRec | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const micSupported = useMemo(() => typeof window !== "undefined" && !!getRecognition(), []);

  useEffect(() => {
    let alive = true;
    get<ChatState>(`/c/${token}`)
      .then((s) => alive && setSt(s))
      .catch((e: unknown) => alive && setErr({ status: e instanceof ApiError ? e.status : 0, msg: e instanceof Error ? e.message : String(e) }));
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    if (st) {
      void i18n.changeLanguage(st.language);
      document.documentElement.lang = st.language;
    }
  }, [st?.language]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Braces matter: Chromium's scrollIntoView now returns a Promise, which must not be the effect's return value.
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [st?.messages.length, sending]);

  async function send(msg: string) {
    if (!msg.trim() || !st) return;
    setSending(true);
    setText("");
    const optimistic: ChatMessage = { id: `tmp-${Date.now()}`, sender: "patient", text: msg, text_en: "", kind: "text", red_flag: false, meta: {}, translation_check_id: null, created_at: new Date().toISOString() };
    setSt({ ...st, messages: [...st.messages, optimistic], quick_replies: [] });
    try {
      setSt(await post<ChatState>(`/c/${token}/message`, { text: msg }));
    } catch (e) {
      setErr({ status: 0, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSending(false);
    }
  }

  async function book(s: Slot) {
    setBusySlot(s.slot_id);
    try {
      setSt(await post<ChatState>(`/c/${token}/book`, { slot_id: s.slot_id }));
    } catch (e) {
      setErr({ status: 0, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusySlot(null);
    }
  }

  async function changeLang(lang: string) {
    setSt(await post<ChatState>(`/c/${token}/language`, { language: lang }));
  }

  async function human() {
    setSending(true);
    try {
      setSt(await post<ChatState>(`/c/${token}/human`, {}));
    } finally {
      setSending(false);
    }
  }

  function toggleMic() {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const r = getRecognition();
    if (!r || !st) return;
    r.lang = SPEECH_LANG[st.language] ?? "en-US";
    r.interimResults = false;
    r.onresult = (e) => setText((prev) => `${prev} ${e.results[0][0].transcript}`.trim());
    r.onend = () => setListening(false);
    recRef.current = r;
    setListening(true);
    r.start();
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(text);
  };

  if (err && !st) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg p-6 text-center">
        <div className="card max-w-sm p-8">
          <Logo />
          <p className="mt-6 text-lg font-semibold">{err.status === 410 ? "This link has expired." : "We couldn't open this conversation."}</p>
          <p className="mt-2 text-sm text-ink-2">{err.status === 410 ? "Please contact your health centre." : err.msg}</p>
        </div>
      </div>
    );
  }

  const rtl = st?.rtl ?? false;
  const lang = st?.language ?? "en";
  return (
    <div className="min-h-screen bg-gradient-to-br from-teal/10 via-bg to-indigo/10 sm:py-6">
      <div className="mx-auto flex h-[100dvh] max-w-[440px] flex-col overflow-hidden bg-bg sm:h-[calc(100dvh-3rem)] sm:rounded-[2.5rem] sm:border-[10px] sm:border-night sm:shadow-lift"
        dir={rtl ? "rtl" : "ltr"} lang={lang}>
        <header className="pattern-stars bg-night px-4 pb-4 pt-5 text-white">
          <div className="flex items-center justify-between gap-2" dir="ltr">
            <Logo light size={32} />
            <label className="flex items-center gap-1.5 rounded-xl bg-white/10 px-2 py-1.5 text-sm">
              <Globe2 size={14} />
              <span className="sr-only">{t("ui.language")}</span>
              <select className="bg-transparent text-sm font-semibold outline-none" value={lang} onChange={(e) => void changeLang(e.target.value)} data-tour="chat-language">
                {(st?.languages ?? []).map((l) => <option key={l.code} value={l.code} className="text-night">{LANG_NAMES[l.code]}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-3 text-lg font-bold">{t("ui.title")}</div>
          <div className="flex items-center gap-1 text-xs text-white/60"><Lock size={11} /> {t("ui.subtitle")}</div>
        </header>

        <AnimatePresence>
          {st?.emergency && (
            <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} className="overflow-hidden bg-bad text-white" role="alert">
              <div className="flex items-center gap-3 px-4 py-3">
                <Siren className="shrink-0 animate-pulse" />
                <div className="flex-1 text-sm">
                  <div className="font-bold">{t("ui.emergency_title")}</div>
                  <div className="opacity-90">{t("ui.emergency_body")}</div>
                </div>
                <a href="tel:999" className="rounded-xl bg-white px-3 py-2 text-sm font-extrabold text-bad"><PhoneCall size={14} className="inline" /> 999</a>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {st?.paused && !st.emergency && <div className="bg-sand-soft px-4 py-2 text-center text-sm text-sand-ink">{t("ui.nurse_reviewing")}</div>}

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 scrollbar-thin" data-tour="chat-messages">
          {!st && (
            <div className="flex items-center gap-2 text-ink-2"><Spinner /> {t("ui.loading")}</div>
          )}
          {st?.messages.map((m) => (
            <Bubble key={m.id} m={m} lang={lang} rtl={rtl} t={t} onBook={(s) => void book(s)} busy={busySlot} booked={!!st.booked} />
          ))}
          {st?.booked && (
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="rounded-3xl bg-gradient-to-br from-teal to-indigo p-4 text-white shadow-glow">
              <div className="flex items-center gap-2 text-sm font-bold"><CheckCircle2 size={18} /> {t("ui.booked")}</div>
              <div className="mt-1 text-lg font-extrabold" dir="ltr">{st.booked.label}</div>
              <div className="text-sm opacity-90" dir="ltr">{st.booked.clinic}</div>
              <div className="mt-2 text-xs opacity-80">{t("ui.reminder_note")}</div>
            </motion.div>
          )}
          {sending && (
            <div className="flex w-16 items-center justify-center gap-1 rounded-3xl bg-card px-4 py-3 shadow-soft" aria-label="typing">
              {[0, 1, 2].map((i) => <motion.span key={i} className="h-2 w-2 rounded-full bg-ink-3" animate={{ y: [0, -4, 0] }} transition={{ repeat: Infinity, duration: 0.8, delay: i * 0.15 }} />)}
            </div>
          )}
          <div ref={endRef} />
        </div>

        {st && st.quick_replies.length > 0 && !sending && (
          <div className="border-t border-line bg-card/60 px-3 pb-1 pt-2">
            <div className="label mb-1.5 px-1">{t("ui.suggestions")}</div>
            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin" data-tour="quick-replies">
              {st.quick_replies.map((k) => (
                <button key={k} className="shrink-0 rounded-2xl border border-teal/40 bg-card px-3 py-2 text-sm font-semibold text-teal-ink shadow-soft hover:bg-teal-soft"
                  onClick={() => void send(t(`quick.${k}`))}>
                  {t(`quick.${k}`)}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="border-t border-line bg-card px-3 pb-3 pt-2">
          <form onSubmit={submit} className="flex items-center gap-2">
            {micSupported && (
              <button type="button" onClick={toggleMic} aria-label={t("ui.speak")}
                className={clsx("grid h-12 w-12 shrink-0 place-items-center rounded-2xl border", listening ? "animate-pulse border-bad bg-bad-soft text-bad" : "border-line text-ink-2")}>
                {listening ? <MicOff size={20} /> : <Mic size={20} />}
              </button>
            )}
            <input className="input !h-12 !rounded-2xl text-base" value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? t("ui.listening") : t("ui.type_message")} aria-label={t("ui.type_message")} />
            <button className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-teal to-indigo text-white disabled:opacity-50" disabled={!text.trim() || sending} aria-label={t("ui.send")}>
              <SendHorizontal size={20} className={rtl ? "rotate-180" : ""} />
            </button>
          </form>
          <button className="mt-2 flex w-full items-center justify-center gap-2 rounded-2xl border border-line py-2.5 text-sm font-bold text-ink hover:bg-bg" onClick={() => void human()} disabled={sending}>
            <Headset size={16} /> {t("ui.talk_to_human")}
          </button>
          <p className="mt-2 text-center text-[10px] leading-snug text-ink-3">{t("ui.not_diagnosis")}</p>
        </div>
      </div>
    </div>
  );
}

import { motion } from "framer-motion";
import { ArrowRight, Gavel, HeartPulse, ShieldCheck, Stethoscope, UserCog, Users } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { useNavigate } from "react-router-dom";
import { post } from "../api/client";
import type { User } from "../api/types";
import { NO_DIAGNOSIS } from "../components/AppShell";
import { Logo, Spinner } from "../components/ui";
import { useAuth } from "../store/auth";

const JURY = { username: "DevTest", password: "DevTest11" };

const ROLES: { email: string; role: string; name: string; icon: ReactNode; blurb: string }[] = [
  { email: "coord@wasl.demo", role: "Coordinator", name: "Omar Haddad", icon: <Users size={18} />, blurb: "Worklist, outreach, twin" },
  { email: "clinician@wasl.demo", role: "Clinician", name: "Dr. Layla Haddad", icon: <Stethoscope size={18} />, blurb: "Patient twin, approvals" },
  { email: "nav@wasl.demo", role: "Navigator", name: "Priya Nair", icon: <HeartPulse size={18} />, blurb: "Assigned loops only" },
  { email: "admin@wasl.demo", role: "Admin", name: "Aisha Rahman", icon: <UserCog size={18} />, blurb: "Everything + demo reset" },
];

function LoopHero() {
  // An animated loop that closes: result → understood → booked → attended.
  const steps = ["Result", "Explained", "Understood", "Booked", "Attended"];
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[340px]">
      <div className="absolute inset-8 rounded-full bg-teal/20 blur-3xl" />
      <svg viewBox="-20 -10 240 220" className="relative h-full w-full">
        <defs>
          <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgb(45 212 191)" />
            <stop offset="100%" stopColor="rgb(129 140 248)" />
          </linearGradient>
        </defs>
        <circle cx="100" cy="100" r="78" stroke="rgba(255,255,255,0.08)" strokeWidth="10" fill="none" />
        <motion.circle
          cx="100" cy="100" r="78" stroke="url(#lg)" strokeWidth="10" fill="none" strokeLinecap="round"
          transform="rotate(-90 100 100)" strokeDasharray={2 * Math.PI * 78}
          initial={{ strokeDashoffset: 2 * Math.PI * 78 }} animate={{ strokeDashoffset: 0 }}
          transition={{ duration: 2.6, ease: "easeInOut", repeat: Infinity, repeatDelay: 1.4 }}
        />
        {steps.map((s, i) => {
          const a = (i / steps.length) * 2 * Math.PI - Math.PI / 2;
          const x = 100 + 78 * Math.cos(a);
          const y = 100 + 78 * Math.sin(a);
          return (
            <g key={s}>
              <motion.circle cx={x} cy={y} r="7" fill="rgb(234 179 88)" initial={{ scale: 0.4, opacity: 0.4 }}
                animate={{ scale: [0.4, 1, 1], opacity: [0.4, 1, 1] }} transition={{ duration: 2.6, delay: (i / steps.length) * 2.6, repeat: Infinity, repeatDelay: 1.4 }} />
              <text x={100 + 97 * Math.cos(a)} y={100 + 97 * Math.sin(a) + 3} textAnchor={Math.cos(a) > 0.3 ? "start" : Math.cos(a) < -0.3 ? "end" : "middle"}
                fill="rgba(255,255,255,0.7)" fontSize="9" fontWeight="700">
                {s}
              </text>
            </g>
          );
        })}
        <text x="100" y="96" textAnchor="middle" fill="white" fontSize="30" fontWeight="800" className="font-arabic">وصل</text>
        <text x="100" y="116" textAnchor="middle" fill="rgba(255,255,255,0.55)" fontSize="8" fontWeight="700" letterSpacing="2">CLOSING THE LOOP</text>
      </svg>
    </div>
  );
}

export default function Login() {
  const setAuth = useAuth((s) => s.setAuth);
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function login(u: string, p: string, key: string) {
    setBusy(key);
    setError(null);
    try {
      const r = await post<{ access_token: string; user: User }>("/auth/login", { username: u, password: p });
      setAuth(r.access_token, r.user);
      nav("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(null);
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void login(username, password, "form");
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="pattern-stars relative hidden overflow-hidden bg-night p-12 text-white lg:flex lg:flex-col">
        <div className="absolute -left-32 top-1/3 h-96 w-96 rounded-full bg-indigo/30 blur-3xl" />
        <div className="absolute -right-24 bottom-0 h-80 w-80 rounded-full bg-teal/25 blur-3xl" />
        <Logo light size={42} />
        <div className="relative my-auto">
          <LoopHero />
          <h1 className="mt-8 text-center text-4xl font-extrabold leading-tight tracking-tight">
            No abnormal result <span className="bg-gradient-to-r from-teal-300 to-indigo-300 bg-clip-text text-transparent">left behind.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-md text-center text-sm leading-relaxed text-white/60">
            AI care navigation for the Future Health Challenge — uplift-ranked outreach, verified translation in 7 languages,
            teach-back, and a digital twin to test policies before they touch real people.
          </p>
          <div className="mx-auto mt-8 grid max-w-md grid-cols-3 gap-3 text-center">
            {[["7", "languages, RTL"], ["5", "policies twinned"], ["SHA-256", "audit chain"]].map(([a, b]) => (
              <div key={b} className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                <div className="text-lg font-extrabold">{a}</div>
                <div className="text-[11px] text-white/50">{b}</div>
              </div>
            ))}
          </div>
        </div>
        <p className="relative text-xs text-white/40">{NO_DIAGNOSIS}</p>
      </section>

      <section className="flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <Logo size={40} />
          </div>
          <div className="label text-teal">Future Health Challenge · Abu Dhabi</div>
          <h2 className="mt-1 text-3xl font-extrabold tracking-tight">Sign in to WASL</h2>
          <p className="mt-1 text-sm text-ink-2">Population Health · Closing the screening-to-care loop</p>

          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="relative mt-6 overflow-hidden rounded-2xl border border-sand/50 bg-gradient-to-br from-sand-soft to-card p-5 shadow-soft">
            <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-sand/20 blur-2xl" />
            <div className="flex items-center gap-2 text-sm font-bold text-sand-ink">
              <Gavel size={16} /> Jury login
            </div>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-ink-2">User</dt>
              <dd className="font-mono font-bold">{JURY.username}</dd>
              <dt className="text-ink-2">Password</dt>
              <dd className="font-mono font-bold">{JURY.password}</dd>
            </dl>
            <button className="btn-primary mt-4 w-full" disabled={!!busy} onClick={() => void login(JURY.username, JURY.password, "jury")}>
              {busy === "jury" ? <Spinner /> : <ShieldCheck size={16} />} Enter as jury <ArrowRight size={16} />
            </button>
            <p className="mt-2 text-[11px] text-ink-2">Full access, including Judge Mode (a guided 3-minute tour with live numbers).</p>
          </motion.div>

          <form onSubmit={submit} className="mt-6 space-y-3">
            <div>
              <label className="label" htmlFor="u">Username or e-mail</label>
              <input id="u" className="input mt-1" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
            </div>
            <div>
              <label className="label" htmlFor="p">Password</label>
              <input id="p" type="password" className="input mt-1" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </div>
            {error && <div role="alert" className="rounded-xl bg-bad-soft px-3 py-2 text-sm text-bad">{error}</div>}
            <button className="btn-dark w-full" disabled={!!busy}>
              {busy === "form" && <Spinner />} Sign in
            </button>
          </form>

          <div className="mt-8">
            <div className="label">Or try a role (demo password demo1234)</div>
            <div className="mt-3 grid grid-cols-2 gap-2.5">
              {ROLES.map((r) => (
                <button key={r.email} disabled={!!busy} onClick={() => void login(r.email, "demo1234", r.email)}
                  className="group rounded-2xl border border-line bg-card p-3 text-left transition hover:-translate-y-0.5 hover:border-teal/50 hover:shadow-soft">
                  <div className="flex items-center gap-2">
                    <span className="grid h-8 w-8 place-items-center rounded-xl bg-teal-soft text-teal-ink">{busy === r.email ? <Spinner /> : r.icon}</span>
                    <div>
                      <div className="text-sm font-bold">{r.role}</div>
                      <div className="text-[11px] text-ink-3">{r.name}</div>
                    </div>
                  </div>
                  <div className="mt-2 text-[11px] text-ink-2">{r.blurb}</div>
                </button>
              ))}
            </div>
          </div>
          <p className="mt-8 text-center text-[11px] text-ink-3 lg:hidden">{NO_DIAGNOSIS}</p>
        </div>
      </section>
    </div>
  );
}

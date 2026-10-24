import clsx from "clsx";
import {
  Activity, BarChart3, BookOpenCheck, Clock3, FlaskConical, LayoutDashboard, ListOrdered, LogOut, Menu, Moon, Scale, Sparkles, Sun, X,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useDemoState } from "../api/hooks";
import type { Role } from "../api/types";
import { useAuth, useUi } from "../store/auth";
import { JudgeModeButton } from "../tour/JudgeModeButton";
import { Logo } from "./ui";

export const NO_DIAGNOSIS = "WASL does not diagnose. It explains a screening result, helps the person act on it, and escalates to a human.";

const NAV: { to: string; label: string; icon: ReactNode; roles: Role[]; tour?: string }[] = [
  { to: "/", label: "Command Center", icon: <LayoutDashboard size={18} />, roles: ["admin", "coordinator", "clinician", "navigator"] },
  { to: "/worklist", label: "Worklist", icon: <ListOrdered size={18} />, roles: ["admin", "coordinator", "clinician", "navigator"] },
  { to: "/twin", label: "Policy Twin", icon: <FlaskConical size={18} />, roles: ["admin", "coordinator", "clinician"] },
  { to: "/fairness", label: "Fairness & Governance", icon: <Scale size={18} />, roles: ["admin", "coordinator", "clinician"] },
  { to: "/content", label: "Content Studio", icon: <BookOpenCheck size={18} />, roles: ["admin", "coordinator", "clinician", "navigator"] },
  { to: "/roi", label: "Impact & ROI", icon: <BarChart3 size={18} />, roles: ["admin", "coordinator", "clinician", "navigator"] },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { dark, toggleDark } = useUi();
  const demo = useDemoState();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const items = NAV.filter((n) => user && n.roles.includes(user.role));

  const sidebar = (
    <aside className="pattern-stars flex h-full w-[260px] flex-col bg-night text-white">
      <div className="flex items-center justify-between px-5 pb-6 pt-6">
        <Logo light />
        <button className="rounded-lg p-1 text-white/60 lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu">
          <X size={18} />
        </button>
      </div>
      <nav className="flex-1 space-y-1 px-3" aria-label="Main">
        {items.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              clsx(
                "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition",
                isActive ? "bg-white/10 text-white shadow-[inset_3px_0_0_rgb(45,212,191)]" : "text-white/60 hover:bg-white/5 hover:text-white",
              )
            }
          >
            <span className="opacity-90">{n.icon}</span>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 rounded-2xl border border-white/10 bg-white/5 p-4">
        <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-white/40">Signed in</div>
        <div className="mt-1 text-sm font-semibold">{user?.display_name}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs capitalize text-teal-300">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-400" /> {user?.role}
        </div>
        <button
          className="mt-3 flex items-center gap-2 text-xs font-semibold text-white/60 hover:text-white"
          onClick={() => {
            logout();
            nav("/login");
          }}
        >
          <LogOut size={14} /> Sign out
        </button>
      </div>
    </aside>
  );

  const now = demo.data ? new Date(demo.data.now) : null;
  return (
    <div className="flex min-h-screen">
      <div className="sticky top-0 hidden h-screen lg:block">{sidebar}</div>
      {open && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          {sidebar}
          <div className="flex-1 bg-night/50" onClick={() => setOpen(false)} />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-bg/80 px-4 py-3 backdrop-blur-xl sm:px-6">
          <button className="rounded-lg p-1.5 text-ink-2 hover:bg-card lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>
          <div className="flex min-w-0 flex-1 items-center gap-2 text-xs text-ink-2">
            {now && (
              <span className="chip bg-card text-ink-2 shadow-soft" title="Simulated clock (demo mode)">
                <Clock3 size={12} />
                {now.toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Dubai" })}
                {demo.data && demo.data.offset_days > 0 && <span className="text-sand-ink">· +{demo.data.offset_days}d</span>}
              </span>
            )}
            {demo.data && (
              <span
                className={clsx("chip shadow-soft", demo.data.llm_live ? "bg-teal-soft text-teal-ink" : "bg-card text-ink-2")}
                title={`LLM provider: ${demo.data.llm_provider}`}
              >
                {demo.data.llm_live ? <Sparkles size={12} /> : <Activity size={12} />}
                {demo.data.llm_live ? "Live AI · PII-firewalled" : "Offline mock AI"}
              </span>
            )}
          </div>
          <JudgeModeButton />
          <button className="rounded-xl border border-line bg-card p-2 text-ink-2 hover:text-ink" onClick={toggleDark} aria-label="Toggle dark mode">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        <footer className="border-t border-line px-6 py-4 text-center text-xs text-ink-3">
          <strong className="text-ink-2">{NO_DIAGNOSIS}</strong> Synthetic data only · Every clinical number marked ILLUSTRATIVE is a configurable assumption.
        </footer>
      </div>
    </div>
  );
}

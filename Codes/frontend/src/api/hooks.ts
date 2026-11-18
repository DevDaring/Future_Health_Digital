import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "./client";
import type {
  DemoState, Escalation, FairnessGroup, Funnel, Kpis, LoopDetail, LoopRow, Owner, PatientTwin, Policy, TwinRun, Worklist,
} from "./types";

/** "added" limits dashboards to results a reviewer or a connected system added. */
export type Scope = "all" | "added";
const sq = (scope: Scope, first: boolean) => (scope === "added" ? `${first ? "?" : "&"}scope=added` : "");
const qs = (params: Record<string, string | undefined>) => {
  const p = Object.entries(params).filter((e): e is [string, string] => !!e[1]);
  return p.length ? `?${new URLSearchParams(p).toString()}` : "";
};

export const useKpis = (scope: Scope = "all") =>
  useQuery({ queryKey: ["kpis", scope], queryFn: () => get<Kpis>(`/dashboard/kpis${sq(scope, true)}`), refetchInterval: scope === "added" ? 4_000 : 10_000 });
export const useFunnel = (program?: string, scope: Scope = "all") =>
  useQuery({
    queryKey: ["funnel", program, scope],
    queryFn: () => get<Funnel>(`/dashboard/funnel${qs({ program, scope: scope === "added" ? "added" : undefined })}`),
    refetchInterval: scope === "added" ? 4_000 : false,
  });
export const useBreaches = (scope: Scope = "all") =>
  useQuery({ queryKey: ["breaches", scope], queryFn: () => get<{ by_program: { program: string; routine: number; high: number; urgent: number }[] }>(`/dashboard/breaches${sq(scope, true)}`) });
export const useStaff = () => useQuery({ queryKey: ["staff"], queryFn: () => get<{ items: (Owner & { languages: string[] })[] }>("/users/staff"), staleTime: 60_000 });
export const useIntakeRecent = () =>
  useQuery({
    queryKey: ["intake-recent"],
    queryFn: () => get<{ items: (LoopRow & { open_flags: string[]; closure: { outcome_label: string } | null })[]; total: number }>("/intake/recent?size=100"),
    refetchInterval: 4_000,
  });
export const useFeed = (scope: Scope = "all") =>
  useQuery({
    queryKey: ["feed", scope],
    queryFn: () => get<{ events: { id: string; seq: number; loop_id: string; patient_code: string; persona: string | null; from_state: string | null; to_state: string; actor: string; reason: string; created_at: string; hash: string }[] }>(`/dashboard/feed?limit=12${sq(scope, false)}`),
    refetchInterval: 5_000,
  });
export const useEscalations = (status = "open", reason?: string, scope: Scope = "all") =>
  useQuery({
    queryKey: ["escalations", status, reason, scope],
    queryFn: () => get<{ items: Escalation[]; total: number; counts: Record<string, number> }>(`/escalations?status=${status}&size=30${reason ? `&reason=${reason}` : ""}${sq(scope, false)}`),
    refetchInterval: 5_000,
  });
export const useWorklist = (policy: Policy, budget: number, page: number, program?: string, q?: string) =>
  useQuery({
    queryKey: ["worklist", policy, budget, page, program, q],
    queryFn: () => get<Worklist>(`/worklist?policy=${policy}&budget=${budget}&page=${page}&size=25${program ? `&program=${program}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
    placeholderData: (prev) => prev,
  });
export const useLoop = (id: string | undefined) =>
  useQuery({ queryKey: ["loop", id], queryFn: () => get<LoopDetail>(`/loops/${id}`), enabled: !!id, refetchInterval: 6_000 });
export const usePatientTwin = (id: string | undefined, enabled: boolean) =>
  useQuery({ queryKey: ["ptwin", id], queryFn: () => get<PatientTwin>(`/loops/${id}/patient-twin`), enabled: !!id && enabled });
export const useDemoState = () => useQuery({ queryKey: ["demo"], queryFn: () => get<DemoState>("/demo/state"), refetchInterval: 15_000 });
export const useFairness = (groupBy: string) =>
  useQuery({
    queryKey: ["fairness", groupBy],
    queryFn: () => get<{ group_by: string; groups: FairnessGroup[]; best_rate: number | null; threshold: number; model_version: string | null }>(`/fairness/metrics?group_by=${groupBy}`),
  });
export const useTwinRuns = (kind?: string) =>
  useQuery({ queryKey: ["twinruns", kind], queryFn: () => get<{ items: TwinRun[] }>(`/twin/runs?limit=8${kind ? `&kind=${kind}` : ""}`) });
export const useTwinRun = (id: string | null) =>
  useQuery({
    queryKey: ["twinrun", id],
    queryFn: () => get<TwinRun>(`/twin/runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "done" || q.state.data.status === "error") ? false : 700),
  });

export function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

export function useAdvanceClock() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (days: number) => post<{ new_breaches: number; reminders_sent: number; offset_days: number }>(`/demo/advance-clock?days=${days}`),
    onSuccess: () => inv("kpis", "funnel", "breaches", "escalations", "feed", "worklist", "demo", "loop"),
  });
}

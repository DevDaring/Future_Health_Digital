// Hand-mirrored from the FastAPI OpenAPI schema (/api/openapi.json).

export type Role = "admin" | "coordinator" | "clinician" | "navigator";
export type Policy = "uplift" | "risk_only" | "uplift_fair";
export type TwinPolicy = "no_outreach" | "sms_everyone" | "risk_ranked" | "wasl_uplift" | "wasl_uplift_fair";

export interface User {
  id: string;
  email: string;
  username: string | null;
  role: Role;
  display_name: string;
  languages: string[];
}

export interface Kpis {
  total_loops: number;
  open_loops: number;
  closure_rate_30d: number;
  never_completed_share: number;
  median_days_to_followup: number | null;
  sla_breaches: number;
  open_escalations: number;
  open_red_flags: number;
  now: string;
  clock_offset_days: number;
}

export interface FunnelStep {
  state: string;
  count: number;
  dropoff_pct: number;
}
export interface Funnel {
  steps: FunnelStep[];
  total: number;
  biggest_drop: FunnelStep | null;
}

export interface LoopRow {
  id: string;
  patient_id: string;
  patient_code: string;
  display_name: string;
  persona: string | null;
  language: string;
  program: string;
  test_code: string;
  value: number | null;
  value_text: string | null;
  severity: "routine" | "high" | "urgent";
  category: string;
  state: string;
  escalated_from: string | null;
  breached: boolean;
  understood: boolean;
  sla_due_at: string;
  sla_days_left: number;
  p_dropoff: number | null;
  uplift: number | null;
  priority: number;
  top_reason: string | null;
  assigned_to: string | null;
  navigator_paused: boolean;
  resulted_at: string;
  rank?: number | null;
  in_budget?: boolean;
  policy_score?: number;
}

export interface Worklist {
  items: LoopRow[];
  total: number;
  page: number;
  size: number;
  policy: Policy;
  budget: number;
  eligible: number;
  personas: Record<string, { loop_id: string; rank: number | null; in_budget: boolean }>;
  vs_risk_only: {
    swapped_in: number;
    swapped_out: number;
    avg_uplift_in: number | null;
    avg_uplift_out: number | null;
    avg_prior_no_shows_out: number | null;
    expected_extra_returns: number;
  };
  expected_returns_from_outreach: number;
  allocation: Record<string, { need_share: number; budget_share: number; floor: number | null }>;
}

export interface ShapItem {
  feature: string;
  label: string;
  value: number;
  shap: number;
}
export interface Counterfactual {
  actions: string[];
  action: { channel: string; lang_matched: boolean; slot: string; cost_info: boolean };
  p_return: number;
  p_baseline: number;
  delta: number;
}
export interface QaMeta {
  score: number;
  passed: boolean;
  fell_back: boolean;
  source: "checked" | "approved_translation" | "english_interpreter";
  entity_match: boolean;
  provider: string;
}
export interface Slot {
  slot_id: string;
  clinic_id: string;
  clinic_name: string;
  clinic_area: string;
  start_at: string;
  local_label: string;
  weekday: string;
  clinician_language: string;
  distance_km: number;
  score: number;
  match_reasons: string[];
}
export interface ChatMessage {
  id: string;
  sender: "patient" | "navigator_ai" | "human" | "system";
  text: string;
  text_en: string;
  kind: "text" | "slots" | "emergency" | "system" | "consent";
  red_flag: boolean;
  meta: { qa?: QaMeta; template_key?: string; slots?: Slot[]; teach_back?: string; intent?: string; barrier?: string; booked_slot?: string };
  translation_check_id: string | null;
  created_at: string;
}
export interface TimelineEvent {
  id: string;
  seq: number;
  from_state: string | null;
  to_state: string;
  actor: string;
  reason: string;
  payload: Record<string, unknown>;
  created_at: string;
  hash: string;
  prev_hash: string;
}
export interface TranslationCheck {
  id: string;
  template_key: string;
  language: string;
  source_en: string;
  simplified_en: string;
  translated: string;
  back_translated: string;
  judge_score: number;
  entity_match: boolean;
  discrepancies: string[];
  passed: boolean;
  fell_back: boolean;
  final_text: string;
  provider: string;
  created_at: string;
}
export interface LoopDetail {
  loop: LoopRow;
  identity: { display_name: string; phone?: string | null; emirates_id?: string; pii_level: string };
  patient: {
    code: string; age: number; sex: string; nationality_group: string; language: string; language_name: string; rtl: boolean;
    literacy_level: number; occupation_type: string; shift_pattern: string; preferred_days: string[]; home_area: string;
    distance_km: number; insurance_tier: string; prior_no_shows: number; has_smartphone: boolean; preferred_channel: string;
    no_free_weekdays: boolean; persona: string | null;
  };
  score: null | {
    model_version: string; p_dropoff: number; p_return_if_not: number; p_return_if_contacted: number; uplift: number;
    shap_top: ShapItem[]; counterfactuals: Counterfactual[]; scored_at: string;
  };
  timeline: TimelineEvent[];
  chain: { valid: boolean; broken_at: string | null; checked: number };
  conversations: { id: string; language: string; channel: string; step: string; started_at: string; expires_at: string }[];
  messages: ChatMessage[];
  translation_checks: TranslationCheck[];
  teach_back: { id: string; question: string; patient_answer: string; answer_en: string; rubric: Record<string, unknown>; passed: boolean; feedback: string; created_at: string }[];
  appointments: { id: string; status: string; slot_label: string; clinic_name: string; match_reasons: string[]; start_at: string }[];
  escalations: { id: string; reason: string; status: string; notes: string; created_at: string }[];
  consents: Record<string, { granted: boolean; at: string }>;
  slots: Slot[];
  allowed_transitions: string[];
  can_view_twin: boolean;
}
export interface PatientTwin {
  program: string;
  category: string;
  outcome_label: string;
  horizon_months: number;
  label: string;
  delays: {
    delay_months: number; p_outcome_5y: number; lo: number; hi: number; excess_vs_now: number;
    trajectory: { month: number[]; p: number[]; lo: number[]; hi: number[] };
  }[];
}
export interface ChatState {
  language: string;
  language_name: string;
  rtl: boolean;
  languages: { code: string; name: string; rtl: boolean }[];
  step: string;
  paused: boolean;
  emergency: boolean;
  booked: { label: string; clinic: string } | null;
  understood: boolean;
  program: string;
  phrases: { ui: Record<string, string>; quick: Record<string, string> };
  quick_replies: string[];
  messages: ChatMessage[];
  expires_at: string;
}
export interface Escalation {
  id: string;
  loop_id: string;
  reason: string;
  status: string;
  notes: string;
  created_at: string;
  display_name: string;
  patient_code: string;
  persona: string | null;
  program: string;
  severity: string;
  loop_state: string;
}
export interface TwinPolicyResult {
  policy: TwinPolicy;
  label: string;
  n: number;
  closure_rate: number;
  closed: number;
  contacts: number;
  median_days_to_followup: number | null;
  p90_days_to_followup: number | null;
  navigator_utilisation: number;
  outreach_cost: number;
  total_cost: number;
  cost_per_closed_loop: number;
  outreach_cost_per_closed_loop: number;
  fairness_gap: number;
  allocation_gap: number | null;
  allocation: Record<string, { need_share: number; budget_share: number }>;
  by_group: Record<string, Record<string, number>>;
  series: { day: number[]; cumulative_closed: number[]; clinic_queue: number[] };
  extra_closed_vs_no_outreach: number;
  incremental_cost_per_extra_loop: number | null;
  runtime_s: number;
  model_used: boolean;
}
export interface TwinRun {
  id: string;
  kind: "compare" | "sensitivity";
  policies: TwinPolicy[];
  params: Record<string, unknown>;
  seed: number;
  status: "queued" | "running" | "done" | "error";
  results: null | {
    results?: Record<string, TwinPolicyResult>;
    calibration?: { simulated_no_outreach: number; historical_no_outreach: number | null; statement: string };
    scales?: number[];
    closure_by_scale?: Record<string, Record<string, number>>;
    robust?: boolean;
    wins?: boolean[];
    program_share?: Record<string, number>;
  };
  error: string | null;
  created_at: string;
  finished_at: string | null;
}
export interface DemoState {
  demo_mode: boolean;
  now: string;
  offset_days: number;
  llm_provider: string;
  llm_live: boolean;
  model_version: string | null;
  seed: number | null;
  checksum: string | null;
  counts: Record<string, number> | null;
  personas: Record<string, { loop_id: string; patient_id: string; name: string; state: string; language: string; program: string; story: string }>;
}
export interface FairnessGroup {
  group: string;
  n_loops: number;
  closure_rate: number | null;
  ratio_to_best: number | null;
  disparity: boolean;
  brier: number | null;
  auroc: number | null;
  tpr_high_risk: number | null;
  need_share: number;
  budget_share: Record<Policy, number>;
}

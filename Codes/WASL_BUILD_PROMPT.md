# WASL (وصل) — Master Build Prompt

> **How to use this file:** Paste this whole file into your coding tool (Claude Code, Cursor, Copilot, Windsurf, etc.) as the first message, or save it at the repo root as `WASL_BUILD_PROMPT.md` and tell the tool: *"Read WASL_BUILD_PROMPT.md and build Phase 0. Stop at the end of each phase, run its acceptance checks, and report."* Build **one phase at a time**. Do not let the tool skip acceptance checks.

---

## 0. Role and ground rules for the coding agent

You are a senior full-stack engineer building a hackathon-grade but **production-shaped** prototype. Follow these rules for the whole project:

1. **It must run end-to-end with zero API keys.** Every external dependency (LLM, speech) has an offline `mock` implementation that is the default. Real providers are opt-in through environment variables.
2. **Build in the phase order given in §14.** At the end of each phase, run that phase's acceptance checks. Fix failures before moving on. Do not leave `TODO` stubs in code paths that the demo uses.
3. **Never invent clinical facts.** All patient-facing medical content comes from the `content_templates` table, which a clinician approves. The LLM only *simplifies, personalises, and translates* that approved text. Every clinical number used in simulations is a **configurable assumption**, labelled `ILLUSTRATIVE` in the code and the UI.
4. **The system never diagnoses.** It explains a screening result, helps the person act on it, and escalates to a human. This sentence must appear in the UI footer and the docs.
5. **Determinism:** every random process takes a `seed`. `make demo` must produce identical data and identical numbers every time.
6. **Type safety:** Python type hints + Pydantic v2 everywhere. TypeScript `strict: true` on the frontend.
7. **Tests:** pytest for the backend (unit + API), Vitest for frontend utilities. `make test` must pass at the end of every phase.
8. Keep the code readable for an engineering student: short modules, docstrings that explain *why*, no clever one-liners.

---

## 1. Product summary

**Challenge:** Future Health Challenge (Abu Dhabi), track **[Population Health] Closing the Screening-to-Care Loop**.

**Problem:** A person receives an abnormal screening result (for example high HbA1c, a positive stool test, a suspicious mammogram). Many people never complete the follow-up. The result is not explained in their language, the appointment doesn't fit their work shift, or they are afraid of the cost. Nobody notices until the disease is advanced.

**WASL** = *"No abnormal result left behind."* It is an AI care-navigation platform with six parts:

| # | Module | One-line purpose |
|---|---|---|
| M1 | **Loop Engine** | A state machine with SLA timers for every abnormal result, plus a tamper-evident audit trail |
| M2 | **Risk + Uplift Intelligence** | Predicts who will drop out *and* who will respond to outreach, with SHAP explanations and counterfactuals |
| M3 | **Multilingual Care Navigator** | Chat (plus optional voice) in 7 languages that explains the result, removes barriers, books the visit and confirms understanding (teach-back) |
| M4 | **Care-Pathway Digital Twin** | A SimPy simulation for testing outreach policies before using them on real people. It includes a clinician-only patient progression view |
| M5 | **Coordinator Command Center** | Worklist, funnel, SLA breaches, "Why this patient?" cards |
| M6 | **Trust & Governance** | Fairness panel, model card, calibration, consent, PII firewall, audit-chain verification |

### Killer features (these are what make the demo stand out — all are required)

1. **Uplift-based prioritisation, not just risk.** The system ranks patients by *how much outreach will change the outcome* (T-learner uplift) under a daily call budget. It also offers a **fairness-constrained allocation** toggle.
2. **Back-translation verification.** Each translated message is translated back to English and checked: an LLM judge checks meaning, and a deterministic check confirms that numbers, test names and dates match exactly. If the check fails, the system falls back to a pre-approved translation and adds the message to the human review queue.
3. **Teach-back confirmation.** The navigator asks the person to explain the result back in their own words. The loop only moves to `UNDERSTOOD` when the teach-back passes. This is an established health-literacy technique.
4. **PII firewall.** Names, phone numbers, Emirates ID and patient IDs are stripped before any LLM call and re-inserted afterwards. The LLM never sees identity.
5. **Barrier-aware smart scheduling.** Slots are matched to the person's shift pattern, preferred day (for example Friday), distance, and preference for a same-language clinician. One-tap booking.
6. **Counterfactual "what would help" card.** Example: *"If contacted by phone in Malayalam with a Friday-evening slot, estimated return probability rises from 0.19 to 0.47."*
7. **Policy Twin.** Compare policies side by side (No outreach / SMS everyone / Risk-ranked / WASL uplift / WASL uplift + fairness) on loop-closure rate, days to follow-up, cost per closed loop, clinic queue and fairness gap. Includes a sensitivity analysis (±50% uplift).
8. **Tamper-evident audit chain.** Every loop event is SHA-256 hash-chained. A "Verify chain" button proves that no record was altered.
9. **Impact & ROI calculator.** Cost per closed loop, extra loops closed per 1,000 abnormal results, and illustrative late-stage cases avoided, all with assumption ranges. This supports a payer pitch.
10. **Judge Mode.** One click resets the demo data and starts a guided, scripted 3-minute tour across all screens, with highlighted callouts.
11. **Arabic RTL and 7-language UI.** Patient chat UI in English, Arabic (RTL), Hindi, Urdu (RTL), Malayalam, Bengali and Tagalog.
12. **FHIR R4 interoperability.** Import and export of Observation, ServiceRequest, Task and Appointment, so the system can connect to a health information exchange (for example Malaffi in Abu Dhabi).

---

## 2. Tech stack (fixed — do not substitute)

**Backend**
- Python 3.11, FastAPI, Uvicorn
- PostgreSQL 16 (via Docker), SQLAlchemy 2.0 (typed ORM, `Mapped[...]`), Alembic migrations, psycopg 3
- Pydantic v2, pydantic-settings
- ML: numpy, pandas, scikit-learn, LightGBM, SHAP
- Simulation: SimPy
- Scheduling of SLA ticks: APScheduler (in-process)
- Auth: JWT (PyJWT), passlib[bcrypt]
- LLM: provider interface with `mock` (default) and `anthropic` (official `anthropic` Python SDK). Optional `azure_openai` adapter (Microsoft is a challenge co-creator).
- Tests: pytest, httpx (`TestClient`), pytest-cov
- Lint/format: ruff, mypy (non-blocking)

**Frontend**
- React 18 + Vite + TypeScript (strict)
- Tailwind CSS, React Router v6, TanStack Query v5, Recharts, react-i18next, Zustand (small UI state only)
- Voice (optional): browser Web Speech API for speech-to-text and text-to-speech, with no backend dependency. Hide the mic button when the browser lacks support.
- Tests: Vitest

**Infra**
- `docker-compose.yml` with `db` (postgres:16), `backend`, `frontend`
- `Makefile` targets: `up`, `down`, `migrate`, `seed`, `train`, `demo`, `test`, `lint`, `reset-demo`
- `.env.example` with every variable documented

---

## 3. Repository layout

```
wasl/
├── README.md                     # quickstart, architecture diagram (mermaid), demo script
├── WASL_BUILD_PROMPT.md          # this file
├── Makefile
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── TECHNICAL.md              # architecture, data flow, design decisions
│   ├── MODEL_CARD.md             # auto-generated + hand-edited sections
│   ├── DATA_CARD.md              # synthetic data generator, assumptions
│   ├── ASSUMPTIONS_AND_LIMITATIONS.md
│   ├── RESPONSIBLE_AI.md         # safety, privacy, fairness, human oversight
│   └── PITCH.md                  # 3-minute demo script + judging-criteria mapping
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py               # FastAPI app, routers, CORS, startup
│   │   ├── config.py             # pydantic-settings
│   │   ├── db.py                 # engine, session dependency
│   │   ├── security.py           # JWT, password hashing, RBAC dependency
│   │   ├── models/               # SQLAlchemy models (one file per aggregate)
│   │   ├── schemas/              # Pydantic request/response models
│   │   ├── api/                  # routers: auth, patients, loops, worklist, navigator,
│   │   │                         #   scheduling, twin, fairness, governance, fhir, content, demo, roi
│   │   ├── loop_engine/          # state machine, SLA rules, audit hash chain
│   │   ├── ml/                   # features, train_risk, train_uplift, explain, counterfactual, registry
│   │   ├── navigator/            # conversation manager, prompts, teach-back, red flags
│   │   ├── llm/                  # base.py, mock.py, anthropic_provider.py, pii_firewall.py, translation_qa.py
│   │   ├── scheduling/           # slot matching
│   │   ├── twin/                 # simpy care-pathway sim, markov patient twin, policies, sensitivity
│   │   ├── fairness/             # metrics, constrained allocation
│   │   ├── fhir/                 # mappers to/from FHIR R4 JSON
│   │   ├── synth/                # synthetic population generator + demo personas
│   │   └── fixtures/             # approved templates, pre-approved translations, red-flag lexicons
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── src/
    │   ├── main.tsx, App.tsx, router.tsx
    │   ├── api/                  # typed client + TanStack Query hooks
    │   ├── i18n/                 # en, ar, hi, ur, ml, bn, tl JSON
    │   ├── components/           # KPI tiles, Funnel, WhyCard, Timeline, ChatBubble, PolicyCompare...
    │   ├── pages/                # see §10
    │   ├── tour/                 # Judge Mode guided tour
    │   └── styles/
    └── tests/
```

---

## 4. Domain model and care-loop state machine

### 4.1 Screening programs (start with these three)

| Program | Test | Abnormal rule | Severity |
|---|---|---|---|
| `DIABETES` | HbA1c (%) | 5.7–6.4 → prediabetes; ≥ 6.5 → diabetes range; ≥ 9.0 → high | routine / high / urgent |
| `COLORECTAL` | FIT (stool test) | positive | high |
| `BREAST` | Mammogram BI-RADS | 0 → recall; 4 → suspicious; 5 → highly suspicious | high / high / urgent |

Thresholds live in `fixtures/screening_rules.yaml` so a clinician can edit them. Show the source note "standard clinical thresholds — verify with clinical advisor" in the docs.

### 4.2 Loop states

```
RESULT_RECEIVED → NOTIFIED → ENGAGED → UNDERSTOOD → BOOKED → ATTENDED → CLOSED
            ↘            ↘          ↘             ↘          ↘
          UNREACHABLE   DECLINED (informed refusal recorded)   NO_SHOW → (back to ENGAGED)
Any state → ESCALATED (red flag or SLA breach) → handled by human → returns to previous state
SLA expired without progress → BREACHED (flag, still actionable)
```

- Transitions are validated in `loop_engine/state_machine.py`. An invalid transition raises a 409 error.
- **SLA (days to reach ATTENDED), configurable:** urgent 7, high 21, routine 60. These values are ILLUSTRATIVE.
- An APScheduler job runs every minute in demo mode (hourly otherwise). It marks breaches and creates escalations.
- `DECLINED` requires a recorded *informed refusal*: the person was told the risk in their language and chose not to proceed. Respect autonomy, and never keep nagging after a refusal.

### 4.3 Audit hash chain

Each `loop_event` row stores `prev_hash` and `hash = sha256(prev_hash || canonical_json(payload) || created_at)`. The chain is per loop, plus one global chain. `GET /api/governance/audit/verify` recomputes every hash and returns `{valid: bool, broken_at: event_id | null}`. Include a test that tampers with one row and confirms the check detects it.

---

## 5. Database schema (PostgreSQL)

Create everything with Alembic. Use UUID primary keys and `created_at` / `updated_at` timestamps. Patient identity data is kept separate from clinical data.

| Table | Key columns |
|---|---|
| `users` | id, email, password_hash, role (`admin`, `coordinator`, `clinician`, `navigator`), display_name |
| `clinics` | id, name, area, lat, lon, languages_spoken (text[]), evening_hours (bool), friday_hours (bool) |
| `clinic_slots` | id, clinic_id, program, start_at, end_at, is_booked, clinician_language |
| `patient_identity` | id, patient_id (FK), full_name, phone, emirates_id_masked — **only the PII firewall and the admin role read this table** |
| `patients` | id (pseudonymous), age, sex, nationality_group, preferred_language, literacy_level (1–3), occupation_type, shift_pattern (`day`, `night`, `rotating`, `split`), preferred_days (text[]), home_area, distance_km, insurance_tier (`thiqa`, `enhanced`, `basic`), prior_no_shows, has_smartphone, preferred_channel (`whatsapp`, `sms`, `call`, `in_person`) |
| `consents` | id, patient_id, scope (`outreach`, `data_for_model`, `share_with_clinic`), granted (bool), granted_at, revoked_at, channel |
| `screening_events` | id, patient_id, program, test_code, value_numeric, value_text, severity, resulted_at, source (`synthetic`, `fhir_import`) |
| `care_loops` | id, screening_event_id, patient_id, state, sla_due_at, assigned_to (user), priority_score, risk_dropoff, uplift, last_contact_at, closed_at |
| `loop_events` | id, loop_id, from_state, to_state, actor (user / system / patient), reason, payload jsonb, prev_hash, hash, created_at |
| `risk_scores` | id, loop_id, model_version, p_dropoff, p_return_if_contacted, p_return_if_not, uplift, shap_top jsonb, counterfactuals jsonb, scored_at |
| `content_templates` | id, program, severity, key (`result_explain`, `next_step`, `cost_info`, `teach_back_q`, ...), language (`en` master), body, approved_by, approved_at, version, status (`draft`, `approved`, `retired`) |
| `approved_translations` | id, template_id, language, body, approved_by, approved_at — human-checked fallbacks |
| `conversations` | id, loop_id, channel, language, started_at, ended_at, magic_token_hash |
| `messages` | id, conversation_id, sender (`patient`, `navigator_ai`, `human`), text, text_en, template_id, translation_check_id, red_flag (bool), created_at |
| `translation_checks` | id, source_en, translated, back_translated, judge_score (0–1), entity_match (bool), discrepancies jsonb, passed (bool), fell_back (bool) |
| `teach_back_attempts` | id, loop_id, question, patient_answer, answer_en, rubric jsonb, passed (bool), feedback |
| `escalations` | id, loop_id, reason (`red_flag`, `sla_breach`, `translation_fail`, `refusal_review`, `llm_refusal`), status (`open`, `ack`, `resolved`), assigned_to, notes |
| `appointments` | id, loop_id, slot_id, status (`booked`, `attended`, `no_show`, `cancelled`), match_reasons jsonb |
| `review_queue` | id, item_type, item_id, reason, status, reviewer_id |
| `model_registry` | id, name (`risk`, `uplift_t0`, `uplift_t1`), version, metrics jsonb, calibration jsonb, fairness jsonb, trained_at, artifact_path, is_active |
| `sim_runs` | id, policy, params jsonb, seed, results jsonb, created_by, created_at |
| `fairness_snapshots` | id, computed_at, group_by, metrics jsonb |

Add indexes on `care_loops(state)`, `care_loops(sla_due_at)`, `care_loops(priority_score desc)`, `screening_events(patient_id)`, and `loop_events(loop_id, created_at)`.

---

## 6. Synthetic data generator (`app/synth/`)

There is **no Java or Synthea dependency.** Build the generator in pure Python. Optionally, write a small script that imports Synthea FHIR bundles if they exist.

`generate_population(n=5000, seed=42)` creates patients whose distributions look like a Gulf-city population (ILLUSTRATIVE, configurable in `synth/config.yaml`):
- Nationality groups: Emirati, South Asian (Indian, Pakistani, Bangladeshi), Filipino, Arab expatriate, Western, Other.
- Language follows nationality: ar / ml / hi / ur / bn / tl / en.
- Occupation (office, construction, domestic, retail, driver, healthcare, hospitality) is correlated with shift pattern, insurance tier and literacy.

**Screening events:** about 30% of patients have one or more abnormal results across the three programs, with severities drawn from §4.1.

**Ground-truth behaviour model (hidden from the ML models, used to create labels and to drive the twin):**

```
logit(p_return_no_outreach) = b0
    − a1·language_mismatch_with_default_SMS(en/ar)
    − a2·(shift in {night, rotating})
    − a3·distance_km/10
    − a4·prior_no_shows
    − a5·(insurance_tier == basic)
    + a6·severity_level
    − a7·(literacy_level == 1)

treatment_effect(outreach) = heterogeneous:
    larger when language-matched outreach fixes a mismatch,
    larger when a shift-compatible slot is offered,
    near zero for people who would return anyway or who have very high barriers (cost)
```

- Coefficients live in `synth/config.yaml`, marked ILLUSTRATIVE.
- **Simulated historical trial:** randomly assign 50% of past loops to outreach, then sample outcomes. This gives the uplift model valid training data, and because the true treatment effect is known, Qini/AUUC can be evaluated honestly.
- Split the data into train / validation / test with a fixed seed.

**Demo personas** (fixed IDs, always present after `make seed`):

| Persona | Profile | Result | Story beat |
|---|---|---|---|
| **Ramesh K.** | 41, Malayalam, construction, night shift, basic insurance, 28 km away, 2 prior no-shows | HbA1c 6.1 (prediabetes) | High drop-off risk, high uplift. Navigator in Malayalam books a Friday-evening slot. Teach-back passes |
| **Fatima A.** | 52, Arabic, office, Thiqa | BI-RADS 4 | Urgent. Red-flag phrase in chat ("I found a lump that is bleeding") → instant escalation to a nurse |
| **Joy M.** | 34, Tagalog, domestic worker, no free weekdays | FIT positive | Cost fear → cost-info template → books with employer-day-off slot |
| **Imran S.** | 29, Urdu, driver, rotating shift | HbA1c 7.4 | Translation QA catches a number mismatch → falls back to the approved translation |
| **Sara L.** | 45, English, office | HbA1c 5.9 | Low uplift (would return anyway). Shows why uplift ranks her below Ramesh |

---

## 7. ML: risk, uplift, explanation, counterfactuals (`app/ml/`)

### 7.1 Features
`features.py` builds one feature vector per care loop from the patient, screening event and history: age, sex, language, literacy, occupation, shift, distance, insurance tier, prior no-shows, smartphone, channel, program, severity, days since result, language-mismatch flag, and weekday-availability flags. Categorical features are one-hot encoded (or use LightGBM categorical support). Save the feature list together with the model.

### 7.2 Drop-off risk model
- LightGBM binary classifier: target = did NOT attend within the SLA.
- Calibrate with isotonic regression (`CalibratedClassifierCV`, cv="prefit" on the validation set).
- Metrics stored in `model_registry`: AUROC, AUPRC, Brier score, a calibration curve (10 bins), and the same metrics **per language group and per insurance tier**.

### 7.3 Uplift model (T-learner)
- Two LightGBM classifiers: `m1` is trained on loops that got outreach and `m0` on loops that didn't. `uplift = P(return | outreach) − P(return | no outreach)`.
- Implement **Qini curve and AUUC by hand** (no extra library). Report them against the known ground-truth effect from the generator.
- Report a baseline comparison: uplift ranking vs risk ranking vs random, as Qini curves.

### 7.4 Explanations
- SHAP `TreeExplainer` on the risk model. Store the top 5 contributing features per loop, with plain-English labels from `ml/feature_labels.yaml` (for example `shift_pattern=night` → "Works night shifts").

### 7.5 Counterfactual "what would help"
- For each loop, evaluate the uplift model under a small set of **actionable** changes only: channel (whatsapp/call/in_person), language-matched outreach (yes/no), offered slot type (evening/Friday/near-home), cost info sent (yes/no).
- Never change immutable attributes (age, sex, nationality).
- Return the top 3 interventions by predicted return probability, as in `[{"actions": [...], "p_return": 0.47, "delta": +0.28}]`.

### 7.6 Prioritisation
`priority = severity_weight × uplift` (the default "WASL" policy), and three alternatives the user can switch between:
- `risk_only`: severity_weight × p_dropoff
- `uplift`: the default
- `uplift_fair`: uplift with a **fairness constraint**. Each language group's share of the daily call budget is at least `need_share × (1 − ε)`, where `need_share` is that group's share of open high-severity loops. Solve with a greedy algorithm and document it.

A **daily outreach budget** (default 200 contacts/day, configurable) picks the top-N patients for the worklist.

### 7.7 Training pipeline
`python -m app.ml.train --seed 42` trains every model, writes artifacts to `backend/artifacts/`, registers versions in `model_registry`, scores all open loops, and writes `docs/MODEL_CARD.md` sections from metrics (this happens automatically on `make train`).

---

## 8. Multilingual Care Navigator (`app/navigator/`, `app/llm/`)

### 8.1 LLM provider interface (`llm/base.py`)

```python
class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...
    def complete_text(self, system: str, user: str) -> str: ...
```

- `MockProvider` (default, deterministic):
  - Translation looks up `fixtures/approved_translations/*.json`. If no entry exists, it returns the English text prefixed with `[{lang}]`.
  - Back-translation returns the source text.
  - The judge returns a pass, **except** for the Imran persona fixture, which deliberately contains a wrong number so the demo shows QA catching it.
  - Teach-back is graded by keyword rubric matching.
  - Red-flag detection uses the lexicon only.
- `AnthropicProvider`, enabled with `LLM_PROVIDER=anthropic` plus `ANTHROPIC_API_KEY`:
  - Use the official `anthropic` Python SDK: `anthropic.Anthropic().messages.create(...)`.
  - Default model: `LLM_MODEL=claude-opus-5-5` (configurable through env; `claude-sonnet-5-5` or `claude-haiku-5-5` are cheaper options for high-volume chat).
  - For JSON outputs, pass `output_config={"format": {"type": "json_schema", "schema": <schema with additionalProperties: false and required>}}`, then `json.loads` the first text block.
  - Pass `output_config={"effort": "low"}` for translation and chat turns (and include it alongside `format` when both apply). The model's default effort is `medium`.
  - **Do not send** `temperature`, `top_p`, a `thinking: {"type": "disabled"}` setting, or an assistant-prefill message. These return HTTP 400 on this model family.
  - Always check `response.stop_reason`. If it is `"refusal"` or `"max_tokens"`, do not use the output: fall back to the approved template text and create an `escalations` row with reason `llm_refusal`.
  - Use `max_tokens=2000` for chat turns.
  - Catch `anthropic.RateLimitError`, `anthropic.APIConnectionError` and `anthropic.APIStatusError` separately. On any error, fall back to `MockProvider` behaviour and log the event.
- Optional `AzureOpenAIProvider` with the same interface.

### 8.2 PII firewall (`llm/pii_firewall.py`)
- Before any LLM call, replace the patient's name, phone, Emirates ID, patient ID, clinic staff names and exact addresses with tokens like `⟦NAME_1⟧`. Also use regexes for phone numbers, emails, ID patterns and dates of birth.
- After the call, restore the tokens.
- Unit test: no original PII string ever appears in the outgoing payload. Log a hash of the redacted payload, not the payload itself.

### 8.3 Message pipeline (every outgoing patient message)

```
approved EN template (+ patient-safe variables)
  → LLM "simplify to literacy level L" (EN)        [keeps every number and test name]
  → LLM translate to patient language
  → LLM back-translate to EN
  → translation_qa: (a) deterministic entity check — numbers, units, dates, test names identical
                    (b) LLM judge: medical meaning preserved? score 0–1 + discrepancies
  → pass (score ≥ 0.85 AND entity_match)  → send
  → fail → send approved_translation if one exists, else EN + interpreter offer; add to review_queue
```

Store every step in `translation_checks`. Show this pipeline visually on the Loop Detail page ("Translation QA ✓ 0.93").

### 8.4 Conversation flow (`navigator/flow.py`)

The flow is a deterministic finite-state dialogue. The LLM is used only for understanding free text and phrasing replies.

1. **Greeting + consent check.** If there is no `outreach` consent, stop.
2. **Explain the result** (template `result_explain`), then **next step** (`next_step`).
3. **Barrier discovery:** "What could make it hard to come?" The LLM classifies the free-text answer into `{time, cost, transport, fear, language, family, none}` using the JSON schema.
4. **Barrier response:** use the matching approved template (for example `cost_info`), plus smart slot suggestions (§9).
5. **Booking:** the person picks a slot and the appointment is created → loop moves to `BOOKED`.
6. **Teach-back:** "To make sure I explained clearly, can you tell me in your own words what the test showed and what you will do next?" The LLM grades the answer against the rubric `{understands_result, knows_next_step, knows_when}`. A pass → `UNDERSTOOD`. A fail → re-explain more simply once, then ask a human navigator.
7. **Reminders** 48 h and 2 h before the appointment (simulated in demo mode).
8. **Red-flag monitor on every patient message:**
   - Check against a multilingual lexicon (`fixtures/red_flags/*.yaml`, e.g. chest pain, bleeding, fainting, suicidal thoughts, very high sugar symptoms) and against an LLM classifier.
   - On a hit, immediately reply with the approved urgent-care message (UAE emergency number 999), create an `escalation`, and alert the dashboard. The AI stops navigating until a human acknowledges.
9. **Refusal:** give the risk explanation once and confirm the person understands. Then record `DECLINED` with reason and stop outreach.

**Navigator system prompt** (`navigator/prompts.py`) must state:
- You are a care navigator, not a doctor. Never diagnose, prescribe, or change clinical content.
- Only rephrase the provided approved text. Keep all numbers and test names exactly.
- Use plain words at literacy level {L}, short sentences, and a warm, respectful tone that fits the person's culture.
- If unsure, say a human will help.

### 8.5 Patient access
- The patient chat opens through a **magic link** (`/c/{token}`) with no login. The token is hashed in the database, expires after 14 days, and is scoped to one loop.
- The page is a mobile-first PWA view.

---

## 9. Barrier-aware smart scheduling (`app/scheduling/`)

`suggest_slots(loop_id, k=3)` scores free slots with:

```
score = w1·shift_compatible + w2·preferred_day + w3·(1/(1+distance_km/5))
      + w4·language_match_clinician + w5·evening_or_friday_if_needed − w6·days_until_slot/30
```

- It returns the top-k slots with human-readable `match_reasons`, for example ["Friday evening — fits night shift", "Malayalam-speaking clinician", "8 km from home"].
- Seed 6 clinics across city areas with slots for the next 30 days, including evening and Friday sessions.

---

## 10. Care-Pathway Digital Twin (`app/twin/`)

### 10.1 System twin (SimPy)

**Entities:**
- Patients, generated from the synthetic population, with the **ground-truth behaviour model** (§6).
- Navigators as a `simpy.Resource` with capacity = navigator count; each call takes about 15 minutes.
- Clinic slots as a `simpy.Resource` per clinic, with daily capacity.

**Process per abnormal result:**
1. Result arrives (spread over the horizon).
2. The policy decides on outreach and channel.
3. If outreach is chosen, wait for navigator capacity.
4. The return probability is the ground truth plus the policy's effect.
5. The person books, waits for a slot and attends.
6. The loop closes.

**Policies** (pluggable functions): `no_outreach`, `sms_everyone`, `risk_ranked`, `wasl_uplift`, `wasl_uplift_fair`. Each runs under the same daily contact budget.

**Parameters** (sliders in the UI): horizon days (default 180), number of navigators, daily contact budget, clinic capacity multiplier, extra evening/Friday sessions (bool), extra-language navigator (choose a language), SMS cost, call cost, visit cost, seed.

**Outputs per run:**
- Loop-closure rate overall and by language / insurance tier / program
- Median and 90th-percentile days to follow-up
- Navigator utilisation
- Clinic queue length over time
- Cost per closed loop
- Fairness gap (max − min closure rate across language groups)
- A daily time series for charts

**Sensitivity analysis:** run each policy with the uplift effect scaled by 0.5, 1.0 and 1.5. Report whether WASL still beats the baselines (a robustness badge).

**Calibration statement:** the twin's no-outreach closure rate is tuned to match the synthetic historical data. Show the match in the UI ("Twin calibrated: simulated 61.8% vs historical 62.3%").

Store results in `sim_runs`. Runs execute as FastAPI background tasks; the frontend polls the run status. Target: 5,000 patients × 5 policies in under 20 s.

### 10.2 Patient twin (clinician-only)
- A Markov model per program with yearly transition probabilities (for example normal → prediabetes → diabetes → complications). These are ILLUSTRATIVE, configurable in `twin/markov.yaml`, and the UI shows the label "illustrative, not for clinical decisions".
- It projects the probability of progression if follow-up is delayed 3 / 6 / 12 months, with an uncertainty band computed by sampling the parameters over a ±range.
- **It is shown only to clinician and coordinator roles, never to patients.** The API enforces this through RBAC.

---

## 11. Fairness, governance and trust (`app/fairness/`, `api/governance.py`)

- **Fairness metrics** by language group, nationality group, insurance tier and sex:
  - Loop-closure rate
  - Model calibration (Brier score per group)
  - True positive rate of the high-risk flag (equal opportunity)
  - Share of outreach budget vs share of need
- Disparity highlights: red if a group is below 80% of the best group (the four-fifths rule, as a heuristic).
- **Model card page:** intended use, out-of-scope uses, training data (synthetic), metrics, per-group metrics, calibration plot, limitations, owner and version.
- **Consent center:** view, grant and revoke consent per scope. Revoking `outreach` immediately stops navigator messages, which a test confirms.
- **Audit:** a "Verify chain" button and a downloadable audit log (CSV).
- **Human oversight:** review queue for translation failures, teach-back failures, refusals and LLM refusals.
- **RBAC matrix**, enforced in the API and tested:

| Capability | admin | coordinator | clinician | navigator |
|---|---|---|---|---|
| Worklist / loops | ✓ | ✓ | ✓ | ✓ (assigned only) |
| PII (patient_identity) | ✓ | ✓ (masked) | ✓ (masked) | ✓ (first name only) |
| Patient twin | ✓ | ✓ | ✓ | ✗ |
| Approve templates | ✓ | ✗ | ✓ | ✗ |
| Run Policy Twin | ✓ | ✓ | ✓ | ✗ |
| Governance / audit | ✓ | ✓ (read) | ✓ (read) | ✗ |

Seed users (password `demo1234`, demo only): `admin@wasl.demo`, `coord@wasl.demo`, `clinician@wasl.demo`, `nav@wasl.demo`.

---

## 12. API endpoints (FastAPI, all under `/api`)

Use OpenAPI tags. Every list endpoint is paginated (`?page=&size=`). The frontend uses a typed client generated from or hand-mirrored to `/openapi.json`.

```
POST   /auth/login                         → JWT
GET    /auth/me

GET    /dashboard/kpis                     → open loops, closure rate 30d, median days, breaches, escalations
GET    /dashboard/funnel?program=&group=   → counts per state
GET    /worklist?policy=uplift|risk_only|uplift_fair&budget=200
GET    /loops/{id}                         → loop + patient (role-masked) + timeline + scores + why + counterfactuals
POST   /loops/{id}/transition              → {to_state, reason}  (validated)
POST   /loops/{id}/assign
POST   /loops/{id}/outreach                → starts conversation, returns magic link (demo shows QR code)
GET    /loops/{id}/patient-twin            → clinician/coordinator only

GET    /c/{token}                          → patient conversation bootstrap (language, messages)
POST   /c/{token}/message                  → patient message → navigator reply(s)
GET    /c/{token}/slots                    → smart slot suggestions
POST   /c/{token}/book                     → {slot_id}

GET    /escalations?status=open
POST   /escalations/{id}/ack | /resolve

POST   /twin/runs                          → {policies[], params} → run id (background)
GET    /twin/runs/{id}                     → status + results
GET    /twin/runs?limit=                   → history for comparison
POST   /twin/sensitivity                   → runs ×0.5/1.0/1.5 for chosen policies

GET    /fairness/metrics?group_by=language|nationality_group|insurance_tier|sex
GET    /governance/model-card
GET    /governance/calibration
GET    /governance/audit/verify
GET    /governance/audit/export.csv
GET    /review-queue  · POST /review-queue/{id}/decide
GET    /consents/{patient_id} · POST /consents/{patient_id}

GET    /content/templates · POST /content/templates · POST /content/templates/{id}/approve
GET    /content/translation-checks?failed=true

GET    /roi?abnormal_per_year=&cost_sms=&cost_call=&cost_visit=&late_stage_cost=   → from latest twin run

GET    /fhir/Observation?patient= · POST /fhir/Bundle (import)
GET    /fhir/Task/{loop_id} · GET /fhir/Appointment/{id}

POST   /demo/reset                         → wipe + seed + train + score (admin; enabled only when DEMO_MODE=true)
POST   /demo/advance-clock?days=           → moves the simulated clock to show SLA breaches and reminders
GET    /health
```

Use a **simulated clock** service (`app/clock.py`). In demo mode, `now()` returns real time plus an offset changed by `advance-clock`. All SLA logic uses this clock.

---

## 13. Frontend pages (React)

Design language: clean clinical UI, Tailwind, teal/indigo accent, and status colours that also carry text or icons (colour must never be the only signal). Support dark mode. Keyboard-accessible, with ARIA labels. RTL switching for `ar` and `ur` uses `dir="rtl"` on the root.

| Route | Page | Contents |
|---|---|---|
| `/login` | Login | Role quick-select buttons for the demo users |
| `/` | **Command Center** | KPI tiles (open loops, 30-day closure %, median days, SLA breaches, open escalations); **funnel chart** RESULT_RECEIVED→CLOSED with drop-off % per step; breaches by program; live escalation feed (poll every 5 s); "Advance clock +7 days" (demo) |
| `/worklist` | **Worklist** | Table ranked by priority. Policy switch (Risk / Uplift / Uplift+Fair) and budget slider. Columns: patient (masked), program, severity, state, SLA countdown, P(drop-off), uplift, top reason chip. Bulk "Start outreach" |
| `/loops/:id` | **Loop Detail** | Timeline of hash-chained events (✓ verified badge); **Why card** (SHAP bars with plain labels); **What would help** (counterfactual cards with Δ probability); conversation transcript with "Translation QA ✓ 0.93" and teach-back result chips; smart slots; **patient twin chart** (clinician only); actions (assign, transition, escalate, record refusal) |
| `/c/:token` | **Patient Chat** (mobile) | Language picker (7), RTL, large text, chat bubbles, quick-reply buttons, slot cards with match reasons, mic button (Web Speech) and play-aloud (TTS), "Talk to a human" button always visible, emergency banner on red flag |
| `/twin` | **Policy Twin** | Parameter sliders; policy multi-select; Run; **side-by-side comparison** (bar chart of closure %, cost per closed loop, fairness gap; line chart of cumulative closures over time; clinic queue chart); sensitivity table with robustness badge; calibration statement; "ILLUSTRATIVE ASSUMPTIONS" expandable list |
| `/fairness` | **Fairness & Governance** | Group selector; closure rate by group (bars with the 80% line); calibration per group; budget share vs need share; model card; "Verify audit chain" button with result; consent center; review queue |
| `/content` | **Content Studio** | Templates by program/severity; approve workflow; translation-check log with failed items highlighted; preview a message in any language through the full QA pipeline |
| `/roi` | **Impact & ROI** | Inputs (abnormal results/year, costs); outputs from the latest twin run: extra loops closed per 1,000, cost per closed loop, illustrative late-stage cases avoided (range), net cost/benefit; download as PDF (browser print stylesheet) |
| (overlay) | **Judge Mode** | Button in the header. Calls `/demo/reset`, then runs a 10-step guided tour (§16) with spotlight overlays and Next/Back. Build the tour engine yourself with a small component; no heavy library |

The frontend must work against the backend at `VITE_API_URL` (default `http://localhost:8000`). Every page has a loading skeleton, an empty state and an error state.

---

## 14. Build phases with acceptance checks

Do these **in order**. After each phase, run `make test` and the listed checks, then report.

### Phase 0 — Skeleton
- Repo layout, docker-compose (postgres + backend + frontend), Makefile, `.env.example`, `/api/health`, React app with the router and an empty layout.
- ✅ `make up` → `curl localhost:8000/api/health` returns `{"status":"ok"}`. The frontend loads at `localhost:5173`.

### Phase 1 — Data layer + synthetic data
- SQLAlchemy models, Alembic migration, synthetic generator, demo personas, clinics/slots, users, approved templates (EN) and fixture translations for the persona messages in all 7 languages (mark them `demo fixture — not clinically validated`).
- ✅ `make migrate seed` creates about 5,000 patients and about 1,500 loops. All 5 personas exist. Re-running with the same seed gives identical row counts and a checksum match.

### Phase 2 — Loop engine + audit chain + clock
- State machine, transitions API, SLA job, escalations, simulated clock, hash chain and verify endpoint.
- ✅ Tests: invalid transition → 409. Advancing the clock past the SLA → `BREACHED` + escalation. Tampering with one `loop_events` row → verify returns `valid=false` with the right `broken_at`.

### Phase 3 — ML
- Features, risk model + calibration, T-learner uplift, Qini/AUUC, SHAP, counterfactuals, prioritisation (3 policies + fairness constraint), model registry, scoring job, `make train`.
- ✅ Risk AUROC > 0.70 on test. WASL uplift Qini AUUC > risk-ranking AUUC > random (on synthetic ground truth). Ramesh ranks above Sara under `uplift`. The fairness-constrained allocation respects the minimum shares (unit test).

### Phase 4 — Navigator + LLM layer
- Provider interface, Mock + Anthropic providers, PII firewall, translation QA pipeline, dialogue flow, barrier classification, teach-back, red flags, magic links, smart scheduling, booking.
- ✅ With `LLM_PROVIDER=mock`, an end-to-end test drives the Ramesh conversation to `UNDERSTOOD` + `BOOKED`. The Fatima red-flag message creates an escalation within one request. Imran's translation check fails and falls back. The PII firewall test confirms no identity strings in LLM payloads. Revoked consent blocks outreach.

### Phase 5 — Digital twin
- SimPy system twin, 5 policies, sensitivity, calibration statement, Markov patient twin, background runs.
- ✅ 5,000 patients × 5 policies finish in under 20 s. Same seed → identical results. `wasl_uplift` closure rate is above `risk_ranked`, which is above `sms_everyone`, which is above `no_outreach` at ×1.0. The robustness badge is computed. The patient-twin endpoint returns 403 for the navigator role.

### Phase 6 — Fairness, governance, FHIR, ROI
- Fairness metrics, model card generation, calibration endpoint, consent center, review queue, FHIR mappers (import a sample Bundle from `fixtures/fhir/sample_bundle.json`), ROI endpoint, CSV audit export, RBAC tests.
- ✅ Importing the sample FHIR bundle creates a new loop. Exported FHIR resources have the correct `resourceType` and required fields. The RBAC test matrix passes.

### Phase 7 — Frontend
- All pages in §13, i18n with 7 languages for the patient chat, RTL, charts, polling, role-based navigation.
- ✅ Manual check (and Playwright smoke test if available): log in as coordinator → worklist → open Ramesh → start outreach → open the magic link → complete the chat in Malayalam → loop shows BOOKED + UNDERSTOOD. The twin run renders the comparison charts. Arabic chat renders RTL.

### Phase 8 — Judge Mode, docs, polish
- Guided tour, `make demo` (reset + seed + train + score + start), all docs in `docs/`, README with a mermaid architecture diagram and screenshots section, and a final pass for loading/error/empty states.
- ✅ From a clean clone: `cp .env.example .env && make demo` brings up a working demo in one command. The Judge Mode tour runs start to finish without errors.

---

## 15. Environment variables (`.env.example`)

```
DATABASE_URL=postgresql+psycopg://wasl:wasl@db:5432/wasl
JWT_SECRET=change-me
DEMO_MODE=true
SEED=42
POPULATION_SIZE=5000
DAILY_OUTREACH_BUDGET=200

LLM_PROVIDER=mock            # mock | anthropic | azure_openai
LLM_MODEL=claude-opus-5-5    # used when LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=

TRANSLATION_PASS_THRESHOLD=0.85
SLA_DAYS_URGENT=7
SLA_DAYS_HIGH=21
SLA_DAYS_ROUTINE=60

VITE_API_URL=http://localhost:8000
```

---

## 16. Judge Mode tour script (10 steps, ~3 minutes)

1. **Command Center:** "1,500 abnormal results. 38% never complete follow-up (simulated baseline). Each one is a missed early diagnosis."
2. **Funnel:** the biggest drop is between NOTIFIED and BOOKED, so the problem is understanding and access, not detection.
3. **Worklist:** switch Risk → Uplift. "Sara drops down: she would return anyway. Ramesh rises: outreach changes his outcome."
4. **Ramesh's Why card + What would help:** night shift, 28 km away, 2 missed visits → "Malayalam call + Friday-evening slot: 0.19 → 0.47".
5. **Patient chat (Malayalam):** explanation → barrier "I work nights" → Friday-evening slot → booked → **teach-back passes**. Show the "Translation QA ✓" chip.
6. **Imran:** the translation check caught a number mismatch → safe fallback + human review. "The AI is checked before it speaks."
7. **Fatima:** red-flag message → instant escalation → nurse acknowledges on the dashboard.
8. **Policy Twin:** run 5 policies. WASL uplift + fairness closes the most loops at the lowest cost per closed loop, with the smallest fairness gap. The robustness badge holds at ±50%.
9. **Fairness & Governance:** closure by language before vs after, calibration, **Verify audit chain ✓**, consent revocation.
10. **ROI + pilot plan:** "Per 1,000 abnormal results: +X loops closed, cost per closed loop Y (illustrative). Pilot: one clinic, one program, 90 days, FHIR-ready."

All numbers in the tour come **live from the API**. Never hard-code numbers in the tour text; use template strings filled from responses.

---

## 17. Documentation the build must produce (needed for submission)

- `docs/TECHNICAL.md`: architecture (mermaid), module descriptions, data flow of one message through the PII firewall → LLM → QA, the state machine diagram, the twin design, and a tech-stack rationale.
- `docs/MODEL_CARD.md`: generated from `model_registry` plus fixed sections.
- `docs/DATA_CARD.md`: generator design, distributions, the ground-truth behaviour model, and **why synthetic data** (privacy, no real patient data in a prototype).
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md`:
  - Every ILLUSTRATIVE parameter, listed with its location in config.
  - Synthetic data only.
  - The uplift results depend on the simulated trial.
  - Translations need clinical validation.
  - The patient twin is not for clinical decisions.
  - The twin is calibrated only to synthetic history.
- `docs/RESPONSIBLE_AI.md`: no diagnosis, human-in-the-loop points, PII firewall, consent, fairness monitoring, audit chain, failure modes and fallbacks, data minimisation, and what would be needed for real deployment (ethics approval, DoH data rules, clinical validation, interpreter services).
- `docs/PITCH.md`: the §16 script plus this judging-criteria mapping:

| Judging criterion | Where WASL proves it |
|---|---|
| Health impact & clinical relevance | Loop closure ↑, days to follow-up ↓, focus on the drop-off step |
| Technical depth & architecture | Uplift T-learner + Qini, SHAP, counterfactuals, SimPy twin, translation QA, hash-chained audit |
| Working solution & demo quality | One-command demo, Judge Mode tour, live numbers |
| Responsible AI, safety, governance | No-diagnosis guardrails, PII firewall, teach-back, red-flag escalation, fairness constraint, consent, model card |
| Scalability & deployment readiness | FHIR R4, provider-agnostic LLM, Postgres, docker-compose, RBAC |
| Commercial viability & path to pilot | ROI calculator, cost per closed loop, 90-day single-clinic pilot plan |

---

## 18. Definition of done (final checklist)

- [ ] `cp .env.example .env && make demo` works from a clean clone with **no API keys**
- [ ] `make test` passes; backend coverage ≥ 70% on `loop_engine`, `ml`, `navigator`, `llm`, `twin`, `fairness`
- [ ] All 5 personas behave as in §6
- [ ] The Judge Mode tour completes with live numbers
- [ ] Switching `LLM_PROVIDER=anthropic` with a key works for translation, judge, barrier classification and teach-back, with fallbacks on errors and refusals
- [ ] Arabic and Urdu render RTL; all 7 chat languages load
- [ ] Every ILLUSTRATIVE number is visible as such in the UI and listed in the docs
- [ ] The "WASL does not diagnose" notice is in the UI footer and the docs
- [ ] Audit-chain tamper test passes
- [ ] Docs in §17 exist and are filled in

---

## 19. Scope guards (cut in this order if time runs short)

1. Voice (Web Speech) — keep text chat
2. Azure OpenAI adapter
3. FHIR import (keep export)
4. ROI PDF export (keep the page)
5. Patient twin uncertainty band (keep the point estimate)

**Never cut:** uplift prioritisation, translation QA, teach-back, red-flag escalation, the Policy Twin comparison, the fairness panel, Judge Mode.

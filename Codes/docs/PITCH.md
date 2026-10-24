# WASL — 3-minute pitch (Judge Mode script)

**Track:** Future Health Challenge · Population Health — Closing the Screening-to-Care Loop.
**One line:** *No abnormal result left behind.*
**Live demo:** https://wasl.koushikdeb.com — jury login **DevTest / DevTest11** → **Judge Mode** (top right).

Judge Mode resets the demo (same seed → same numbers) and walks through 10 steps. Each step performs the real action and fills its narration from the API; numbers below are what seed 42 produces.

1. **Command Center.** 1,591 abnormal results; in the simulated as-is baseline 47 % never complete follow-up within 30 days.
2. **Funnel.** 1,408 notified, only 755 booked; the biggest single drop is before "Engaged" (−33 %): the problem is understanding and access, not detection.
3. **Worklist: Risk → Uplift.** 60 people swap. Those leaving average 2.3 past no-shows — a call barely moves them; those joining add ≈ +8.6 expected returns from the same 200 calls. Imran rises #95 → #51; Sara (would return anyway) stays near the bottom.
4. **Ramesh — Why + What would help.** SHAP: default SMS not in his language, 2 missed visits, 28 km. Counterfactual: phone call in Malayalam + evening slot + cost information → 0.14 → 0.65.
5. **Patient chat in Malayalam.** Explanation → barrier "I work nights" → teach-back passes → Friday-evening slot booked. Every message shows "Translation QA ✓".
6. **Imran.** The machine translation turned 7.4 into 4.7; the entity check caught it, the patient received the clinician-approved translation, and a human review item opened. *The AI is checked before it speaks.*
7. **Fatima.** "I found a lump that is bleeding" (Arabic) → urgent-care message with 999, red-flag escalation in ≈ 40 ms, AI paused until a nurse acknowledges.
8. **Policy Twin.** 5,000 patients × 5 policies on common random numbers: WASL uplift closes 79.5 % vs 59.7 % (no outreach) and 70.2 % (risk-ranked), at AED 95 per extra closed loop vs AED 178. The fairness floor cuts the allocation gap from 15.8 % to 4.3 %. Robust at ×0.5 / ×1.0 / ×1.5 effect.
9. **Fairness & Governance.** Verify audit chain ✓ (~6,750 events). Closure gap by language 40.9 % → 15.1 % in the twin. Consent revocation stops outreach.
10. **ROI + pilot.** Per 1,000 abnormal results +187 loops closed; ~AED 100 outreach per extra closed loop; 80–235 late-stage cases avoided per 20,000 results/year (illustrative). Pilot: one clinic, one program, 90 days, FHIR-ready.

## Judging-criteria mapping
| Judging criterion | Where WASL proves it |
|---|---|
| Health impact & clinical relevance | Loop closure ↑ (59.7 → 79.5 % in the twin), days to follow-up ↓ (14.2 → 11.1 median), focus on the drop-off step (notified → engaged/booked) |
| Technical depth & architecture | Uplift T-learner + hand-written Qini/AUUC vs known ground truth, SHAP, counterfactuals, SimPy twin with common random numbers + sensitivity, translation QA with independent judge, hash-chained audit |
| Working solution & demo quality | Hosted live; one-command `make demo`; Judge Mode tour with live numbers; 64 backend tests + Vitest |
| Responsible AI, safety, governance | No-diagnosis guardrails, approved-template-only content, PII firewall, teach-back, red-flag escalation, fairness floors, consent, model card, review queue |
| Scalability & deployment readiness | FHIR R4 import/export, provider-agnostic LLM (mock / Anthropic / relays / Azure), PostgreSQL, Docker Compose, RBAC, Alembic |
| Commercial viability & path to pilot | ROI calculator with ranges, cost per extra closed loop, 90-day single-clinic randomised pilot that also re-trains the uplift model |

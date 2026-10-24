# Responsible AI

> **WASL does not diagnose.** It explains a screening result, helps the person act on it, and escalates to a human. This sentence is in every page footer, the patient chat, the API description and these docs.

## Safety by design
| Risk | Control | Where |
|---|---|---|
| AI invents medical facts | Patient-facing content comes only from clinician-approved templates; the LLM may only simplify, personalise and translate. Draft templates are invisible to patients until a clinician approves them. | `content_templates`, Content Studio |
| Mistranslated numbers or meaning | Back-translation + deterministic entity check (numbers, units, test names, Eastern digits normalised) + LLM judge from a different model family. Fail → clinician-approved translation or English + interpreter offer, and a human review item. | `llm/translation_qa.py`, `navigator/messaging.py` |
| Model refusal / truncation | Never used: approved text is sent and an `llm_refusal` escalation opens. | `messaging.prepare` |
| Emergencies in chat | Every patient message is checked against multilingual red-flag lexicons *and* an LLM classifier. A hit sends the approved urgent-care message (UAE 999), opens an escalation and pauses the AI until a human acknowledges. | `navigator/flow.py` |
| Misunderstanding | Teach-back: the person explains the result in their own words; graded on result, next step and timing. Two failures → human navigator; booking is never blocked. | `flow._teach_back` |
| Pressure after "no" | Risk explained once in the person's language; a confirmed refusal is recorded as an informed refusal (DECLINED) and outreach stops. | `flow._record_refusal` |

## Human in the loop
* Escalations (red flags, SLA breaches, translation failures, LLM refusals) appear on the Command Center within 5 s.
* Review queue for translation failures, teach-back failures, refusals, LLM refusals and "talk to a human" requests; clinicians approve or reject.
* Coordinators can override any state through validated transitions; DECLINED requires a recorded informed refusal.

## Privacy
* **PII firewall:** names, phone numbers, Emirates ID, patient codes, staff names, e-mails and dates of birth are replaced by tokens (`⟦NAME_1⟧`) before any LLM call and restored afterwards. Only a SHA-256 of the redacted payload is logged. A unit test proves no identity string leaves.
* **Data minimisation:** identity is stored separately from pseudonymous clinical data; role-masked views (admin full, coordinator/clinician masked, navigator first name only). Nationality is not a model feature.
* **Consent:** outreach, data-for-model and share-with-clinic scopes. Revoking outreach stops the navigator immediately (tested).
* **Magic links:** only a hash is stored; 14-day expiry; one loop per link.

## Fairness monitoring
* Closure rate, calibration (Brier), AUROC and true-positive rate of the high-risk flag by language, nationality group, insurance tier and sex; four-fifths rule flags groups below 80 % of the best.
* Budget share vs need share for each policy; the `uplift_fair` policy guarantees each language group ≥ need share × (1 − ε).
* **Known gap, surfaced not hidden:** the high-risk flag's true-positive rate is low for Arabic speakers (0.09 vs 0.70–0.86 for South Asian languages at seed 42) because, in this synthetic population, Arabic speakers mostly return anyway. This is why WASL ranks by **uplift** and audits allocation per group rather than relying on a risk threshold; a real deployment would set group-aware thresholds or review this with the clinical lead.
* The Policy Twin shows the trade-off honestly: plain uplift targeting narrows the *closure* gap the most (0.41 → 0.15 at seed 42), while the fairness floor equalises *allocation* (gap 0.16 → 0.04) for about one point of closure.

## Accountability
* Every loop event is SHA-256 hash-chained (per loop and globally). "Verify chain" recomputes every hash; the Audit tab can demonstrate tampering being detected. CSV export for auditors.
* Model registry with versions, metrics, calibration and per-group metrics; model card regenerated on every training run.

## Failure modes and fallbacks
| Failure | Behaviour |
|---|---|
| No API keys / provider down | Deterministic mock behaviour; the demo runs fully offline |
| LLM transport error mid-pipeline | Task falls back to mock behaviour (logged); result not cached |
| Translation QA fails | Approved translation (or English + interpreter) + review item |
| Red flag | AI paused until a human acknowledges |
| SLA expires | BREACHED + escalation; loop stays actionable |
| Navigator capacity exceeded (twin) | Calls queue; utilisation and delays reported |

## What real deployment would need
Research ethics approval; DoH Abu Dhabi data-protection approvals and an HIE (e.g. Malaffi) integration agreement; clinical validation of templates, thresholds and red-flag lexicons; professional medical translation of every template; interpreter services; a randomised pilot to estimate real uplift; local model retraining and recalibration; a clinical safety case and incident process; security review and penetration test.

# Assumptions and limitations

Every number below is **ILLUSTRATIVE**: a configurable assumption for a demo, not an estimate. The UI marks them with an "ILLUSTRATIVE" badge.

## Illustrative parameters and where they live
| Assumption | Value (default) | Location |
|---|---|---|
| Population distributions (nationality, language, occupation, shift, insurance, literacy) | see file | `backend/app/synth/config.yaml` |
| Abnormal-result rates | HbA1c 19 % base + age/South-Asian terms; FIT 6 %; BI-RADS abnormal 11 % | `synth/config.yaml → abnormal` |
| Ground-truth return model and outreach effects | b0 = 2.05, … | `synth/config.yaml → behaviour` |
| Screening thresholds | HbA1c 5.7/6.5/9.0; FIT positive; BI-RADS 0/4/5 | `backend/app/fixtures/screening_rules.yaml` (standard thresholds — verify with clinical advisor) |
| SLA days | urgent 7 · high 21 · routine 60 | `.env` (`SLA_DAYS_*`) |
| Severity weights in ranking | routine 1.0 · high 1.25 · urgent 1.5 | `backend/app/ml/prioritise.py` |
| Fairness slack ε | 0.10 | `prioritise.allocate`, `TwinParams.fairness_epsilon` |
| Daily outreach budget | 200 (worklist) · 20 (twin) | `.env`, `TwinParams` |
| Navigator call time / day | 15 min / 7 h | `TwinParams` |
| Clinic visits per clinic per day | 8 | `TwinParams.visits_per_clinic_per_day` |
| Native navigator languages | ar, en, hi, ur (others via interpreter at 60 % of the language effect) | `system_twin.NATIVE_NAVIGATOR_LANGS` |
| Evening/Friday slot availability | 60 % (100 % with extra sessions) | `system_twin.simulate` |
| Costs | SMS 0.5 · tailored contact 25 · visit 150 · late-stage case 150,000 AED | `TwinParams`, ROI page inputs |
| P(late-stage disease or complication \| missed follow-up) | DM 2–6 %, CRC 3–8 %, breast 5–12 % | `backend/app/api/roi.py` |
| Patient-twin Markov rates and ±35 % band | see file | `backend/app/twin/markov.yaml` |
| Translation pass threshold | judge ≥ 0.85 and exact entity match | `.env` (`TRANSLATION_PASS_THRESHOLD`) |

## Limitations
* **Synthetic data only.** No result here says anything about real people in Abu Dhabi.
* **Uplift depends on the simulated trial.** Uplift is identifiable only because historical outreach packages were randomised in the simulation. Real deployment needs a randomised (e.g. stepped-wedge) rollout to learn real effects.
* **Translations need clinical validation.** The fixture translations were produced with an LLM for the demo and are marked "demo fixture — not clinically validated". A medical translator must approve every entry before real use. The red-flag lexicons need review by a clinical safety officer.
* **The patient twin is not for clinical decisions.** Its transition rates are illustrative orders of magnitude.
* **The system twin is calibrated only to synthetic history** (59.7 % simulated vs 59.0 % historical no-outreach closure at seed 42).
* **Demo fault injection.** Imran's Urdu number error (7.4 → 4.7) is injected on purpose so the QA catch is reproducible; it is labelled as such in the code and docs.
* **Cost information** templates describe the process ("a small co-payment may apply; staff will confirm") and contain no prices; real benefit rules must come from payers.
* The FHIR BI-RADS coding uses a local code system; HbA1c (LOINC 4548-4) and FIT (LOINC 29771-3) codes should be confirmed with an informatics lead.

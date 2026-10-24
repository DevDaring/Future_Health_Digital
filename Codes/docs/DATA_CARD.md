# WASL Data Card — synthetic population

## Why synthetic data
A prototype must never touch real patient data: no consent, no ethics approval, no Department of Health data-sharing agreement. A seeded generator also lets every judge reproduce identical numbers (`make demo`), and — because the generator knows each person's *true* response to outreach — lets us evaluate uplift models honestly, which is impossible with real observational data.

## Generator (`backend/app/synth/`, pure Python, no Synthea/Java)
`generate_population(n=5000, seed=42)`; every draw goes through one seeded `numpy.random.Generator`. All distributions live in `synth/config.yaml` and are **ILLUSTRATIVE**.

| Attribute | How it is drawn |
|---|---|
| Nationality group | Emirati 19 %, Indian 27 %, Pakistani 12 %, Bangladeshi 7 %, Filipino 10 %, Arab expatriate 13 %, Western 6 %, Other 6 % |
| Preferred language | Follows nationality (ar / ml / hi / ur / bn / tl / en) |
| Occupation | Conditional on nationality (office, construction, domestic, retail, driver, healthcare, hospitality) |
| Shift pattern, insurance tier, literacy, sex | Conditional on occupation (Emiratis: Thiqa) |
| Home area, distance | 11 Abu Dhabi areas; labour-camp areas and construction work → longer trips (log-normal) |
| Prior no-shows | Poisson, higher for night/rotating shifts and low literacy |
| Channel, smartphone, preferred days | Conditional on literacy / shift; domestic workers often have no free weekdays |

**Screening results** (`draw_abnormal_results`): HbA1c (rate rises with age and for South Asian groups), FIT for age ≥ 45, mammogram BI-RADS for women ≥ 40. About 30 % of people have an abnormal result. Severity comes from the clinician-editable thresholds in `fixtures/screening_rules.yaml` (standard clinical thresholds — verify with clinical advisor).

**Live loops (seed 42):** 5,005 patients (incl. 5 personas), 1,591 abnormal results / care loops, with an as-is history (bilingual en/ar SMS only) that produces a realistic funnel and SLA breaches.

## Ground-truth behaviour model (hidden from the ML)
```
logit P(return | no outreach) = b0 − a1·language_mismatch − a2·night_or_rotating − a3·distance/10
                                − a4·prior_no_shows − a5·basic_insurance + a6·severity
                                − a7·low_literacy − a8·no_free_weekdays − decay·days_since_result
effect(outreach package)      = base + language-match (if mismatch) + evening/Friday slot (if shift)
                                + Friday (if no free weekdays) + near-home (if far) + cost info (if basic)
                                + call/in-person (if low literacy)
                                × damping for wrong-language messages, unaddressed severe cost barriers,
                                  and chronic non-attenders (≥ 3 prior no-shows)
```
The effect is heterogeneous by design: near zero for people who return anyway and for very high, unaddressed barriers. Coefficients: `synth/config.yaml → behaviour`.

## Simulated historical trial
≈35,000 historical abnormal results (`simulate_history`; 35,118 at seed 42): 50 % randomly assigned to outreach, each with a **random** package (channel, language match, slot type, cost info). Outcomes sampled from the ground truth. Split 60/20/20 (train/val/test) with a fixed seed. Historical return rate: 59.0 % without outreach, 71.5 % with randomly chosen outreach packages.

## Demo personas (fixed IDs)
| Persona | Profile | Result | Story |
|---|---|---|---|
| Ramesh K. | 41, Malayalam, construction, night shift, basic insurance, 28 km, 2 no-shows | HbA1c 6.1 | High risk + high uplift; Malayalam chat, Friday-evening slot, teach-back passes |
| Fatima A. | 52, Arabic, office, Thiqa | BI-RADS 4 | Red-flag phrase → instant nurse escalation |
| Joy M. | 34, Tagalog, domestic worker, Sunday off | FIT positive | Cost worry → cost-info template → day-off slot |
| Imran S. | 29, Urdu, driver, rotating shift | HbA1c 7.4 | Demo fault injection: simulated MT digit swap 7.4→4.7 caught by QA |
| Sara L. | 45, English, office | HbA1c 5.9 | Low uplift (would return anyway) → ranked far below Ramesh |

## Determinism
`make seed` twice → identical row counts and the same checksum (stored in `demo_state`; covers all attributes, results and loop histories as day offsets). Tested in `tests/test_phase1_data.py`.

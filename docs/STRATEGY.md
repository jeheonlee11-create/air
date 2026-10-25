# AIR — Airspace Incident Record
## Strategy memo v2 — July 28, 2026

Every statement in this memo is tagged:
- **[TESTED]** — verified in this repo by running code (see [AUDIT.md](AUDIT.md), [eval/EVALUATION.md](../eval/EVALUATION.md)).
- **[SOURCED]** — supported by a cited public source, with the URL.
- **[INFERENCE]** — our reasoning from tested/sourced facts; could be wrong.
- **[UNVERIFIED]** — a hypothesis or secondhand claim we have not confirmed. Do not repeat externally.

This memo supersedes v1, which mixed these categories. Section 8 lists the v1 claims we now explicitly retract or downgrade.

---

## 1. What AIR is [TESTED]

AIR reconstructs drone incidents from raw telemetry and produces an explainable, tamper-evident record. In initial testing on public PX4 crashes, it identified procedure violations and sensor conflicts that ordinary log viewers leave investigators to find manually.

Concretely, today: PX4 ULog in → normalized timeline → deterministic findings (every threshold cites its basis) → cross-source conflict findings → procedure PASS/FAIL/NOT_EVALUABLE verdicts against operator-supplied rules → a signed record bundle (RFC 9162 Merkle tree, Ed25519, optional RFC 3161) with a standalone offline verifier. Evaluation on a seeded 100-log public sample: 99% ingestion, 0 uncaught errors, 10/10 deterministic reruns, 5/5 tamper detection, zero false-positive "ends-in-flight" calls (recall vs noisy uploader crash labels: 12%). Full caveats in eval/EVALUATION.md.

**What AIR is not, and must never be marketed as:** court-admissible, legally compliant, legally sufficient, a crash detector, or a guarantee of anything. The cryptography establishes record integrity; legal conclusions belong to lawyers and courts.

## 2. Competitive landscape [SOURCED, research run 2026-07-28]

Method: 13 targeted searches + 8 page fetches on this date. Bounded claim discipline: a capability not shown on a public page is **UNKNOWN — not shown publicly**, never "absent." Products may ship undocumented capabilities; sales decks may exceed websites.

| Product | Replay/reconstruction | Anomaly detection | Procedure conformance (post-hoc, vs operator's own rules) | Cross-source conflict findings | Evidence integrity | Reports | Pricing |
|---|---|---|---|---|---|---|---|
| **Airdata UAV** ([features](https://airdata.com/features), [Wind 3.0](https://airdata.com/blog/2026/wind3.0)) | YES — "Full telemetry playback with map, sensor, weather, and warning overlays"; 3D player; Wind 3.0 marketed for incident causation ("can show whether wind was the cause") | YES — "Trend and anomaly detection across pilots, aircraft, and missions" | UNKNOWN — not shown publicly (manual checklists exist; no telemetry-vs-rules verdicts found) | UNKNOWN — not shown publicly | UNKNOWN — not shown publicly (no hashing/signing/tamper language found on features page) | YES — "audit-ready compliance reports" | Free–$14.99/mo; enterprise custom |
| **PX4 Flight Review** ([docs](https://docs.px4.io/main/en/log/flight_review), [repo](https://github.com/PX4/flight_review)) | YES — plots incl. GPS noise/jamming, vibration FFT, estimator watchdog | PARTIAL — diagnostic plots; separate ecl_ekf scripts | UNKNOWN — no automated verdicts documented | UNKNOWN — innovation ratios are expert-read plots, not packaged findings | UNKNOWN — none documented | UNKNOWN — web share links, no report export documented | Free, BSD-3 |
| **"Drone Incident Insight"** | **No credible product found under this name** (two exact-phrase searches). Near-matches are different things: Drone Industry Insights (market research), DJI Enterprise Insights (blog), AirSight AirGuard (counter-UAS airspace monitoring). If this name came from a private source, we need that source; otherwise treat as nonexistent. | | | | | | |
| **DroneSense** (Versaterm) ([site](https://www.versaterm.com/solution/dronesense/)) | UNKNOWN — not shown publicly | UNKNOWN | UNKNOWN — "policy-driven tools for tracking, auditing and oversight" (program governance language) | UNKNOWN | UNKNOWN — no cryptographic claims on pages fetched | YES — "flight logs can be turned into reports or dashboards" | Not public |
| **Skydio DFR Command / Axon Air** ([CJIS blog](https://www.skydio.com/blog/skydio-cjis-compliance), [Axon Air](https://www.axon.com/products/axon-air)) | UNKNOWN as investigator replay | UNKNOWN | UNKNOWN | UNKNOWN | **YES for captured media** — "SHA256 hashing at the point of capture"; "cryptographic chain-of-custody transparency" into Axon Evidence | Evidence packages via Axon Evidence | Not public |
| **DroneLogbook** ([features](https://www.dronelogbook.com/hp/1/features.html)) | UNKNOWN | UNKNOWN | PARTIAL/adjacent — compliance violation notifications (currency/certs, not telemetry-vs-SOP) | UNKNOWN | UNKNOWN | YES — incident logging; authority-formatted PDFs | Public tiers |
| **Dronedesk** ([compliance blog](https://blog.dronedesk.io/dronedesk-compliance-features/)) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | "auditable trail" language, no cryptographic claims | YES — exports | Public tiers |
| **Flight Reader** ([site](https://www.flightreader.com/)) | PARTIAL — DJI TXT→CSV/KML, charts | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN — none shown | CSV/KML | $79–$379 one-time |

Exact-phrase sweeps for "Merkle", "RFC 3161", "tamper-evident report", digital signatures on drone reports: **no product hits in the searches run** — only academic/engineering material. Same for post-hoc "SOP conformance" products. [SOURCED, bounded by search scope]

**Differentiation assessment [INFERENCE, conservative]:**
- *Signed, offline-verifiable record bundles* — strongest claim. Nothing found combining Merkle + signature + RFC 3161 + offline verifier in drone software. Nearest neighbor is Skydio's SHA256-at-capture chain of custody, which covers **captured media** flowing into Axon's cloud, not an investigator-facing record of the flight itself. Caveat: "chain of custody" vocabulary is heavily owned by Axon/Skydio in public safety; our distinct angle is *offline verification without trusting any vendor cloud*.
- *Post-hoc procedure verdicts vs the operator's own written rules* — survives, with a naming hazard: "conformance monitoring" is becoming regulated UTM vocabulary for something else (real-time intent conformance under proposed Part 108 §108.5). Position as "post-hoc, against your own SOP, with cited evidence."
- *Conflict-as-findings* — survives as packaging, not invention: PX4's own ecl_ekf tooling computes cross-sensor disagreement as expert-read plots. We productize it into plain-language findings. Claim the packaging.
- *Where we are behind:* Airdata leads on replay polish, breadth (200+ aircraft/formats vs our one), distribution (their claimed 450k pilots [SOURCED via [dronelife](https://dronelife.com/2026/05/07/airdata-commercial-drone-alliance-part-108/), their number]), and general compliance-report language. We do not compete on those axes today.

## 3. Regulatory context — stated precisely

**What the rule is [SOURCED]:** DOJ/DHS interim final rule, "Counter-UAS Authority for State, Local, Tribal, and Territorial Law Enforcement and Correctional Agencies," 91 FR 41466 (July 6, 2026), effective July 1, 2026, codified at 6 CFR Part 124 and 28 CFR Part 124 ([Federal Register](https://www.federalregister.gov/documents/2026/07/06/2026-13609/counter-uas-authority-for-state-local-tribal-and-territorial-law-enforcement-and-correctional); law-firm summaries: [Crowell](https://www.crowell.com/en/insights/client-alerts/doj-and-dhs-issue-interim-final-rule-on-state-and-local-counter-drone-authority-under-the-safer-skies-act), [DWT](https://www.dwt.com/blogs/broadband-advisor/2026/07/safer-skies-counter-drone-framework)). Comment period open until September 4, 2026.

**Accurate scope statements (use these words, not v1's):**
- It applies to **covered SLTT law-enforcement and correctional agencies exercising authorized counter-UAS authority** under the SAFER SKIES framework — not to commercial drone operators, not to private critical-infrastructure owners (who received no mitigation authority), and not to anyone outside the authorization.
- **Qualifying mitigation operations carry a 48-hour post-operation reporting requirement** with enumerated data elements (per our reading of §124.13 and Crowell's summary). Detection-tier activity reports semiannually; passive-sensor-only detection that doesn't rely on the Act's authority sits largely outside the rule.
- Required audit trails must be **searchable, protected from unauthorized modification or deletion, and retained for at least six years**, with the agency's implementation policy specifying the format and system of records (§124.14(g) as quoted in our research).
- **The rule does not require cryptographic signatures, Merkle trees, or any specific technology — including AIR's architecture.** "Protected against unauthorized modification or deletion" can plausibly be satisfied by access-controlled conventional systems. AIR's cryptography is *one way* to demonstrate that property strongly [INFERENCE]; a spreadsheet on a permissioned share may be a compliant answer, and cheap incumbency ("good enough") is the real competitor.
- **Some violations may carry civil fines up to $100,000 per violation, subject to the rule's enforcement provisions and exceptions** — including, per our reading, a good-faith safe harbor for first procedural violations. Penalty exposure is real but bounded and second-order; do not lead sales with it.
- Burden estimates in the rule's PRA section (~45 min per post-operation report; ~1,650 expected participating agencies over two years) are the government's own estimates [SOURCED to the rule text as extracted in our research]. **v1's claim that required elements are "near-impossible to produce by hand" is retracted** — they are burdensome and error-prone by hand [INFERENCE], not impossible; the Departments themselves priced the manual work at under an hour.

**Verification status [UNVERIFIED]:** our section-level quotes come from our own research pass over the public-inspection PDF and secondary law-firm coverage. Before any external use, a regulatory attorney must confirm them against the final CFR text — see REGULATORY_QUESTIONS.md. **No comment will be drafted or filed without explicit founder approval and attorney review.** A filed comment is public positioning and possibly useful signaling [INFERENCE]; it is not a "legal moat," and v1's framing of it as one is retracted.

**Part 108 (BVLOS) [SOURCED]:** final rule under OIRA review as of July 10, 2026; publication expected late 2026–2027 ([Airdata's tracker](https://airdata.com/blog/2026/part-108), [Flying](https://www.flyingmag.com/2-rules-under-review-could-reshape-u-s-commercial-drone-operations/)). Its NPRM proposed operator recordkeeping/reporting obligations. Timing and final content are outside our control; treat as upside, not plan-of-record.

## 4. Market hypotheses [INFERENCE unless noted]

Buyer segments, cheapest first: commercial fleet operators, drone manufacturers (PX4-based), inspection companies, universities/test sites, insurers/investigators, public-safety teams. The agency/counter-UAS segment from v1 remains interesting but is procurement-heavy and now correctly scoped (Section 3) — it is a later, harder market, not the wedge for a solo founder [INFERENCE].

Pricing anchors that are sourced: Litigation Forensics publishes $3,000–$6,000 for flight-log analysis and $6,000–$12,000 for incident reconstruction as manual services ([litigationforensics.com](https://litigationforensics.com/services/drone-forensics)); Airdata enterprise per-drone pricing ~$120–240/yr via resellers; USAIG contributes up to $2,500/policy-year toward safety software (Polaris VOCUS precedent, [usau.com](https://www.usau.com/safety/polaris-vocus/)). What any buyer will pay for AIR specifically: **unknown until discovery interviews happen.**

Exit comparables are data points, not predictions: Flock–Aerodome >$300M ([TechCrunch](https://techcrunch.com/2024/10/23/flock-safety-paid-over-300-million-for-17-month-old-drone-startup-aerodome/)); Cellebrite–SCG Canada undisclosed (Mar 2026); CAE–Flightscape ~C$18M (2007); Gael £18M (2014). **v1's "$15–25M predictable exit" is retracted — no exit is predictable.**

Competitor motion: Cellebrite, Axon, Motorola/D-Fend, and Airdata all have adjacent assets and could move into operator-side incident records. **Timing is unknown; v1's "3–12 months" precision is retracted.** The observable facts are their 2024–2026 acquisitions and job postings, which show interest in the space, not a schedule.

## 5. What has actually been validated [TESTED]

Engine correctness properties (determinism, tamper-evidence, honest abstention, coverage) on a 100-log public sample; a working local demo; zero customer conversations, zero revenue, zero letters of intent, zero external users. The next validation milestone is 10 discovery interviews, and nothing in this memo substitutes for them.

## 6. Risks (unchanged in substance, now honestly ranked)

1. **Demand risk is #1 and untested** — "good enough" manual records may satisfy everyone who matters.
2. Format risk: PX4-only covers a minority of the commercial fleet; DJI ingestion depends on a revocable vendor key.
3. Incumbent risk: Airdata's distribution; Axon/Cellebrite's evidence franchises.
4. Regulatory timing: Part 108 could slip or dilute; Part 124 markets are slow procurement.
5. Solo-founder capacity across product + sales + standards work.

## 7. Next 30 days (gated, in order)

1. Attorney review of REGULATORY_QUESTIONS.md **[requires founder: engage counsel]**.
2. 10 discovery interviews (founder sends; nothing is sent by tooling).
3. Fresh-seed confirmation run of the evaluation before quoting numbers externally.
4. ArduPilot `.bin` ingestion only if ≥3 interviewees fly ArduPilot [gate].
5. Decision on comment filing after (1) and (2) **[founder decision]**.

## 8. Claims from v1 explicitly retracted or downgraded

- "Nobody ships X / no competitors" → bounded: *not found in our searches on 2026-07-28*; unknowns are unknowns.
- "The regulation requires [our capabilities]" → it requires protected, searchable, retained audit trails for covered agencies; **it does not require cryptography**.
- "Required information is near-impossible to produce manually" → retracted; government's own estimate is ~45 min/report.
- "Sept 4 comment = unrepeatable moat" → a comment is public input; influence is speculative.
- "Competitors are 3–6/6–12 months away" → timing unknown.
- "$15–25M outcome / $2.4M ARR math" → illustrative arithmetic on unvalidated prices; retracted as a forecast.
- "FlybyOps is a 69-day-old site with no legal entity" → our checks found no Finnish registry entry or team page **on that date**; they may operate under a parent entity; treat as unverified early-stage, monitor.
- Any implication of admissibility/compliance → removed everywhere; see AUDIT.md scope note.

# AIR website claims ledger
**Every sentence on the public site must trace to a claim ID below. Claims not listed here may not appear on the site. Generated 2026-07-28 from: AUDIT.md, eval/EVALUATION.md (round 2 authoritative), DEMO.md, ONE_PAGER.md, STRATEGY.md v2, and the canonical regenerated bundle `bundles/site-source/`. Section C and A6/A7 updated 2026-10-24 after the engine changes of that date (bundle regenerated: merkle root `61c7e1c1…`, RFC 3161 skipped). Section B numbers were measured with the July engine and have not been re-run.**

## A. Verified product facts [source: AUDIT.md §1–8; code in this repo; reproducible]

- **A1** AIR ingests PX4 ULog (`.ulg`) flight logs. It supports nothing else today.
- **A2** All analyzers are deterministic rules — no ML verdicts; every finding carries its threshold and the threshold's basis (published ruleset or labeled heuristic).
- **A3** AIR checks flight telemetry against an operator-supplied machine-readable procedures file; verdicts are PASS / FAIL / MARGINAL (within the stated measurement tolerance) / NOT EVALUABLE with the observed value, limit, tolerance, and evidence sample. Six quantitative rule types exist. Altitude rules use height above the home (launch) position, not terrain AGL; barometric altitude is never substituted.
- **A4** AIR compares independent altitude sources (barometer vs GPS vs EKF) and reports offset-corrected disagreements as findings, quoting both sources; agreement is also stated explicitly.
- **A5** Missing evidence is reported, never silently passed: NOT_EVALUABLE verdicts, coverage-gap findings, and whole-log abstention ("no flight in this log") exist and are exercised in tests.
- **A6** The record bundle commits report.json, report.html and source-file SHA-256 digests to an RFC 9162 Merkle tree; the root is Ed25519-signed; an RFC 3161 timestamp is optional; a standalone Python verifier checks the bundle offline with no network access.
- **A7** The verifier shows integrity (unchanged-since-signing + source digests match) and, given the operator's published key fingerprint, that the expected key signed; without one it reports the signer as unverified (exit 3). It does **not** prove who controls the key (no identity PKI), validates the TSA certificate chain only with `--tsa-ca`, and does not establish truth, compliance, or admissibility. AIR's records are intended to support a qualified person's certification; AIR does not itself certify identity or admissibility.
- **A8** Raw telemetry arrays are NOT inside the signed record — evidence samples and a series inventory are; re-derivation needs the original log.
- **A9** Analysis of the sample log takes well under a second on a laptop (eval mean 0.18 s/log).
- **A10** The upload demo is local-only software (binds 127.0.0.1) and is not exposed by this website. The website has no upload endpoint.
- **A11** Tampering with one byte of a record makes verification fail (tested 5/5 in eval; unit-tested).
- **A12** The record separates and labels: raw evidence, deterministic calculation, inference, procedure verdict, and unknown/missing.

## B. Evaluation results [source: eval/EVALUATION.md; n=100 processed of 120 seeded sample; round 2 authoritative]

- **B1** Seeded, stratified sample of 120 logs from the public PX4 Flight Review index (436,637 entries); 20 skipped by a pre-set 20 MB size cap; **100 processed**. Development fixtures excluded. Metrics pre-registered.
- **B2** Ingestion success 99/100; the 1 failure was rejected cleanly with no crash.
- **B3** Zero uncaught pipeline errors on the sample.
- **B4** Determinism: 10/10 logs byte-identical analysis on repeated runs (volatile record metadata excluded by design).
- **B5** Verification: 5/5 clean bundles pass; 5/5 tampered bundles fail.
- **B6** Honest abstention: 3/99 parsed logs contained no armed flight; AIR reported "no flight" rather than inventing findings.
- **B7** Ends-in-flight signal vs uploader labels (n=66 labeled, non-abstained): 4 TP, **0 FP**, 30 FN, 32 TN — zero false positives, low recall (12%). It is a narrow high-precision signal, not a crash detector.
- **B8 (caveat, must display)** The evaluation did not process all 436,637 logs; nothing is claimed beyond the 100.
- **B9 (caveat, must display)** Corpus labels are uploader-assigned and noisy, not verified ground truth.
- **B10 (caveat, must display)** Round 2 followed an ingestion-coverage fix discovered in round 1 (arming-topic aliasing); methodology is disclosed in the eval report.
- **B11 (caveat, must display)** A fresh-seed confirmation run has not yet been performed; treat results as internal until it is.
- **B12 (caveat, must display)** Conformance coverage on the sample: mean 5.65/6 rules evaluable; 79/99 logs fully evaluable. Conflict cross-check ran on 67/99 (the rest lack a second altitude source — and the record says so).

## C. Sample-crash facts [source: bundles/site-source/report.json — regenerated 2026-07-28, engine v0.1.0; public log 75957ba9-f979-430d-a49c-8ef6e5ceec12]

- **C0** Provenance: public PX4 Flight Review corpus log `75957ba9-f979-430d-a49c-8ef6e5ceec12`; flight 2023-02-26; uploaded 2023-03-02; uploader rating "crash_sw_hw"; uploader description: "at minute 12, my drone started to gain altitude sharply…". Octorotor; 594.71 s of log. The corpus is publicly downloadable but carries no explicit redistribution license → the site ships **derived data and summaries with citation, not the raw log**. Geographic location deliberately omitted.
- **C1** Battery remaining fell to 0% in flight at T+579.2 s (11:15:19Z). [BAT-LOW, critical; threshold basis dronekit-la 15%/our 7%]
- **C2** Voltage fell 26.0 V → 12.8 V within 10 s, low point at T+587.8 s (51% below the 10 s rolling baseline). [BAT-SAG, critical; labeled heuristic]
- **C3** Procedure ALT-1 FAIL: max height above home 121.57 m vs 120 m limit, beyond the 1 m default tolerance (sample Part 107-style demonstration ruleset — must be labeled as a demonstration ruleset, not the operator's real manual). [PROC-ALT-1, critical]
- **C4** Procedure BAT-1 FAIL: landed-battery 0.00% vs ≥15% required (same demonstration ruleset). PASSes: DIST-1 356.91/500 m; SPD-1 17.88/19 m/s; GPS-1 min 20 sats vs ≥6; MODE-1 no forbidden modes.
- **C5** Barometric and GPS altitude diverged up to 20.3 m (offset-corrected; baro 204.73 m vs GPS 164.01 m at T+580.5 s, initial reference offset +20.4 m). Worded as "one of these sources is wrong — the record quotes both", never as which one. [CONF-ALT-BARO-GPS, warning]
- **C6** The log ends while the vehicle is still armed at ≈14.2 m above home. Worded as *consistent with* sudden power loss / brownout / in-air breakup — cause **not determinable from this log alone**. [INT-TRUNC, critical; ArduPilot TestBrownout basis]
- **C7** EKF rejected magnetometer/heading measurements, peak test ratio 2.38 at T+578.4 s — an indicator, not a conclusion. [EKF-MAGNETOMETER, warning]
- **C8** Real terminal sequence (timeline events): battery 0% (T+579.2 s) → failsafe activated (T+591.6 s) → failure detector ROLL tripped ×3 (T+592.5–594.0 s) → ground-station connection lost (T+594.4 s) → log ends in flight (T+594.6 s).
- **C9** Unknowns AIR states for this flight: why power was lost (no maintenance/weather evidence ingested); no impact or disarm recorded; conclusions are single-log; the uploader's description is the uploader's, not AIR's.
- **C10** Record integrity for this bundle: Merkle root `61c7e1c1633ef7dc91e8e12cf5f5902f…`, tree size 4 (report.json, report.html, 2 source digests), Ed25519, RFC 3161 skipped in this regeneration; the offline verifier passes on the unchanged bundle when given the signing key's fingerprint, and reports "signer NOT verified" (exit 3) without it.

## D. Permitted framing / hypotheses (must be framed as intent or design goals, never as achievements)

- **D1** Core description (verbatim, approved): "AIR reconstructs drone incidents from raw telemetry and produces an explainable, tamper-evident record. In initial testing on public PX4 logs, it identified procedure violations and sensor conflicts that ordinary log viewers leave investigators to find manually."
- **D2** Who it is for: fleet operators, manufacturer support/reliability teams, safety teams, insurers and incident investigators, universities and UAS test sites — framed as "built for", not "used by".
- **D3** Roadmap items (label as roadmap): ArduPilot dataflash and DJI ingestion; weather/Remote ID/detection-alert multi-source ingest; richer procedure rule types.
- **D4** Comparison rows for other product categories must use exactly: "shown publicly" / "not shown publicly" / "varies". "Not shown publicly" ≠ absent, and the table must say so.
- **D5** Design-partner ask: "Request a 20-minute design-partner conversation" via mailto only; no program-membership claims.

## E. Prohibited on the site (from the brief + STRATEGY v2 retractions)

- **E1** Any of: court-admissible, legally compliant/sufficient, guaranteed, proven (unqualified), certified, regulatory approval, "no competitors", "nobody else can/does", "only product that…".
- **E2** Claiming customers, users, revenue, partnerships, pilots, LOIs, or interest.
- **E3** Claiming performance across the full 436,637-log corpus, or any accuracy number without its n and caveats adjacent.
- **E4** Calling AIR a crash detector, or stating the sample crash's cause as determined.
- **E5** Weapon/counter-drone-mitigation framing; military imagery; tracking/interception implications; the sample flight's geography.
- **E6** Fake corporate identity (Inc./LLC, team pages, testimonials, logos of others), fake urgency, fake scarcity.
- **E7** Implying the website analyzes logs (no upload control exists; demo is local software).
- **E8** "Tamper-proof" (use tamper-evident); "blockchain" (it is not one); "military-grade" anything.

## Usage map
- Hero: D1, A12, D2, D5 · Crash section: C0–C10, E4 guard · How it works: A1–A6, A12 · Record preview: C-series + A6/A7/A11 · Evaluation: B1–B12 (caveats co-located) · Comparison: A2–A6 vs D4 categories · Limitations: A1, A3 (6 rule types), A7, A8, B8, B11, D3, E2 (stated as "no customers/revenue yet") · Legal/footer: A10, E-series guards.

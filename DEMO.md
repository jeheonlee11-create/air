# AIR — Demo Guide

## Source-log provenance (cite this exactly)

The demo uses one real, public flight log:

- **Log ID:** `75957ba9-f979-430d-a49c-8ef6e5ceec12`
- **Source:** PX4 Flight Review public log database — https://review.px4.io/plot_app?log=75957ba9-f979-430d-a49c-8ef6e5ceec12 (bulk index: https://cdn.logs.px4.io/dbinfo.json; direct file: https://cdn.logs.px4.io/75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg)
- **Corpus metadata (uploader-provided):** log date 2023-03-02; rating `crash_sw_hw`; airframe octorotor; duration 594 s; uploader description: *"at minute 12, my drone started to gain altitude sharply…"*
- **License note:** the Flight Review corpus is publicly downloadable but carries no explicit license; we use this log for local analysis and demonstration, not redistribution. (Open question tracked in EVALUATION/README.)
- SHA-256 of the file as analyzed: `4542956597d8d1a9…` (full digest inside every generated record).

## Run the demo locally

```bash
cd air
python3 -m venv .venv
./.venv/bin/pip install pyulog pymavlink cryptography httpx astral rfc3161-client flask
# fetch the sample log (20 MB, public corpus):
curl -L -o fixtures/75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg \
  https://cdn.logs.px4.io/75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg
./.venv/bin/python demo/app.py        # → http://127.0.0.1:8420
```

Click **"Run the sample crash instead"** — no upload needed. Everything runs locally; the only optional external call is the RFC 3161 timestamp checkbox (off by default; sends a 32-byte hash, never log data).

---

## 60–90 second script

> This is a real flight log from the public PX4 database — an octorotor whose owner wrote: "at minute 12, my drone started to gain altitude sharply." That one sentence is all the human analysis that existed. Watch what AIR does with the raw log.
>
> *(click "Run the sample crash instead" — processing takes under a second)*
>
> One upload, one record. Five critical findings, each with the evidence sample, the timestamp, and the threshold it tripped — and where that threshold comes from. The battery hit 0% in flight, and in its last ten seconds the voltage collapsed by half. The flight broke the 120-meter height rule in the ops manual: 121.57 meters above the launch point, past the rule's one-meter measurement tolerance, and the record says which altitude reference it used. And the log ends *in the air* at about 14 meters above home — consistent with sudden power loss.
>
> Here's the part no log viewer does: AIR cross-checked the barometer against GPS altitude. They disagree by 20 meters right at the crash. The record doesn't hide that — it reports which sensors conflict, so nobody builds a conclusion on the wrong one.
>
> *(click "Verify record now")*
>
> And the whole record is tamper-evident: hash tree, signature, offline verifier. Change one byte of any finding, or of the HTML page, and this verification fails; check it against the operator's published key fingerprint and a re-signed copy fails too. That's the product: from raw telemetry to a defensible, checkable incident record in seconds.

## 3-minute extended script

1. **Setup (20 s).** "Drone programs generate incidents — crashes, flyaways, near-misses — and the record of what happened is usually a pilot's memory plus a log file nobody can read. Investigators, insurers, and safety managers need three answers: what happened, did we follow our own procedures, and can we prove the record wasn't massaged after the fact. AIR produces all three from the raw log."
2. **Provenance (15 s).** Show the provenance card. "This is a public, real crash — log 75957ba9 from the PX4 corpus. The uploader's entire analysis was one sentence. Nothing in this demo is staged; you can download the same file and reproduce every number."
3. **Run + summary (20 s).** Click the sample. Walk the chips: 5 critical, 2 warnings, procedures 4 pass / 2 fail. "Under a second of compute, deterministic rules only — no ML verdicts, every threshold cites its source."
4. **Findings discipline (45 s).** Open two findings and narrate the epistemics: "Each card separates **raw evidence** — the value, the timestamp, the exact telemetry channel — from the **deterministic calculation** — the threshold and its basis, here a ruleset ArduPilot shipped for years — from **interpretation**, which is worded as 'consistent with', never as a cause. The battery finding is measured fact. 'Possible power loss' is labeled inference. And where AIR can't know something, it says so —" show a NOT_EVALUABLE row or the coverage note. "Missing evidence is reported, never papered over. Upload a log that never flew, and AIR tells you that instead of inventing a crash."
5. **Conformance (30 s).** Conformance table. "The operator's ops manual, as machine-checkable rules. Six rules; two failed, with the observed value and the moment it happened. 121.57 meters above home against a 120 limit, past the stated 1 m tolerance. A reading within the tolerance would be MARGINAL, not FAIL: the record never claims more precision than the sensors have."
6. **Conflict (25 s).** Altitude-by-source chart + conflict finding. "Three altitude sources on one timeline, each with its own reference. Barometer and GPS, which are independent sensors, diverge 20 meters at the crash; the record quotes both and flags every altitude-dependent conclusion near that moment. Single-source tools can't tell you when their one source is lying."
7. **Evidence layer (25 s).** Download the bundle, run the verifier (or click Verify). "Merkle tree over the record and the source-file digests, Ed25519 signature, optional trusted timestamp. The verifier is a single readable Python file that runs offline — built to be audited by the other side's expert, not just ours."
8. **Close (10 s).** "Runs locally, one engine end to end, evaluated against a 100-log public sample with results published in the repo — including what it can't do yet. That honesty is the product."

## What AIR found that an ordinary log viewer leaves to a human

A log viewer (Flight Review, UAV Log Viewer, CSV export) *plots* this flight; a human must then notice, cross-reference, and write everything below. AIR produced it directly, in 0.2 s:

| AIR output | The manual work it replaces |
|---|---|
| Log ends in flight at 14.2 m above home (INT-TRUNC, threshold and reference cited) | Notice the log stops without a disarm; check final altitude; know that this pattern means power loss/impact |
| Battery 0% + 51% voltage collapse within 10 s, with timestamps and current | Read voltage and current, separate load sag from normal discharge, know sag thresholds |
| Baro-vs-GPS 20.3 m divergence at the crash moment, both values quoted | Overlay two altitude sources, offset-correct different references, spot the divergence window |
| 121.57 m above home vs 120 m ops-manual limit (1 m tolerance), verdict per rule with evidence sample | Open the ops manual, extract each limit, scrub the log for each extreme, write it up |
| Explicit "sources agree" statements and NOT_EVALUABLE gaps | Nobody writes down what they *checked and found fine* — which is exactly what an investigator or insurer needs |
| Signed, offline-verifiable bundle | No manual equivalent exists |

## Epistemic labels used throughout the record

- **Raw evidence** — value + timestamp + telemetry channel (e.g., `battery_status.remaining = 0.0 at 11:15:19Z`).
- **Deterministic calculation** — a documented rule applied to evidence (threshold + basis line on every finding).
- **Inference** — plain-language interpretation, worded as "consistent with / indicates / typical causes", never as a determined cause; interference indicators explicitly demand corroboration.
- **Procedure verdicts** — PASS/FAIL against the operator's own supplied rules, with observed value and limit.
- **Unknown / missing** — NOT_EVALUABLE verdicts, coverage-gap findings, and abstention ("no flight in this log").

## Limitations (say these out loud before anyone asks)

1. **PX4 `.ulg` only today.** ArduPilot and DJI are unimplemented (DJI additionally requires a revocable vendor API key). The market-share majority of small drones is DJI — this demo does not cover them.
2. **Evaluated on 100 public logs, not 436k, with the July 2026 engine** (not re-run since the October fixes). Results: 99% ingestion, 0 false-positive ends-in-flight calls, determinism 10/10, tamper detection 5/5 — but recall of uploader-labeled "crashes" via the ends-in-flight signal is 12%: most crashes keep logging to the ground, and AIR does not yet detect ground-impact signatures. Full numbers and caveats: `eval/EVALUATION.md`.
3. **Altitude rules use height above the launch point**, not terrain-corrected AGL; without a logged home position they are NOT_EVALUABLE.
4. **Conformance covers 6 quantitative rule types.** Real ops manuals contain weather minima, airspace, and crew rules AIR cannot yet express.
5. **The cryptography proves integrity, not identity or truth.** It shows the record hasn't changed since signing and that the source files match their digests. Given the operator's published fingerprint it shows which key signed, not who controls that key (key on disk today; no identity PKI). It validates the TSA certificate chain only when given a trusted CA (`--tsa-ca`). AIR's records are intended to support a qualified person's certification; AIR does not itself certify identity or admissibility, and we never call it court-admissible or legally compliant.
6. **Single-source evidence in this demo** — one flight log plus procedures. The multi-source story (detection alerts, weather, Remote ID) is roadmap, not product.
7. **Uploader labels in the corpus are noisy** — one "crash"-labeled fixture turned out to be a bench test that never armed (AIR abstained; that behavior is the feature).

## Screenshot-ready views

- Result page with verifier output open (chips + PASS lines): run sample → click "Verify record now".
- The report itself: `demo` result iframe, or open `bundles/75957ba9…/report.html` directly — "Altitude by source" chart with the divergence at the crash, findings cards, conformance table.

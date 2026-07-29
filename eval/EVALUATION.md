# AIR v0.1 — Evaluation Report
**Date: 2026-07-28 · Harness: `eval/harness.py` (seed 42) + `eval/rerun_subset.py` · Machine-readable results: `eval/results.json` (round 1), `eval/results_round2.json` (round 2, authoritative)**

## What was tested, and what was not

- **Tested:** a seeded, stratified sample of **120 logs** drawn from the public PX4 Flight Review index (436,637 entries): 45 crash-labeled (`crash_sw_hw`/`crash_pilot`), 45 healthy-labeled (`good`/`great`), 30 unlabeled. 20 were skipped by the pre-set 20 MB per-log size cap, leaving **100 processed** (34 crash-labeled, 41 healthy-labeled, 25 unlabeled). The three development fixture logs were excluded from sampling (they were used to build the analyzers).
- **Not tested:** the other 436,517 corpus logs. **No claim in this document extends beyond the 100 processed logs.** The size cap biases the sample toward shorter flights; this is a known, disclosed bias.
- Labels are **uploader-assigned ratings**, not verified ground truth. A "crash" label may describe a session the uploader considered a crash for any reason; a "good" label may hide problems. All label-based numbers inherit this noise.
- Contamination controls: analyzer thresholds were fixed (from external published rulesets, documented in AUDIT.md) before the harness existed; fixtures excluded; the classification rule was pre-registered in the harness docstring before the first run and not changed afterward.
- RFC 3161 timestamping was disabled for all evaluation runs; the only network use was corpus downloads (round 1: 744 MB; round 2: 489 MB; all streamed and deleted after processing).

## Two rounds — what changed and why

**Round 1** (full sample) exposed a real ingestion gap: **50/99 logs were falsely abstained** as "never armed," including 30 healthy-labeled logs. Diagnosis (verified on two affected logs): older PX4 firmware does not log the `actuator_armed` topic; arming state lives in `vehicle_status.arming_state`. The arming detector only read `actuator_armed`.

**Fix:** an additive fallback — if `actuator_armed` yields no arming events, read `vehicle_status.arming_state` (2=armed). The fallback is inert for logs where round 1 found arming events, so **round 2 re-processed only the 51 affected rows** (50 abstained + 1 unsupported recheck); all other rows carry forward, which is sound because determinism was measured at 10/10 identical reruns in round 1.

Methodology note, stated plainly: the fix was motivated by round-1 results, and round 2 reuses the same sample. This is legitimate for an ingestion-coverage bug (reading data that exists), but it means round-2 numbers describe a sample the pipeline has now "seen" once. No thresholds or classification rules were changed at any point. A future confirmation run on a fresh seed is the right next step before quoting these numbers externally.

## Results (round 2, n=100 processed unless noted)

### Tested facts

| Metric | Result |
|---|---|
| Ingestion success | **99/100** (99%) |
| Unsupported logs | 1/100 — pyulog rejects the file ("file corruption" on open); recorded, clean error, no crash |
| Pipeline errors (uncaught exceptions) | **0/100** |
| Honest abstention (never armed) | **3/99** parsed logs — all three are `crash_pilot`-labeled logs with no arming event in the data; AIR reports "no flight in this log" rather than inventing findings |
| Procedure-verdict coverage | mean **5.65 of 6** rules evaluable; **79/99** logs fully evaluable (round 1 before the arming fix: 2.86 and 38 — the fix, not tuning, produced the improvement) |
| Conflict-analysis coverage | **67/99** logs had the altitude cross-check performed (needs ≥2 altitude sources); the rest lack a second source and say so |
| Determinism | **10/10** logs produced byte-identical analysis content across repeated runs (volatile metadata — record id, creation time — excluded by design) |
| Verification of unchanged bundles | **5/5** pass (exit 0) |
| Verification after controlled tamper (1 bit flipped in report.json) | **5/5** fail as intended (exit 1) |
| Runtime | mean **0.18 s** per log, max 0.51 s (Apple Silicon laptop, single process) |
| Peak memory | ~1.6 GB RSS for the harness process — dominated by loading the 436k-entry corpus index, not per-log analysis |

### Classification vs. uploader labels (pre-registered rule, n=66 labeled non-abstained)

Rule (fixed before run 1): *predict crash iff the record contains critical INT-TRUNC ("log ends in flight").*

| | Labeled crash | Labeled healthy |
|---|---|---|
| **INT-TRUNC fired** | 4 | **0** |
| **did not fire** | 30 | 32 |

- **Precision 4/4 (100% on this sample): zero false positives on healthy-labeled flights.** When AIR says the log ends in flight, the label agrees it was a crash — on this sample, every time.
- **Recall 4/34 (11.8%):** most uploader-labeled crashes do *not* end mid-air — logging continues through impact and disarm on the ground. INT-TRUNC detects a specific, serious scenario (power loss / in-air destruction / mid-air log cutoff), not "crashes" in general.

### Interpretation (hypotheses, not tested facts)

- AIR should be described as an **evidence and investigation layer, not a crash detector**. The measured value on this sample is: it almost never cries wolf (0 FP), it abstains honestly, its verdict coverage is high, and its records verify and tamper-detect perfectly.
- The 30 false negatives are hypothesized to be crashes where logging survived to the ground; detecting those likely requires impact signatures (accel clipping bursts + attitude excursions + immediate disarm). **Untested** — future work, and it must be validated on a fresh sample, not this one.
- Uploader label noise plausibly affects both directions (the 3 abstained `crash_pilot` logs contain no armed flight at all, and the round-1 fixture set already surfaced one "crash"-labeled bench log).

## Reproduction

```bash
.venv/bin/python eval/harness.py                 # full run (downloads ~750 MB, deletes after)
.venv/bin/python eval/rerun_subset.py            # round-2 targeted rerun
```
Requires `fixtures/dbinfo.json` (see README). Results land in `eval/results*.json`.

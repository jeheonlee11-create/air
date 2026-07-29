# AIR — Airspace Incident Record

Operator-side drone incident investigation. Upload a flight log; get back a
synchronized timeline, deterministic anomaly findings, cross-source conflict
analysis, a procedure-conformance verdict, and a cryptographically signed,
tamper-evident incident record with an offline verifier.

**Positioning:** designed to support authentication of electronic records
(cf. FRE 902(13)/(14)). Authentication is not admissibility; AIR produces
records of measured, provenanced sensor data — it does not simulate physics
and it does not draw causal conclusions. Deterministic rules only; every
threshold cites its basis.

## Quick start

```bash
python3 -m venv .venv
./.venv/bin/pip install pyulog pymavlink cryptography httpx astral rfc3161-client flask

# investigate a PX4 log against an ops-manual ruleset
./.venv/bin/python -m air.cli investigate fixtures/<log>.ulg \
    --procedures procedures/sample_ops_manual.json

# output: bundles/<log>/report.html  report.json  manifest.json  verify.py
cd bundles/<log> && python3 verify.py    # offline integrity verification
```

## Web demo (local-first)

```bash
# one-time: fetch the public sample crash log (20 MB)
curl -L -o fixtures/75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg \
  https://cdn.logs.px4.io/75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg

./.venv/bin/python demo/app.py     # → http://127.0.0.1:8420
```

Upload a `.ulg` (or click "Run the sample crash instead"), get the incident
record, download the signed bundle, verify it offline. Binds to localhost only;
no data leaves the machine (the RFC 3161 timestamp is opt-in and sends a
32-byte hash only). Demo walkthrough and scripts: [DEMO.md](DEMO.md).

## Evaluation

Reproducible harness against a seeded 120-log sample of the public PX4 corpus
(fixtures excluded; pre-registered metrics): 99% ingestion, 0 uncaught pipeline
errors, deterministic reruns 10/10, tamper detection 5/5, and a
zero-false-positive (low-recall) ends-in-flight signal vs uploader labels.
Full numbers, both evaluation rounds, and all caveats: [eval/EVALUATION.md](eval/EVALUATION.md).
Product audit (formats, thresholds, failure behavior, crypto scope): [AUDIT.md](AUDIT.md).

## What's implemented (v0.1)

| Layer | Status |
|---|---|
| PX4 ULog ingestion, cross-firmware field aliasing (`sensor_gps` vs `vehicle_gps_position`, int-1e7 vs float-degree positions, etc.) | working |
| Normalized schema: Series / TimelineEvent / SourceFile (SHA-256 at ingest) | working |
| Analyzers: log-truncation/brownout, NaN scan, GPS quality/jamming/spoofing indicators, EKF innovation-ratio rejection, vibration + accel clipping, IMU disagreement, battery depletion/sag | working — thresholds ported from the retired ArduPilot LogAnalyzer (Copter-4.5.0) and PX4 `Tools/ecl_ekf` conventions |
| Cross-source conflict: baro vs GPS vs EKF altitude divergence, with explicit "sources agree" statements when checked and clean | working |
| Procedure conformance: declarative JSON rules → PASS / FAIL / NOT_EVALUABLE with evidence samples | working |
| Evidence bundle: canonical JSON record, RFC 9162 Merkle tree (0x00/0x01 domain separation), Ed25519 signature, RFC 3161 timestamp (FreeTSA), standalone `verify.py` (stdlib + cryptography only) | working, tamper-test verified |
| Self-contained HTML incident record (charts per dataviz reference palette) | working |

Tested on real logs from the public PX4 Flight Review corpus (index of
436,637 logs; our evaluation processed a seeded 100-log sample — see
eval/EVALUATION.md for exactly what was and was not measured). Corpus labels
are uploader-assigned and noisy, not verified ground truth.

## Roadmap (v0.2+)

- ArduPilot dataflash `.bin` ingestion (pymavlink DFReader; keep LGPL server-side)
- Enrichment: IEM ASOS 1-minute wind gusts, FAA airspace/TFR (start the TFR
  snapshot cron — no public archive exists), astral daylight check, WMM
  declination-vs-compass delta
- DJI `.txt` via `pydjirecord` (phase 2 — requires revocable DJI API key; a
  distribution play, not a foundation)
- Detection-alert ingestion (counter-UAS sensor exports) → the §124.13(c)
  48-hour post-operation report generator
- Part 124 audit-trail mode: 6-year retention ledger, purge verification
  records, dissemination log (see STRATEGY.md)
- Hourly Merkle tree head → public transparency log + contracted TSA/QTSP

## Repository layout

```
air/
  ingest/ulog.py      PX4 ULog → normalized Incident (all aliasing lives here)
  analyze/            deterministic analyzers + conformance engine
  evidence/           merkle (RFC 9162), Ed25519 signing, RFC 3161, bundle
  report/html.py      evidence-document rendering
  cli.py              python -m air.cli investigate <log>
verify.py             standalone offline verifier (copied into every bundle)
procedures/           declarative ops-manual rulesets
fixtures/             real labeled crash logs (public PX4 corpus)
STRATEGY.md           full market synthesis, moat plan, 90-day GTM
```

Keys in `keys/` are development keys; production signing belongs in an HSM/KMS.

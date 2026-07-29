# AIR v0.1 — Product Audit
**Date: 2026-07-28. Auditor: automated inspection + experiments in this repo. Every statement below was verified against the code or by running an experiment; experiments are reproducible with the commands shown.**

Scope note on legal language: nothing in this audit or product should be described as court-admissible, legally compliant, or legally sufficient. The cryptography supports *integrity verification* of the record; it does not establish legal conclusions.

## 1. Supported formats

| Format | Status | Evidence |
|---|---|---|
| PX4 ULog (`.ulg`) | **Supported** — sole ingestion path | `air/ingest/ulog.py`; `air/api.py` error text |
| ArduPilot dataflash (`.bin`) | **Not supported.** `pymavlink` is installed but no parser exists | no `air/ingest/dataflash.py`; README roadmap item |
| MAVLink `.tlog`, DJI `.txt`/`.DAT`, others | **Not supported** | — |

ULog version coverage: whatever the installed `pyulog` parses. Cross-firmware topic aliasing is implemented for: GPS (`vehicle_gps_position` vs `sensor_gps`), GPS position encodings (`lat`·1e-7 vs `latitude_deg`; `alt` mm vs `altitude_msl_m`), battery voltage (`voltage_filtered_v` vs `voltage_v`), current (`current_filtered_a` vs `current_a`). Verified against three real logs spanning 2023–2025 firmware with different topic sets.

## 2. Analyzer determinism

All analyzers are deterministic pure functions of the parsed log: fixed thresholds, no randomness, no ML, no network input. Verified by code inspection; measured across repeated runs in the evaluation harness (see EVALUATION.md).

**Nondeterministic fields in the output record (metadata, not analysis):** `incident_id` (uuid4), `created_utc` (wall clock), the RFC 3161 token (TSA-issued), and therefore the Merkle root and signature (they commit to the bytes that include those fields). Two runs on the same log produce identical findings/conformance/timeline content but different record identity and signatures. This is by design (each investigation is a distinct record) but must be understood when comparing runs.

## 3. Threshold bases (complete list)

| Finding | Threshold | Basis (as cited in code and report output) |
|---|---|---|
| INT-TRUNC ends-in-flight | final altitude > 3.0 m while armed | ArduPilot LogAnalyzer `TestBrownout` `finalAltMax=3.0`, Copter-4.5.0 tag (tool deleted from ArduPilot master Aug 2024) |
| INT-NAN | any NaN in a normalized series | ArduPilot LogAnalyzer `TestNaN` port |
| INT-CORRUPT | parser corruption flag | `pyulog` `ULog.file_corruption` |
| GPS-SATS | warn <6, fail <5 satellites | ArduPilot LogAnalyzer `TestGPSGlitch` `minSatsWARN/FAIL` |
| GPS-EPH | warn >5 m, fail >10 m | **Heuristic** — labeled as such; analog of ArduPilot HDOP 3.0/10.0, which is a different statistic |
| GPS-JAM / GPS-SPOOF | receiver state ≥2 warn, ≥3 fail | PX4/u-blox `jamming_state`/`spoofing_state` semantics (0 unknown, 1 OK, 2 WARNING, 3 CRITICAL) |
| GPS-FIXLOSS | fix_type <3 in flight | 3D fix required for position control |
| EKF-* ratios | amber >0.5, red >1.0; critical if >2% of samples red | PX4 `Tools/ecl_ekf` convention |
| EKF-FAULT | `filter_fault_flags` ≠ 0 | PX4 estimator_status documentation ("should always be zero") |
| VIB-HIGH | warn >15, fail >30 m/s² | PX4 Flight Review convention for `accel_vibration_metric` |
| VIB-CLIP | any clipping warn; >100 events critical | clipping invalidates samples by definition |
| IMU-DISAGREE | warn >0.7, fail >1.5 m/s² | **Heuristic** near PX4 sensors-module defaults — labeled as such |
| BAT-LOW | warn <15%, critical <7% | dronekit-la `low_battery_threshold=15%` (7% is our extension, labeled) |
| BAT-SAG | >25% drop from flight-start voltage | **Heuristic** (LiPo sag) — labeled as such |
| CONF-ALT-* divergence | warn >10 m, fail >25 m | **Heuristic** offset-corrected cross-source residual — labeled as such |

Honest characterization: roughly half the thresholds are direct ports of published/community rulesets; the rest are heuristics and are labeled "heuristic" in the finding's `threshold.basis` field. No threshold was tuned against the evaluation set (they were fixed before the harness existed; sources are external rulesets).

## 4. What "procedure conformance" currently checks

Six declarative metrics evaluated over the flight window (arm→disarm/end), against a JSON ruleset the operator supplies:
`max_alt_agl_m`, `max_dist_home_m`, `max_groundspeed_ms`, `min_gps_sats`, `battery_at_landing_pct`, `modes_flown` (forbidden-mode list). Verdicts: PASS / FAIL / **NOT_EVALUABLE** (missing data is reported, never silently passed). Each verdict carries the extreme value, its timestamp, and the source channel.

**Known caveats (documented limitations, not bugs):**
- "AGL" altitude is EKF local altitude relative to the arming origin (fallback: barometric). It is not terrain-corrected AGL; over sloping terrain the number diverges from true AGL.
- `max_dist_home_m` uses the EKF local origin as "home", which is set at EKF start, not necessarily the launch point.
- `battery_at_landing_pct` is battery at *end of in-flight data*; if the log truncates mid-air this is "battery at last evidence", which is the conservative reading for an investigator.
- It checks 6 quantitative rule types. A real ops manual contains many rule types (weather minima, airspace, crew requirements) that are not yet expressible.

## 5. How cross-source conflict is calculated

For pairs of independent altitude sources (barometer vs GPS; barometer vs EKF-fused): both series are sampled on a common 500 ms grid (last-value-at-or-before), the constant reference offset is estimated from the first ≤5 paired samples, and the divergence is `|(a−b)−offset|`. Peak divergence above 10 m (warn) / 25 m (critical) produces a conflict finding quoting *both* source values at the worst timestamp. When sources were compared and stayed within bounds, an explicit "sources agree" info finding is emitted — checked-and-agreed is distinct from not-checked. IMU-vs-IMU disagreement uses the firmware's own `sensors_status_imu.accel_inconsistency_m_s_s` channel.

Limitation: offset estimation from early samples assumes the sources agree at flight start; a sensor already faulty before arming would corrupt the baseline. Constant-offset correction also removes any slow constant drift from detection.

## 6. Cryptographic implementation

- **RFC 9162 Merkle tree** (`air/evidence/merkle.py`): exact §2.1 MTH construction; `0x00`/`0x01` leaf/node domain separation; split at largest power of two < n; no lonely-leaf duplication; inclusion proofs per §2.1.3.1 and verification per §2.1.3.2. Leaves: canonical `report.json` bytes (leaf 0), then each source file's SHA-256 hex digest as ASCII bytes (leaves 1..n).
- **Ed25519** (`air/evidence/signing.py`): `cryptography` library; signs the raw 32-byte Merkle root; dev keypair auto-generated to `keys/air_signing_key.pem` (PKCS8 PEM, file mode 0600, gitignored). Canonical JSON = sorted keys, compact separators, UTF-8.
- **RFC 3161** (`air/evidence/timestamp.py`): `rfc3161-client` builds the request; POSTs to FreeTSA (`https://freetsa.org/tsr`) over httpx, 10 s timeout; message imprint = SHA-256 of the Merkle root; full DER token stored base64 in the manifest. Any failure degrades to `status: unavailable` with the error recorded — the bundle is still produced and signed.
- **Not implemented / known gaps:** no HSM/KMS (dev key on disk); one static TSA with no redundancy; the verifier checks the token's *claimed imprint binding*, not the TSA's certificate chain (see §7); no transparency-log publication of tree heads yet.

## 7. Offline verifier

`verify.py` (copied into every bundle) uses Python stdlib + `cryptography` only. **It performs no network access** (verified by code inspection: file I/O only). Checks: (1) report.json inclusion against the Merkle root, (2) every source-digest leaf inclusion, (3) Ed25519 signature over the root using the public key *embedded in the bundle*, (4) RFC 3161 token imprint binding, (5) re-hash of any source files present locally.

**Honest limitations, stated in its output:** check 4 verifies that the recorded imprint matches the root — it does **not** cryptographically validate the TSA's signature or certificate chain (the output points to `openssl ts` for that). Check 3 proves the bundle was signed by the embedded key; binding that key to a specific operator/vendor identity requires key distribution infrastructure that does not exist yet. Experimentally verified: unchanged bundle → exit 0; single-byte change in `report.json` → exit 1.

## 8. Exactly what the signed record includes and excludes

**Committed (under the signed Merkle root):**
- `report.json`, canonically encoded: generator version, incident id, created time, aircraft metadata, flight window + UTC anchor + home position, source-file digests, all findings with evidence samples and thresholds, full conformance results, the **full event timeline**, and a **series inventory** (names, provenance, sample counts, units).
- The SHA-256 digest of every source file (the raw flight log and the procedures file). The raw files themselves stay wherever the operator keeps them; the digests bind them immutably to the record.

**NOT committed (excluded from the signature):**
- **Raw telemetry arrays** — the record contains evidence *samples* (specific values at specific timestamps) and the series inventory, not the full time series. Consequence: the record proves what the log file was (by digest) and what AIR concluded, but re-deriving the conclusions requires the original log file plus a rerun.
- `report.html` — explicitly labeled an unsigned *rendering* of report.json.
- `manifest.json` itself (it carries the signature; it cannot be under it). Tampering with the manifest breaks verification anyway (wrong root/signature/proofs).
- The RFC 3161 token arrives after root computation and lives in the manifest, outside the tree.

## 9. Failure behavior (all tested 2026-07-28)

| Input | Behavior | Exit |
|---|---|---|
| Random bytes as `.ulg` | `error: Not a parseable PX4 ULog file: Invalid file format (Failed to parse header). AIR v0.1.0 supports PX4 .ulg logs only…` — no traceback | 2 |
| Empty file | same clean error (`Header too short`) | 2 |
| Text file renamed `.ulg` | same clean error | 2 |
| Missing file | `error: file not found: …` | 2 |
| Truncated real log (first 300 KB of a 4.8 MB log) | Parses the surviving 10 s of data and reports on it. pyulog's `file_corruption` flag did **not** trigger for clean truncation (truncation at a message boundary is not "corruption" to the parser). If the vehicle was armed at cutoff, INT-TRUNC/INT-NODISARM fires; if not, the record simply covers less time. **Limitation: AIR cannot distinguish "file was cut" from "logging stopped".** | 0 |
| Corrupt-mid-file log (parser sets `file_corruption`) | INT-CORRUPT warning finding in the record | 0 |
| Mislabeled log (corpus-labeled "crash" that never armed — real case `b7d8c6fd`) | **Honest abstention**: INT-NOARM info finding "Vehicle never armed in this log"; all 6 conformance rules NOT_EVALUABLE; no crash narrative invented. Verified: `armed=0` for all 294 samples, altitude ±0.7 m | 0 |
| Log with no GPS topic | Ingest note → INT-COVERAGE finding; GPS analyzers and GPS-dependent conformance rules abstain (NOT_EVALUABLE) | 0 |

## 10. Secrets / hardcoded material

- **No private keys, tokens, or credentials in tracked files** (verified: `git grep` for PEM blocks and secret patterns; hits are code identifiers only).
- `keys/air_signing_key.pem` exists on disk (dev key, 0600) and is **gitignored**; `bundles/`, `fixtures/*.ulg`, `fixtures/dbinfo.json`, `.venv/` are gitignored. `.DS_Store` was tracked and has been removed from tracking.
- Hardcoded external endpoints: FreeTSA URL (`air/evidence/timestamp.py`) and the PX4 corpus CDN in the eval harness — both documented. **The only network calls in the entire pipeline are (a) the opt-in RFC 3161 request, which sends a 32-byte hash and never log data, and (b) evaluation-harness downloads.**
- No hardcoded findings, timestamps, fixtures-as-results, or demo data anywhere in the analysis path. The three fixture logs are real public-corpus downloads used as development fixtures; they are excluded from the evaluation sample (see EVALUATION.md).

## Changes made as a result of this audit

1. Clean error boundary (`air/api.py` `UnsupportedLogError`): unsupported/corrupt/empty/missing files now produce a one-line error and exit 2 instead of a traceback.
2. `pyulog` `file_corruption` surfaced as INT-CORRUPT warning finding.
3. Header-only files with zero data topics rejected explicitly.
4. Pipeline refactored into `air/api.py::investigate_log` so the CLI and web demo share one implementation (no second analysis path).
5. `.DS_Store` untracked.

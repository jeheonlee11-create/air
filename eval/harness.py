"""AIR evaluation harness — reproducible run against the public PX4 corpus.

PRE-REGISTERED DESIGN (fixed before any evaluation run; do not tune analyzers
against these results — thresholds derive from external rulesets and were
frozen in AUDIT.md prior to this harness existing):

Sample:  seeded (SEED=42) stratified draw from the public Flight Review index
         (https://cdn.logs.px4.io/dbinfo.json):
           - up to 45 crash-labeled logs (rating in {crash_sw_hw, crash_pilot})
           - up to 45 healthy-labeled logs (rating in {good, great})
           - up to 30 unlabeled logs
         The three development fixture logs are EXCLUDED (they were used while
         building the analyzers; including them would contaminate evaluation).
Budget:  per-log size cap 20 MB (skipped, recorded); cumulative download cap
         900 MB (run stops early, recorded). Logs are deleted after processing.
Network: corpus CDN downloads only. RFC 3161 timestamping is DISABLED for all
         eval runs (no other external calls exist in the pipeline).

Metrics and their definitions:
  ingest_ok        log parsed and pipeline completed
  unsupported      UnsupportedLogError (parser rejected the file)
  pipeline_error   any other exception (a bug or unhandled layout — reported
                   by exception type/message)
  abstained        record contains INT-NOARM (vehicle never armed) — the
                   honest-abstention path
  ends_in_flight   record contains critical INT-TRUNC ("log ends in flight")
CLASSIFICATION (pre-registered, fixed): prediction = ends_in_flight.
  Ground truth = corpus rating (crash_* vs good/great), uploader-assigned.
  Abstained logs are excluded from the confusion matrix and reported
  separately. NOTE the constructs differ: INT-TRUNC detects "log ends in
  flight"; a labeled crash whose log continues after impact, or a landed
  flight labeled crash by its uploader, will disagree with the label. The
  confusion matrix therefore measures agreement with noisy human labels,
  not ground-truth accident detection.
  conformance_coverage  per log: evaluable rules / 6 (sample ops manual)
  conflict_checked      CONF-ALT-* finding present (incl. explicit agreement)
  determinism           first N_DET successfully-processed logs run twice;
                        reports stripped of volatile metadata (incident_id,
                        created_utc) must hash identically
  verify_pass           bundle verify.py exit 0 on first N_VER bundles
  tamper_fail           verify.py exit 1 after flipping one byte in report.json
  runtime/memory        wall seconds per stage; ru_maxrss at end

Usage:  .venv/bin/python eval/harness.py [--limit-crash 45 --limit-good 45
        --limit-unlabeled 30] [--out eval/results.json]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import resource
import shutil
import subprocess
import sys
import tempfile
import time

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from air import __version__
from air.api import UnsupportedLogError, investigate_log

SEED = 42
PER_LOG_CAP = 20 * 1024 * 1024          # 20 MB
TOTAL_BUDGET = 900 * 1024 * 1024        # 900 MB cumulative download
N_DET = 10                              # determinism re-run count
N_VER = 5                               # verify/tamper test count
CDN = "https://cdn.logs.px4.io"
FIXTURE_IDS = {                          # development logs — excluded
    "b7d8c6fd-95d3-4b4b-82e4-5ff8c9a2f30e",
    "75957ba9-f979-430d-a49c-8ef6e5ceec12",
    "bb94988c-fc8c-4a44-b8ca-cf62052a227e",
}
PROCEDURES = os.path.join(REPO, "procedures", "sample_ops_manual.json")
CRASH = {"crash_sw_hw", "crash_pilot"}
HEALTHY = {"good", "great"}


def load_index() -> list[dict]:
    path = os.path.join(REPO, "fixtures", "dbinfo.json")
    with gzip.open(path) as f:
        return json.load(f)


def sample(db: list[dict], n_crash: int, n_healthy: int, n_unlabeled: int) -> list[dict]:
    rng = random.Random(SEED)
    crash = [e for e in db if e.get("rating") in CRASH and e["log_id"] not in FIXTURE_IDS]
    healthy = [e for e in db if e.get("rating") in HEALTHY and e["log_id"] not in FIXTURE_IDS]
    unlabeled = [e for e in db if not e.get("rating") and e["log_id"] not in FIXTURE_IDS]
    picks = (rng.sample(crash, min(n_crash, len(crash)))
             + rng.sample(healthy, min(n_healthy, len(healthy)))
             + rng.sample(unlabeled, min(n_unlabeled, len(unlabeled))))
    rng.shuffle(picks)
    return picks


def stripped_report_hash(report_path: str) -> str:
    with open(report_path) as f:
        r = json.load(f)
    r.pop("incident_id", None)
    r.pop("created_utc", None)
    blob = json.dumps(r, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def run_one(log_path: str, out_dir: str) -> dict:
    t0 = time.monotonic()
    try:
        res = investigate_log(log_path, PROCEDURES, out_dir, os.path.join(REPO, "keys"),
                              with_timestamp=False)
    except UnsupportedLogError as e:
        return {"ok": False, "error_class": "unsupported", "error": str(e)[:200],
                "process_s": round(time.monotonic() - t0, 2)}
    except Exception as e:
        return {"ok": False, "error_class": "pipeline_error",
                "error": f"{type(e).__name__}: {e}"[:300],
                "process_s": round(time.monotonic() - t0, 2)}
    report = res["report"]
    codes = {f["code"] for f in report["findings"]}
    sev = {}
    for f in report["findings"]:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    conf = report["conformance"] or {}
    return {
        "ok": True,
        "process_s": round(time.monotonic() - t0, 2),
        "fw_commit": report["aircraft"].get("fw_commit", "")[:12],
        "hardware": report["aircraft"].get("hardware", ""),
        "duration_s": report["flight"]["duration_s"],
        "abstained": "INT-NOARM" in codes,
        "ends_in_flight": "INT-TRUNC" in codes,
        "file_corruption": "INT-CORRUPT" in codes,
        "findings_by_severity": sev,
        "finding_codes": sorted(codes),
        "conformance_evaluable": (conf.get("rules_total", 0) - conf.get("not_evaluable", 0)),
        "conformance_total": conf.get("rules_total", 0),
        "conflict_checked": any(c.startswith("CONF-ALT") for c in codes),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-crash", type=int, default=45)
    ap.add_argument("--limit-good", type=int, default=45)
    ap.add_argument("--limit-unlabeled", type=int, default=30)
    ap.add_argument("--out", default=os.path.join(REPO, "eval", "results.json"))
    args = ap.parse_args()

    db = load_index()
    picks = sample(db, args.limit_crash, args.limit_good, args.limit_unlabeled)
    print(f"AIR eval harness — {len(picks)} logs sampled (seed={SEED}), "
          f"budget {TOTAL_BUDGET/1e6:.0f} MB, per-log cap {PER_LOG_CAP/1e6:.0f} MB")

    work = tempfile.mkdtemp(prefix="air_eval_")
    results, downloaded, skipped_size, dl_fail = [], 0, 0, 0
    det_candidates: list[str] = []       # log paths kept for determinism re-run
    ver_bundles: list[str] = []          # bundle dirs kept for verify/tamper

    client = httpx.Client(timeout=60)
    for i, e in enumerate(picks):
        log_id = e["log_id"]
        label = e.get("rating") or "unlabeled"
        if downloaded >= TOTAL_BUDGET:
            results.append({"log_id": log_id, "label": label, "status": "budget_exhausted"})
            continue
        url = f"{CDN}/{log_id}.ulg"
        path = os.path.join(work, f"{log_id}.ulg")
        try:
            with client.stream("GET", url, follow_redirects=True) as r:
                r.raise_for_status()
                clen = int(r.headers.get("content-length") or 0)
                if clen > PER_LOG_CAP:
                    skipped_size += 1
                    results.append({"log_id": log_id, "label": label,
                                    "status": "skipped_size", "size": clen})
                    continue
                size = 0
                with open(path, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        size += len(chunk)
                        if size > PER_LOG_CAP:
                            raise ValueError("size cap exceeded mid-stream")
                        f.write(chunk)
        except Exception as ex:
            dl_fail += 1
            results.append({"log_id": log_id, "label": label, "status": "download_failed",
                            "error": f"{type(ex).__name__}: {ex}"[:200]})
            if os.path.exists(path):
                os.remove(path)
            continue
        downloaded += size

        out_dir = os.path.join(work, f"bundle_{log_id}")
        row = {"log_id": log_id, "label": label, "size": size, "status": "processed",
               **run_one(path, out_dir)}
        results.append(row)

        keep_for_det = row.get("ok") and len(det_candidates) < N_DET
        keep_for_ver = row.get("ok") and len(ver_bundles) < N_VER
        if keep_for_det:
            det_candidates.append(path)
        if keep_for_ver:
            ver_bundles.append(out_dir)
        if not keep_for_det:
            os.remove(path)
        if not keep_for_ver and os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(picks)}] downloaded={downloaded/1e6:.0f}MB "
                  f"ok={sum(1 for r in results if r.get('ok'))}")

    # --- determinism: rerun kept logs, compare stripped-report hashes ---
    determinism = []
    for path in det_candidates:
        lid = os.path.basename(path)[:-4]
        d1 = os.path.join(work, f"det1_{lid}")
        d2 = os.path.join(work, f"det2_{lid}")
        try:
            investigate_log(path, PROCEDURES, d1, os.path.join(REPO, "keys"), with_timestamp=False)
            investigate_log(path, PROCEDURES, d2, os.path.join(REPO, "keys"), with_timestamp=False)
            h1 = stripped_report_hash(os.path.join(d1, "report.json"))
            h2 = stripped_report_hash(os.path.join(d2, "report.json"))
            determinism.append({"log_id": lid, "identical": h1 == h2})
        except Exception as ex:
            determinism.append({"log_id": lid, "identical": False,
                                "error": f"{type(ex).__name__}: {ex}"[:200]})
        for d in (d1, d2):
            shutil.rmtree(d, ignore_errors=True)
        os.remove(path)

    # --- verification + controlled tamper ---
    verification = []
    py = sys.executable
    for b in ver_bundles:
        lid = os.path.basename(b)[7:]
        v1 = subprocess.run([py, "verify.py"], cwd=b, capture_output=True)
        rp = os.path.join(b, "report.json")
        data = bytearray(open(rp, "rb").read())
        data[len(data) // 2] ^= 0x01          # flip one bit mid-file
        open(rp, "wb").write(bytes(data))
        v2 = subprocess.run([py, "verify.py"], cwd=b, capture_output=True)
        verification.append({"log_id": lid,
                             "clean_exit": v1.returncode, "tampered_exit": v2.returncode,
                             "clean_pass": v1.returncode == 0,
                             "tamper_detected": v2.returncode == 1})
        shutil.rmtree(b, ignore_errors=True)

    processed = [r for r in results if r.get("status") == "processed"]
    ok = [r for r in processed if r.get("ok")]
    abstained = [r for r in ok if r.get("abstained")]
    classified = [r for r in ok if not r.get("abstained") and r["label"] != "unlabeled"]
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for r in classified:
        is_crash = r["label"] in CRASH
        pred = r.get("ends_in_flight", False)
        key = ("tp" if is_crash else "fp") if pred else ("fn" if is_crash else "tn")
        cm[key] += 1

    summary = {
        "harness_version": 1,
        "air_version": __version__,
        "seed": SEED,
        "sampled": len(picks),
        "processed": len(processed),
        "download_failed": dl_fail,
        "skipped_size_cap": skipped_size,
        "budget_exhausted": sum(1 for r in results if r.get("status") == "budget_exhausted"),
        "bytes_downloaded": downloaded,
        "ingest_ok": len(ok),
        "unsupported": sum(1 for r in processed if r.get("error_class") == "unsupported"),
        "pipeline_errors": sum(1 for r in processed if r.get("error_class") == "pipeline_error"),
        "pipeline_error_detail": [
            {"log_id": r["log_id"], "error": r.get("error")}
            for r in processed if r.get("error_class") == "pipeline_error"],
        "abstained_never_armed": len(abstained),
        "classification": {
            "rule": "prediction := critical INT-TRUNC (log ends in flight); "
                    "labels are uploader-assigned; abstentions excluded",
            "n": len(classified), **cm,
        },
        "conformance": {
            "mean_evaluable_rules": (sum(r["conformance_evaluable"] for r in ok) / len(ok))
            if ok else None,
            "fully_evaluable_logs": sum(1 for r in ok if r["conformance_evaluable"] == 6),
        },
        "conflict_checked_logs": sum(1 for r in ok if r.get("conflict_checked")),
        "determinism": {"n": len(determinism),
                        "all_identical": all(d["identical"] for d in determinism) if determinism else None,
                        "detail": determinism},
        "verification": {"n": len(verification),
                         "all_clean_pass": all(v["clean_pass"] for v in verification) if verification else None,
                         "all_tamper_detected": all(v["tamper_detected"] for v in verification) if verification else None,
                         "detail": verification},
        "runtime": {
            "mean_process_s": (sum(r["process_s"] for r in ok) / len(ok)) if ok else None,
            "max_process_s": max((r["process_s"] for r in ok), default=None),
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "per_log": results}, f, indent=2)
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(summary, indent=2)[:4000])
    print(f"\nresults written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

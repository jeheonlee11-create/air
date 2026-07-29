"""Round-2 targeted re-evaluation.

Round 1 found that logs lacking the `actuator_armed` topic were falsely
abstained (arming lives in `vehicle_status.arming_state` on older firmware).
The fix is an additive fallback that can only change results for logs where
`actuator_armed` produced no arming events — i.e. exactly the round-1
abstained set plus the one unsupported log. This script re-downloads and
re-processes ONLY that subset (bandwidth-conscious), merges results into
round-1 rows, and writes results_round2.json. All other rows are carried
forward unchanged, which is sound because the pipeline is deterministic
(round-1 measurement: 10/10 identical reruns) and the fallback is inert when
arming events already exist.

The seed, sample, and pre-registered classification rule are unchanged.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from harness import CRASH, run_one

CDN = "https://cdn.logs.px4.io"


def main() -> int:
    with open(os.path.join(REPO, "eval", "results.json")) as f:
        r1 = json.load(f)
    rows = r1["per_log"]
    targets = [r for r in rows
               if r.get("abstained") or r.get("error_class") == "unsupported"]
    print(f"round 2: re-processing {len(targets)} of {len(rows)} rows "
          f"(abstained or unsupported in round 1)")

    work = tempfile.mkdtemp(prefix="air_eval_r2_")
    client = httpx.Client(timeout=60)
    downloaded = 0
    merged = {r["log_id"]: dict(r) for r in rows}
    for i, r in enumerate(targets):
        lid = r["log_id"]
        path = os.path.join(work, f"{lid}.ulg")
        try:
            with client.stream("GET", f"{CDN}/{lid}.ulg", follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(path, "wb") as f:
                    f.writelines(resp.iter_bytes(1 << 20))
        except Exception as ex:
            merged[lid]["round2"] = {"status": "download_failed", "error": str(ex)[:200]}
            continue
        downloaded += os.path.getsize(path)
        out = os.path.join(work, f"b_{lid}")
        res = run_one(path, out)
        merged[lid].update({**res, "round2_reprocessed": True})
        os.remove(path)
        import shutil
        shutil.rmtree(out, ignore_errors=True)
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(targets)}] downloaded={downloaded/1e6:.0f}MB")

    rows2 = list(merged.values())
    ok = [r for r in rows2 if r.get("ok")]
    abstained = [r for r in ok if r.get("abstained")]
    classified = [r for r in ok if not r.get("abstained") and r["label"] != "unlabeled"]
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for r in classified:
        is_crash = r["label"] in CRASH
        pred = r.get("ends_in_flight", False)
        key = ("tp" if is_crash else "fp") if pred else ("fn" if is_crash else "tn")
        cm[key] += 1

    summary2 = {
        "round": 2,
        "reprocessed": len(targets),
        "round2_bytes_downloaded": downloaded,
        "ingest_ok": len(ok),
        "unsupported": sum(1 for r in rows2 if r.get("error_class") == "unsupported"),
        "pipeline_errors": sum(1 for r in rows2 if r.get("error_class") == "pipeline_error"),
        "abstained_never_armed": len(abstained),
        "abstained_by_label": {},
        "classification": {"rule": r1["summary"]["classification"]["rule"],
                           "n": len(classified), **cm},
        "conformance": {
            "mean_evaluable_rules": (sum(x["conformance_evaluable"] for x in ok) / len(ok))
            if ok else None,
            "fully_evaluable_logs": sum(1 for x in ok if x["conformance_evaluable"] == 6),
        },
        "conflict_checked_logs": sum(1 for x in ok if x.get("conflict_checked")),
        "runtime_mean_process_s": (sum(x["process_s"] for x in ok) / len(ok)) if ok else None,
    }
    from collections import Counter
    summary2["abstained_by_label"] = dict(Counter(x["label"] for x in abstained))

    with open(os.path.join(REPO, "eval", "results_round2.json"), "w") as f:
        json.dump({"summary_round1": r1["summary"], "summary_round2": summary2,
                   "per_log": rows2}, f, indent=2)
    print(json.dumps(summary2, indent=1))
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(REPO, "eval"))
    sys.exit(main())

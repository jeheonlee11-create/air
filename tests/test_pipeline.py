"""End-to-end pipeline tests against real fixture logs.

Skipped automatically when fixtures are absent (they are gitignored downloads;
see README for the fetch commands).
"""

import json
import os
import subprocess
import sys

import pytest

from air.api import UnsupportedLogError, investigate_log

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRASH_LOG = os.path.join(REPO, "fixtures", "75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg")
NOARM_LOG = os.path.join(REPO, "fixtures", "b7d8c6fd-95d3-4b4b-82e4-5ff8c9a2f30e.ulg")
PROCEDURES = os.path.join(REPO, "procedures", "sample_ops_manual.json")

needs_crash = pytest.mark.skipif(not os.path.exists(CRASH_LOG), reason="fixture not downloaded")
needs_noarm = pytest.mark.skipif(not os.path.exists(NOARM_LOG), reason="fixture not downloaded")


@needs_crash
def test_crash_log_end_to_end(tmp_path):
    res = investigate_log(CRASH_LOG, PROCEDURES, str(tmp_path / "b"),
                          str(tmp_path / "k"), with_timestamp=False)
    codes = {f.code for f in res["findings"]}
    assert "INT-TRUNC" in codes            # log ends in flight
    assert "BAT-LOW" in codes              # battery depleted
    assert "CONF-ALT-BARO-GPS" in codes    # cross-source conflict detected
    conf = res["conformance"]
    assert conf["failed"] == 2 and conf["not_evaluable"] == 0
    alt = next(r for r in conf["results"] if r["id"] == "ALT-1")
    assert alt["verdict"] == "FAIL" and alt["observed"] == 120.04


@needs_crash
def test_bundle_verifies_and_detects_tamper(tmp_path):
    out = str(tmp_path / "bundle")
    investigate_log(CRASH_LOG, PROCEDURES, out, str(tmp_path / "k"), with_timestamp=False)
    v = subprocess.run([sys.executable, "verify.py"], cwd=out, capture_output=True)
    assert v.returncode == 0, v.stdout
    rp = os.path.join(out, "report.json")
    data = bytearray(open(rp, "rb").read())
    data[len(data) // 2] ^= 0x01
    open(rp, "wb").write(bytes(data))
    v2 = subprocess.run([sys.executable, "verify.py"], cwd=out, capture_output=True)
    assert v2.returncode == 1


@needs_crash
def test_report_json_is_committed_leaf(tmp_path):
    out = str(tmp_path / "bundle")
    res = investigate_log(CRASH_LOG, None, out, str(tmp_path / "k"), with_timestamp=False)
    manifest = res["manifest"]
    assert manifest["merkle"]["tree_size"] == 1 + len(res["report"]["sources"])
    with open(os.path.join(out, "manifest.json")) as f:
        assert json.load(f)["signature"]["algorithm"] == "Ed25519"


@needs_noarm
def test_never_armed_log_abstains(tmp_path):
    res = investigate_log(NOARM_LOG, PROCEDURES, str(tmp_path / "b"),
                          str(tmp_path / "k"), with_timestamp=False)
    codes = {f.code for f in res["findings"]}
    assert "INT-NOARM" in codes
    assert res["conformance"]["not_evaluable"] == 6
    # abstention means no crash narrative
    assert "INT-TRUNC" not in codes


def test_unsupported_file_raises_clean_error(tmp_path):
    bad = tmp_path / "bad.ulg"
    bad.write_bytes(b"this is not a ulog")
    with pytest.raises(UnsupportedLogError):
        investigate_log(str(bad), None, str(tmp_path / "b"), str(tmp_path / "k"),
                        with_timestamp=False)

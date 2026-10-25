"""report.html is a signed Merkle leaf: editing or removing it fails verification."""

import hashlib
import json
import os
import subprocess
import sys

from air.evidence import build_bundle
from air.evidence.signing import PUBLIC_KEY_FILE

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(REPO, "verify.py")


def _report():
    return {"format": "air-incident-record/1",
            "sources": [{"path": "flight.ulg", "sha256": hashlib.sha256(b"log").hexdigest(),
                         "size_bytes": 3, "kind": "px4_ulog", "meta": {}}],
            "findings": [{"code": "BAT-LOW", "severity": "critical"}]}


def _bundle(tmp_path, with_html=True):
    out, keys = tmp_path / "bundle", tmp_path / "keys"
    seen = {}

    def render(fp):
        seen["fp"] = fp
        return f"<!doctype html><p>BAT-LOW critical</p><p>key {fp}</p>"

    manifest = build_bundle(_report(), str(out), str(keys), with_timestamp=False,
                            render_html=render if with_html else None)
    return out, keys, manifest, seen


def _verify(out, keys):
    p = subprocess.run([sys.executable, VERIFY, str(out), "--trusted-key",
                        str(keys / PUBLIC_KEY_FILE)], capture_output=True, text=True)
    return p.returncode, p.stdout


def test_html_is_a_leaf_and_verifies(tmp_path):
    out, keys, manifest, seen = _bundle(tmp_path)
    assert manifest["merkle"]["tree_size"] == 3
    assert manifest["merkle"]["leaves"][1]["kind"] == "report.html"
    layout = json.loads((out / "report.json").read_text())["bundle_layout"]
    assert layout == {"report_json_leaf": 0, "report_html_leaf": 1, "first_source_leaf": 2}
    assert seen["fp"] in (out / "report.html").read_text()   # fingerprint shown on the page
    code, stdout = _verify(out, keys)
    assert code == 0, stdout
    assert "[PASS] report.html is committed to the Merkle root" in stdout


def test_edited_html_fails(tmp_path):
    out, keys, _, _ = _bundle(tmp_path)
    page = out / "report.html"
    page.write_text(page.read_text().replace("critical", "info"))
    code, stdout = _verify(out, keys)
    assert code == 1
    assert "[FAIL] report.html is committed to the Merkle root" in stdout


def test_missing_html_fails(tmp_path):
    out, keys, _, _ = _bundle(tmp_path)
    (out / "report.html").unlink()
    code, stdout = _verify(out, keys)
    assert code == 1 and "file is missing" in stdout


def test_dropping_html_from_layout_breaks_report_leaf(tmp_path):
    # an attacker who rewrites the layout to skip the page must edit report.json
    out, keys, _, _ = _bundle(tmp_path)
    rp = out / "report.json"
    rep = json.loads(rp.read_text())
    rep["bundle_layout"]["report_html_leaf"] = None
    rp.write_text(json.dumps(rep, sort_keys=True, separators=(",", ":")))
    code, stdout = _verify(out, keys)
    assert code == 1
    assert "[FAIL] report.json is the record committed to the Merkle root" in stdout


def test_uncommitted_html_is_flagged_unsigned(tmp_path):
    out, keys, manifest, _ = _bundle(tmp_path, with_html=False)
    assert manifest["merkle"]["tree_size"] == 2
    (out / "report.html").write_text("<p>anything</p>")
    code, stdout = _verify(out, keys)
    assert code == 0
    assert "NOT covered by the signature" in stdout

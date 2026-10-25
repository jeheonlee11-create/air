"""Procedure-file validation: clear errors instead of KeyError / HTTP 500."""

import importlib.util
import io
import json
import os

import pytest

from air.analyze.conformance import ProcedureError, load_procedures, validate_procedures
from air.api import investigate_log

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = {"id": "ALT-1", "description": "d", "metric": "max_alt_agl_m", "op": "<=", "limit": 120}


def _err(proc) -> str:
    with pytest.raises(ProcedureError) as e:
        validate_procedures(proc, "p.json")
    return str(e.value)


def test_bundled_sample_ruleset_is_valid():
    proc = load_procedures(os.path.join(REPO, "procedures", "sample_ops_manual.json"))
    assert len(proc["rules"]) == 6


def test_missing_id_is_reported_not_keyerror():
    rule = {k: v for k, v in GOOD.items() if k != "id"}
    assert 'rule #1: missing or empty "id"' in _err({"rules": [rule]})


def test_every_problem_is_listed():
    msg = _err({"rules": [GOOD, GOOD, {"id": "X", "metric": "nope", "op": "!=", "limit": "a"},
                          {**GOOD, "id": "T", "tolerance": -1},
                          {**GOOD, "id": "M", "metric": "modes_flown"}]})
    assert "duplicate id" in msg
    assert "unknown metric 'nope'" in msg and "unknown op '!='" in msg
    assert 'missing "description"' in msg
    assert '"tolerance" must be a non-negative number' in msg
    assert "op '<=' cannot be used with metric 'modes_flown'" in msg


@pytest.mark.parametrize("proc", [[], {"rules": []}, {"rules": "x"}, {"name": "no rules"}])
def test_bad_shapes(proc):
    _err(proc)


def test_not_json_and_missing_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(ProcedureError, match="not valid JSON"):
        load_procedures(str(p))
    with pytest.raises(ProcedureError, match="not found"):
        load_procedures(str(tmp_path / "missing.json"))


def test_pipeline_rejects_bad_ruleset_before_parsing_the_log(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"rules": [{"description": "no id"}]}))
    with pytest.raises(ProcedureError):
        investigate_log(str(tmp_path / "not-even-read.ulg"), str(p), str(tmp_path / "b"),
                        str(tmp_path / "k"), with_timestamp=False)


def test_demo_returns_422_with_message(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    spec = importlib.util.spec_from_file_location("air_demo", os.path.join(REPO, "demo", "app.py"))
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    monkeypatch.setattr(demo, "RUNS_DIR", str(tmp_path / "runs"))
    client = demo.app.test_client()
    bad = json.dumps({"rules": [{"description": "no id", "metric": "max_alt_agl_m"}]})
    r = client.post("/run", data={
        "log": (io.BytesIO(b"not a ulog"), "flight.ulg"),
        "procedures": (io.BytesIO(bad.encode()), "rules.json"),
    }, content_type="multipart/form-data")
    assert r.status_code == 422
    assert 'missing or empty "id"' in r.get_json()["error"]

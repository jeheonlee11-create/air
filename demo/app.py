"""AIR local demo — upload a flight log, receive an incident record.

Local-first by design:
- Binds to 127.0.0.1 only.
- All processing happens on this machine via the same engine as the CLI
  (air.api.investigate_log — there is no second analysis implementation).
- The ONLY optional external call is RFC 3161 timestamping (OFF by default;
  when enabled it sends a 32-byte hash to the TSA, never any log data).
- Uploads and results are stored under demo/demo_runs/ on local disk and can
  be deleted from the UI at any time. Nothing is transmitted anywhere.

Run:  .venv/bin/python demo/app.py   →  http://127.0.0.1:8420
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_file,
)

from air import __version__
from air.api import ProcedureError, UnsupportedLogError, investigate_log
from air.evidence.signing import (
    PUBLIC_KEY_FILE,
    default_key_dir,
    load_or_create_key,
    public_key_fingerprint,
    public_pem,
)

RUNS_DIR = os.path.join(REPO, "demo", "demo_runs")
KEY_DIR = default_key_dir()  # same key as the CLI: $AIR_KEY_DIR or ~/.air/keys
SAMPLE_LOG = os.path.join(REPO, "fixtures", "75957ba9-f979-430d-a49c-8ef6e5ceec12.ulg")
SAMPLE_PROVENANCE = (
    "Public log 75957ba9-f979-430d-a49c-8ef6e5ceec12 from the PX4 Flight Review "
    "public database (review.px4.io), uploaded 2023-03-02, uploader rating "
    "“crash_sw_hw”, uploader description: “at minute 12, my drone "
    "started to gain altitude sharply…”")
PROCEDURES = os.path.join(REPO, "procedures", "sample_ops_manual.json")
MAX_UPLOAD = 200 * 1024 * 1024
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD

BASE_CSS = """
  :root { --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
          --muted:#898781; --grid:#e1e0d9; --blue:#2a78d6; --crit:#d03b3b;
          --crit-text:#a02020; --warn:#8a5a00; --good:#006300; }
  body { margin:0; background:var(--page); color:var(--ink);
         font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
  .page { max-width:820px; margin:0 auto; padding:36px 24px 60px; }
  .kicker { font-size:11px; letter-spacing:2.5px; color:var(--muted); font-weight:600; }
  h1 { font-size:22px; margin:10px 0 4px; }
  .sub { font-size:13px; color:var(--ink2); line-height:1.55; }
  .card { border:1px solid var(--grid); border-radius:8px; background:var(--surface);
          padding:18px 20px; margin:16px 0; }
  .btn { display:inline-block; border:1px solid var(--grid); border-radius:6px;
         background:var(--surface); color:var(--ink); padding:9px 16px; font-size:13.5px;
         font-weight:600; cursor:pointer; text-decoration:none; }
  .btn.primary { background:var(--blue); border-color:var(--blue); color:#fff; }
  .btn:focus-visible { outline:2px solid var(--blue); outline-offset:2px; }
  .note { font-size:12px; color:var(--muted); line-height:1.6; }
  .error { border-left:3px solid var(--crit); padding:10px 14px; background:var(--surface);
           color:var(--crit-text); font-size:13px; border-radius:4px; }
  .okmsg { color:var(--good); font-size:13px; }
  label { font-size:13px; font-weight:600; display:block; margin:12px 0 4px; }
  input[type=file] { font-size:13px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  td, th { padding:6px 10px 6px 0; border-bottom:1px solid var(--grid); text-align:left; }
"""

INDEX_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIR — drone incident investigation (local demo)</title>
<style>{{ css|safe }}</style></head><body><div class="page">
<div class="kicker">AIR — AIRSPACE INCIDENT RECORD · LOCAL DEMO v{{ version }}</div>
<h1>Upload a flight log. Receive an incident record.</h1>
<p class="sub">AIR reconstructs what happened in a drone flight from raw telemetry:
a synchronized timeline, deterministic findings with cited thresholds, disagreements
between independent sensors, and procedure-conformance verdicts — packaged as a
tamper-evident record you can verify offline. This is investigation and evidence
reconstruction software; it does not provide legal advice or promise legal
compliance or admissibility.</p>

<div class="card">
  <form id="f" enctype="multipart/form-data">
    <label for="log">Flight log (PX4 <code>.ulg</code> only, max 200 MB)</label>
    <input id="log" name="log" type="file" accept=".ulg" required
           aria-describedby="fmt-note">
    <div id="fmt-note" class="note">Currently supported: PX4 ULog. ArduPilot
      dataflash and DJI logs are not yet supported and will be rejected with a
      clear message.</div>
    <label for="proc">Procedures ruleset (optional JSON; defaults to the bundled
      sample Part 107-style ruleset)</label>
    <input id="proc" name="procedures" type="file" accept=".json">
    <label style="font-weight:400;margin-top:14px">
      <input id="ts" name="timestamp" type="checkbox" value="1">
      Request an RFC 3161 timestamp from FreeTSA (external call — sends only a
      32-byte hash of the record, never your log data). Off by default.
    </label>
    <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn primary" type="submit">Investigate log</button>
      <button class="btn" type="button" id="sample">Run the sample crash instead</button>
    </div>
  </form>
  <div id="status" role="status" aria-live="polite" style="margin-top:12px;font-size:13px"></div>
</div>

<div class="card">
  <strong style="font-size:13.5px">Sample data provenance</strong>
  <p class="note" style="margin:6px 0 0">{{ provenance }}</p>
</div>

<div class="card">
  <strong style="font-size:13.5px">Privacy &amp; data retention</strong>
  <p class="note" style="margin:6px 0 0">
    Processing is local: your log is analyzed on this machine by this process and
    is not uploaded to any external service. Results are written to
    <code>demo/demo_runs/</code> on this machine and persist until you delete them
    (a delete button is on every result page). The only optional network call is
    the RFC 3161 timestamp above, which transmits a 32-byte hash and never log
    content. No analytics, no tracking.</p>
</div>
<script>
const f = document.getElementById('f'), st = document.getElementById('status');
function busy(msg){ st.innerHTML = '<span aria-busy="true">&#8987; ' + msg + '</span>'; }
function fail(msg){ st.innerHTML = '<div class="error" role="alert">' + msg + '</div>'; }
async function submit(url, body){
  busy('Processing… parsing telemetry, running analyzers, building the signed record.');
  try {
    const r = await fetch(url, {method:'POST', body});
    const j = await r.json();
    if (!r.ok) { fail(j.error || ('Server error (' + r.status + ')')); return; }
    st.innerHTML = '<span class="okmsg">Done — opening record…</span>';
    window.location = '/run/' + j.run_id;
  } catch(e) { fail('Could not reach the local server: ' + e); }
}
f.addEventListener('submit', ev => { ev.preventDefault();
  const file = document.getElementById('log').files[0];
  if (!file) { fail('Choose a .ulg file first.'); return; }
  if (!file.name.toLowerCase().endsWith('.ulg')) {
    fail('Unsupported file type: ' + file.name + ' — AIR currently supports PX4 .ulg logs only.'); return; }
  if (file.size > {{ max_upload }}) { fail('File exceeds the 200 MB demo limit.'); return; }
  submit('/run', new FormData(f));
});
document.getElementById('sample').addEventListener('click', () => {
  const fd = new FormData();
  if (document.getElementById('ts').checked) fd.append('timestamp','1');
  submit('/run-sample', fd);
});
</script>
</div></body></html>"""

RESULT_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIR record {{ short_id }}</title>
<style>{{ css|safe }}
  iframe { width:100%; height:72vh; border:1px solid var(--grid); border-radius:8px;
           background:#fff; }
  .chips { display:flex; gap:10px; flex-wrap:wrap; margin:12px 0; font-size:13px; }
  .chip { border:1px solid var(--grid); border-radius:14px; padding:3px 12px;
          background:var(--surface); }
</style></head><body><div class="page">
<div class="kicker"><a href="/" style="color:inherit;text-decoration:none">&larr; AIR LOCAL DEMO</a></div>
<h1>Incident record</h1>
<div class="sub">{{ source_name }} · {{ duration }}s of log · generated {{ created }}</div>

{% if abstained %}
<div class="card" style="border-left:3px solid var(--warn)">
  <strong>AIR abstained from flight-level conclusions on this log.</strong>
  <p class="note" style="margin:6px 0 0">No arming event was found — this log does
  not contain a flight. Rather than invent findings, the record reports the
  abstention and marks flight-dependent procedure rules NOT_EVALUABLE. This is
  deliberate: absence of evidence is reported, never papered over.</p>
</div>
{% endif %}

<div class="chips" aria-label="record summary">
  <span class="chip" style="color:var(--crit-text)">{{ n_crit }} critical</span>
  <span class="chip" style="color:var(--warn)">{{ n_warn }} warnings</span>
  <span class="chip">{{ conf_line }}</span>
  <span class="chip">timestamp: {{ ts_status }}</span>
</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">
  <a class="btn primary" href="/run/{{ run_id }}/bundle.zip" download>Download signed bundle (.zip)</a>
  <button class="btn" id="verify">Verify record now</button>
  <form method="post" action="/run/{{ run_id }}/delete" style="display:inline"
        onsubmit="return confirm('Delete this run and all its files from local disk?')">
    <button class="btn" type="submit" style="color:var(--crit-text)">Delete this run</button>
  </form>
</div>
<pre id="vout" role="status" aria-live="polite" style="display:none;background:var(--surface);
  border:1px solid var(--grid);border-radius:8px;padding:12px;font-size:12px;
  white-space:pre-wrap;max-height:260px;overflow:auto"></pre>
<p class="note">The bundle contains <code>report.json</code> and <code>report.html</code>
(both covered by the signature), <code>manifest.json</code>, and <code>verify.py</code>.
To verify independently: unzip, then run <code>python3 verify.py --fingerprint
{{ fingerprint }}</code> in the bundle directory (in real use, take the fingerprint from
the operator, not from this page or the bundle) (requires Python 3.10+ and the <code>cryptography</code> package; no network
access is needed or used).</p>

<iframe src="/run/{{ run_id }}/report.html" title="Full incident record"></iframe>
<script>
document.getElementById('verify').addEventListener('click', async () => {
  const out = document.getElementById('vout');
  out.style.display = 'block'; out.textContent = 'Running standalone verifier…';
  const r = await fetch('/run/{{ run_id }}/verify', {method:'POST'});
  const j = await r.json();
  out.textContent = j.output + '\\n(exit code ' + j.exit + ')';
});
</script>
</div></body></html>"""


def _run_dir(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        abort(404)
    d = os.path.join(RUNS_DIR, run_id)
    if not os.path.isdir(d):
        abort(404)
    return d


def _execute(log_path: str, procedures_path: str, with_timestamp: bool, source_name: str):
    run_id = uuid.uuid4().hex[:12]
    out_dir = os.path.join(RUNS_DIR, run_id, "bundle")
    try:
        investigate_log(log_path, procedures_path, out_dir,
                        KEY_DIR, with_timestamp=with_timestamp)
    except (UnsupportedLogError, ProcedureError) as e:
        shutil.rmtree(os.path.join(RUNS_DIR, run_id), ignore_errors=True)
        return None, str(e)
    with open(os.path.join(RUNS_DIR, run_id, "meta.json"), "w") as f:
        json.dump({"source_name": source_name}, f)
    return run_id, None


@app.get("/")
def index():
    return render_template_string(INDEX_HTML, css=BASE_CSS, version=__version__,
                                  provenance=SAMPLE_PROVENANCE, max_upload=MAX_UPLOAD)


@app.post("/run")
def run_upload():
    f = request.files.get("log")
    if f is None or not f.filename:
        return jsonify({"error": "No file received."}), 400
    if not f.filename.lower().endswith(".ulg"):
        return jsonify({"error": f"Unsupported file type: {f.filename}. AIR currently "
                                 f"supports PX4 .ulg logs only."}), 415
    run_id = uuid.uuid4().hex[:12]
    updir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(updir, exist_ok=True)
    log_path = os.path.join(updir, "uploaded.ulg")
    f.save(log_path)

    proc_path = PROCEDURES
    pf = request.files.get("procedures")
    if pf is not None and pf.filename:
        proc_path = os.path.join(updir, "procedures.json")
        pf.save(proc_path)

    out_dir = os.path.join(updir, "bundle")
    try:
        investigate_log(log_path, proc_path, out_dir, KEY_DIR,
                        with_timestamp=bool(request.form.get("timestamp")))
    except (UnsupportedLogError, ProcedureError) as e:
        shutil.rmtree(updir, ignore_errors=True)
        return jsonify({"error": str(e)}), 422
    with open(os.path.join(updir, "meta.json"), "w") as f2:
        json.dump({"source_name": f.filename}, f2)
    return jsonify({"run_id": run_id})


@app.post("/run-sample")
def run_sample():
    if not os.path.exists(SAMPLE_LOG):
        return jsonify({"error": "Sample log missing from fixtures/ — see README for "
                                 "the download command."}), 500
    run_id, err = _execute(SAMPLE_LOG, PROCEDURES,
                           bool(request.form.get("timestamp")),
                           "sample: public PX4 corpus log 75957ba9 (crash_sw_hw)")
    if err:
        return jsonify({"error": err}), 422
    return jsonify({"run_id": run_id})


@app.get("/run/<run_id>")
def result(run_id: str):
    d = _run_dir(run_id)
    with open(os.path.join(d, "bundle", "report.json")) as f:
        report = json.load(f)
    with open(os.path.join(d, "meta.json")) as f:
        meta = json.load(f)
    codes = {x["code"] for x in report["findings"]}
    n_crit = sum(1 for x in report["findings"] if x["severity"] == "critical")
    n_warn = sum(1 for x in report["findings"] if x["severity"] == "warning")
    conf = report.get("conformance")
    conf_line = (f"procedures: {conf['passed']} pass / {conf['failed']} fail / "
                 f"{conf.get('marginal', 0)} marginal / {conf['not_evaluable']} not evaluable"
                 if conf else "no procedures")
    with open(os.path.join(d, "bundle", "manifest.json")) as f:
        manifest = json.load(f)
    ts_status = manifest.get("rfc3161_timestamp", {}).get("status", "absent")
    # from the operator's own key, not from the bundle being verified
    fingerprint = public_key_fingerprint(public_pem(load_or_create_key(KEY_DIR)))
    return render_template_string(
        RESULT_HTML, css=BASE_CSS, run_id=run_id, short_id=run_id[:6],
        source_name=meta.get("source_name", "uploaded log"),
        duration=report["flight"]["duration_s"], created=report["created_utc"],
        abstained="INT-NOARM" in codes, n_crit=n_crit, n_warn=n_warn,
        conf_line=conf_line, ts_status=ts_status, fingerprint=fingerprint)


@app.get("/run/<run_id>/report.html")
def report_html(run_id: str):
    return send_file(os.path.join(_run_dir(run_id), "bundle", "report.html"))


@app.get("/run/<run_id>/report.json")
def report_json(run_id: str):
    return send_file(os.path.join(_run_dir(run_id), "bundle", "report.json"))


@app.get("/run/<run_id>/bundle.zip")
def bundle_zip(run_id: str):
    d = _run_dir(run_id)
    zpath = os.path.join(d, "bundle.zip")
    if not os.path.exists(zpath):
        shutil.make_archive(zpath[:-4], "zip", os.path.join(d, "bundle"))
    return send_file(zpath, as_attachment=True,
                     download_name=f"air-record-{run_id}.zip")


@app.post("/run/<run_id>/verify")
def verify(run_id: str):
    d = _run_dir(run_id)
    # The demo server is the operator here, so it verifies against its own
    # signing key (written by load_or_create_key) as the trust anchor.
    load_or_create_key(KEY_DIR)  # ensures the .pub.pem exists
    pub = os.path.join(KEY_DIR, PUBLIC_KEY_FILE)
    p = subprocess.run([sys.executable, "verify.py", "--trusted-key", pub],
                       cwd=os.path.join(d, "bundle"), capture_output=True, text=True,
                       timeout=60)
    return jsonify({"exit": p.returncode, "output": p.stdout + p.stderr})


@app.post("/run/<run_id>/delete")
def delete(run_id: str):
    shutil.rmtree(_run_dir(run_id), ignore_errors=True)
    return redirect("/")


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "File exceeds the 200 MB demo limit."}), 413


if __name__ == "__main__":
    os.makedirs(RUNS_DIR, exist_ok=True)
    app.run(host="127.0.0.1", port=8420, debug=False)

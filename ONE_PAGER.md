# AIR — Airspace Incident Record
*One-pager · July 28, 2026 · pre-revenue, pre-customer, solo founder*

**AIR reconstructs drone incidents from raw telemetry and produces an explainable, tamper-evident record. In initial testing on public PX4 crashes, it identified procedure violations and sensor conflicts that ordinary log viewers leave investigators to find manually.**

## What it does
Upload a flight log → get a synchronized timeline, deterministic findings (every threshold cites its published basis), disagreements between independent sensors reported as findings, PASS/FAIL verdicts against the operator's own written procedures, and a signed record bundle anyone can verify offline with a 200-line standalone script. Missing evidence is reported, never papered over: logs that contain no flight get an explicit abstention, and unevaluable rules say so.

## Who has the problem
Anyone who must explain a drone incident to someone with power over them: fleet operators answering insurers and clients; manufacturers' support teams triaging customer crash logs; test sites and universities writing safety cases; investigators billing $3,000–$12,000 per manual reconstruction (published service pricing); public-safety programs facing transparency obligations. **Which of these will pay is untested — 10 discovery interviews are the next milestone, and the interview kit is written.**

## What exists today
Log *viewers* (PX4 Flight Review — free plots, expert-read; Airdata — polished replay, 200+ aircraft, anomaly trends and audit-ready compliance reports). In our July 2026 survey of public materials, we found no product offering post-hoc procedure verdicts against an operator's own rules, cross-sensor conflict findings, or cryptographically verifiable incident records — recorded per-product as "not shown publicly," which is not proof of absence. Skydio/Axon hash captured *media* for chain of custody in their cloud ecosystem; that is adjacent, not the same artifact.

## What has been tested (and what hasn't)
On a seeded 100-log sample of the public PX4 corpus (development fixtures excluded, metrics pre-registered): 99% ingestion, zero uncaught pipeline errors, byte-identical analysis across repeated runs (10/10), tamper detection on altered records (5/5), zero false-positive "ends-in-flight" calls against uploader labels — with honest weaknesses published alongside: 12% recall on noisy "crash" labels (most crashes keep logging to the ground; impact-signature detection is unbuilt), PX4-only ingestion, and evaluation on 100 logs, not 436,000. **Untested: demand, pricing, every market claim.**

## What makes the approach different
Epistemic discipline as product: raw evidence, deterministic calculation, inference, verdict, and unknown are separated and labeled in every record; the verifier is built for a hostile reader; the evaluation publishes false negatives. In a domain where the record gets challenged, being conservatively right is the feature.

## What remains unverified
Willingness to pay; which segment feels the pain hardest; whether "good enough" manual records beat us; DJI/ArduPilot format demand; every regulatory-market hypothesis (a rule effective July 2026 imposes audit-trail and reporting duties on certain counter-UAS-authorized agencies — it does not require our technology, and counsel hasn't reviewed our reading; question list drafted).

## Why now
2025–2026 brought incident-documentation pressure from several directions at once — new counter-UAS authority for covered agencies with recordkeeping duties, a pending BVLOS rule with operator reporting proposals, insurer interest in telemetry-based claims — while the tooling in market remains viewers and dashboards. Timing claims beyond that are speculation, and we treat them as such.

## Next 30 days
Attorney review of the regulatory question list · 10 discovery interviews from the prepared kit (founder-sent) · fresh-seed confirmation of the evaluation · ArduPilot ingestion only if interviews demand it · no public claims beyond this page.

*No users, revenue, partnerships, accuracy guarantees, or customer interest are claimed. Working demo: `demo/` in the repo, runs locally in under a minute.*

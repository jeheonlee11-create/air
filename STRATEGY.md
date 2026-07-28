# AIR — Airspace Incident Record
## Strategy memo — July 28, 2026

*Synthesis of ~9 deep research passes (≈150 web searches, primary sources including the full 180-page DOJ/DHS rule text). Verdicts below cite the load-bearing sources; full citations live in the research transcripts.*

---

## 1. The one-paragraph thesis

Counter-drone authority just reached 1,650+ state/local agencies (DOJ/DHS interim final rule, effective July 1, 2026), and with it came a federal mandate: a searchable, tamper-protected, six-year audit trail and 48-hour post-operation reports, backed by $100K-per-violation fines — with **no software product in existence that produces them**. AIR is that product: it turns drone incident evidence (flight logs, detection alerts, weather, written procedures) into a defensible, cryptographically signed incident record. Commercial drone fleets (Part 108, final rule at OIRA now) become the second market with the same engine.

## 2. Is the idea taken? No — verified across ~35 vendors

Nobody ships the three core capabilities together or separately:

| Capability | Closest existing thing | Gap |
|---|---|---|
| Procedure-conformance verdict (flight vs. the operator's own written rules) | DroneLogbook threshold alerts | Real-time nags, not post-hoc verdicts against a document |
| Cross-source conflict analysis (which sensors agree/dispute) | Nothing. Every replay tool (Airdata 3D Player, D-Fend Replay View, Foxglove, SkySafe) is single-source | Absent from the market entirely |
| Cryptographically signed incident report | Skydio hashes captured media; Cellebrite hashes extractions; Axon fingerprints files | **Nobody signs the report itself.** Only related patent (US10703478) covers pre-flight plan signing |

Category language is unclaimed: "airspace incident record", "drone evidence package", "counter-UAS incident documentation", "UAS occurrence report software" — all free.

**Corrections from earlier assumptions:** FlybyOps (feared competitor) is a 69-day-old site with no legal entity, no team, no funding, no telemetry parsing — a positioning threat only. "Truvo" does not exist. The law-enforcement extraction-forensics lane (seized drone → attribute pilot) is closing fast — Cellebrite acquired SCG Canada (Mar 2026) and locked SkySafe exclusive (Jul 2026) — **do not enter that lane**; it doesn't overlap with the operator/defender-side record.

## 3. The forcing function (the part that makes this fundable)

**6 CFR / 28 CFR Part 124** (SAFER SKIES interim final rule, effective July 1, 2026):

- **§ 124.14(g)** — audit trail "searchable and accessible to compliance auditors, protected against unauthorized modification or deletion, and retained for a minimum of 6 years. The agency's implementation policy **must specify the format and system of records** for the audit trail." ← the procurement trigger: every agency must *name* a system of records.
- **§ 124.13** — 48-hour post-operation report, 7 mandatory elements, including per-system **firmware/software versions as deployed** and **deduplicated detection counts** — near-impossible to produce by hand after the fact.
- **§ 124.14(d)** — 180-day purge cap, 90-day reviews, documented retention bases, purge *verification* recorded in the audit trail.
- **§ 124.16(b)** — civil fines up to **$100,000 per violation**; audits explicitly review post-operation reports.
- Government's own sizing: **~1,500 detection-tier + ~150 mitigation-tier agencies** in two years; ~72,000 aggregate burden-hours/year.
- **§ 124.4(b) helps us:** contractors may NOT operate C-UAS ("turnkey/managed service" = unauthorized delegation) — killing managed-service competitors and pushing the compliance workload onto agency staff, who need tooling. A documentation SaaS is explicitly outside the prohibition ("detection services that do not require the authority of the Act... may be provided by contractors").

**The money exists:** FEMA C-UAS Grant Program (DHS-FEMA-C-UAS-161, $500M; Pub. L. 119-21 §90005(a)) lists **"Third Party Data Service Providers," "sensor fusion software," and "UAS SaaS subscription models... data as a service"** as named allowable equipment costs. FY2026 = $250M to 11 World Cup states + NCR; **FY2027 = $250M+ open to all 56 states/territories, NOFO expected late 2026**. Secondary: Byrne JAG, COPS.

Second wave: **Part 108** (BVLOS) — final rule at OIRA since July 10, 2026, publication late 2026/early 2027. Its NPRM hard-codes the workload: 10-day safety-event reports, 96-hour security-occurrence reports, monthly data submissions, 2-year retention, SMS for certificated operators.

## 4. Who buys, in order

1. **Corrections** — best-fit vertical: standing 365-day authorizations (§124.8(h)(2)) + per-event reporting + prosecutions needing evidence (June 2026: 12 indicted across 10 federal prisons; new 5-year sentence enhancement). Named pain: SC DOC (273 incidents in 2025), Georgia (58/month, AG lobbying publicly), federal BOP. San Bernardino County Probation already RFP'd detection for 3 facilities (PROB26-PROB-6069).
2. **The Agency Approving Official + agency counsel** (roles *created by the rule*; counsel must review policy annually) at the 1,500 detection-tier agencies.
3. **Critical-infrastructure sites** (airports via TSA-NA-14-01B immediate-reporting duty; utilities via NERC EOP-004-4/OE-417; stadiums post-World Cup — 700+ drones seized, detection hardware now deployed and evidence-layer-less).
4. **Commercial/BVLOS fleets + insurers** when Part 108 lands (USAIG already pays up to **$2,500/policy-year** toward safety software — the distribution template; contacts: Paul Ratté/USAIG, Dana DiPietro/Global Aerospace).

Pricing anchors: forensics tools $6K–$90K/seat/yr; DFR programs $125K–$850K/yr; aviation SMS $3K–$90K/yr. Sell as evidence/compliance (those anchors), never as a logbook ($7–20/user/mo lane). Litigation Forensics charges **$6K–$12K per manual incident reconstruction** — AIR does it in minutes; per-report pricing writes itself.

## 5. Moat plan (ranked by defensibility per unit of effort)

**Do immediately:**
1. **File a public comment on the IFR before September 4, 2026** (Docket FBI-2026-0001) proposing an audit-trail data schema for §124.14(g) and report format for §124.13(c). Unrepeatable once the window closes; a schema echoed in the final rule is a moat no funding buys back.
2. **Start the transparency log now** — the Merkle log's *age* is the moat (a 2028 competitor cannot backdate history). Already running in the MVP.
3. **ASTM membership ($115/yr)** — join **F38 (UAS)** *and* **E30.12 (Digital & Multimedia Evidence)**; apparently nobody sits at both.
4. Draft **model §124.6 implementation-policy language** naming AIR as the audit-trail system of records; give it away to agencies. The policy is legally required, counsel-reviewed, annually renewed — whoever's language gets adopted is embedded.

**6–18 months:** author the drone-forensics tool-testing methodology (NIST CFTT has **no drone category** — unclaimed institutional ground); SWGDE membership + Request-for-Modification to 21-F-002; publish validation per ASTM E3016 (answers Daubert's error-rate prong, which is the field's known weak point); standing FRE 902(13) certification template + named qualified person.

**18 months+:** get onto the §124.7 **Authorized Systems List** (six-agency federal whitelist — maximum copy difficulty); vendor training plugged into the FBI NCUTC pipeline (the Cellebrite playbook: trained examiners write your tool into SOPs, then testify it's "industry standard").

**Legal positioning discipline (from the evidence-standards research):**
- Market as "designed to support authentication under FRE 902(13)" — **never "court-admissible"** (authentication ≠ admissibility; overclaiming is legal risk).
- Output = *record of measured, provenanced sensor data*, **never a physics reconstruction** (a "simulation" makes the computer the expert → full Daubert exposure; an authenticated record does not).
- Deterministic rules with cited thresholds, no ML verdicts — "the examiner could not explain the tool" is the #1 way digital evidence dies in court.

## 6. Who kills this, and the clock

| Threat | Move | Timeline |
|---|---|---|
| **Cellebrite** | Wrap timeline UI around CFID + SkySafe + Guardian; they already blog about hashes/Daubert/evidence packaging | 3–6 months |
| **Axon** | "Axon Air Review": Dedrone detections + flight logs + bodycam → Evidence.com package. Job postings show a Dedrone PM owning "historical analysis tools"; Dedrone bookings +500% YoY | 6–12 months |
| **Motorola + D-Fend** ($1.5B deal, June 2026) | D-Fend's EnforceAir Analytics already ships incident Replay View; Motorola owns the records/evidence layer | 12–18 months |
| **Airdata** | Signed "incident report" export on top of 61M flights and 180+ supported aircraft | 12–24 months (culture gap: $2.99/mo DNA) |
| **Versaterm** (sleeper) | Owns Aloft + DroneSense + forensics RMS; nobody is watching | — |

**Survival logic:** every one of them is conflicted (they'd be grading their own detections/drones) or buyer-mismatched. The neutral-evidence position + the regulatory-schema moves above are the counters. Also the realistic exit: these five are the acquirer list (comps: Aerodome $300M+ at 17 months old; SCG undisclosed; Dedrone undisclosed; aviation-SMS niche leaders £18M/C$18M — the spread between "niche safety software" and "strategic evidence layer" is the whole game).

## 7. Honest risks (read before quitting anything)

1. **"Good enough" is the competitor** — a spreadsheet + network share technically satisfies §124.14(g). The counter is the 48-hour report's impossible-by-hand elements (firmware versions, deduplicated counts) and the $100K audit exposure.
2. **No solicitation asks for this by name yet** (every 2025-26 RFP found specifies sensors). Category creation on a 12-month grant clock is the central execution risk. The FY2027 NOFO (late 2026) is the deadline for getting language into state Investment Justifications.
3. **Detection-tier pain is modest** (~33 hrs/yr by the government's own estimate); urgency concentrates in mitigation agencies + corrections. Volume ≠ urgency.
4. **Part 108 could slip or dilute** (already delayed by shutdown; industry pushback on reporting burden is loud).
5. **DJI ingestion rests on a revocable API key** from a company whose partners (Airdata) are incumbents — which is why the MVP is built on open formats (PX4/ArduPilot, no gatekeeper, 436K-log free corpus) with DJI as a phase-2 distribution play, not a foundation.
6. **The "millions" math:** realistic bottom-up ARR at niche scale is ~$2.4M (50 fleets × $15K + 20 agencies × $40K + 2 insurers × $150K + 10 sites × $50K) → a $15–25M outcome on the safety-software path. The venture-scale outcome requires winning the agency/evidence wedge before Axon/Cellebrite close it — that is what the Sept 4 comment, the FY2027 grant cycle, and the ASL listing are for. The cross-domain "accountability for autonomous systems" story is real but dated **Dec 2027 / Aug 2028** (EU AI Act Art. 12/19/26/73, already slipped once) — it's the Series A slide, not the seed revenue.

## 8. 90-day plan (Jul 28 → Oct 26, 2026)

1. **Wk 1–3:** Ship the free tool — "upload a log → incident report" (the SERP for "drone incident report template" is empty; SecurityScorecard's free-widget → $140M ARR is the template). The engine in this repo is that tool.
2. **Wk 1–5:** Write and file the **IFR comment (due Sept 4)** proposing the §124.14(g) schema. Publish it as content simultaneously.
3. **Wk 2:** Email David Kovar (URSA; founded UAV forensics, feeds FAA/CBP) — design partner, validator, or acquirer-adjacent; know which within 30 days.
4. **Wk 3+:** Launch monthly "Drone Incident Evidence Briefing" (clone D-Fend's rogue-drone briefing with an evidence lens; June 2026 material: JFK collision, Eastern Iowa contractor incident, FCC Pollock, Sing Sing).
5. **Sept 1–3:** Commercial UAV Expo + DRONERESPONDERS Public Safety Summit, Las Vegas (conference pass, no booth; World Cup C-UAS lessons-learned session is the room).
6. **Aug–Oct:** Corrections outreach — SC DOC, GA AG's office, and the ACA Congress program book; pitch: "you detect them; you can't prosecute or defend budget without a defensible record."
7. **Wk 4–6:** Insurance channel — Ratté (USAIG) and DiPietro (Global Aerospace) with the $2,500/policy-year precedent.
8. **Wk 5–8:** Consultant channel as resellers (Litigation Forensics, Envista, Robson — they do manually what AIR automates).
9. **Sept 14–16 / Oct 24–27:** GSX (submit session: "After the Detection Alert: Building a Defensible Drone Incident Record") and IACP floor.
10. **By Oct 26:** three paid pilots ($5–15K each), one per segment: a corrections/DFR agency, a utility (Entergy's UAS manager is on record about the data-management pain), a post-World-Cup venue.

## 9. What exists as of today

Working MVP in this repo (see README): PX4 ULog ingestion with cross-version aliasing → normalized timeline → deterministic analyzers (ported from the ruleset ArduPilot deleted in 2024 + PX4 ecl_ekf conventions) → cross-source conflict detection → procedure-conformance verdicts → canonical signed JSON record + RFC 9162 Merkle tree + Ed25519 signature + live RFC 3161 timestamp → self-contained HTML record + standalone offline verifier. Validated against real labeled crashes from the 436,637-log public PX4 corpus; tamper test passes (single-byte change → verification fails).

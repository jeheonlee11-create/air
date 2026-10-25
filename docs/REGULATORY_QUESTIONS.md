# Questions for a regulatory attorney / experienced counter-UAS practitioner

Purpose: these must be answered **before** we (a) cite 6/28 CFR Part 124 in any sales or marketing material, (b) decide whether to file a public comment (deadline: September 4, 2026, Docket FBI-2026-0001), or (c) build Part 124-specific product features. Our current understanding comes from our own reading of the public-inspection PDF and law-firm client alerts; none of it has been verified by counsel.

## Scope and applicability
1. Please confirm, against the final CFR text: which entities are "covered" SLTT agencies, and precisely which activities trigger Part 124 obligations vs. fall outside them (especially passive-sensor detection that does not rely on the Act's authority).
2. Do the audit-trail and reporting obligations attach to *detection-tier* agencies in any per-event form, or only via semiannual summaries? What exactly must a small sheriff's office that only detects (never mitigates) retain?
3. Private critical-infrastructure owners: is there any obligation or safe-harbor documentation practice the rule creates for them (e.g., documenting protection requests to SLTT agencies), or is that purely voluntary?

## The audit-trail requirement (§124.14(g))
4. What, in your judgment, satisfies "protected against unauthorized modification or deletion" in practice? Would an access-controlled shared drive or a records-management system pass an audit? Is there any precedent (from CJIS, body-camera, or wiretap-records audits) for what auditors accept?
5. The rule says the agency's implementation policy "must specify the format and system of records for the audit trail." Are there constraints on what may be named (e.g., must it be a government system, may it be a commercial SaaS, may it be vendor-hosted vs. agency-hosted)?
6. Does naming a commercial product in an implementation policy create procurement obligations (sole-source exposure, competitive-bid triggers) we should understand before suggesting model policy language?

## Reporting (§124.13)
7. Please verify the 48-hour trigger set and the exact seven data elements from the final text, including whether the firmware/software-version element applies to all reportable actions or only certain mitigation categories.
8. Who is legally responsible for report accuracy, and what liability attaches to a third-party tool that helps generate a report containing an error?

## Enforcement (§124.16)
9. Confirm the fine structure ($100,000 per violation), which violations it actually reaches, and the scope of the good-faith / self-report safe harbor. Is describing the fine in marketing accurate-but-misleading if the safe harbor makes first-violation fines unlikely?

## Data handling constraints that shape our architecture
10. §124.14(d) retention caps (180-day communications purge, review cycles): if an agency stores counter-UAS data in AIR, do these caps impose deletion obligations on us as a processor, and how do they interact with the 6-year audit-trail retention?
11. §124.14(j) vendor access to raw sensor data "for diagnostics… provided communications content is removed": does ordinary SaaS processing of detection data fall inside or outside this provision?
12. §124.15 sensitivity markings and public-records-resistance obligations: what marking/redaction capabilities would a compliant system of records need?

## The comment decision
13. Is filing a comment advisable at all for a pre-revenue vendor (visibility vs. anchoring positions we may regret)? If yes, what narrow, technically-grounded points are worth making, and what should we avoid claiming?
14. Are there ex parte or lobbying-registration considerations for a vendor engaging agencies about a rule during an open comment period?

## Practitioner reality-check (for a counter-UAS operator, not a lawyer)
15. How are agencies actually planning to satisfy the audit trail and 48-hour reports today — what tools, what staffing? Have you seen any solicitation language referencing these obligations?
16. What would make an Agency Approving Official trust a signed record from a small vendor — and what would make them laugh it out of the room?

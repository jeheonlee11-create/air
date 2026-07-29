# Site verification report — 2026-07-28

Artifact: `site/public/` (253 KB, 18 files). Server for testing: `site/tools/serve.py`,
which applies the production `_headers` values so CSP is enforced during tests.

## Automated (release gate inside `site/build.py` — build fails on violation)
- ✅ No `.ulg`, `.pem`, `.key` files in artifact; no PEM blocks
- ✅ No local filesystem paths (`/Users/`) or usernames in artifact
- ✅ Banned-language scan clean (court-admissible, tamper-proof, military, blockchain,
  guaranteed*, certified, patent, "no competitors", "only product", compliant, proven,
  "trusted by", "our customers", hype vocabulary) — *negated usages allowlisted
  ("not a guaranteed crash detector")
- ✅ Required caveat text present (We evaluated 100 · uploader-assigned labels ·
  round-2 disclosure · fresh-seed run owed · license note · both email addresses)
- ✅ All internal links/assets resolve (checked every href/src in every page)

## Headers (curl against local server, identical values ship in `_headers`)
- ✅ CSP: `default-src 'none'` with per-type `'self'`; `frame-ancestors 'none'`; `form-action 'self' mailto:`
- ✅ X-Content-Type-Options nosniff · X-Frame-Options DENY · Referrer-Policy no-referrer ·
  Permissions-Policy (camera/mic/geo/payment/usb/FLoC off) · COOP/CORP same-origin

## Browser testing (Chromium engine, local server)
- ✅ Desktop (1280): all sections render; annotations at real evidence timestamps
- ✅ Tablet (768×1024): zero horizontal overflow
- ✅ Mobile (375×812): zero horizontal overflow; nav wraps; charts scroll within panels
- ✅ Console: zero errors/warnings with CSP enforced
- ✅ Scrubber: live readout from real data (verified at T+580: EKF 49.3 m, battery 0%,
  23.1 V, last event POSITION→OFFBOARD) ; cursor lines move in both charts
- ✅ Keyboard: skip-link first; focus visible (2.5px signal outline verified computed)
- ✅ Anchor jumps clear the sticky header (scroll-margin)
- ✅ Section screenshots captured: hero, crash reconstruction, record integrity,
  evaluation (stats + caveats), limitations, CTA

## No-JS / reduced-motion
- ✅ curl (executes no JS) contains all core content: findings, 120.04, conformance,
  eval numbers, VERIFICATION PASSED, emails, chart SVGs
- ✅ Scrubber is display:none without the JS-set class; plain mailto fallback with prefilled
  body is present for the form
- ✅ All animation lives inside `@media (prefers-reduced-motion: no-preference)`; the base
  state is the fully-drawn static visual (verified by construction + code review), plus a
  global animation-none reduce block

## Repo hygiene
- ✅ `ruff check .` — clean (site tools included)
- ✅ `pytest` — 16/16 passing (engine untouched by site work)
- ✅ Build is deterministic: rebuild produced byte-identical artifact totals
- ✅ Local demo remains local-only (binds 127.0.0.1; not referenced by the public site)

## Not verified / known gaps (honest list)
- **Lighthouse not run** — no Chrome CLI/Node toolchain on this machine and the $0
  constraint precludes adding one; proxies: 253 KB total, zero external requests,
  no render-blocking third parties, semantic HTML. Run Lighthouse from any Chrome
  DevTools after deploy for the numbers.
- **Reduced-motion tested by code construction**, not by OS-level toggle in the harness
  (the embedded browser doesn't expose the emulation switch).
- **Real mail-client behavior of long mailto bodies** varies by client; the plain
  address is always shown alongside as fallback.
- **OG card rendering** verified as a generated 1200×630 PNG, but not against live
  Slack/Twitter scrapers (needs a public URL).
- Cross-browser (Safari/Firefox) not exercised in-harness; the site uses no APIs newer
  than widely-supported baselines (CSS custom properties, clamp, grid, `<input type=range>`).

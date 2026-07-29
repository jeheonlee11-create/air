# AIR site design system

**Concept: editorial forensic.** The site should feel like a precision instrument's
documentation — calm, technical, high-trust — with the real crash data as the only drama.
No stock imagery, no AI-startup gradients, no military anything. Every visual is generated
from the canonical record (`bundles/site-source/`) by code in `site/tools/`.

## Palette (all values in `site.css` custom properties)
| Token | Value | Role | Contrast (measured) |
|---|---|---|---|
| `--paper` | `#f7f5f0` | warm-white page | — |
| `--panel` | `#fdfcf9` | chart/card surface | — |
| `--ink` | `#141413` | primary text | 16.9:1 on paper (AAA) |
| `--ink-2` | `#3a3937` | body text | 10.6:1 (AAA) |
| `--muted` | `#75726c` | secondary/axis text | 4.4:1 (AA) |
| `--signal` | `#c2410c` | THE one signal color: CTAs, focus rings, EKF trace, wordmark dot | white on signal 5.2:1 (AA) |
| `--signal-ink` | `#9a3409` | links on paper | 6.7:1 (AA+) |
| `--crit` / `--warn` / `--ok` | `#b3261e` / `#8a5a00` / `#1d6b2a` | evidence-state semantics | 6.4 / 5.8 / 6.4:1 (AA+) |
| `--dark` / `--dark-2` | `#131211` / `#1c1b19` | hero, pipeline, integrity, CTA sections | — |
| `--dark-ink` / `--dark-muted` | `#f0ede6` / `#a09c93` | text on dark | 16.0 / 6.8:1 |
| trace colors | baro `#2563af` · gps `#0e7d6f` · ekf `#c2410c` | chart series, mirrored in HTML legends | decorative |

Status semantics are consistent everywhere: **crit red** = critical finding/FAIL/log-end,
**warn amber** = warning/conflict, **green** = PASS/verification, **muted italic** =
unknown/not-evaluable, **violet-gray tag** = inference. Six epistemic tags (`.tag-*`) mark
Raw evidence / Calculation / Procedure verdict / Conflict / Inference / Unknown.

## Typography
- Sans: `system-ui, -apple-system, "Segoe UI", Roboto, …` — body, headings.
- Mono: `ui-monospace, "SF Mono", Menlo, Consolas` — timestamps, hashes, kickers, table
  numerics, evidence rows. Monospace is the "instrument voice": anything measured or
  cryptographic renders in it.
- Scale: h1 `clamp(30px→50px)`, h2 `clamp(24px→34px)`, body 16px/1.6, small 13.5px,
  kickers 12px with 0.22em tracking. No webfonts — $0 and zero requests.

## Layout & texture
- One column, `max-width 1080px`, sections 74px vertical rhythm (54px mobile).
- Thin 1px grids (`--grid #e4e1d8` light, `#2a2926` dark) — the "technical grid" texture.
- Alternating paper/dark sections: hero(dark) → crash(paper) → pipeline(dark) →
  record(paper, with dark integrity card) → evaluation(paper) → limitations(paper) →
  CTA(dark). Dark frames the product's two "sealed" moments: the story and the ask.

## Motion policy
- Exactly one animation: the hero trace draws itself (stroke-dashoffset, 2.8s) and its three
  markers fade in. Defined ONLY inside `@media (prefers-reduced-motion: no-preference)` —
  the base state is the complete static image, so reduced-motion users, no-JS users, and
  crawlers all get the finished visual. A global reduce block kills all animation besides.
- No parallax, no scroll-jacking, no autoplaying anything.

## Charts (generated, not drawn)
`site/tools/render_charts.py` renders inline SVG from `crash.json`: min/max-preserving
downsampling (≤241 pts/series), annotations placed at exact evidence timestamps from the
record, `<title>+<desc>` for screen readers, presentation attributes only (CSP-safe: no
inline styles). Wide charts scroll inside `.panel-chart` (`overflow-x:auto; min-width 620px`)
so mobile never overflows the page.

## Accessibility contract
Skip link → `#main`; sticky header with real `<nav aria-label>`; one `<h1>`; landmarks;
`:focus-visible` 2.5px signal outline everywhere; charts have text alternatives; the
scrubber is a native `<input type=range>` with `aria-live` readout, hidden entirely when JS
is absent; tables carry `<caption>` + `scope`; all text ≥AA contrast (measured, above);
`scroll-margin-top` clears the sticky header on anchor jumps.

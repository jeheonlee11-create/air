# External-dependency & network-request report — the $0 proof

Generated 2026-07-28 for the `site/public/` artifact.

## Network requests the deployed site makes

**Runtime (visitor's browser), exhaustive list:**
| Request | Destination | When |
|---|---|---|
| HTML/CSS/JS/SVG/PNG/JSON assets | air.findanything.dev (same origin) | page load |
| `/assets/data/crash.json` | same origin | only if JS runs and the scrubber exists |
| — | **no other destination is reachable** | CSP `default-src 'none'` + per-type `'self'` makes any external request a browser-enforced error, not just a policy |

Outbound links (user-initiated navigation only, not resource loads): two `https://review.px4.io/...`
citation links; `mailto:` links open the visitor's own mail client. Zero third-party scripts,
fonts, pixels, iframes, or CDNs. No cookies, no storage APIs used.

**Build time (developer machine only, not the visitor):** Python stdlib + `pyulog` (parses the
local fixture log) + `Pillow` (renders og/poster/icon PNGs locally). Both free, open-source,
already vendored in `.venv`. macOS system fonts are rasterized into the PNGs locally; no font
files are shipped or embedded.

## Services and their cost
| Item | Tier used | Cost | Could it ever charge? |
|---|---|---|---|
| Cloudflare Pages (static hosting) | Free | $0 | Free tier: unlimited static bandwidth/requests; 500 builds/mo (direct upload uses none). Paid features (Functions beyond free, Zaraz, etc.) are simply not used — nothing in the artifact can invoke them. |
| Cloudflare Email Routing (hello@/security@) | Free | $0 | No paid tier involved in forwarding. |
| findanything.dev domain | already owned | $0 additional | Pre-existing renewal you already pay; this project adds no domain cost. |
| TLS certificate | Cloudflare automatic | $0 | Never charged. |
| Analytics / forms / media / fonts / APIs | none | $0 | Nothing to bill. |

**Items that could ever create a charge: none in the final design.** There is no payment
method, trial, subscription, credit-based tool, or metered API anywhere in the build or
runtime path. Higgsfield was not used. The design degrades to $0 forever: a static folder
that any free static host could serve.

## Verifying this yourself
```bash
# after deploy: confirm the only hosts the page can touch
curl -sI https://air.findanything.dev/ | grep -i content-security-policy
# locally: confirm no external URLs in the artifact besides the two citation links + schema namespaces
grep -RohE 'https?://[^"'\'' )<]+' site/public --include='*.html' --include='*.css' --include='*.js' | sort -u
```
Verified output on 2026-07-28 — the complete hostname list: `review.px4.io` (citation link),
`www.cloudflare.com` (privacy-policy citation link on /privacy.html), and
`air.findanything.dev` canonical/OG self-references. (`sitemap.xml` additionally contains the
`www.sitemaps.org` XML namespace identifier and `favicon.svg` the `www.w3.org` SVG namespace —
identifiers, not network requests.)

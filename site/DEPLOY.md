# Deploying the AIR site to Cloudflare Pages (free tier)

**STOP CONDITION: nothing below has been executed. Deployment and DNS attachment
happen only after your explicit approval, by you (or by Claude only after you say go).**

## What you are deploying
- Artifact folder: **`site/public/`** — fully static, 253 KB, no server code, no upload
  endpoints, no external requests. `_headers` inside the folder configures CSP and security
  headers (Cloudflare Pages reads it natively).
- Rebuilding it (any time source or data changes):
  ```bash
  cd air && ./.venv/bin/python site/build.py
  ```
  The build refuses to produce an artifact if the release gate finds raw logs, keys, local
  paths, banned claim language, or broken links.

## Option A — dashboard direct upload (simplest, no tooling)
1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Upload assets**.
2. Project name: `air-site` (any name; it only sets the default `*.pages.dev` URL).
3. Drag the **contents of `site/public/`** (or the folder) into the upload box → **Deploy**.
4. You get `https://air-site-XXX.pages.dev` immediately — verify everything there first.

## Option B — wrangler CLI (repeatable)
```bash
npx wrangler login                # one-time browser auth to your existing account
npx wrangler pages project create air-site --production-branch main
npx wrangler pages deploy site/public --project-name air-site
```
(wrangler is free; it runs under your existing account — it does not create accounts.)

## Attaching air.findanything.dev (DNS change — needs your approval)
1. In the Pages project → **Custom domains → Set up a custom domain** → enter
   `air.findanything.dev`.
2. Because `findanything.dev` is already on Cloudflare, the dashboard adds the CNAME for you
   after you confirm — this is the only DNS change, it does **not** touch the root domain or
   the existing Find Anything deployment on it.
3. TLS is automatic. Propagation is usually minutes.

## Post-deploy checks (5 minutes)
- `curl -sI https://air.findanything.dev/ | grep -i content-security` → CSP present.
- Click both mailto links; run the scrubber; check `/privacy.html`.
- Paste the URL into a Slack/Twitter preview debugger → OG card shows the trace image.

## Free-tier limits that matter (and don't)
- Cloudflare Pages free: 500 builds/month (irrelevant — direct upload doesn't count builds),
  unlimited static requests and bandwidth. This site fits permanently in the free tier.
- Email: hello@/security@ already work via Cloudflare Email Routing (free).
- **Items that could ever create a charge: none in this design.** No functions, no KV, no
  analytics, no external APIs. The only standing cost anywhere is the findanything.dev
  domain renewal you already pay.

## Rollback
Pages keeps every deployment; the dashboard's Deployments tab → "Rollback to this
deployment" is one click. Local artifact history lives in git.

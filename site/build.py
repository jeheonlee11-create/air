"""Build the AIR public site: site/src -> site/public (the deploy artifact).

Steps: regenerate derived data + charts, inline SVG partials into pages, copy
assets, emit _headers / robots.txt / sitemap.xml, then run the release gate:
  - no raw logs, keys, or PEM material in the artifact
  - no absolute local filesystem paths or usernames
  - no prohibited claim language (CLAIMS_LEDGER.md section E)
  - required caveat language present
  - all internal links resolve
Build FAILS on any violation.

Usage: .venv/bin/python site/build.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

SITE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SITE)
SRC = os.path.join(SITE, "src")
PUB = os.path.join(SITE, "public")
PY = sys.executable

CANONICAL = "https://air.findanything.dev"

HEADERS = """/*
  Content-Security-Policy: default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self' mailto:; frame-ancestors 'none'
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Resource-Policy: same-origin
/assets/*
  Cache-Control: public, max-age=604800
"""

ROBOTS = f"""User-agent: *
Allow: /

Sitemap: {CANONICAL}/sitemap.xml
"""

PAGES_FOR_SITEMAP = ["", "privacy.html", "terms.html", "security.html", "contact.html"]

# Release gate: prohibited language (CLAIMS_LEDGER E). Case-insensitive.
# Each entry: (pattern, allowed_contexts) — a hit is fatal unless one of the
# allowed context strings (lowercase) appears in the same line.
BANNED: list[tuple[str, list[str]]] = [
    (r"court[- ]admissible", []),
    (r"tamper[- ]proof", []),
    (r"military", []),
    (r"blockchain", []),
    (r"guaranteed?\b", ["not a guaranteed", "no guarantee"]),
    (r"\bcertified\b", []),
    (r"\bpatent", []),
    (r"no competitors", []),
    (r"\bonly (product|tool|platform)\b", []),
    (r"revolutionary|game.chang|cutting.edge|state.of.the.art", []),
    (r"\bcompliant\b", []),
    (r"\bproven\b", []),
    (r"trusted by", []),
    (r"our customers", []),
]
REQUIRED = [
    ("index.html", "We evaluated 100"),
    ("index.html", "a claim that a capability doesn"),
    ("index.html", "uploader-assigned"),
    ("index.html", "fresh-seed confirmation run has not yet been performed"),
    ("index.html", "no explicit redistribution license"),
    ("index.html", "hello@findanything.dev"),
    ("index.html", "security@findanything.dev"),
]
SECRET_PATTERNS = [r"BEGIN [A-Z ]*PRIVATE KEY", r"/Users/", r"jeheonlee",
                   r"api[_-]?key\s*[:=]", r"\.ulg\b"]
SECRET_ALLOWED_CONTEXT = ["ulg", "supported", "log (px4", ".ulg logs", "px4 <code>.ulg</code>",
                          "px4 .ulg only", "px4 <code>", "ulg</code>"]


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        sys.exit(f"build step failed: {' '.join(cmd)}")


def inline_includes(html: str, partials: str) -> str:
    def repl(m):
        path = os.path.join(partials, m.group(1))
        with open(path) as f:
            return f.read()
    return re.sub(r"<!--#include:([\w.]+)-->", repl, html)


def gate(pub: str) -> list[str]:
    problems: list[str] = []
    for root, _dirs, files in os.walk(pub):
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, pub)
            if fn.endswith((".ulg", ".pem", ".key")):
                problems.append(f"forbidden file type in artifact: {rel}")
                continue
            if fn.endswith((".png", ".ico", ".jpg", ".webp")):
                continue
            with open(p, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for i, line in enumerate(text.splitlines(), 1):
                low = line.lower()
                for pat, allowed in BANNED:
                    if re.search(pat, low) and not any(a in low for a in allowed):
                        problems.append(f"{rel}:{i} banned language /{pat}/: {line.strip()[:110]}")
                for pat in SECRET_PATTERNS:
                    if re.search(pat, line, re.I):
                        if pat == r"\.ulg\b" and any(a in low for a in SECRET_ALLOWED_CONTEXT):
                            continue
                        problems.append(f"{rel}:{i} secret/path pattern /{pat}/: {line.strip()[:110]}")
    for fn, needle in REQUIRED:
        with open(os.path.join(pub, fn)) as f:
            normalized = re.sub(r"\s+", " ", f.read())
        if needle not in normalized:
            problems.append(f"{fn}: required caveat text missing: {needle[:60]!r}")
    # internal link check
    for root, _dirs, files in os.walk(pub):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            with open(os.path.join(root, fn)) as f:
                html = f.read()
            for href in re.findall(r'(?:href|src)="([^"]+)"', html):
                if href.startswith(("http", "mailto:", "#")):
                    continue
                target = href.split("#")[0].lstrip("/")
                if target and not os.path.exists(os.path.join(pub, target)):
                    problems.append(f"{fn}: broken internal link {href}")
    return problems


def main() -> int:
    run([PY, os.path.join(SITE, "tools", "export_site_data.py")])
    run([PY, os.path.join(SITE, "tools", "render_charts.py")])
    run([PY, os.path.join(SITE, "tools", "gen_images.py")])

    if os.path.isdir(PUB):
        shutil.rmtree(PUB)
    os.makedirs(os.path.join(PUB, "assets", "data"), exist_ok=True)

    partials = os.path.join(SRC, "partials")
    for fn in os.listdir(os.path.join(SRC, "pages")):
        with open(os.path.join(SRC, "pages", fn)) as f:
            html = f.read()
        html = inline_includes(html, partials)
        with open(os.path.join(PUB, fn), "w") as f:
            f.write(html)

    shutil.copytree(os.path.join(SRC, "assets", "css"), os.path.join(PUB, "assets", "css"))
    shutil.copytree(os.path.join(SRC, "assets", "js"), os.path.join(PUB, "assets", "js"))
    shutil.copytree(os.path.join(SRC, "assets", "img"), os.path.join(PUB, "assets", "img"))
    shutil.copy(os.path.join(SRC, "data", "crash.json"),
                os.path.join(PUB, "assets", "data", "crash.json"))

    with open(os.path.join(PUB, "_headers"), "w") as f:
        f.write(HEADERS)
    with open(os.path.join(PUB, "robots.txt"), "w") as f:
        f.write(ROBOTS)
    urls = "\n".join(
        f"  <url><loc>{CANONICAL}/{p}</loc></url>" for p in PAGES_FOR_SITEMAP)
    with open(os.path.join(PUB, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                f"{urls}\n</urlset>\n")

    problems = gate(PUB)
    if problems:
        print("RELEASE GATE FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    total = 0
    print("artifact site/public/:")
    for root, _dirs, files in os.walk(PUB):
        for fn in sorted(files):
            sz = os.path.getsize(os.path.join(root, fn))
            total += sz
            print(f"  {os.path.relpath(os.path.join(root, fn), PUB):42s} {sz/1024:7.1f} KB")
    print(f"  TOTAL {total/1024:.0f} KB — gate passed, artifact ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Evidence bundle assembly.

A bundle is a self-contained directory a third party can inspect offline:

    bundle/
      report.json          canonical machine-readable incident record   (leaf 0)
      report.html          human-readable rendering of the same record  (leaf 1)
      manifest.json        Merkle root, inclusion proofs, signature, timestamp token
      verify.py            standalone verifier (stdlib + cryptography only)

Merkle leaves: report.json bytes, report.html bytes, then each source file's
SHA-256 hex digest (the raw logs stay with the operator; the digests bind them).
report.json records this layout in "bundle_layout", and since report.json is
itself leaf 0, an edited layout breaks verification too. Changing a byte of
report.json, report.html or a source file changes the root and the signature
no longer verifies. manifest.json is outside the tree (it carries the root).

Because the signer's public key travels inside the bundle, a forger could
rebuild and re-sign it with a key of their own; that is caught only when
verify.py is given the operator's published key fingerprint (--fingerprint) or
public key (--trusted-key). Without one it reports "integrity OK, signer NOT
verified" and exits 3.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable

from .merkle import inclusion_proof, merkle_root
from .signing import (
    canonical_json_bytes,
    load_or_create_key,
    public_key_fingerprint,
    public_pem,
    sign,
)
from .timestamp import request_timestamp


def build_bundle(report: dict, out_dir: str, key_dir: str,
                 with_timestamp: bool = True,
                 render_html: Callable[[str], str] | None = None) -> dict:
    """Write report.json (+ report.html), sign, and write manifest.json.

    render_html(key_fingerprint) -> html is called before signing so the page
    can show the fingerprint and be committed as a leaf. `report` gains a
    "bundle_layout" entry describing the leaf order.
    """
    os.makedirs(out_dir, exist_ok=True)
    key = load_or_create_key(key_dir)

    html_bytes = None
    if render_html is not None:
        html_bytes = render_html(public_key_fingerprint(public_pem(key))).encode("utf-8")
    first_source = 2 if html_bytes is not None else 1
    report["bundle_layout"] = {
        "report_json_leaf": 0,
        "report_html_leaf": 1 if html_bytes is not None else None,
        "first_source_leaf": first_source,
    }

    report_bytes = canonical_json_bytes(report)
    with open(os.path.join(out_dir, "report.json"), "wb") as f:
        f.write(report_bytes)

    leaves: list[bytes] = [report_bytes]
    leaf_descriptors = [{"leaf": 0, "kind": "report.json",
                         "sha256": hashlib.sha256(report_bytes).hexdigest()}]
    if html_bytes is not None:
        with open(os.path.join(out_dir, "report.html"), "wb") as f:
            f.write(html_bytes)
        leaves.append(html_bytes)
        leaf_descriptors.append({"leaf": 1, "kind": "report.html",
                                 "sha256": hashlib.sha256(html_bytes).hexdigest()})
    for i, src in enumerate(report["sources"], start=first_source):
        leaves.append(src["sha256"].encode("ascii"))
        leaf_descriptors.append({"leaf": i, "kind": src["kind"],
                                 "path": os.path.basename(src["path"]),
                                 "sha256": src["sha256"]})

    root = merkle_root(leaves)
    signature = sign(key, root)

    manifest = {
        "format": "air-evidence-bundle/2",
        "merkle": {
            "algorithm": "RFC9162-SHA256",
            "root_hex": root.hex(),
            "tree_size": len(leaves),
            "leaves": leaf_descriptors,
            "inclusion_proofs": {
                str(i): [h.hex() for h in inclusion_proof(leaves, i)]
                for i in range(len(leaves))
            },
        },
        "signature": {
            "algorithm": "Ed25519",
            "signed_data": "merkle.root (raw 32 bytes)",
            "signature_b64": signature,
            "public_key_pem": public_pem(key),
        },
        "rfc3161_timestamp": request_timestamp(root) if with_timestamp else {"status": "skipped"},
        "verification": "run: python3 verify.py --fingerprint <operator's published key "
                        "fingerprint>  (from inside this bundle directory)",
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    verifier_src = os.path.join(os.path.dirname(__file__), "..", "..", "verify.py")
    if os.path.exists(verifier_src):
        shutil.copy(verifier_src, os.path.join(out_dir, "verify.py"))

    return manifest

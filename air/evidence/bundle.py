"""Evidence bundle assembly.

A bundle is a self-contained directory a hostile third party can inspect
offline (FRE 902(11) requires making the record available for inspection):

    bundle/
      report.json          canonical machine-readable incident record
      report.html          human-readable rendering
      manifest.json        file hashes, Merkle root, signature, timestamp token
      verify.py            standalone verifier (stdlib + cryptography only)
      sources/             (referenced by hash; raw logs stay with the operator)

The signature covers the Merkle root; the Merkle tree covers report.json and
every source file hash. Change any byte anywhere and verification fails.
"""

from __future__ import annotations

import json
import os
import shutil

from .merkle import inclusion_proof, merkle_root
from .signing import canonical_json_bytes, load_or_create_key, public_pem, sign
from .timestamp import request_timestamp


def build_bundle(report: dict, out_dir: str, key_dir: str,
                 with_timestamp: bool = True) -> dict:
    os.makedirs(out_dir, exist_ok=True)

    report_bytes = canonical_json_bytes(report)
    with open(os.path.join(out_dir, "report.json"), "wb") as f:
        f.write(report_bytes)

    # Leaves: canonical report bytes, then each source file's hex digest (as bytes).
    # Source files themselves stay in place; their digests bind them to the record.
    leaves: list[bytes] = [report_bytes]
    leaf_descriptors = [{"leaf": 0, "kind": "report.json", "sha256_of_content": None}]
    for i, src in enumerate(report["sources"], start=1):
        leaves.append(src["sha256"].encode("ascii"))
        leaf_descriptors.append({"leaf": i, "kind": src["kind"],
                                 "path": os.path.basename(src["path"]),
                                 "sha256": src["sha256"]})

    root = merkle_root(leaves)
    key = load_or_create_key(key_dir)
    signature = sign(key, root)

    manifest = {
        "format": "air-evidence-bundle/1",
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
        "verification": "run: python3 verify.py  (from inside this bundle directory)",
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    verifier_src = os.path.join(os.path.dirname(__file__), "..", "..", "verify.py")
    if os.path.exists(verifier_src):
        shutil.copy(verifier_src, os.path.join(out_dir, "verify.py"))

    return manifest

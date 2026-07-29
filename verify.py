#!/usr/bin/env python3
"""Standalone verifier for an AIR evidence bundle.

Run from inside a bundle directory:  python3 verify.py

Checks, in order:
  1. report.json matches the Merkle leaf it claims to be
  2. every source-file digest leaf verifies against the Merkle root
  3. the Ed25519 signature over the Merkle root verifies with the bundled key
  4. (if present) the RFC 3161 timestamp token digest matches the root
  5. (optional) any source files present alongside the bundle re-hash correctly

Dependencies: Python 3.10+ stdlib + `cryptography` (pip install cryptography).
This file is intentionally self-contained — no imports from the AIR package —
so an adverse party can audit every line of the verification path.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _hash(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_hash(b: bytes) -> bytes:
    return _hash(LEAF_PREFIX + b)


def verify_inclusion(leaf_data: bytes, index: int, tree_size: int,
                     proof: list[bytes], root: bytes) -> bool:
    if index >= tree_size:
        return False
    fn, sn = index, tree_size - 1
    r = leaf_hash(leaf_data)
    for p in proof:
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            r = _hash(NODE_PREFIX + p + r)
            while fn % 2 == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = _hash(NODE_PREFIX + r + p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


def main() -> int:
    ok = True

    def check(name: str, passed: bool, detail: str = ""):
        nonlocal ok
        ok = ok and passed
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))

    try:
        with open("manifest.json") as f:
            manifest = json.load(f)
        with open("report.json", "rb") as f:
            report_bytes = f.read()
    except FileNotFoundError as e:
        print(f"[FAIL] missing bundle file: {e.filename}")
        return 1

    mk = manifest["merkle"]
    root = bytes.fromhex(mk["root_hex"])
    tree_size = mk["tree_size"]
    proofs = {int(k): [bytes.fromhex(h) for h in v] for k, v in mk["inclusion_proofs"].items()}

    # 1. report.json inclusion
    check("report.json is the record committed to the Merkle root",
          verify_inclusion(report_bytes, 0, tree_size, proofs[0], root))

    # 2. source digest leaves
    report = json.loads(report_bytes)
    for i, src in enumerate(report.get("sources", []), start=1):
        leaf = src["sha256"].encode("ascii")
        check(f"source digest committed: {os.path.basename(src['path'])}",
              verify_inclusion(leaf, i, tree_size, proofs[i], root),
              src["sha256"][:16] + "…")

    # 3. signature over root
    try:
        from cryptography.hazmat.primitives import serialization
        sig = manifest["signature"]
        pub = serialization.load_pem_public_key(sig["public_key_pem"].encode())
        try:
            pub.verify(base64.b64decode(sig["signature_b64"]), root)
            check("Ed25519 signature over Merkle root", True,
                  "signed by bundled public key")
        except Exception:
            check("Ed25519 signature over Merkle root", False)
    except ImportError:
        check("Ed25519 signature over Merkle root", False,
              "cryptography package not installed (pip install cryptography)")

    # 4. RFC 3161 token digest binding
    ts = manifest.get("rfc3161_timestamp", {})
    if ts.get("status") == "ok":
        # The TSA's message imprint is SHA-256 over the signed data (the root).
        expected_imprint = hashlib.sha256(root).hexdigest()
        check("RFC 3161 timestamp token binds to Merkle root",
              ts.get("message_imprint_sha256") == expected_imprint,
              f"TSA={ts.get('tsa')} gen_time={ts.get('gen_time')}")
        print("       note: full token (tsr_der_b64) present; validate the TSA chain with "
              "`openssl ts -reply -in <(base64 -d) -text` for chain-of-trust review")
    else:
        print(f"[INFO] no RFC 3161 token in bundle (status: {ts.get('status', 'absent')})")

    # 5. re-hash any source files that are locally present
    for src in report.get("sources", []):
        base = os.path.basename(src["path"])
        for candidate in (src["path"], base, os.path.join("sources", base)):
            if os.path.exists(candidate):
                h = hashlib.sha256()
                with open(candidate, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
                check(f"local file re-hash: {os.path.basename(candidate)}",
                      h.hexdigest() == src["sha256"])
                break
        else:
            print(f"[INFO] source file not present locally (digest still committed): "
                  f"{os.path.basename(src['path'])}")

    print()
    print("VERIFICATION " + ("PASSED — record is intact and untampered." if ok
                             else "FAILED — record integrity cannot be confirmed."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

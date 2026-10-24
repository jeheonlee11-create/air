#!/usr/bin/env python3
"""Standalone verifier for an AIR evidence bundle.

Run from inside a bundle directory:

    python3 verify.py --fingerprint <operator's published key fingerprint>
    python3 verify.py --trusted-key operator_pub.pem [--tsa-ca tsa_ca.pem]

Checks, in order:
  1. report.json matches the Merkle leaf it claims to be
  2. every source-file digest leaf verifies against the Merkle root
  3. the Ed25519 signature over the Merkle root verifies, and the signer is the
     key you trust (--trusted-key / --fingerprint, obtained OUTSIDE the bundle)
  4. (if present) the RFC 3161 token: its own messageImprint matches the root,
     its CMS signature verifies with the certificate embedded in the token, and
     (with --tsa-ca) the TSA certificate chain validates via `openssl ts -verify`
  5. (optional) any source files present alongside the bundle re-hash correctly

The public key inside manifest.json is NOT a trust anchor: whoever edits the
record can re-sign it with a fresh key. Without --trusted-key/--fingerprint the
verifier reports integrity only and exits 3 ("signer NOT verified").

Exit codes: 0 = intact and signed by the trusted key; 1 = a check failed;
3 = integrity OK but signer not verified (no trust anchor given).

Dependencies: Python 3.10+ stdlib + `cryptography` (pip install cryptography);
`openssl` only when --tsa-ca is used. The RFC 3161 token is parsed with the
small DER reader below rather than an ASN.1 library, so the file stays
self-contained — no imports from the AIR package — and an adverse party can
audit every line of the verification path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"
EXIT_OK, EXIT_FAIL, EXIT_SIGNER_UNVERIFIED = 0, 1, 3


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


def key_fingerprint(pub) -> str:
    """SHA-256 over the DER SubjectPublicKeyInfo, hex (as printed by `air investigate`)."""
    from cryptography.hazmat.primitives import serialization
    der = pub.public_bytes(encoding=serialization.Encoding.DER,
                           format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def _normalize_fingerprint(s: str) -> str:
    s = s.strip().lower()
    if s.startswith("sha256:"):
        s = s[7:]
    return s.replace(":", "").replace(" ", "")


def _ed25519_ok(pub, signature: bytes, data: bytes) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(pub, Ed25519PublicKey):
        return False
    try:
        pub.verify(signature, data)
        return True
    except Exception:
        return False


# ---- minimal DER reader (definite lengths only — DER forbids indefinite) ----

def der_read(buf: bytes, pos: int = 0) -> tuple[int, bytes, bytes, int]:
    """Parse the TLV at `pos`. Returns (tag, content, whole_tlv, next_pos)."""
    start = pos
    tag = buf[pos]
    if tag & 0x1F == 0x1F:
        raise ValueError("high-tag-number DER form not supported")
    ln = buf[pos + 1]
    pos += 2
    if ln & 0x80:
        n = ln & 0x7F
        if n == 0 or n > 4:
            raise ValueError("unsupported DER length encoding")
        ln = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    end = pos + ln
    if end > len(buf):
        raise ValueError("truncated DER")
    return tag, buf[pos:end], buf[start:end], end


def der_children(content: bytes) -> list[tuple[int, bytes, bytes]]:
    """Children of a constructed value: [(tag, content, whole_tlv), ...]."""
    out, pos = [], 0
    while pos < len(content):
        tag, c, tlv, pos = der_read(content, pos)
        out.append((tag, c, tlv))
    return out


def der_oid(content: bytes) -> str:
    subids, v = [], 0
    for b in content:
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            subids.append(v)
            v = 0
    first = subids[0]
    head = [first // 40, first % 40] if first < 80 else [2, first - 80]
    return ".".join(str(x) for x in head + subids[1:])


OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
OID_TST_INFO = "1.2.840.113549.1.9.16.1.4"
OID_ATTR_CONTENT_TYPE = "1.2.840.113549.1.9.3"
OID_ATTR_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"
HASH_OIDS = {
    "1.3.14.3.2.26": "sha1",
    "2.16.840.1.101.3.4.2.4": "sha224",
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
}
RSA_SIG_OIDS = {  # sha*WithRSAEncryption -> hash; plain rsaEncryption uses digestAlgorithm
    "1.2.840.113549.1.1.5": "sha1", "1.2.840.113549.1.1.14": "sha224",
    "1.2.840.113549.1.1.11": "sha256", "1.2.840.113549.1.1.12": "sha384",
    "1.2.840.113549.1.1.13": "sha512", "1.2.840.113549.1.1.1": None,
}
ECDSA_SIG_OIDS = {"1.2.840.10045.4.3.1": "sha224", "1.2.840.10045.4.3.2": "sha256",
                  "1.2.840.10045.4.3.3": "sha384", "1.2.840.10045.4.3.4": "sha512"}


def _gen_time(s: str) -> str:
    """GeneralizedTime 'YYYYMMDDHHMMSS[.f]Z' -> 'YYYY-MM-DDTHH:MM:SS[.f]Z'."""
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:]}"


def parse_timestamp_token(der: bytes) -> dict:
    """Parse an RFC 3161 TimeStampResp (or bare TimeStampToken) into the parts
    needed for verification. Raises ValueError on malformed input."""
    _, top, _, _ = der_read(der)
    top_kids = der_children(top)
    is_token = top_kids[0][0] == 0x06          # ContentInfo starts with an OID
    if is_token:
        token_tlv = der
    else:                                       # TimeStampResp: status, token
        status = int.from_bytes(der_children(top_kids[0][1])[0][1], "big")
        if status not in (0, 1):                # granted / grantedWithMods
            raise ValueError(f"TSA refused the request (PKIStatus {status})")
        if len(top_kids) < 2:
            raise ValueError("TimeStampResp carries no token")
        token_tlv = top_kids[1][2]
    _, ci, _, _ = der_read(token_tlv)
    ci_kids = der_children(ci)
    if der_oid(ci_kids[0][1]) != OID_SIGNED_DATA:
        raise ValueError("token is not CMS SignedData")
    sd = der_children(der_children(ci_kids[1][1])[0][1])
    encap = der_children(sd[2][1])
    if der_oid(encap[0][1]) != OID_TST_INFO:
        raise ValueError("token content is not TSTInfo")
    e_content = der_children(encap[1][1])[0][1]
    tst = der_children(der_read(e_content)[1])
    imprint = der_children(tst[2][1])
    hash_oid = der_oid(der_children(imprint[0][1])[0][1])
    certs = []
    signer_infos = None
    for tag, content, _tlv in sd[3:]:
        if tag == 0xA0:                         # certificates [0] IMPLICIT
            certs = [c[2] for c in der_children(content) if c[0] == 0x30]
        elif tag == 0x31:
            signer_infos = der_children(content)
    if not signer_infos:
        raise ValueError("token has no SignerInfo")
    si = der_children(signer_infos[0][1])
    signed_attrs = next((x for x in si if x[0] == 0xA0), None)
    rest = [x for x in si[3:] if x[0] != 0xA0]  # signatureAlgorithm, signature, ...
    return {
        "is_token": is_token,
        "hash_oid": hash_oid,
        "hash_name": HASH_OIDS.get(hash_oid),
        "hashed_message": imprint[1][1],
        "gen_time": _gen_time(tst[4][1].decode("ascii")),
        "e_content": e_content,
        "certs": certs,
        "sid": si[1],
        "digest_oid": der_oid(der_children(si[2][1])[0][1]),
        "signed_attrs": signed_attrs,
        "sig_oid": der_oid(der_children(rest[0][1])[0][1]),
        "signature": rest[1][1],
    }


def verify_token_signature(tok: dict) -> tuple[bool | None, str]:
    """Verify the CMS signature over the signed attributes with the certificate
    embedded in the token. Returns (True/False, detail), or (None, reason) when
    the check cannot be performed. Does NOT validate the certificate chain."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

    if tok["signed_attrs"] is None:
        return None, "token has no signed attributes (unsupported form)"
    digest_name = HASH_OIDS.get(tok["digest_oid"])
    if digest_name is None:
        return None, f"unsupported digest algorithm {tok['digest_oid']}"
    attrs = {der_oid(der_children(a[1])[0][1]): der_children(der_children(a[1])[1][1])[0]
             for a in der_children(tok["signed_attrs"][1])}
    ct = attrs.get(OID_ATTR_CONTENT_TYPE)
    md = attrs.get(OID_ATTR_MESSAGE_DIGEST)
    if ct is None or der_oid(ct[1]) != OID_TST_INFO:
        return False, "signed contentType attribute is not id-ct-TSTInfo"
    if md is None or md[1] != hashlib.new(digest_name, tok["e_content"]).digest():
        return False, "signed messageDigest does not match the TSTInfo content"

    certs = [x509.load_der_x509_certificate(c) for c in tok["certs"]]
    sid_tag, sid_content, _ = tok["sid"]
    signer = None
    for c in certs:
        if sid_tag == 0x30:                     # IssuerAndSerialNumber
            issuer, serial = der_children(sid_content)[:2]
            if (c.issuer.public_bytes() == issuer[2]
                    and c.serial_number == int.from_bytes(serial[1], "big", signed=True)):
                signer = c
        elif sid_tag == 0x80:                   # [0] SubjectKeyIdentifier
            try:
                ski = c.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
            except x509.ExtensionNotFound:
                continue
            if ski.digest == sid_content:
                signer = c
        if signer is not None:
            break
    if signer is None:
        return None, "signer certificate not embedded in token"

    data = b"\x31" + tok["signed_attrs"][2][1:]  # signed over as SET OF, not [0]
    pub = signer.public_key()
    sig = tok["signature"]
    hash_cls = {"sha1": hashes.SHA1, "sha224": hashes.SHA224, "sha256": hashes.SHA256,
                "sha384": hashes.SHA384, "sha512": hashes.SHA512}
    try:
        if tok["sig_oid"] in RSA_SIG_OIDS and isinstance(pub, rsa.RSAPublicKey):
            h = RSA_SIG_OIDS[tok["sig_oid"]] or digest_name
            pub.verify(sig, data, padding.PKCS1v15(), hash_cls[h]())
        elif tok["sig_oid"] in ECDSA_SIG_OIDS and isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(sig, data, ec.ECDSA(hash_cls[ECDSA_SIG_OIDS[tok["sig_oid"]]]()))
        elif tok["sig_oid"] == "1.3.101.112" and isinstance(pub, ed25519.Ed25519PublicKey):
            pub.verify(sig, data)
        else:
            return None, f"unsupported signature algorithm {tok['sig_oid']}"
    except Exception:
        return False, "CMS signature does not verify with the embedded certificate"
    return True, f"signed by embedded cert '{signer.subject.rfc4514_string()}'"


def openssl_ts_verify(tsr: bytes, data: bytes, ca_file: str, is_token: bool) -> tuple[bool, str]:
    """Validate the token, including the TSA certificate chain up to `ca_file`."""
    exe = shutil.which("openssl")
    if exe is None:
        return False, "openssl not found on PATH; chain could not be validated"
    with tempfile.TemporaryDirectory() as td:
        tsr_path, data_path = os.path.join(td, "token.tsr"), os.path.join(td, "root.bin")
        with open(tsr_path, "wb") as f:
            f.write(tsr)
        with open(data_path, "wb") as f:
            f.write(data)
        cmd = [exe, "ts", "-verify", "-data", data_path, "-in", tsr_path, "-CAfile", ca_file]
        if is_token:
            cmd.append("-token_in")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0 and "Verification: OK" in p.stdout, (out[-1] if out else "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify an AIR evidence bundle offline.")
    ap.add_argument("bundle", nargs="?", default=".",
                    help="bundle directory (default: current directory)")
    ap.add_argument("--trusted-key", metavar="PEM",
                    help="the operator's Ed25519 public key, obtained outside the bundle")
    ap.add_argument("--fingerprint", metavar="SHA256",
                    help="SHA-256 fingerprint of the operator's public key, obtained "
                         "outside the bundle (printed by `air investigate`)")
    ap.add_argument("--tsa-ca", metavar="PEM",
                    help="CA certificate(s) trusted for the RFC 3161 TSA; validates the "
                         "TSA chain with `openssl ts -verify`")
    args = ap.parse_args(argv)
    ok = True

    def check(name: str, passed: bool, detail: str = ""):
        nonlocal ok
        ok = ok and passed
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))

    try:
        with open(os.path.join(args.bundle, "manifest.json")) as f:
            manifest = json.load(f)
        with open(os.path.join(args.bundle, "report.json"), "rb") as f:
            report_bytes = f.read()
    except FileNotFoundError as e:
        print(f"[FAIL] missing bundle file: {e.filename}")
        return EXIT_FAIL

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
              verify_inclusion(leaf, i, tree_size, proofs.get(i, []), root),
              src["sha256"][:16] + "…")

    # 3. signature over root, and whether the signer is the key we trust
    anchored = bool(args.trusted_key or args.fingerprint)
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        check("Ed25519 signature over Merkle root", False,
              "cryptography package not installed (pip install cryptography)")
        serialization = None
    if serialization is not None:
        sig = manifest["signature"]
        signature = base64.b64decode(sig["signature_b64"])
        embedded = serialization.load_pem_public_key(sig["public_key_pem"].encode())
        embedded_fp = key_fingerprint(embedded)
        check("Ed25519 signature over Merkle root", _ed25519_ok(embedded, signature, root),
              f"valid for the key embedded in manifest.json (fingerprint {embedded_fp})")
        if args.trusted_key:
            try:
                with open(args.trusted_key, "rb") as f:
                    trusted = serialization.load_pem_public_key(f.read())
            except (OSError, ValueError) as e:
                check("signer is the trusted key (--trusted-key)", False,
                      f"cannot load {args.trusted_key}: {e}")
            else:
                check("signer is the trusted key (--trusted-key)",
                      _ed25519_ok(trusted, signature, root),
                      f"trusted fingerprint {key_fingerprint(trusted)}")
        if args.fingerprint:
            want = _normalize_fingerprint(args.fingerprint)
            check("signer key matches --fingerprint", embedded_fp == want,
                  f"expected {want}" + ("" if embedded_fp == want else f", bundle has {embedded_fp}"))
        if not anchored:
            print("[WARN] signer identity NOT verified — the key above came from the bundle "
                  "itself, so anyone who edits the record can re-sign it with a key of their "
                  "own. Rerun with --fingerprint <sha256> or --trusted-key <pem> obtained from "
                  "the operator out of band.")

    # 4. RFC 3161 timestamp token
    ts = manifest.get("rfc3161_timestamp", {})
    if ts.get("tsr_der_b64"):
        tsr = base64.b64decode(ts["tsr_der_b64"])
        try:
            tok = parse_timestamp_token(tsr)
        except (ValueError, IndexError, UnicodeDecodeError) as e:
            check("RFC 3161 token parses", False, str(e))
            tok = None
        if tok is not None:
            if tok["hash_name"] is None:
                check("RFC 3161 token messageImprint matches Merkle root", False,
                      f"unsupported imprint hash algorithm {tok['hash_oid']}")
            else:
                check("RFC 3161 token messageImprint matches Merkle root",
                      hashlib.new(tok["hash_name"], root).digest() == tok["hashed_message"],
                      f"{tok['hash_name']} imprint, genTime {tok['gen_time']} (from token), "
                      f"TSA={ts.get('tsa')}")
            if serialization is not None:
                sig_ok, detail = verify_token_signature(tok)
                if sig_ok is None:
                    print(f"[WARN] RFC 3161 token signature not checked — {detail}")
                else:
                    check("RFC 3161 token CMS signature", sig_ok, detail)
            if args.tsa_ca:
                chain_ok, detail = openssl_ts_verify(tsr, root, args.tsa_ca, tok["is_token"])
                check("RFC 3161 TSA certificate chain (openssl ts -verify)", chain_ok, detail)
            else:
                print("[INFO] TSA certificate chain NOT validated (no --tsa-ca given); the "
                      "token's signing certificate is not yet tied to a trusted TSA root")
    else:
        print(f"[INFO] no RFC 3161 token in bundle (status: {ts.get('status', 'absent')})")

    # 5. re-hash any source files that are locally present
    for src in report.get("sources", []):
        base = os.path.basename(src["path"])
        for candidate in (src["path"], os.path.join(args.bundle, base),
                          os.path.join(args.bundle, "sources", base)):
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
    if not ok:
        print("VERIFICATION FAILED — record integrity or signer identity cannot be confirmed.")
        return EXIT_FAIL
    if not anchored:
        print("VERIFICATION INCOMPLETE — integrity OK, signer NOT verified (no --trusted-key "
              "or --fingerprint given). This does not show who produced the record.")
        return EXIT_SIGNER_UNVERIFIED
    print("VERIFICATION PASSED — record is intact and signed by the trusted key.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

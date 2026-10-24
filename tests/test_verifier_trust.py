"""verify.py: signer trust anchor and RFC 3161 token checks.

Runs on a clean clone: bundles are built from a synthetic report, and RFC 3161
tokens are either a saved real FreeTSA response (tests/data) or minted by a
throwaway test TSA built here.
"""

import base64
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import verify
from air.evidence import build_bundle
from air.evidence.signing import PUBLIC_KEY_FILE, load_or_create_key, public_key_fingerprint

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREETSA = os.path.join(REPO, "tests", "data", "freetsa_response.json")


def _report(findings):
    return {
        "format": "air-incident-record/1",
        "sources": [{"path": "flight.ulg", "sha256": hashlib.sha256(b"log").hexdigest(),
                     "size_bytes": 3, "kind": "px4_ulog", "meta": {}}],
        "findings": findings,
    }


GENUINE_FINDINGS = [{"code": "BAT-LOW", "severity": "critical", "title": "Battery depleted"}]


def _run(bundle, *args):
    p = subprocess.run([sys.executable, "verify.py", *args], cwd=bundle,
                       capture_output=True, text=True)
    return p.returncode, p.stdout


@pytest.fixture
def genuine(tmp_path):
    keys = tmp_path / "operator_keys"
    out = tmp_path / "genuine"
    manifest = build_bundle(_report(GENUINE_FINDINGS), str(out), str(keys), with_timestamp=False)
    pub = keys / PUBLIC_KEY_FILE
    return {"dir": str(out), "pub": str(pub), "manifest": manifest,
            "fp": public_key_fingerprint(pub.read_text())}


@pytest.fixture
def forged(tmp_path, genuine):
    """Attacker edits report.json (drops the findings), rebuilds the Merkle tree
    and re-signs with a fresh key of their own."""
    with open(os.path.join(genuine["dir"], "report.json")) as f:
        report = json.load(f)
    report["findings"] = []
    out = tmp_path / "forged"
    build_bundle(report, str(out), str(tmp_path / "attacker_keys"), with_timestamp=False)
    return str(out)


# ---- signer trust anchor ----

def test_genuine_bundle_passes_with_trusted_key(genuine):
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_OK, out
    assert "VERIFICATION PASSED" in out


def test_genuine_bundle_passes_with_fingerprint(genuine):
    fp = genuine["fp"].upper()  # case-insensitive, optional prefix
    code, out = _run(genuine["dir"], "--fingerprint", f"sha256:{fp}")
    assert code == verify.EXIT_OK, out


def test_forged_bundle_rejected_with_trusted_key(genuine, forged):
    code, out = _run(forged, "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_FAIL, out
    assert "[FAIL] signer is the trusted key" in out
    assert "PASSED" not in out


def test_forged_bundle_rejected_with_fingerprint(genuine, forged):
    code, out = _run(forged, "--fingerprint", genuine["fp"])
    assert code == verify.EXIT_FAIL, out
    assert "[FAIL] signer key matches --fingerprint" in out


def test_forged_bundle_not_reported_authentic_without_anchor(forged):
    code, out = _run(forged)
    assert code == verify.EXIT_SIGNER_UNVERIFIED, out
    assert "signer NOT verified" in out
    assert "PASSED" not in out


def test_genuine_bundle_without_anchor_is_integrity_only(genuine):
    code, out = _run(genuine["dir"])
    assert code == verify.EXIT_SIGNER_UNVERIFIED
    assert "integrity OK, signer NOT verified" in out


def test_byte_flip_fails_even_with_trusted_key(genuine):
    rp = os.path.join(genuine["dir"], "report.json")
    data = bytearray(open(rp, "rb").read())
    data[len(data) // 2] ^= 0x01
    open(rp, "wb").write(bytes(data))
    code, _ = _run(genuine["dir"], "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_FAIL


def test_new_key_generation_is_announced_with_fingerprint(tmp_path, capsys):
    key = load_or_create_key(str(tmp_path))
    err = capsys.readouterr().err
    fp = public_key_fingerprint((tmp_path / PUBLIC_KEY_FILE).read_text())
    assert "generated a NEW Ed25519 key" in err and fp in err
    assert verify.key_fingerprint(key.public_key()) == fp   # same formula both sides
    load_or_create_key(str(tmp_path))
    assert capsys.readouterr().err == ""                     # reload is silent


# ---- RFC 3161: real FreeTSA token ----

def _freetsa():
    with open(FREETSA) as f:
        d = json.load(f)
    return bytes.fromhex(d["root_hex"]), base64.b64decode(d["tsr_der_b64"])


def test_real_freetsa_token_imprint_and_signature():
    root, tsr = _freetsa()
    tok = verify.parse_timestamp_token(tsr)
    assert tok["hash_name"] == "sha512"                      # not the SHA-256 we used to assume
    assert hashlib.sha512(root).digest() == tok["hashed_message"]
    assert hashlib.sha512(b"\x00" * 32).digest() != tok["hashed_message"]
    assert tok["gen_time"] == "2026-07-28T22:06:13Z"
    ok, detail = verify.verify_token_signature(tok)
    assert ok is True, detail


def test_real_freetsa_token_with_tampered_signature_fails():
    _, tsr = _freetsa()
    tok = verify.parse_timestamp_token(tsr)
    tok["signature"] = tok["signature"][:-1] + bytes([tok["signature"][-1] ^ 1])
    ok, _ = verify.verify_token_signature(tok)
    assert ok is False


def _attach_token(bundle_dir, tsr):
    mp = os.path.join(bundle_dir, "manifest.json")
    with open(mp) as f:
        m = json.load(f)
    # The stale manifest field the old verifier trusted is made to "match" here,
    # to prove it is no longer what decides the result.
    root = bytes.fromhex(m["merkle"]["root_hex"])
    m["rfc3161_timestamp"] = {"status": "ok", "tsa": "test",
                              "message_imprint_sha256": hashlib.sha256(root).hexdigest(),
                              "tsr_der_b64": base64.b64encode(tsr).decode()}
    with open(mp, "w") as f:
        json.dump(m, f)
    return root


def test_token_for_another_root_fails_end_to_end(genuine):
    _, tsr = _freetsa()                                      # timestamps a different root
    _attach_token(genuine["dir"], tsr)
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_FAIL, out
    assert "[FAIL] RFC 3161 token messageImprint matches Merkle root" in out


# ---- RFC 3161: synthetic token from a throwaway TSA ----

def _tlv(tag, content):
    n = len(content)
    if n < 0x80:
        return bytes([tag, n]) + content
    ln = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(ln)]) + ln + content


def _seq(*xs):
    return _tlv(0x30, b"".join(xs))


def _set(*xs):
    return _tlv(0x31, b"".join(sorted(xs)))                  # DER SET OF is sorted


def _int(i):
    return _tlv(0x02, i.to_bytes(i.bit_length() // 8 + 1, "big", signed=True))


def _oid(dotted):
    arcs = [int(a) for a in dotted.split(".")]
    out = b""
    for a in [40 * arcs[0] + arcs[1], *arcs[2:]]:
        enc = [a & 0x7F]
        a >>= 7
        while a:
            enc.append(0x80 | (a & 0x7F))
            a >>= 7
        out += bytes(reversed(enc))
    return _tlv(0x06, out)


SHA256_ALG = _seq(_oid("2.16.840.1.101.3.4.2.1"), b"\x05\x00")


def _test_tsa(tmp_path):
    now = datetime.datetime.now(datetime.timezone.utc)

    def cert(subject, issuer, pub, signer, ca):
        b = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
             .public_key(pub).serial_number(x509.random_serial_number())
             .not_valid_before(now - datetime.timedelta(days=1))
             .not_valid_after(now + datetime.timedelta(days=1))
             .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if not ca:
            b = b.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
                                critical=True)
        return b.sign(signer, hashes.SHA256())

    ca_key, tsa_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AIR test TSA root")])
    tsa_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AIR test TSA")])
    ca_cert = cert(ca_name, ca_name, ca_key.public_key(), ca_key, True)
    tsa_cert = cert(tsa_name, ca_name, tsa_key.public_key(), ca_key, False)
    ca_pem = tmp_path / "test_tsa_ca.pem"
    ca_pem.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    return tsa_key, tsa_cert, str(ca_pem)


def _mint_token(tsa_key, tsa_cert, data: bytes) -> bytes:
    """RFC 3161 TimeStampResp over sha256(data), ECDSA-signed by tsa_key."""
    tst_info = _seq(_int(1), _oid("1.2.3.4.1"),
                    _seq(SHA256_ALG, _tlv(0x04, hashlib.sha256(data).digest())),
                    _int(42), _tlv(0x18, b"20261024120000Z"))
    tsa_der = tsa_cert.public_bytes(serialization.Encoding.DER)
    attrs = _set(
        _seq(_oid("1.2.840.113549.1.9.3"), _set(_oid("1.2.840.113549.1.9.16.1.4"))),
        _seq(_oid("1.2.840.113549.1.9.4"), _set(_tlv(0x04, hashlib.sha256(tst_info).digest()))),
        # ESS signingCertificate (required by `openssl ts -verify`)
        _seq(_oid("1.2.840.113549.1.9.16.2.12"),
             _set(_seq(_seq(_seq(_tlv(0x04, hashlib.sha1(tsa_der).digest())))))),
    )
    signature = tsa_key.sign(attrs, ec.ECDSA(hashes.SHA256()))
    signer_info = _seq(
        _int(1), _seq(tsa_cert.issuer.public_bytes(), _int(tsa_cert.serial_number)),
        SHA256_ALG, b"\xa0" + attrs[1:], _seq(_oid("1.2.840.10045.4.3.2")),
        _tlv(0x04, signature))
    signed_data = _seq(
        _int(3), _set(SHA256_ALG),
        _seq(_oid("1.2.840.113549.1.9.16.1.4"), _tlv(0xA0, _tlv(0x04, tst_info))),
        _tlv(0xA0, tsa_der), _set(signer_info))
    token = _seq(_oid("1.2.840.113549.1.7.2"), _tlv(0xA0, signed_data))
    return _seq(_seq(_int(0)), token)


def test_matching_synthetic_token_passes(genuine, tmp_path):
    tsa_key, tsa_cert, _ = _test_tsa(tmp_path)
    root = bytes.fromhex(genuine["manifest"]["merkle"]["root_hex"])
    _attach_token(genuine["dir"], _mint_token(tsa_key, tsa_cert, root))
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_OK, out
    assert "[PASS] RFC 3161 token messageImprint matches Merkle root" in out
    assert "genTime 2026-10-24T12:00:00Z (from token)" in out
    assert "[PASS] RFC 3161 token CMS signature" in out
    assert "chain NOT validated" in out


def test_mismatched_synthetic_token_fails(genuine, tmp_path):
    tsa_key, tsa_cert, _ = _test_tsa(tmp_path)
    _attach_token(genuine["dir"], _mint_token(tsa_key, tsa_cert, b"some other root"))
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_FAIL, out
    assert "[FAIL] RFC 3161 token messageImprint matches Merkle root" in out


def test_token_signed_by_wrong_key_fails(genuine, tmp_path):
    _, tsa_cert, _ = _test_tsa(tmp_path)
    impostor = ec.generate_private_key(ec.SECP256R1())
    root = bytes.fromhex(genuine["manifest"]["merkle"]["root_hex"])
    _attach_token(genuine["dir"], _mint_token(impostor, tsa_cert, root))
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"])
    assert code == verify.EXIT_FAIL, out
    assert "[FAIL] RFC 3161 token CMS signature" in out


def _openssl_has_ts():
    exe = shutil.which("openssl")
    if exe is None:
        return False
    p = subprocess.run([exe, "ts", "-help"], capture_output=True, text=True)
    return "-verify" in p.stdout + p.stderr


@pytest.mark.skipif(not _openssl_has_ts(), reason="openssl with `ts` not available")
def test_tsa_chain_validation_with_tsa_ca(genuine, tmp_path):
    tsa_key, tsa_cert, ca_pem = _test_tsa(tmp_path)
    root = bytes.fromhex(genuine["manifest"]["merkle"]["root_hex"])
    _attach_token(genuine["dir"], _mint_token(tsa_key, tsa_cert, root))
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"], "--tsa-ca", ca_pem)
    assert code == verify.EXIT_OK, out
    assert "[PASS] RFC 3161 TSA certificate chain" in out
    # a CA the TSA does not chain to is rejected
    (tmp_path / "other").mkdir()
    _, _, other_ca = _test_tsa(tmp_path / "other")
    code, out = _run(genuine["dir"], "--trusted-key", genuine["pub"], "--tsa-ca", other_ca)
    assert code == verify.EXIT_FAIL, out
    assert "[FAIL] RFC 3161 TSA certificate chain" in out

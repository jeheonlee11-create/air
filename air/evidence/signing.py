"""Ed25519 signing over canonical JSON.

- The signed record is human-readable JSON (sorted keys, compact separators,
  UTF-8) so a reviewer can open it in a text editor and re-derive its bytes.
- The public key ships inside the bundle for convenience, but it is not a
  trust anchor: anyone can re-sign an edited record with a fresh key. The
  operator publishes the key's SHA-256 fingerprint out of band and verifiers
  pass it to verify.py (--fingerprint / --trusted-key). Verification stays
  offline (a third party runs verify.py without contacting the vendor).
- A matching fingerprint shows which key signed, not who controls it. AIR has
  no PKI for signer identity. Its records are intended to support a qualified
  person's certification of an electronic record (e.g. under Fed. R. Evid.
  902(13)/(14)); AIR does not itself certify identity or admissibility.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json_bytes(obj) -> bytes:
    """Deterministic JSON encoding: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


PRIVATE_KEY_FILE = "air_signing_key.pem"
PUBLIC_KEY_FILE = "air_signing_key.pub.pem"
KEY_DIR_ENV = "AIR_KEY_DIR"


def default_key_dir() -> str:
    """$AIR_KEY_DIR if set, else ~/.air/keys.

    Fixed regardless of the working directory, so running the CLI from a
    different folder never silently generates a second signing key, and kept
    outside the source tree so it cannot be committed by accident.
    """
    return os.path.expanduser(os.environ.get(KEY_DIR_ENV) or os.path.join("~", ".air", "keys"))


def load_or_create_key(key_dir: str) -> Ed25519PrivateKey:
    """Load the signing key, or generate one on first run.

    Generation is announced on stderr: a silently replaced key would make every
    later bundle fail verification against the previously published fingerprint.
    The public half is written next to it for publication / --trusted-key.
    """
    os.makedirs(key_dir, exist_ok=True)
    priv_path = os.path.join(key_dir, PRIVATE_KEY_FILE)
    if os.path.exists(priv_path):
        with open(priv_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        fd = os.open(priv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        print(f"AIR: no signing key in {key_dir}/ — generated a NEW Ed25519 key at {priv_path}\n"
              f"     fingerprint (sha256): {public_key_fingerprint(public_pem(key))}\n"
              f"     publish this fingerprint out of band; bundles signed with a previous "
              f"key will not match it.", file=sys.stderr)
    pub_path = os.path.join(key_dir, PUBLIC_KEY_FILE)
    if not os.path.exists(pub_path):
        with open(pub_path, "w") as f:
            f.write(public_pem(key))
    return key


def public_pem(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def public_key_fingerprint(pub_pem: str) -> str:
    """SHA-256 over the DER SubjectPublicKeyInfo, hex. Same formula as verify.py."""
    pub = serialization.load_pem_public_key(pub_pem.encode())
    der = pub.public_bytes(encoding=serialization.Encoding.DER,
                           format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def sign(key: Ed25519PrivateKey, data: bytes) -> str:
    return base64.b64encode(key.sign(data)).decode()


def verify_signature(pub_pem: str, signature_b64: str, data: bytes) -> bool:
    pub = serialization.load_pem_public_key(pub_pem.encode())
    if not isinstance(pub, Ed25519PublicKey):
        return False
    try:
        pub.verify(base64.b64decode(signature_b64), data)
        return True
    except Exception:
        return False

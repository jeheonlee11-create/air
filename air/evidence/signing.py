"""Ed25519 signing over canonical JSON.

Design constraints (from FRE 902(13)/(14) practice):
- The signed artifact must be human-readable (JSON, not CBOR) so an adjuster
  or opposing expert can open it in a text editor.
- Numbers that matter are stringified before signing to avoid float-encoding
  ambiguity across JSON implementations.
- The public key ships inside the bundle; verification must not require
  contacting the vendor (a hostile third party runs verify.py offline).
"""

from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json_bytes(obj) -> bytes:
    """Deterministic JSON encoding: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_or_create_key(key_dir: str) -> Ed25519PrivateKey:
    os.makedirs(key_dir, exist_ok=True)
    priv_path = os.path.join(key_dir, "air_signing_key.pem")
    if os.path.exists(priv_path):
        with open(priv_path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(priv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    return key


def public_pem(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


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

"""Signing roundtrip, canonical JSON, conformance operators."""

import pytest

from air.analyze.conformance import _passes
from air.evidence.signing import (
    canonical_json_bytes,
    load_or_create_key,
    public_pem,
    sign,
    verify_signature,
)


def test_canonical_json_is_order_independent():
    assert canonical_json_bytes({"b": 1, "a": [1, 2]}) == canonical_json_bytes({"a": [1, 2], "b": 1})
    assert canonical_json_bytes({"a": 1}) == b'{"a":1}'


def test_sign_verify_roundtrip(tmp_path):
    key = load_or_create_key(str(tmp_path))
    sig = sign(key, b"payload")
    pub = public_pem(key)
    assert verify_signature(pub, sig, b"payload")
    assert not verify_signature(pub, sig, b"payload2")


def test_key_is_persisted_and_reloaded(tmp_path):
    k1 = load_or_create_key(str(tmp_path))
    k2 = load_or_create_key(str(tmp_path))
    assert public_pem(k1) == public_pem(k2)


def test_conformance_operators():
    assert _passes(100, "<=", 120)
    assert not _passes(120.04, "<=", 120)
    assert _passes(20, ">=", 6)
    assert not _passes(0.0, ">=", 15)
    assert _passes(["POSITION"], "not_contains", ["TERMINATION"])
    assert not _passes(["TERMINATION", "POSITION"], "not_contains", ["TERMINATION"])
    with pytest.raises(ValueError):
        _passes(1, "!!", 2)

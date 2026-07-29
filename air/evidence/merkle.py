"""RFC 9162 (Certificate Transparency v2) Merkle tree.

Implements the exact MTH construction from RFC 9162 §2.1:

    MTH({})     = HASH()
    MTH({d0})   = HASH(0x00 || d0)                      (leaf)
    MTH(D[n])   = HASH(0x01 || MTH(D[0:k]) || MTH(D[k:n]))   (interior)

where k is the largest power of two smaller than n.

The 0x00/0x01 domain separation between leaves and interior nodes is
mandatory: without it, a 64-byte interior preimage can be replayed as a leaf,
letting an attacker prove inclusion of a record that was never in the tree
(the classic CVE-2012-2459-family flaw). Lonely leaves are never duplicated.
"""

from __future__ import annotations

import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _hash(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(data: bytes) -> bytes:
    return _hash(LEAF_PREFIX + data)


def _largest_power_of_two_lt(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root(leaves: list[bytes]) -> bytes:
    """Root over raw leaf data blobs (leaf hashing applied internally)."""
    if not leaves:
        return _hash(b"")
    hashes = [leaf_hash(d) for d in leaves]
    return _mth(hashes)


def _mth(hashes: list[bytes]) -> bytes:
    n = len(hashes)
    if n == 1:
        return hashes[0]
    k = _largest_power_of_two_lt(n)
    return _hash(NODE_PREFIX + _mth(hashes[:k]) + _mth(hashes[k:]))


def inclusion_proof(leaves: list[bytes], index: int) -> list[bytes]:
    """Audit path for leaf `index` per RFC 9162 §2.1.3.1."""
    hashes = [leaf_hash(d) for d in leaves]

    def path(m: int, hs: list[bytes]) -> list[bytes]:
        n = len(hs)
        if n == 1:
            return []
        k = _largest_power_of_two_lt(n)
        if m < k:
            return [*path(m, hs[:k]), _mth(hs[k:])]
        return [*path(m - k, hs[k:]), _mth(hs[:k])]

    return path(index, hashes)


def verify_inclusion(leaf_data: bytes, index: int, tree_size: int,
                     proof: list[bytes], root: bytes) -> bool:
    """Verify an audit path per RFC 9162 §2.1.3.2."""
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

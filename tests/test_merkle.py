"""RFC 9162 Merkle tree correctness."""

import hashlib

from air.evidence.merkle import (
    inclusion_proof,
    leaf_hash,
    merkle_root,
    verify_inclusion,
)


def h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def test_empty_tree_is_hash_of_empty_string():
    assert merkle_root([]) == h(b"")


def test_single_leaf_uses_leaf_prefix():
    assert merkle_root([b"data"]) == h(b"\x00" + b"data")


def test_two_leaves_hand_computed():
    a, b = leaf_hash(b"a"), leaf_hash(b"b")
    assert merkle_root([b"a", b"b"]) == h(b"\x01" + a + b)


def test_three_leaves_uneven_split():
    # RFC 9162: k = largest power of two < n → for n=3, k=2
    la, lb, lc = leaf_hash(b"a"), leaf_hash(b"b"), leaf_hash(b"c")
    left = h(b"\x01" + la + lb)
    assert merkle_root([b"a", b"b", b"c"]) == h(b"\x01" + left + lc)


def test_inclusion_proofs_verify_for_all_leaves_sizes_1_to_8():
    for n in range(1, 9):
        leaves = [f"leaf-{i}".encode() for i in range(n)]
        root = merkle_root(leaves)
        for i in range(n):
            proof = inclusion_proof(leaves, i)
            assert verify_inclusion(leaves[i], i, n, proof, root), (n, i)


def test_wrong_leaf_fails_verification():
    leaves = [b"a", b"b", b"c", b"d"]
    root = merkle_root(leaves)
    proof = inclusion_proof(leaves, 1)
    assert not verify_inclusion(b"tampered", 1, 4, proof, root)


def test_domain_separation_blocks_node_as_leaf_replay():
    # An interior node's 64-byte preimage must not verify as a leaf: without
    # the 0x00/0x01 prefixes this attack succeeds (CVE-2012-2459 family).
    leaves = [b"a", b"b", b"c", b"d"]
    root = merkle_root(leaves)
    la, lb = leaf_hash(b"a"), leaf_hash(b"b")
    fake_leaf = la + lb  # preimage of the left interior node
    right = hashlib.sha256(b"\x01" + leaf_hash(b"c") + leaf_hash(b"d")).digest()
    # If prefixes were absent, [right] would prove fake_leaf at index 0 of a 2-tree.
    assert not verify_inclusion(fake_leaf, 0, 2, [right], root)

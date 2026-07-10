"""MinHash: compresses a set of shingles into a fixed-size signature.

Key idea: if you apply a hash function to all elements of two sets and
keep only the MINIMUM, the probability that the two minimums coincide
is exactly the Jaccard similarity of the two sets.

Repeating with `num_perm` independent hash functions yields a signature
of `num_perm` integers: the fraction of matching positions between two
signatures estimates Jaccard. A document of 10,000 shingles becomes 128
numbers.
"""

from __future__ import annotations

import random

# Mersenne prime > 2^32: makes (a*x + b) % P a universal hash family
# over the 32-bit hashes of the shingles
_MERSENNE = (1 << 61) - 1
_MAX_HASH = (1 << 32) - 1


class MinHasher:
    """Generates reproducible MinHash signatures (same seed -> same signatures)."""

    def __init__(self, num_perm: int = 128, seed: int = 42) -> None:
        if num_perm < 1:
            raise ValueError("num_perm must be >= 1")
        self.num_perm = num_perm
        rng = random.Random(seed)
        # coefficients (a, b) for num_perm functions h(x) = (a*x + b) % P
        self._params = [
            (rng.randrange(1, _MERSENNE), rng.randrange(0, _MERSENNE))
            for _ in range(num_perm)
        ]

    def signature(self, items: set[str]) -> tuple[int, ...]:
        """MinHash signature of a set of shingles."""
        if not items:
            return (0,) * self.num_perm
        # 32-bit base hash of each shingle (stable across runs)
        base = [_fnv1a(s) for s in items]
        mersenne = _MERSENNE  # local lookup: the inner loop runs n*num_perm times
        # the minimum is computed over the 61-bit values; the 32-bit
        # truncation happens once, on the winner (equivalent for the
        # estimate, but num_perm * n fewer operations)
        return tuple(
            min((a * x + b) % mersenne for x in base) & _MAX_HASH
            for a, b in self._params
        )

    @staticmethod
    def estimate_jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
        """Jaccard estimate: fraction of identical positions between two signatures."""
        if len(sig_a) != len(sig_b):
            raise ValueError("signatures must have the same length")
        equal = sum(1 for x, y in zip(sig_a, sig_b) if x == y)
        return equal / len(sig_a)


def _fnv1a(text: str) -> int:
    """32-bit FNV-1a hash: fast, deterministic across processes
    (unlike the built-in hash(), which is randomized)."""
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h

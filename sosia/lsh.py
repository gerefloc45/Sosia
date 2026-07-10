"""Banded LSH (Locality-Sensitive Hashing) over MinHash signatures.

The problem: with n records there are n*(n-1)/2 pairs. On 1 million
records that's ~500 billion comparisons — impossible.

The solution: split each signature into `bands` bands of `rows` values
each. Two records land in the same "bucket" if AT LEAST ONE band matches
exactly. Similar pairs almost certainly share a band; dissimilar pairs
almost never do. So we only compare the ones that collide in a bucket.

The probability of becoming candidates for a pair with Jaccard s is:
    P(candidate) = 1 - (1 - s^rows)^bands
an S-curve: nearly 0 below the threshold, nearly 1 above. The
approximate threshold is (1/bands)^(1/rows).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Hashable, Iterator


class LSHIndex:
    """LSH index: insert signatures, then ask for the candidate pairs."""

    def __init__(self, num_perm: int = 128, bands: int = 32) -> None:
        if num_perm % bands != 0:
            raise ValueError(
                f"num_perm ({num_perm}) must be divisible by bands ({bands})"
            )
        self.bands = bands
        self.rows = num_perm // bands
        # one dict of buckets per band:
        # buckets[band][tuple_of_values] -> list of record keys
        self._buckets: list[dict[tuple, list[Hashable]]] = [
            defaultdict(list) for _ in range(bands)
        ]
        self._keys: set[Hashable] = set()

    @property
    def threshold(self) -> float:
        """Approximate Jaccard threshold above which pairs become
        candidates: (1/bands)^(1/rows)."""
        return (1.0 / self.bands) ** (1.0 / self.rows)

    def insert(self, key: Hashable, signature: tuple[int, ...]) -> None:
        """Index the signature of the record identified by `key`."""
        if key in self._keys:
            raise KeyError(f"duplicate key in index: {key!r}")
        if len(signature) != self.bands * self.rows:
            raise ValueError("signature length differs from the index num_perm")
        self._keys.add(key)
        for band in range(self.bands):
            start = band * self.rows
            chunk = signature[start:start + self.rows]
            self._buckets[band][chunk].append(key)

    def candidate_pairs(self) -> Iterator[tuple[Hashable, Hashable]]:
        """All pairs of records that share at least one bucket.

        Each pair is emitted only once even if it collides in
        multiple bands.
        """
        seen: set[tuple] = set()
        for band_buckets in self._buckets:
            for keys in band_buckets.values():
                if len(keys) < 2:
                    continue
                for i in range(len(keys)):
                    for j in range(i + 1, len(keys)):
                        pair = (keys[i], keys[j]) if keys[i] <= keys[j] else (keys[j], keys[i])
                        if pair not in seen:
                            seen.add(pair)
                            yield pair

    def __len__(self) -> int:
        return len(self._keys)

"""Full deduplication pipeline.

    texts -> normalize -> shingles -> MinHash signature -> LSH index
          -> candidate pairs -> verification with true Jaccard
          -> duplicate clusters (union-find)

The LSH cuts the pairs to check from O(n^2) to near-linear; the final
verification with the true similarity removes the false positives.
"""

from __future__ import annotations

from typing import Sequence

from .similarity import jaccard, normalize, shingles
from .minhash import MinHasher
from .lsh import LSHIndex


def find_duplicates(
    texts: Sequence[str],
    threshold: float = 0.7,
    k: int | None = None,
    num_perm: int = 128,
    bands: int = 32,
) -> list[tuple[int, int, float]]:
    """Find the pairs of texts with Jaccard (over shingles) >= threshold.

    With k=None the shingle length adapts to each text's script (2 for
    Chinese/Japanese/Korean, 3 otherwise).
    Empty texts (or texts that become empty after normalization) are
    ignored: "empty" is not content, so two empty fields do NOT count
    as duplicates of each other.
    Returns triples (index_a, index_b, similarity) sorted from the most
    similar pair to the least similar.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")

    normalized = [normalize(t) for t in texts]
    shingle_sets = [shingles(t, k) for t in normalized]

    hasher = MinHasher(num_perm=num_perm)
    index = LSHIndex(num_perm=num_perm, bands=bands)
    for i, s in enumerate(shingle_sets):
        if not s:
            continue
        index.insert(i, hasher.signature(s))

    results = []
    for i, j in index.candidate_pairs():
        sim = jaccard(shingle_sets[i], shingle_sets[j])
        if sim >= threshold:
            results.append((i, j, sim))

    results.sort(key=lambda t: -t[2])
    return results


def cluster_duplicates(
    texts: Sequence[str],
    threshold: float = 0.7,
    **kwargs,
) -> list[list[int]]:
    """Group duplicates into clusters with union-find.

    If A~B and B~C, then A, B and C end up in the same cluster even if
    A and C don't pass the threshold directly (transitive closure).
    Returns only clusters with at least 2 elements, largest first.
    """
    pairs = find_duplicates(texts, threshold=threshold, **kwargs)

    parent = list(range(len(texts)))

    def find(x: int) -> int:
        # path compression: flattens the tree while walking up
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j, _ in pairs:
        union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(texts)):
        groups.setdefault(find(i), []).append(i)

    clusters = [sorted(g) for g in groups.values() if len(g) >= 2]
    clusters.sort(key=len, reverse=True)
    return clusters

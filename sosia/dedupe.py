"""Pipeline completa di deduplica.

    testi -> normalizza -> shingle -> firma MinHash -> indice LSH
          -> coppie candidate -> verifica con Jaccard vero
          -> cluster di duplicati (union-find)

L'LSH riduce le coppie da controllare da O(n^2) a quasi lineare; la
verifica finale con la similarita' vera elimina i falsi positivi.
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
    """Trova le coppie di testi con Jaccard (su shingle) >= threshold.

    Con k=None la lunghezza degli shingle si adatta allo script di ogni
    testo (2 per cinese/giapponese/coreano, 3 altrimenti).
    Ritorna triple (indice_a, indice_b, similarita') ordinate dalla
    coppia piu' simile alla meno simile.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold deve essere in (0, 1]")

    normalized = [normalize(t) for t in texts]
    shingle_sets = [shingles(t, k) for t in normalized]

    hasher = MinHasher(num_perm=num_perm)
    index = LSHIndex(num_perm=num_perm, bands=bands)
    for i, s in enumerate(shingle_sets):
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
    """Raggruppa i duplicati in cluster con union-find.

    Se A~B e B~C, allora A, B e C finiscono nello stesso cluster anche
    se A e C non superano la soglia direttamente (chiusura transitiva).
    Ritorna solo i cluster con almeno 2 elementi, il piu' grande prima.
    """
    pairs = find_duplicates(texts, threshold=threshold, **kwargs)

    parent = list(range(len(texts)))

    def find(x: int) -> int:
        # path compression: appiattisce l'albero mentre risale
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

"""sosia - fuzzy matching and record deduplication, in every language.

Layers:
    similarity  -> exact comparison between two strings (Levenshtein, Jaccard)
    minhash     -> compact signatures that estimate Jaccard similarity
    lsh         -> index that finds candidate pairs without O(n^2)
    dedupe      -> full pipeline: records -> duplicate clusters
"""

from .similarity import (
    levenshtein, levenshtein_ratio, jaccard, shingles, normalize, pick_k,
)
from .minhash import MinHasher
from .lsh import LSHIndex
from .dedupe import find_duplicates, cluster_duplicates

__all__ = [
    "levenshtein",
    "levenshtein_ratio",
    "jaccard",
    "shingles",
    "normalize",
    "pick_k",
    "MinHasher",
    "LSHIndex",
    "find_duplicates",
    "cluster_duplicates",
]

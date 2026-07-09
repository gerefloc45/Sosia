"""sosia - fuzzy matching e deduplica record, in ogni lingua.

Livelli:
    similarity  -> confronto esatto tra due stringhe (Levenshtein, Jaccard)
    minhash     -> firme compatte che stimano la similarita' di Jaccard
    lsh         -> indice che trova coppie candidate senza O(n^2)
    dedupe      -> pipeline completa: record -> cluster di duplicati
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

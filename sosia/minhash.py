"""MinHash: comprime un insieme di shingle in una firma di numeri fissi.

Idea chiave: se applichi una funzione hash a tutti gli elementi di due
insiemi e tieni solo il MINIMO, la probabilita' che i due minimi coincidano
e' esattamente la similarita' di Jaccard dei due insiemi.

Ripetendo con `num_perm` funzioni hash indipendenti ottieni una firma di
`num_perm` interi: la frazione di posizioni uguali tra due firme stima
Jaccard. Un documento di 10.000 shingle diventa 128 numeri.
"""

from __future__ import annotations

import random

# primo di Mersenne > 2^32: rende (a*x + b) % P una famiglia di hash
# universale sugli hash a 32 bit degli shingle
_MERSENNE = (1 << 61) - 1
_MAX_HASH = (1 << 32) - 1


class MinHasher:
    """Genera firme MinHash riproducibili (stesso seed -> stesse firme)."""

    def __init__(self, num_perm: int = 128, seed: int = 42) -> None:
        if num_perm < 1:
            raise ValueError("num_perm deve essere >= 1")
        self.num_perm = num_perm
        rng = random.Random(seed)
        # coefficienti (a, b) per num_perm funzioni h(x) = (a*x + b) % P
        self._params = [
            (rng.randrange(1, _MERSENNE), rng.randrange(0, _MERSENNE))
            for _ in range(num_perm)
        ]

    def signature(self, items: set[str]) -> tuple[int, ...]:
        """Firma MinHash di un insieme di shingle."""
        if not items:
            return (0,) * self.num_perm
        # hash base a 32 bit di ogni shingle (stabile tra esecuzioni)
        base = [_fnv1a(s) for s in items]
        sig = []
        for a, b in self._params:
            sig.append(min(((a * x + b) % _MERSENNE) & _MAX_HASH for x in base))
        return tuple(sig)

    @staticmethod
    def estimate_jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
        """Stima di Jaccard: frazione di posizioni identiche tra due firme."""
        if len(sig_a) != len(sig_b):
            raise ValueError("le firme devono avere la stessa lunghezza")
        equal = sum(1 for x, y in zip(sig_a, sig_b) if x == y)
        return equal / len(sig_a)


def _fnv1a(text: str) -> int:
    """Hash FNV-1a a 32 bit: veloce, deterministico tra processi
    (a differenza di hash() built-in, che e' randomizzato)."""
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h

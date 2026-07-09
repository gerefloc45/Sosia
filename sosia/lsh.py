"""LSH (Locality-Sensitive Hashing) a bande sulle firme MinHash.

Il problema: con n record ci sono n*(n-1)/2 coppie. Su 1 milione di record
sono ~500 miliardi di confronti — impossibile.

La soluzione: spezza ogni firma in `bands` bande di `rows` valori ciascuna.
Due record finiscono nello stesso "bucket" se ALMENO UNA banda coincide
esattamente. Coppie simili condividono quasi sicuramente una banda; coppie
diverse quasi mai. Cosi' confrontiamo solo chi collide in un bucket.

La probabilita' di diventare candidati per una coppia con Jaccard s e':
    P(candidato) = 1 - (1 - s^rows)^bands
una curva a S: quasi 0 sotto la soglia, quasi 1 sopra. La soglia
approssimata e' (1/bands)^(1/rows).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Hashable, Iterator


class LSHIndex:
    """Indice LSH: inserisci firme, poi chiedi le coppie candidate."""

    def __init__(self, num_perm: int = 128, bands: int = 32) -> None:
        if num_perm % bands != 0:
            raise ValueError(
                f"num_perm ({num_perm}) deve essere divisibile per bands ({bands})"
            )
        self.bands = bands
        self.rows = num_perm // bands
        # un dizionario di bucket per ogni banda:
        # buckets[banda][tupla_di_valori] -> lista di chiavi record
        self._buckets: list[dict[tuple, list[Hashable]]] = [
            defaultdict(list) for _ in range(bands)
        ]
        self._keys: set[Hashable] = set()

    @property
    def threshold(self) -> float:
        """Soglia di Jaccard approssimata sopra cui le coppie diventano
        candidate: (1/bands)^(1/rows)."""
        return (1.0 / self.bands) ** (1.0 / self.rows)

    def insert(self, key: Hashable, signature: tuple[int, ...]) -> None:
        """Indicizza la firma di un record identificato da `key`."""
        if key in self._keys:
            raise KeyError(f"chiave duplicata nell'indice: {key!r}")
        if len(signature) != self.bands * self.rows:
            raise ValueError("lunghezza firma diversa da num_perm dell'indice")
        self._keys.add(key)
        for band in range(self.bands):
            start = band * self.rows
            chunk = signature[start:start + self.rows]
            self._buckets[band][chunk].append(key)

    def candidate_pairs(self) -> Iterator[tuple[Hashable, Hashable]]:
        """Tutte le coppie di record che condividono almeno un bucket.

        Ogni coppia viene emessa una sola volta anche se collide in
        piu' bande.
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

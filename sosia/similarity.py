"""Misure di similarita' tra due stringhe.

Queste funzioni sono il "giudice finale": costano O(len_a * len_b),
quindi vanno usate solo sulle coppie candidate trovate dall'LSH,
mai su tutte le coppie di un dataset grande.
"""

from __future__ import annotations

import re
import unicodedata


def _strippable_base(ch: str) -> bool:
    """True se i segni combinanti che seguono `ch` sono solo decorativi
    (accenti) e possono essere rimossi senza cambiare la parola.

    Vale per latino, greco, cirillico (accenti), arabo (harakat) ed
    ebraico (niqqud). NON vale per gli script indiani, il thai o il
    giapponese, dove i segni combinanti sono vocali o cambiano la
    consonante (hindi: कि != क; giapponese: が != か).
    """
    cp = ord(ch)
    return (
        0x0041 <= cp <= 0x024F      # latino base + esteso
        or 0x0370 <= cp <= 0x03FF   # greco
        or 0x0400 <= cp <= 0x052F   # cirillico
        or 0x0590 <= cp <= 0x05FF   # ebraico
        or 0x0600 <= cp <= 0x06FF   # arabo
        or 0x1E00 <= cp <= 0x1FFF   # latino/greco esteso addizionale
    )


# script dove lo spazio tra caratteri e' rumore (cinese e giapponese non
# usano spazi): "北京市 朝阳区" deve combaciare con "北京市朝阳区"
_CJK_RANGE = "぀-ヿ㐀-鿿가-힯豈-﫿"
_CJK_SPACE = re.compile(f"(?<=[{_CJK_RANGE}]) (?=[{_CJK_RANGE}])")

# varianti di alef arabo che nella pratica si scrivono in modo intercambiabile
_ARABIC_MAP = str.maketrans({
    "آ": "ا", "أ": "ا",   # آ أ -> ا
    "إ": "ا", "ٱ": "ا",   # إ ٱ -> ا
    "ـ": None,                            # tatweel (allungamento grafico)
})


def normalize(text: str) -> str:
    """Normalizza un testo per il confronto, per qualsiasi lingua.

    - NFKC: larghezza piena -> normale (Ｔｏｋｙｏ -> Tokyo), legature
    - casefold: minuscole robuste (STRASSE e straße combaciano)
    - accenti via solo dove sono decorativi (latino, greco, cirillico,
      harakat arabi, niqqud ebraici); i segni vocalici di hindi, thai,
      giapponese ecc. vengono PRESERVATI
    - punteggiatura e simboli -> spazio, spazi compattati
    - spazi tra caratteri CJK rimossi (il cinese non usa spazi)
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(_ARABIC_MAP)

    out = []
    safe_base = False
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch):
            if not safe_base:
                out.append(ch)  # segno semantico (matra, dakuten...): resta
            continue
        safe_base = _strippable_base(ch)
        cat = unicodedata.category(ch)
        # L=lettere, N=cifre, M=segni vocalici "spacing" (es. matra hindi
        # con classe combinante 0, che arrivano in questo ramo)
        if cat[0] in ("L", "N", "M"):
            out.append(ch)
        else:                        # punteggiatura, simboli, spazi
            out.append(" ")
    text = unicodedata.normalize("NFC", "".join(out))
    text = " ".join(text.split())
    return _CJK_SPACE.sub("", text)


def levenshtein(a: str, b: str) -> int:
    """Distanza di edit: numero minimo di inserimenti, cancellazioni e
    sostituzioni per trasformare `a` in `b`.

    Programmazione dinamica con due sole righe di memoria: O(len_a * len_b)
    tempo, O(min(len_a, len_b)) spazio.
    """
    if a == b:
        return 0
    # la riga della DP e' lunga quanto la stringa piu' corta
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(
                prev[j] + 1,        # cancellazione
                curr[j - 1] + 1,    # inserimento
                prev[j - 1] + cost, # sostituzione (o match)
            ))
        prev = curr
    return prev[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    """Similarita' in [0, 1] derivata dalla distanza di edit.

    1.0 = identiche, 0.0 = completamente diverse.
    """
    if not a and not b:
        return 1.0
    dist = levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b))


def _is_dense_script(ch: str) -> bool:
    """True per gli script dove un singolo carattere vale quanto una
    sillaba o una parola intera (ideogrammi CJK, kana, sillabe hangul)."""
    cp = ord(ch)
    return (
        0x3040 <= cp <= 0x30FF      # hiragana + katakana
        or 0x3400 <= cp <= 0x9FFF   # ideogrammi CJK (est. A + base)
        or 0xAC00 <= cp <= 0xD7AF   # sillabe hangul
        or 0xF900 <= cp <= 0xFAFF   # ideogrammi di compatibilita'
        or 0x20000 <= cp <= 0x2FFFF # ideogrammi CJK estensioni B+
    )


def pick_k(text: str) -> int:
    """Sceglie la lunghezza degli shingle in base allo script.

    2 se il testo e' in maggioranza cinese/giapponese/coreano (ogni
    carattere e' gia' una sillaba/parola), altrimenti 3.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 3
    dense = sum(1 for c in chars if _is_dense_script(c))
    return 2 if dense * 2 > len(chars) else 3


def shingles(text: str, k: int | None = None) -> set[str]:
    """Insieme degli n-grammi di caratteri di lunghezza `k`.

    "ciao" con k=3 -> {"cia", "iao"}.  Gli shingle trasformano una stringa
    in un INSIEME, il che permette di usare Jaccard (e quindi MinHash).
    Con k=None la lunghezza viene scelta in base allo script (vedi
    pick_k). Testi piu' corti di k producono un singolo shingle: il
    testo stesso.
    """
    if k is None:
        k = pick_k(text)
    if len(text) <= k:
        return {text} if text else set()
    return {text[i:i + k] for i in range(len(text) - k + 1)}


def jaccard(set_a: set, set_b: set) -> float:
    """Similarita' di Jaccard tra due insiemi: |A ∩ B| / |A ∪ B|.

    E' la misura che MinHash stima senza calcolare gli insiemi interi.
    """
    if not set_a and not set_b:
        return 1.0
    inter = len(set_a & set_b)
    if inter == 0:
        return 0.0
    return inter / (len(set_a) + len(set_b) - inter)

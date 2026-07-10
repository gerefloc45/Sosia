"""Similarity measures between two strings.

These functions are the "final judge": they cost O(len_a * len_b),
so they should only be used on the candidate pairs found by the LSH,
never on every pair of a large dataset.
"""

from __future__ import annotations

import re
import unicodedata


def _strippable_base(ch: str) -> bool:
    """True if the combining marks following `ch` are merely decorative
    (accents) and can be removed without changing the word.

    Holds for Latin, Greek, Cyrillic (accents), Arabic (harakat) and
    Hebrew (niqqud). Does NOT hold for Indic scripts, Thai or Japanese,
    where combining marks are vowels or change the consonant
    (Hindi: कि != क; Japanese: が != か).
    """
    cp = ord(ch)
    return (
        0x0041 <= cp <= 0x024F      # base + extended Latin
        or 0x0370 <= cp <= 0x03FF   # Greek
        or 0x0400 <= cp <= 0x052F   # Cyrillic
        or 0x0590 <= cp <= 0x05FF   # Hebrew
        or 0x0600 <= cp <= 0x06FF   # Arabic
        or 0x1E00 <= cp <= 0x1FFF   # Latin/Greek extended additional
    )


# scripts where a space between characters is noise (Chinese and Japanese
# don't use spaces): "北京市 朝阳区" must match "北京市朝阳区"
_CJK_RANGE = "぀-ヿ㐀-鿿가-힯豈-﫿"
_CJK_SPACE = re.compile(f"(?<=[{_CJK_RANGE}]) (?=[{_CJK_RANGE}])")

# Arabic alef variants that are written interchangeably in practice
_ARABIC_MAP = str.maketrans({
    "آ": "ا", "أ": "ا",   # آ أ -> ا
    "إ": "ا", "ٱ": "ا",   # إ ٱ -> ا
    "ـ": None,                            # tatweel (graphic elongation)
})


def normalize(text: str) -> str:
    """Normalize a text for comparison, for any language.

    - NFKC: full-width -> regular (Ｔｏｋｙｏ -> Tokyo), ligatures expanded
    - casefold: robust lowercasing (STRASSE and straße match)
    - accents removed only where decorative (Latin, Greek, Cyrillic,
      Arabic harakat, Hebrew niqqud); the vowel marks of Hindi, Thai,
      Japanese etc. are PRESERVED
    - punctuation and symbols -> space, whitespace collapsed
    - spaces between CJK characters removed (Chinese doesn't use spaces)
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(_ARABIC_MAP)

    out = []
    safe_base = False
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.combining(ch):
            if not safe_base:
                out.append(ch)  # semantic mark (matra, dakuten...): keep it
            continue
        safe_base = _strippable_base(ch)
        cat = unicodedata.category(ch)
        # L=letters, N=digits, M="spacing" vowel marks (e.g. Hindi matras
        # with combining class 0, which arrive in this branch)
        if cat[0] in ("L", "N", "M"):
            out.append(ch)
        else:                        # punctuation, symbols, spaces
            out.append(" ")
    text = unicodedata.normalize("NFC", "".join(out))
    text = " ".join(text.split())
    return _CJK_SPACE.sub("", text)


def levenshtein(a: str, b: str) -> int:
    """Edit distance: minimum number of insertions, deletions and
    substitutions needed to turn `a` into `b`.

    Dynamic programming with only two rows of memory: O(len_a * len_b)
    time, O(min(len_a, len_b)) space.
    """
    if a == b:
        return 0
    # a common prefix/suffix contributes nothing to the distance:
    # stripping it shrinks the DP matrix (often dramatically, since
    # near-duplicates differ in a single spot)
    start = 0
    end_a, end_b = len(a), len(b)
    while start < end_a and start < end_b and a[start] == b[start]:
        start += 1
    while end_a > start and end_b > start and a[end_a - 1] == b[end_b - 1]:
        end_a -= 1
        end_b -= 1
    a, b = a[start:end_a], b[start:end_b]

    # the DP row is as long as the shorter string
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
                prev[j] + 1,        # deletion
                curr[j - 1] + 1,    # insertion
                prev[j - 1] + cost, # substitution (or match)
            ))
        prev = curr
    return prev[-1]


def levenshtein_ratio(a: str, b: str) -> float:
    """Similarity in [0, 1] derived from the edit distance.

    1.0 = identical, 0.0 = completely different.
    """
    if not a and not b:
        return 1.0
    dist = levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b))


def _is_dense_script(ch: str) -> bool:
    """True for scripts where a single character is worth a whole
    syllable or word (CJK ideographs, kana, hangul syllables)."""
    cp = ord(ch)
    return (
        0x3040 <= cp <= 0x30FF      # hiragana + katakana
        or 0x3400 <= cp <= 0x9FFF   # CJK ideographs (ext. A + base)
        or 0xAC00 <= cp <= 0xD7AF   # hangul syllables
        or 0xF900 <= cp <= 0xFAFF   # compatibility ideographs
        or 0x20000 <= cp <= 0x2FFFF # CJK ideographs, extensions B+
    )


def pick_k(text: str) -> int:
    """Choose the shingle length based on the script.

    2 if the text is mostly Chinese/Japanese/Korean (each character is
    already a syllable/word), 3 otherwise.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 3
    dense = sum(1 for c in chars if _is_dense_script(c))
    return 2 if dense * 2 > len(chars) else 3


def shingles(text: str, k: int | None = None) -> set[str]:
    """Set of the character n-grams of length `k`.

    "ciao" with k=3 -> {"cia", "iao"}.  Shingling turns a string into a
    SET, which makes Jaccard (and therefore MinHash) applicable.
    With k=None the length is chosen based on the script (see pick_k).
    Texts shorter than k produce a single shingle: the text itself.
    """
    if k is None:
        k = pick_k(text)
    if len(text) <= k:
        return {text} if text else set()
    return {text[i:i + k] for i in range(len(text) - k + 1)}


def jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets: |A ∩ B| / |A ∪ B|.

    This is the measure that MinHash estimates without computing the
    full sets.
    """
    if not set_a and not set_b:
        return 1.0
    inter = len(set_a & set_b)
    if inter == 0:
        return 0.0
    return inter / (len(set_a) + len(set_b) - inter)

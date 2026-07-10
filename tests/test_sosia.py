"""Tests for the sosia library. Run with: python -m unittest discover tests"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sosia.similarity import (
    levenshtein, levenshtein_ratio, jaccard, shingles, normalize, pick_k,
)
from sosia.minhash import MinHasher
from sosia.lsh import LSHIndex
from sosia.dedupe import find_duplicates, cluster_duplicates
from sosia.__main__ import main as cli_main


class TestNormalize(unittest.TestCase):
    def test_accents_and_uppercase(self):
        self.assertEqual(normalize("Müller, JÖRG "), "muller jorg")

    def test_punctuation_and_whitespace(self):
        self.assertEqual(normalize("Rossi,   Mario!!"), "rossi mario")


class TestNormalizeMultilingual(unittest.TestCase):
    def test_japanese_full_width(self):
        # NFKC: full-width Latin characters -> regular
        self.assertEqual(normalize("Ｔｏｋｙｏ　Ｔｏｗｅｒ"), "tokyo tower")

    def test_japanese_dakuten_preserved(self):
        # か (ka) and が (ga) are different words: the dakuten must NOT go
        self.assertNotEqual(normalize("かき"), normalize("がき"))

    def test_german_casefold(self):
        self.assertEqual(normalize("STRASSE"), normalize("straße"))

    def test_arabic_harakat_removed(self):
        # with and without short vowels: same word (Muhammad)
        self.assertEqual(normalize("مُحَمَّد"), normalize("محمد"))

    def test_arabic_alef_variants(self):
        self.assertEqual(normalize("أحمد"), normalize("احمد"))

    def test_hebrew_niqqud_removed(self):
        # shalom with and without vowel points
        self.assertEqual(normalize("שָׁלוֹם"), normalize("שלום"))

    def test_hindi_matra_preserved(self):
        # कि (ki) and क (ka): the vowel is semantic, it must stay
        self.assertNotEqual(normalize("किताब"), normalize("कताब"))

    def test_russian_uppercase_and_stress(self):
        # the Russian stress mark (rare but present in dictionaries) goes
        self.assertEqual(normalize("МОСКВА́"), normalize("москва"))

    def test_greek(self):
        self.assertEqual(normalize("Αθήνα"), normalize("αθηνα"))

    def test_chinese_punctuation_and_spaces(self):
        # punctuation becomes a space, but between CJK characters spaces
        # are noise and get removed
        self.assertEqual(normalize("北京市，朝阳区！"), "北京市朝阳区")
        self.assertEqual(normalize("北京市 朝阳区"), normalize("北京市朝阳区"))


class TestPickK(unittest.TestCase):
    def test_latin(self):
        self.assertEqual(pick_k("mario rossi via garibaldi"), 3)

    def test_chinese(self):
        self.assertEqual(pick_k("北京市朝阳区建国路"), 2)

    def test_japanese(self):
        self.assertEqual(pick_k("東京都渋谷区のレストラン"), 2)

    def test_korean(self):
        self.assertEqual(pick_k("서울특별시 강남구"), 2)

    def test_mixed_latin_prevails(self):
        self.assertEqual(pick_k("hotel roma near 駅"), 3)

    def test_empty(self):
        self.assertEqual(pick_k(""), 3)


class TestLevenshtein(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(levenshtein("ciao", "ciao"), 0)

    def test_empty(self):
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("abc", ""), 3)
        self.assertEqual(levenshtein("", ""), 0)

    def test_known_cases(self):
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("flaw", "lawn"), 2)

    def test_symmetric(self):
        self.assertEqual(levenshtein("domenica", "sabato"),
                         levenshtein("sabato", "domenica"))

    def test_common_prefix_and_suffix(self):
        # prefix/suffix trimming must not alter the result
        self.assertEqual(levenshtein("via garibaldi 12", "via garibaldo 12"), 1)
        self.assertEqual(levenshtein("aaabbbccc", "aaaccc"), 3)
        self.assertEqual(levenshtein("abc", "abcabc"), 3)

    def test_ratio(self):
        self.assertEqual(levenshtein_ratio("abc", "abc"), 1.0)
        self.assertEqual(levenshtein_ratio("", ""), 1.0)
        self.assertAlmostEqual(levenshtein_ratio("abcd", "abce"), 0.75)


class TestShinglesJaccard(unittest.TestCase):
    def test_shingles(self):
        self.assertEqual(shingles("ciao", 3), {"cia", "iao"})

    def test_short_text(self):
        self.assertEqual(shingles("ab", 3), {"ab"})
        self.assertEqual(shingles("", 3), set())

    def test_jaccard(self):
        self.assertEqual(jaccard({1, 2, 3}, {2, 3, 4}), 0.5)
        self.assertEqual(jaccard(set(), set()), 1.0)
        self.assertEqual(jaccard({1}, {2}), 0.0)


class TestMinHash(unittest.TestCase):
    def test_deterministic(self):
        s = shingles("il gatto sul tetto", 3)
        self.assertEqual(MinHasher(64).signature(s), MinHasher(64).signature(s))

    def test_identical_estimate_is_1(self):
        h = MinHasher(64)
        s = shingles("stessa stringa", 3)
        self.assertEqual(h.estimate_jaccard(h.signature(s), h.signature(s)), 1.0)

    def test_estimate_close_to_truth(self):
        h = MinHasher(256)
        a = shingles("il consiglio comunale ha approvato il bilancio 2026", 3)
        b = shingles("il consiglio comunale ha approvato il bilancio 2025", 3)
        true = jaccard(a, b)
        estimate = h.estimate_jaccard(h.signature(a), h.signature(b))
        # with 256 permutations the expected error is ~1/sqrt(256) = 0.0625
        self.assertAlmostEqual(estimate, true, delta=0.15)

    def test_different_estimate_is_low(self):
        h = MinHasher(128)
        a = h.signature(shingles("fattura elettronica gennaio", 3))
        b = h.signature(shingles("zqx wvy kjh plm", 3))
        self.assertLess(h.estimate_jaccard(a, b), 0.2)


class TestLSH(unittest.TestCase):
    def test_similar_become_candidates(self):
        h = MinHasher(128)
        idx = LSHIndex(num_perm=128, bands=32)
        idx.insert("a", h.signature(shingles("mario rossi via garibaldi 12 milano", 3)))
        idx.insert("b", h.signature(shingles("mario rossi via garibaldi 12 milan", 3)))
        idx.insert("c", h.signature(shingles("tutt altra cosa completamente diversa", 3)))
        pairs = set(idx.candidate_pairs())
        self.assertIn(("a", "b"), pairs)
        self.assertNotIn(("a", "c"), pairs)
        self.assertNotIn(("b", "c"), pairs)

    def test_duplicate_key(self):
        idx = LSHIndex(num_perm=8, bands=2)
        idx.insert("x", (1,) * 8)
        with self.assertRaises(KeyError):
            idx.insert("x", (2,) * 8)

    def test_bands_not_divisible(self):
        with self.assertRaises(ValueError):
            LSHIndex(num_perm=100, bands=33)


class TestPipeline(unittest.TestCase):
    TEXTS = [
        "Mario Rossi, Via Garibaldi 12, Milano",     # 0
        "mario rossi via garibaldi 12 milano",       # 1 (dup of 0)
        "Mario Rossi - v. Garibaldi 12 - MILANO",    # 2 (dup of 0)
        "Giulia Bianchi, Corso Italia 5, Torino",    # 3
        "giulia bianchi corso italia 5 torino (TO)", # 4 (dup of 3)
        "Ristorante Da Peppino, Napoli",             # 5 (unique)
    ]

    def test_find_duplicates(self):
        pairs = {(i, j) for i, j, _ in find_duplicates(self.TEXTS, threshold=0.6)}
        self.assertIn((0, 1), pairs)
        self.assertIn((3, 4), pairs)
        for i, j in pairs:
            self.assertNotIn(5, (i, j))

    def test_cluster(self):
        clusters = cluster_duplicates(self.TEXTS, threshold=0.6)
        as_sets = [set(c) for c in clusters]
        self.assertIn({0, 1, 2}, as_sets)
        self.assertIn({3, 4}, as_sets)
        self.assertEqual(len(clusters), 2)

    def test_no_duplicates(self):
        self.assertEqual(cluster_duplicates(["alfa beta", "gamma delta"], 0.8), [])

    def test_cluster_multilingual(self):
        texts = [
            "北京市朝阳区建国路88号",           # 0 Chinese
            "北京市 朝阳区 建国路 88号",         # 1 dup of 0 (with spaces)
            "東京都渋谷区神南1-19-11",          # 2 Japanese
            "東京都渋谷区神南１－１９－１１",    # 3 dup of 2 (full-width)
            "شارع الملك فهد، الرياض",           # 4 Arabic
            "شارع الملك فهد الرياض",            # 5 dup of 4 (no comma)
            "Москва, Тверская улица 7",         # 6 Russian
            "МОСКВА ТВЕРСКАЯ УЛИЦА 7",          # 7 dup of 6 (uppercase)
            "Bäckerstraße 12, Wien",            # 8 German (unique)
        ]
        clusters = cluster_duplicates(texts, threshold=0.6)
        as_sets = [set(c) for c in clusters]
        self.assertIn({0, 1}, as_sets)
        self.assertIn({2, 3}, as_sets)
        self.assertIn({4, 5}, as_sets)
        self.assertIn({6, 7}, as_sets)
        for c in as_sets:
            self.assertNotIn(8, c)

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            find_duplicates(["a"], threshold=0.0)

    def test_empty_texts_are_not_duplicates(self):
        # two empty fields must not count as "the same record"
        texts = ["", "   ", "Mario Rossi Milano", "mario rossi milano", "!!!"]
        clusters = cluster_duplicates(texts, threshold=0.6)
        self.assertEqual([set(c) for c in clusters], [{2, 3}])


class TestCLI(unittest.TestCase):
    CSV = (
        "name,city\n"
        "Mario Rossi,Milano\n"
        "Giulia Bianchi,Torino\n"
        "MARIO ROSSI,MILANO\n"
        "Anna Neri,Bologna\n"
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.input = self.dir / "customers.csv"
        self.input.write_text(self.CSV, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_readable_report(self):
        code, out, _ = self._run(
            str(self.input), "--column", "name,city", "--threshold", "0.6")
        self.assertEqual(code, 0)
        self.assertIn("1 duplicate groups", out)
        self.assertIn("row 2", out)   # Mario Rossi
        self.assertIn("row 4", out)   # MARIO ROSSI

    def test_output_removes_redundant(self):
        cleaned = self.dir / "cleaned.csv"
        code, _, err = self._run(
            str(self.input), "--column", "name,city",
            "--threshold", "0.6", "--output", str(cleaned))
        self.assertEqual(code, 0)
        self.assertIn("1 redundant removed", err)
        with cleaned.open(newline="", encoding="utf-8") as f:
            names = [row["name"] for row in csv.DictReader(f)]
        # the FIRST of each group survives, original order is preserved
        self.assertEqual(names, ["Mario Rossi", "Giulia Bianchi", "Anna Neri"])

    def test_output_does_not_overwrite_input(self):
        code, _, err = self._run(
            str(self.input), "--column", "name", "--output", str(self.input))
        self.assertEqual(code, 1)
        self.assertIn("error", err)
        # the input file must be untouched
        self.assertEqual(self.input.read_text(encoding="utf-8"), self.CSV)

    def test_json(self):
        code, out, _ = self._run(
            str(self.input), "--column", "name,city",
            "--threshold", "0.6", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["records"], 4)
        self.assertEqual([g["rows"] for g in payload["groups"]], [[2, 4]])

    def test_missing_column(self):
        code, _, err = self._run(str(self.input), "--column", "email")
        self.assertEqual(code, 1)
        self.assertIn("available columns: name, city", err)


if __name__ == "__main__":
    unittest.main()

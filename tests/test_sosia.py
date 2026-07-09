"""Test della libreria sosia. Esegui con: python -m unittest discover tests"""

import unittest

from sosia.similarity import (
    levenshtein, levenshtein_ratio, jaccard, shingles, normalize, pick_k,
)
from sosia.minhash import MinHasher
from sosia.lsh import LSHIndex
from sosia.dedupe import find_duplicates, cluster_duplicates


class TestNormalize(unittest.TestCase):
    def test_accenti_e_maiuscole(self):
        self.assertEqual(normalize("Müller, JÖRG "), "muller jorg")

    def test_punteggiatura_e_spazi(self):
        self.assertEqual(normalize("Rossi,   Mario!!"), "rossi mario")


class TestNormalizeMultilingua(unittest.TestCase):
    def test_giapponese_larghezza_piena(self):
        # NFKC: caratteri latini a larghezza piena -> normali
        self.assertEqual(normalize("Ｔｏｋｙｏ　Ｔｏｗｅｒ"), "tokyo tower")

    def test_giapponese_dakuten_preservato(self):
        # か (ka) e が (ga) sono parole diverse: il dakuten NON va rimosso
        self.assertNotEqual(normalize("かき"), normalize("がき"))

    def test_tedesco_casefold(self):
        self.assertEqual(normalize("STRASSE"), normalize("straße"))

    def test_arabo_harakat_rimossi(self):
        # con e senza vocali brevi: stessa parola (Muhammad)
        self.assertEqual(normalize("مُحَمَّد"), normalize("محمد"))

    def test_arabo_varianti_alef(self):
        self.assertEqual(normalize("أحمد"), normalize("احمد"))

    def test_ebraico_niqqud_rimosso(self):
        # shalom con e senza puntini vocalici
        self.assertEqual(normalize("שָׁלוֹם"), normalize("שלום"))

    def test_hindi_matra_preservata(self):
        # कि (ki) e क (ka): la vocale e' semantica, deve restare
        self.assertNotEqual(normalize("किताब"), normalize("कताब"))

    def test_russo_maiuscole_e_accento(self):
        # l'accento tonico russo (raro ma presente nei dizionari) va via
        self.assertEqual(normalize("МОСКВА́"), normalize("москва"))

    def test_greco(self):
        self.assertEqual(normalize("Αθήνα"), normalize("αθηνα"))

    def test_cinese_punteggiatura_e_spazi(self):
        # la punteggiatura diventa spazio, ma tra caratteri CJK gli spazi
        # sono rumore e vengono rimossi
        self.assertEqual(normalize("北京市，朝阳区！"), "北京市朝阳区")
        self.assertEqual(normalize("北京市 朝阳区"), normalize("北京市朝阳区"))


class TestPickK(unittest.TestCase):
    def test_latino(self):
        self.assertEqual(pick_k("mario rossi via garibaldi"), 3)

    def test_cinese(self):
        self.assertEqual(pick_k("北京市朝阳区建国路"), 2)

    def test_giapponese(self):
        self.assertEqual(pick_k("東京都渋谷区のレストラン"), 2)

    def test_coreano(self):
        self.assertEqual(pick_k("서울특별시 강남구"), 2)

    def test_misto_prevale_latino(self):
        self.assertEqual(pick_k("hotel roma near 駅"), 3)

    def test_vuoto(self):
        self.assertEqual(pick_k(""), 3)


class TestLevenshtein(unittest.TestCase):
    def test_identiche(self):
        self.assertEqual(levenshtein("ciao", "ciao"), 0)

    def test_vuote(self):
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("abc", ""), 3)
        self.assertEqual(levenshtein("", ""), 0)

    def test_casi_noti(self):
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("flaw", "lawn"), 2)

    def test_simmetrica(self):
        self.assertEqual(levenshtein("domenica", "sabato"),
                         levenshtein("sabato", "domenica"))

    def test_ratio(self):
        self.assertEqual(levenshtein_ratio("abc", "abc"), 1.0)
        self.assertEqual(levenshtein_ratio("", ""), 1.0)
        self.assertAlmostEqual(levenshtein_ratio("abcd", "abce"), 0.75)


class TestShinglesJaccard(unittest.TestCase):
    def test_shingles(self):
        self.assertEqual(shingles("ciao", 3), {"cia", "iao"})

    def test_testo_corto(self):
        self.assertEqual(shingles("ab", 3), {"ab"})
        self.assertEqual(shingles("", 3), set())

    def test_jaccard(self):
        self.assertEqual(jaccard({1, 2, 3}, {2, 3, 4}), 0.5)
        self.assertEqual(jaccard(set(), set()), 1.0)
        self.assertEqual(jaccard({1}, {2}), 0.0)


class TestMinHash(unittest.TestCase):
    def test_deterministico(self):
        s = shingles("il gatto sul tetto", 3)
        self.assertEqual(MinHasher(64).signature(s), MinHasher(64).signature(s))

    def test_identici_stima_1(self):
        h = MinHasher(64)
        s = shingles("stessa stringa", 3)
        self.assertEqual(h.estimate_jaccard(h.signature(s), h.signature(s)), 1.0)

    def test_stima_vicina_al_vero(self):
        h = MinHasher(256)
        a = shingles("il consiglio comunale ha approvato il bilancio 2026", 3)
        b = shingles("il consiglio comunale ha approvato il bilancio 2025", 3)
        vero = jaccard(a, b)
        stima = h.estimate_jaccard(h.signature(a), h.signature(b))
        # con 256 permutazioni l'errore atteso e' ~1/sqrt(256) = 0.0625
        self.assertAlmostEqual(stima, vero, delta=0.15)

    def test_diversi_stima_bassa(self):
        h = MinHasher(128)
        a = h.signature(shingles("fattura elettronica gennaio", 3))
        b = h.signature(shingles("zqx wvy kjh plm", 3))
        self.assertLess(h.estimate_jaccard(a, b), 0.2)


class TestLSH(unittest.TestCase):
    def test_simili_diventano_candidati(self):
        h = MinHasher(128)
        idx = LSHIndex(num_perm=128, bands=32)
        idx.insert("a", h.signature(shingles("mario rossi via garibaldi 12 milano", 3)))
        idx.insert("b", h.signature(shingles("mario rossi via garibaldi 12 milan", 3)))
        idx.insert("c", h.signature(shingles("tutt altra cosa completamente diversa", 3)))
        pairs = set(idx.candidate_pairs())
        self.assertIn(("a", "b"), pairs)
        self.assertNotIn(("a", "c"), pairs)
        self.assertNotIn(("b", "c"), pairs)

    def test_chiave_duplicata(self):
        idx = LSHIndex(num_perm=8, bands=2)
        idx.insert("x", (1,) * 8)
        with self.assertRaises(KeyError):
            idx.insert("x", (2,) * 8)

    def test_bands_non_divisibili(self):
        with self.assertRaises(ValueError):
            LSHIndex(num_perm=100, bands=33)


class TestPipeline(unittest.TestCase):
    TESTI = [
        "Mario Rossi, Via Garibaldi 12, Milano",     # 0
        "mario rossi via garibaldi 12 milano",       # 1 (dup di 0)
        "Mario Rossi - v. Garibaldi 12 - MILANO",    # 2 (dup di 0)
        "Giulia Bianchi, Corso Italia 5, Torino",    # 3
        "giulia bianchi corso italia 5 torino (TO)", # 4 (dup di 3)
        "Ristorante Da Peppino, Napoli",             # 5 (unico)
    ]

    def test_find_duplicates(self):
        pairs = {(i, j) for i, j, _ in find_duplicates(self.TESTI, threshold=0.6)}
        self.assertIn((0, 1), pairs)
        self.assertIn((3, 4), pairs)
        for i, j in pairs:
            self.assertNotIn(5, (i, j))

    def test_cluster(self):
        clusters = cluster_duplicates(self.TESTI, threshold=0.6)
        as_sets = [set(c) for c in clusters]
        self.assertIn({0, 1, 2}, as_sets)
        self.assertIn({3, 4}, as_sets)
        self.assertEqual(len(clusters), 2)

    def test_nessun_duplicato(self):
        self.assertEqual(cluster_duplicates(["alfa beta", "gamma delta"], 0.8), [])

    def test_cluster_multilingua(self):
        testi = [
            "北京市朝阳区建国路88号",           # 0 cinese
            "北京市 朝阳区 建国路 88号",         # 1 dup di 0 (con spazi)
            "東京都渋谷区神南1-19-11",          # 2 giapponese
            "東京都渋谷区神南１－１９－１１",    # 3 dup di 2 (larghezza piena)
            "شارع الملك فهد، الرياض",           # 4 arabo
            "شارع الملك فهد الرياض",            # 5 dup di 4 (senza virgola)
            "Москва, Тверская улица 7",         # 6 russo
            "МОСКВА ТВЕРСКАЯ УЛИЦА 7",          # 7 dup di 6 (maiuscole)
            "Bäckerstraße 12, Wien",            # 8 tedesco (unico)
        ]
        clusters = cluster_duplicates(testi, threshold=0.6)
        as_sets = [set(c) for c in clusters]
        self.assertIn({0, 1}, as_sets)
        self.assertIn({2, 3}, as_sets)
        self.assertIn({4, 5}, as_sets)
        self.assertIn({6, 7}, as_sets)
        for c in as_sets:
            self.assertNotIn(8, c)

    def test_threshold_invalida(self):
        with self.assertRaises(ValueError):
            find_duplicates(["a"], threshold=0.0)


if __name__ == "__main__":
    unittest.main()

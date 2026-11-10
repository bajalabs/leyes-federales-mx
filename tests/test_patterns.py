"""The article grammar in scripts/patterns.py: leads, suffixes, keys, annotations."""
import unittest

from tests import REPO  # noqa: F401  (puts scripts/ on sys.path)
from patterns import (ANNOT_TEXT_RE, ART_ORD_RE, ART_RE, BARE_ORD_RE, DECRETO_RE,
                      DISPOSICIONES_TRANS_RE, SPACED_TRANS_RE, TRANS_RE, article_key,
                      deaccent, display_suffix, suffix_tokens, ultima_reforma_in_text)


def key_of(lead: str) -> str | None:
    m = ART_RE.match(lead)
    return article_key(m.group(1), m.group(2), None, False, "") if m else None


class ArticleLeads(unittest.TestCase):
    def test_suffix_chain(self):
        cases = {
            "Artículo 8 Bis.- texto": "8-bis",
            "Artículo 119 Bis 1.- texto": "119-bis-1",
            "Artículo 77 BIS 35 A.- texto": "77-bis-35-a",
            "Artículo 113-F. Será aplicable": "113-f",
            "Artículo 1298-A. texto": "1298-a",
            "Artículo 58-1. texto": "58-1",
            "Artículo 195-Z-1. texto": "195-z-1",
            "Artículo 26-LL. texto": "26-ll",
            "Artículo 195-Ñ. texto": "195-ñ",
            "Artículo 223-Bis. texto": "223-bis",
            "Artículo 228 a. texto": "228-a",
            "Artículo 228 a bis. texto": "228-a-bis",
            "Artículo 257 Quintus. texto": "257-quintus",
        }
        for lead, key in cases.items():
            with self.subTest(lead=lead):
                self.assertEqual(key_of(lead), key)

    def test_two_levels_of_suffix_stay_distinct(self):
        self.assertNotEqual(key_of("Artículo 195-Z-1. x"), key_of("Artículo 195-Z. x"))

    def test_prose_never_becomes_a_suffix(self):
        self.assertEqual(key_of("Artículo 1o.- Los actos de comercio"), "1")
        self.assertEqual(key_of("Artículo 3o. El Instituto"), "3")
        self.assertEqual(key_of("Artículo 5 a falta de disposición"), "5")

    def test_bare_header_paragraph(self):
        self.assertEqual(key_of("Artículo 10"), "10")

    def test_annotation_is_not_an_article(self):
        self.assertIsNone(ART_RE.match("Artículo reformado DOF 14-08-2001"))


class OrdinalLeads(unittest.TestCase):
    def test_compound_ordinals_are_one_key(self):
        m = ART_ORD_RE.match("ARTÍCULO DÉCIMO PRIMERO.- texto")
        self.assertEqual(article_key(None, m.group(2), m.group(1), True, "03"), "T[03]:decimo-primero")
        m = ART_ORD_RE.match("ARTICULO CUADRAGÉSIMO NOVENO. texto")
        self.assertEqual(article_key(None, m.group(2), m.group(1), True, "03"), "T[03]:cuadragesimo-noveno")

    def test_ordinal_with_bis(self):
        m = ART_ORD_RE.match("Artículo Vigésimo Bis.- texto")
        self.assertEqual(article_key(None, m.group(2), m.group(1), True, "07"), "T[07]:vigesimo-bis")

    def test_decree_body_sub_phase(self):
        self.assertEqual(article_key(None, "", "Primero", True, "04", "d"), "T[04]:d:primero")
        self.assertEqual(article_key(None, "", "Primero", True, "04"), "T[04]:primero")

    def test_bare_ordinal_leads(self):
        for text in ("PRIMERO.- El presente Decreto", "DÉCIMO PRIMERO.- x", "ÚNICO.- x"):
            self.assertTrue(BARE_ORD_RE.match(text), text)
        self.assertIsNone(BARE_ORD_RE.match("Primero que nada"))


class Zones(unittest.TestCase):
    def test_transitorios_headings(self):
        for text in ("TRANSITORIOS", "ARTÍCULOS TRANSITORIOS", "Transitorio"):
            self.assertTrue(TRANS_RE.match(text), text)
        self.assertTrue(SPACED_TRANS_RE.match("T R A N S I T O R I O S"))
        self.assertTrue(DISPOSICIONES_TRANS_RE.match("DISPOSICIONES TRANSITORIAS DE LA LEY"))

    def test_decree_leads(self):
        self.assertTrue(DECRETO_RE.match("DECRETO por el que se reforma el artículo 4o."))
        self.assertTrue(DECRETO_RE.match("DECRETO mediante el cual se adiciona"))
        self.assertIsNone(DECRETO_RE.match("Decretos anteriores"))


class Annotations(unittest.TestCase):
    def test_provenance_lines(self):
        for text in ("Artículo reformado DOF 14-08-2001", "Fracción adicionada DOF 26-03-2019",
                     "Párrafo reformado DOF 10-06-2011, 29-01-2016"):
            self.assertTrue(ANNOT_TEXT_RE.match(text), text)

    def test_numbered_article_with_sic_is_not_an_annotation(self):
        self.assertIsNone(ANNOT_TEXT_RE.match("Artículo 47. El Estado del (sic DOF 05-02-1917) Nayarit"))


class Helpers(unittest.TestCase):
    def test_suffix_helpers(self):
        self.assertEqual(suffix_tokens(" Bis 35 A"), ["bis", "35", "a"])
        self.assertEqual(suffix_tokens("-Z-1"), ["z", "1"])
        self.assertEqual(suffix_tokens(""), [])
        self.assertEqual(display_suffix(" Bis 35 A"), "Bis 35 A")
        self.assertEqual(display_suffix("-Z-1"), "Z-1")
        self.assertIsNone(display_suffix(""))

    def test_deaccent_is_length_preserving(self):
        s = "Ñandú, título, constitución"
        self.assertEqual(deaccent(s), "Nandu, titulo, constitucion")
        self.assertEqual(len(deaccent(s)), len(s))


class LastReform(unittest.TestCase):
    def test_the_edition_states_its_last_reform(self):
        self.assertEqual(ultima_reforma_in_text(["TEXTO VIGENTE", "Últimas reformas publicadas DOF 02-06-2026"]),
                         "DOF 02/06/2026")
        self.assertEqual(ultima_reforma_in_text(["Última reforma publicada DOF 29-12-2025"]), "DOF 29/12/2025")
        self.assertEqual(ultima_reforma_in_text(["Última reforma publicada 14-11-2025"]), "DOF 14/11/2025")
        self.assertIsNone(ultima_reforma_in_text(["TEXTO VIGENTE", "Sin reforma"]))

    def test_only_the_opening_paragraphs_count(self):
        late = ["x"] * 40 + ["Última reforma publicada DOF 01-01-2000"]
        self.assertIsNone(ultima_reforma_in_text(late))


if __name__ == "__main__":
    unittest.main()

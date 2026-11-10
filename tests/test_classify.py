"""Paragraph classification (doc_to_md.classify, pdf_to_md.classify) and the
PDF fallback's furniture stripping and reflow. No textutil or pdftotext needed."""
import unittest

from tests import REPO  # noqa: F401
from doc_to_md import classify as classify_doc
from pdf_to_md import classify as classify_pdf, reflow, strip_furniture

PLAIN = {"size": 10.0, "color": "#000000", "align": "justify"}


class DocClassify(unittest.TestCase):
    def test_article_leads_win_regardless_of_bold(self):
        self.assertEqual(classify_doc("Artículo 27.- La propiedad de las tierras", PLAIN, 0.0, False), "article")
        self.assertEqual(classify_doc("Artículo Primero.- Se expide", PLAIN, 0.0, False), "article_ordinal")

    def test_tables_and_blanks(self):
        self.assertEqual(classify_doc("Artículo 1", PLAIN, 0.0, True), "table")
        self.assertEqual(classify_doc("", PLAIN, 0.0, False), "blank")

    def test_editorial_annotation_by_style(self):
        small_blue = {"size": 8.0, "color": "#0000ff", "align": "right"}
        self.assertEqual(classify_doc("Fe de erratas al párrafo DOF 06-02-1917", small_blue, 0.0, False),
                         "annotation")
        self.assertEqual(classify_doc("Algo editorial", {"size": 8.0, "color": "#000000", "align": "right"}, 0.0,
                                      False), "annotation")

    def test_editorial_annotation_by_text(self):
        self.assertEqual(classify_doc("Artículo reformado DOF 14-08-2001", PLAIN, 0.0, False), "annotation")

    def test_notes_headings_and_body(self):
        self.assertEqual(classify_doc("Las notas de la Cámara", {"color": "#008000"}, 0.0, False), "note")
        centred = {"size": 10.0, "color": "#000000", "align": "center"}
        self.assertEqual(classify_doc("TÍTULO PRIMERO", centred, 1.0, False), "heading")
        self.assertEqual(classify_doc("CAPÍTULO I", centred, 0.0, False), "heading")
        self.assertEqual(classify_doc("De los Derechos Humanos y sus Garantías", centred, 1.0, False), "heading")
        self.assertEqual(classify_doc("Toda persona tiene derecho a la educación.", PLAIN, 0.0, False), "body")

    def test_transitorio_zone_markers(self):
        self.assertEqual(classify_doc("TRANSITORIOS", PLAIN, 1.0, False), "transitorio_heading")
        self.assertEqual(classify_doc("PRIMERO.- El presente Decreto entrará en vigor", PLAIN, 0.0, False),
                         "ordinal_lead")


class PdfFallback(unittest.TestCase):
    PAGE = "\n".join([
        "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
        "Secretaría General",
        "Secretaría de Servicios Parlamentarios",
        "Última Reforma DOF 03-03-2026",
        "",
        "Artículo 1o.- En los Estados Unidos Mexicanos todas las per-",
        "sonas gozarán de los derechos humanos.",
        "",
        "  I. Primera fracción",
        "     que continúa aquí.",
        "",
        "                              12 de 414",
    ])

    def test_strip_furniture_drops_running_headers_and_page_numbers(self):
        lines = strip_furniture(self.PAGE + "\f" + self.PAGE)
        text = "\n".join(lines)
        self.assertNotIn("CÁMARA DE DIPUTADOS", text)
        self.assertNotIn("Servicios Parlamentarios", text)
        self.assertNotIn("12 de 414", text)
        self.assertEqual(text.count("Artículo 1o.-"), 2)

    def test_reflow_joins_wrapped_lines_and_dehyphenates(self):
        paras = [t for t, _ in reflow(strip_furniture(self.PAGE))]
        self.assertEqual(paras[0], "Artículo 1o.- En los Estados Unidos Mexicanos todas las personas "
                                   "gozarán de los derechos humanos.")
        self.assertEqual(paras[1], "I. Primera fracción que continúa aquí.")

    def test_pdf_classify(self):
        self.assertEqual(classify_pdf("Artículo 1o.- En los Estados", 0), "article")
        self.assertEqual(classify_pdf("Artículo reformado DOF 10-06-2011", 0), "annotation")
        self.assertEqual(classify_pdf("TÍTULO PRIMERO", 40), "heading")
        self.assertEqual(classify_pdf("DE LOS DERECHOS", 40), "heading")
        self.assertEqual(classify_pdf("texto normal", 0), "body")


if __name__ == "__main__":
    unittest.main()

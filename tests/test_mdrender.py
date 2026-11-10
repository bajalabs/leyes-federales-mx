"""Markdown rendering (scripts/mdrender.py), including the byte-for-byte
round trip: every committed sample law's .md is exactly what its blocks render to."""
import unittest

from tests import REPO
from blocks_to_md import render_law
from corpus import load_manifest, sample_slugs, select
from mdrender import header_md, heading_level, render_doc_block, render_pdf_block, to_markdown

DATA = REPO / "data"
META = {"url_detalle": "https://example.org/ref/x.htm", "dof_original": "DOF 05/02/1917",
        "ultima_reforma": "DOF 03/03/2026", "estado_vigencia": "vigente",
        "resolved_url": "https://example.org/doc/X.doc", "sha256": "ab" * 32}


class Units(unittest.TestCase):
    def test_heading_levels(self):
        self.assertEqual(heading_level("TÍTULO PRIMERO"), 2)
        self.assertEqual(heading_level("Libro Segundo"), 2)
        self.assertEqual(heading_level("CAPÍTULO I"), 3)
        self.assertEqual(heading_level("Sección Primera"), 4)
        self.assertEqual(heading_level("De las Garantías"), 3)

    def test_doc_blocks(self):
        self.assertEqual(render_doc_block("heading", "TÍTULO PRIMERO", "**TÍTULO PRIMERO**"), "\n## TÍTULO PRIMERO\n")
        self.assertEqual(render_doc_block("annotation", "x", "Párrafo reformado DOF 01-01-2000"),
                         "\n> _Párrafo reformado DOF 01-01-2000_\n")
        self.assertEqual(render_doc_block("note", "x", "Nota aclaratoria"), "\n> **Nota:** Nota aclaratoria\n")
        self.assertEqual(render_doc_block("table", "a", "a"), "| a |")
        self.assertEqual(render_doc_block("body", "a", "texto"), "\ntexto\n")

    def test_pdf_blocks(self):
        self.assertEqual(render_pdf_block("article", "Artículo 1o. Texto"), "\n**Artículo 1o.** Texto\n")
        self.assertEqual(render_pdf_block("heading", "TÍTULO"), "\n### TÍTULO\n")

    def test_header_cites_the_converted_file(self):
        doc = "".join(header_md("Ley X", META, "doc"))
        self.assertIn("sha256 `abababababababab`", doc)
        self.assertIn("Convertido desde el .doc oficial", doc)
        pdf = "".join(header_md("Ley X", META, "pdf"))
        self.assertIn("**PDF** oficial", pdf)

    def test_to_markdown_collapses_blank_runs(self):
        blocks = [{"kind": "heading", "text": "TÍTULO", "md": "TÍTULO"},
                  {"kind": "body", "text": "uno", "md": "uno\ndos"}]
        md = to_markdown("Ley X", None, "doc", blocks)
        self.assertEqual(md, "# Ley X\n\n## TÍTULO\n\nuno  \ndos\n")


class RoundTrip(unittest.TestCase):
    def test_sample_markdown_is_regenerated_byte_for_byte(self):
        laws = select(load_manifest(DATA)["laws"], set(sample_slugs()))
        self.assertEqual(len(laws), len(sample_slugs()))
        for rec in laws:
            with self.subTest(law=rec["slug"]):
                md_path, md_text = render_law(DATA, rec)
                self.assertEqual(md_text, md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

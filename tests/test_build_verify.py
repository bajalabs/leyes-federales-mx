"""Build the database from the committed sample, run the verification gate on
it, and query it the way the README's cookbook does."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests import REPO
from build_db import build, law_tipo, norm_dof, parse_annotation, split_parts
from corpus import sample_slugs
from diff_versions import diff_versions
from export_csv import export
from verify_db import verify

DATA = REPO / "data"


class Extraction(unittest.TestCase):
    def test_parse_annotation(self):
        self.assertEqual(parse_annotation("Artículo reformado DOF 14-08-2001"),
                         ("articulo", "reformado", ["2001-08-14"]))
        self.assertEqual(parse_annotation("Párrafo reformado DOF 10-06-2011, 29-01-2016"),
                         ("parrafo", "reformado", ["2011-06-10", "2016-01-29"]))
        self.assertEqual(parse_annotation("Artículo declarado inválido por sentencia de la SCJN DOF 13-10-2022"),
                         ("articulo", "declarado invalido", ["2022-10-13"]))
        self.assertEqual(parse_annotation("Multa de la fracción compilada por resolución miscelánea fiscal DOF 28-12-2018")[:2],
                         ("fraccion", "compilada"))

    def test_split_parts(self):
        parts = split_parts(["Artículo 1.- x", "I. uno", "a) inciso", "1. numeral", "otro párrafo"])
        self.assertEqual([(k, l) for k, l, _ in parts],
                         [("parrafo", None), ("fraccion", "I"), ("inciso", "a)"), ("numeral", "1."), ("parrafo", None)])

    def test_small_helpers(self):
        self.assertEqual(norm_dof("DOF 02/06/2026"), "2026-06-02")
        self.assertIsNone(norm_dof("Sin reforma"))
        self.assertEqual(law_tipo("CONSTITUCIÓN Política de los Estados Unidos Mexicanos"), "constitucion")
        self.assertEqual(law_tipo("CÓDIGO Civil Federal"), "codigo")
        self.assertEqual(law_tipo("LEY de Comercio Exterior"), "ley")


class SampleDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "sample.sqlite"
        cls.totals = build(DATA, cls.db, set(sample_slugs()), quiet=True)
        cls.con = sqlite3.connect(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()

    def one(self, sql, *args):
        return self.con.execute(sql, args).fetchone()[0]

    def test_every_sample_law_is_built(self):
        self.assertEqual(self.totals["laws"], len(sample_slugs()))
        self.assertEqual(self.totals["skipped"], 0)

    def test_verify_passes(self):
        receipt = verify(DATA, self.db, set(sample_slugs()))
        self.assertEqual(receipt["status"], "PASS", json.dumps(receipt["problems"], ensure_ascii=False))
        self.assertEqual(receipt["checks"]["floors"]["001-cpeum"]["regular_articles"], 136)

    def test_constitution_article_27_with_its_place(self):
        row = self.con.execute("""SELECT label, division_heading FROM v_articles
                                  WHERE law_slug='001-cpeum' AND numero_int=27 AND is_transitorio=0""").fetchone()
        self.assertTrue(row[0].startswith("Artículo 27"))
        self.assertIsNotNone(row[1])

    def test_full_text_search_ignores_accents(self):
        plain = self.one("SELECT count(*) FROM articles_fts WHERE articles_fts MATCH 'importacion'")
        accented = self.one("SELECT count(*) FROM articles_fts WHERE articles_fts MATCH 'importación'")
        self.assertGreater(plain, 0)
        self.assertEqual(plain, accented)

    def test_citations_to_the_constitution_resolve(self):
        n = self.one("""SELECT count(*) FROM cross_references x JOIN laws l ON l.id=x.target_law_id
                        WHERE x.ref_kind='constitution' AND l.slug='001-cpeum' AND x.resolved=1""")
        self.assertGreater(n, 0)

    def test_reform_annotations_are_parsed(self):
        n = self.one("SELECT count(*) FROM v_reformas WHERE law_slug='001-cpeum' AND action LIKE 'reformad%'")
        self.assertGreater(n, 100)

    def test_two_captures_of_the_constitution_are_diffed(self):
        versions = self.one("""SELECT count(*) FROM law_versions v JOIN laws l ON l.id = v.law_id
                               WHERE l.slug = '001-cpeum'""")
        self.assertEqual(versions, 2)
        changes = dict(self.con.execute("""
            SELECT c.change_type, count(*) FROM article_changes c
            JOIN version_diffs d ON d.id = c.version_diff_id JOIN laws l ON l.id = d.law_id
            WHERE l.slug = '001-cpeum' GROUP BY 1""").fetchall())
        self.assertGreater(changes.get("added", 0), 0)
        self.assertNotIn("removed", changes)
        art82 = self.one("""SELECT c.change_type FROM article_changes c
                            JOIN version_diffs d ON d.id = c.version_diff_id JOIN laws l ON l.id = d.law_id
                            WHERE l.slug = '001-cpeum' AND c.article_key = '82'""")
        self.assertEqual(art82, "modified")

    def test_current_version_is_the_latest_capture(self):
        latest = self.one("""SELECT max(v.captured_at) FROM law_versions v JOIN laws l ON l.id = v.law_id
                             WHERE l.slug = '001-cpeum'""")
        self.assertEqual(self.one("SELECT captured_at FROM v_laws WHERE slug = '001-cpeum'"), latest)

    def test_csv_export(self):
        out = Path(self.tmp.name) / "csv"
        rows = export(self.db, out)
        self.assertEqual(rows["laws"], len(sample_slugs()))
        current = self.one("SELECT count(*) FROM articles WHERE law_version_id IN (SELECT law_version_id FROM v_laws)")
        self.assertEqual(rows["articles"], current)   # the export holds the current version of each law
        header = (out / "leyes-federales-mx-laws.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(header.startswith("slug,numero,nombre"))


class Diff(unittest.TestCase):
    def test_added_removed_modified_renumbered(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.executescript((REPO / "db" / "schema.sql").read_text(encoding="utf-8"))
        con.execute("INSERT INTO jurisdictions VALUES('MX','México')")
        con.execute("INSERT INTO corpora(id,jurisdiction,slug,name) VALUES(1,'MX','t','t')")
        con.execute("INSERT INTO laws(id,corpus_id,slug,nombre) VALUES(1,1,'x','Ley X')")
        for v in (1, 2):
            con.execute("""INSERT INTO law_versions(id,law_id,captured_at,source_kind,source_sha256)
                           VALUES(?,1,?,'doc',?)""", (v, f"2026-0{v}-01", f"sha{v}"))
        arts = {1: [("1", "uno"), ("2", "dos"), ("3", "tres"), ("4", "cuatro")],
                2: [("1", "uno"), ("2", "dos cambiado"), ("5", "cuatro"), ("6", "seis")]}
        for v, rows in arts.items():
            for seq, (key, text) in enumerate(rows):
                con.execute("""INSERT INTO articles(law_version_id,law_id,article_key,label,seq,text,text_sha256,char_count)
                               VALUES(?,1,?,?,?,?,?,?)""", (v, key, f"Artículo {key}", seq, text, text, len(text)))
        r = diff_versions(con, 1, 2)
        self.assertEqual((r["unchanged"], r["modified"], r["renumbered"], r["removed"], r["added"]), (1, 1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()

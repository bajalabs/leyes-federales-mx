#!/usr/bin/env python3
"""
Export the current version of every law and article to CSV.

    python3 scripts/export_csv.py [--db build/leyes-federales-mx.sqlite] [--out dist]

Writes <out>/leyes-federales-mx-laws.csv and <out>/leyes-federales-mx-articles.csv:
UTF-8, comma-separated, RFC 4180 quoting (article texts keep their paragraph
breaks inside quoted fields). package_release.py zips the articles file.
"""
from __future__ import annotations
import argparse, csv, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DB_BASENAME, DEFAULT_DB, DEFAULT_DIST  # noqa: E402

LAWS_SQL = """
SELECT slug, numero, nombre, nombre_corto, codigo_archivo, tipo, estado_vigencia,
       dof_original, ultima_reforma, reforma_date, ultima_reforma_indice, url_detalle,
       source_kind, resolved_url, source_sha256, captured_at,
       article_count, division_count, annotation_count, crossref_count
FROM v_laws ORDER BY slug
"""

ARTICLES_SQL = """
SELECT a.law_slug, a.article_key, a.label, a.numero_int, a.suffix, a.is_transitorio, a.decree_group,
       a.division_kind, a.division_heading, a.division_rubric, a.division_path,
       a.last_reform_date, a.char_count, a.text
FROM v_articles a
JOIN v_laws l ON l.law_version_id = a.law_version_id
ORDER BY a.law_slug, a.seq
"""


def export(db: Path, out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    rows = {}
    for name, sql in (("laws", LAWS_SQL), ("articles", ARTICLES_SQL)):
        cur = con.execute(sql)
        path = out / f"{DB_BASENAME}-{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cur.description])
            n = 0
            for r in cur:
                w.writerow(r)
                n += 1
        rows[name] = n
    con.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file (default: %(default)s)")
    ap.add_argument("--out", type=Path, default=DEFAULT_DIST, help="output folder (default: %(default)s)")
    a = ap.parse_args()
    rows = export(a.db, a.out)
    print(", ".join(f"{k}: {v} rows" for k, v in rows.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

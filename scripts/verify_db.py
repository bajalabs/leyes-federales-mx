#!/usr/bin/env python3
"""
The regression gate for a built database: one command, one JSON receipt,
non-zero exit when any check fails.

    python3 scripts/verify_db.py                 # the full corpus
    python3 scripts/verify_db.py --sample        # the CI sample

Checks
  1. referential integrity: PRAGMA foreign_key_check plus an orphan sweep
  2. article identity: no duplicate article_key among regular articles
     (a bounded residue inside transitorio decree zones is reported, not failed:
     Supreme Court invalidation resolutions repeat PRIMERO/SEGUNDO/TERCERO
     under one heading with no decree boundary between them)
  3. tripwire: every standalone "**Artículo N**" header in a law's markdown is
     an article in the database (catches a classifier that silently stops
     recognising a header style)
  4. numbering gaps among regular articles, beyond the known renumberings
  5. reform annotations: at least 99% parsed into an action
  6. full-text index has one row per article
  7. totals: one law per manifest entry, each with at least one version
  8. floors: article counts for laws that once regressed never drop again
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_BUILD, DEFAULT_DATA, DEFAULT_DB, law_dir, load_manifest, parse_only, select  # noqa: E402

STANDALONE_HDR = re.compile(r"^\*\*Art[ií]culo\s+\d+[^\n]*\*\*\s*$", re.M | re.I)

# Laws whose numbering holes are renumberings in the source itself, checked by
# hand against the official .doc: not extraction misses.
KNOWN_GAPS = {"313-oga"}

# Regular-article floors. 316-reg_senado prints article headers as bare
# paragraphs ("Artículo 10") and once lost 93% of its body to a classifier that
# required punctuation; 224-lgsmime closes decree bodies with "DISPOSICIONES
# TRANSITORIAS". CPEUM has 136 articles.
ARTICLE_FLOORS = {"001-cpeum": 136, "224-lgsmime": 115, "316-reg_senado": 300}

MIN_ANNOTATION_PARSE_RATE = 0.99


def verify(data: Path, db: Path, want: set[str] | None = None) -> dict:
    laws = select(load_manifest(data)["laws"], want or set())
    con = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    q = lambda s: con.execute(s).fetchall()
    one = lambda s: con.execute(s).fetchone()[0]
    problems, notes = [], []

    # 1 — referential integrity
    fk = len(q("PRAGMA foreign_key_check"))
    orphans = {
        "articles->law_versions": one("SELECT count(*) FROM articles a LEFT JOIN law_versions v ON v.id=a.law_version_id WHERE v.id IS NULL"),
        "articles->laws": one("SELECT count(*) FROM articles a LEFT JOIN laws l ON l.id=a.law_id WHERE l.id IS NULL"),
        "law_versions->laws": one("SELECT count(*) FROM law_versions v LEFT JOIN laws l ON l.id=v.law_id WHERE l.id IS NULL"),
        "article_parts->articles": one("SELECT count(*) FROM article_parts p LEFT JOIN articles a ON a.id=p.article_id WHERE a.id IS NULL"),
        "annotations->law_versions": one("SELECT count(*) FROM annotations n LEFT JOIN law_versions v ON v.id=n.law_version_id WHERE v.id IS NULL"),
        "cross_references->articles": one("SELECT count(*) FROM cross_references x LEFT JOIN articles a ON a.id=x.article_id WHERE x.article_id IS NOT NULL AND a.id IS NULL"),
        "cross_references->target_laws": one("SELECT count(*) FROM cross_references x LEFT JOIN laws l ON l.id=x.target_law_id WHERE x.target_law_id IS NOT NULL AND l.id IS NULL"),
    }
    if fk or any(orphans.values()):
        problems.append(f"referential integrity: fk_check={fk} orphans={orphans}")

    # 2 — article_key identity
    dup_groups = q("""SELECT l.slug, a.article_key, count(*) c FROM articles a
                      JOIN laws l ON l.id=a.law_id
                      GROUP BY a.law_version_id, a.article_key HAVING c>1 ORDER BY c DESC""")
    dup_regular = [d for d in dup_groups if not d[1].startswith("T[")]
    if dup_regular:
        problems.append(f"duplicate article_keys in regular articles: {dup_regular[:10]}")
    if dup_groups:
        notes.append(f"transitorio-zone duplicate keys (bounded, matched by position when diffing): "
                     f"{len(dup_groups)} groups")

    # 3 — tripwire: standalone headers in the markdown must be articles
    tripwire = []
    # per law, in its current (latest) version
    counts = dict(q("""SELECT v.slug, count(*) FROM articles a JOIN v_laws v ON v.law_version_id=a.law_version_id
                       WHERE a.is_transitorio=0 GROUP BY 1"""))
    for rec in laws:
        md = law_dir(data, rec["slug"]) / f"{rec['codigo_archivo']}.md"
        if not md.exists():
            continue
        headers = len(STANDALONE_HDR.findall(md.read_text(encoding="utf-8", errors="replace")))
        regular = counts.get(rec["slug"], 0)
        if headers > regular + 1:
            tripwire.append({"slug": rec["slug"], "standalone_headers": headers, "regular_articles": regular})
    if tripwire:
        problems.append(f"unclassified standalone article headers: {tripwire[:10]}")

    # 4 — numbering gaps (regular articles)
    gaps = q("""WITH s AS (SELECT a.law_id, a.numero_int FROM articles a
                           JOIN v_laws v ON v.law_version_id=a.law_version_id
                           WHERE a.is_transitorio=0 AND a.numero_int IS NOT NULL)
                SELECT l.slug, count(*) n, max(s.numero_int) mx,
                       max(s.numero_int)-count(*) holes
                FROM s JOIN laws l ON l.id=s.law_id GROUP BY 1
                HAVING holes>5 ORDER BY holes DESC""")
    suspect = [g for g in gaps if g[0] not in KNOWN_GAPS]
    if suspect:
        problems.append(f"numbering gaps beyond the known renumberings: {suspect[:10]}")

    # 5 — annotation parse rate
    n_ann = one("SELECT count(*) FROM annotations")
    n_noaction = one("SELECT count(*) FROM annotations WHERE action IS NULL")
    n_nodates = one("SELECT count(*) FROM annotations WHERE dof_dates IS NULL OR dof_dates='[]'")
    rate = (n_ann - n_noaction) / n_ann if n_ann else 1.0
    if rate < MIN_ANNOTATION_PARSE_RATE:
        problems.append(f"annotation action parse rate {rate:.4f} < {MIN_ANNOTATION_PARSE_RATE}")

    # 6 — FTS parity
    n_fts = one("SELECT count(*) FROM articles_fts")
    n_art = one("SELECT count(*) FROM articles")
    if n_fts != n_art:
        problems.append(f"FTS rows {n_fts} != articles {n_art}")

    # 7 — manifest totals
    n_laws = one("SELECT count(*) FROM laws")
    n_lv = one("SELECT count(*) FROM law_versions")
    if n_laws != len(laws):
        problems.append(f"laws {n_laws} != manifest {len(laws)}")
    unversioned = one("SELECT count(*) FROM laws l WHERE NOT EXISTS (SELECT 1 FROM law_versions v WHERE v.law_id=l.id)")
    if unversioned:
        problems.append(f"{unversioned} laws have no version (no blocks were found for them)")
    if n_lv > n_laws:
        notes.append(f"{n_lv - n_laws} extra versions: this database holds more than one capture of some laws")

    # 8 — floors
    floors = {}
    for slug, floor in ARTICLE_FLOORS.items():
        if any(r["slug"] == slug for r in laws):
            floors[slug] = {"floor": floor, "regular_articles": counts.get(slug, 0)}
            if counts.get(slug, 0) < floor:
                problems.append(f"{slug}: {counts.get(slug, 0)} regular articles < floor {floor}")

    counts_summary = {
        "laws": n_laws, "law_versions": n_lv,
        "laws_by_status": dict(q("SELECT estado_vigencia, count(*) FROM laws GROUP BY 1 ORDER BY 2 DESC")),
        "laws_by_source": dict(q("SELECT source_kind, count(*) FROM law_versions GROUP BY 1 ORDER BY 2 DESC")),
        "divisions": one("SELECT count(*) FROM divisions"),
        "articles": n_art,
        "articles_regular": one("SELECT count(*) FROM articles WHERE is_transitorio=0"),
        "articles_transitorio": one("SELECT count(*) FROM articles WHERE is_transitorio=1"),
        "article_parts": one("SELECT count(*) FROM article_parts"),
        "annotations": n_ann,
        "blocks": one("SELECT count(*) FROM blocks"),
        "cross_references": one("SELECT count(*) FROM cross_references"),
        "cross_references_resolved": one("SELECT count(*) FROM cross_references WHERE resolved=1"),
    }
    con.close()
    return {
        "status": "FAIL" if problems else "PASS",
        "db": str(db),
        "counts": counts_summary,
        "checks": {
            "foreign_key_violations": fk,
            "orphans": orphans,
            "duplicate_key_groups": {"total": len(dup_groups), "regular": len(dup_regular)},
            "standalone_header_tripwire": tripwire,
            "numbering_gaps": [{"law": g[0], "articles": g[1], "max": g[2], "holes": g[3]} for g in gaps],
            "annotation_parse": {"total": n_ann, "no_action": n_noaction, "no_dates": n_nodates,
                                 "action_rate": round(rate, 4)},
            "fts_parity": {"articles": n_art, "fts_rows": n_fts},
            "manifest_totals": {"manifest_laws": len(laws), "laws": n_laws, "law_versions": n_lv},
            "floors": floors,
        },
        "notes": notes,
        "problems": problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file to check (default: %(default)s)")
    ap.add_argument("--only", default="", help="comma-separated slugs or short names the build used")
    ap.add_argument("--sample", action="store_true", help="the build used the CI sample (data/sample.txt)")
    ap.add_argument("--receipt", type=Path, default=DEFAULT_BUILD / "verify.json",
                    help="where to write the JSON receipt (default: %(default)s)")
    a = ap.parse_args()

    if not a.db.exists():
        print(f"no database at {a.db}: run scripts/build_db.py first", file=sys.stderr)
        return 2
    receipt = verify(a.data, a.db, parse_only(a.only, a.sample))
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 1 if receipt["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())

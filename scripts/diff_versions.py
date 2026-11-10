#!/usr/bin/env python3
"""
Change tracking: diff two captured versions of the same law, article by article.

    python3 scripts/diff_versions.py --law 001-cpeum
    python3 scripts/diff_versions.py --from-version 12 --to-version 340

This is why law_versions exists as its own table. A new capture never overwrites
the previous one: it lands as a new version row, and this script computes the
article-level delta between any two of them into version_diffs/article_changes.

Matching strategy, in order:
  1. article_key  ('27', '15-bis', 'T[03]:primero')  -- the normal case
  2. text_sha256  -- catches an article that kept its text but was RENUMBERED
Anything left over is added/removed. Survivors compare by hash first (cheap) and
only fall through to SequenceMatcher when the hashes differ.
"""
from __future__ import annotations
import argparse, difflib, json, sqlite3, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_DB  # noqa: E402


def load(con, version_id: int) -> list[dict]:
    cur = con.execute("SELECT id,article_key,label,seq,text,text_sha256 FROM articles "
                      "WHERE law_version_id=? ORDER BY seq", (version_id,))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur]


def diff_versions(con: sqlite3.Connection, v_from: int, v_to: int, ctx: int = 2,
                  computed_at: str | None = None) -> dict:
    """Diff two versions into version_diffs/article_changes. computed_at defaults to
    now; build_db.py passes the newer capture's timestamp so builds are reproducible."""
    A, B = load(con, v_from), load(con, v_to)
    by_key_a = {a["article_key"]: a for a in A}
    by_key_b = {b["article_key"]: b for b in B}

    pairs, used_a, used_b = [], set(), set()
    for k, a in by_key_a.items():                       # 1. same key
        b = by_key_b.get(k)
        if b:
            pairs.append((a, b)); used_a.add(a["id"]); used_b.add(b["id"])

    rem = [a for a in A if a["id"] not in used_a]
    add = [b for b in B if b["id"] not in used_b]
    by_sha_b: dict[str, list[dict]] = {}
    for b in add:
        by_sha_b.setdefault(b["text_sha256"], []).append(b)
    renamed = []
    for a in list(rem):                                  # 2. same text, new key
        bucket = by_sha_b.get(a["text_sha256"])
        if bucket:
            b = bucket.pop(0)
            renamed.append((a, b)); used_a.add(a["id"]); used_b.add(b["id"])
    rem = [a for a in rem if a["id"] not in used_a]
    add = [b for b in add if b["id"] not in used_b]

    rows, n = [], {"added": 0, "removed": 0, "modified": 0, "unchanged": 0, "renumbered": 0}
    for a, b in pairs:
        if a["text_sha256"] == b["text_sha256"]:
            rows.append((b["article_key"], "unchanged", a["id"], b["id"], 1.0, None)); n["unchanged"] += 1
        else:
            sim = difflib.SequenceMatcher(None, a["text"], b["text"]).ratio()
            ud = "\n".join(difflib.unified_diff(
                a["text"].splitlines(), b["text"].splitlines(),
                fromfile=f"v{v_from}:{a['label']}", tofile=f"v{v_to}:{b['label']}",
                lineterm="", n=ctx))
            rows.append((b["article_key"], "modified", a["id"], b["id"], round(sim, 4), ud)); n["modified"] += 1
    for a, b in renamed:
        rows.append((b["article_key"], "renumbered", a["id"], b["id"], 1.0,
                     f"{a['label']} -> {b['label']}")); n["renumbered"] += 1
    for a in rem:
        rows.append((a["article_key"], "removed", a["id"], None, None, None)); n["removed"] += 1
    for b in add:
        rows.append((b["article_key"], "added", None, b["id"], None, None)); n["added"] += 1

    law_id = con.execute("SELECT law_id FROM law_versions WHERE id=?", (v_to,)).fetchone()[0]
    cur = con.cursor()
    cur.execute("""DELETE FROM article_changes WHERE version_diff_id IN
                   (SELECT id FROM version_diffs WHERE from_version_id=? AND to_version_id=?)""", (v_from, v_to))
    cur.execute("DELETE FROM version_diffs WHERE from_version_id=? AND to_version_id=?", (v_from, v_to))
    cur.execute("""INSERT INTO version_diffs(law_id,from_version_id,to_version_id,computed_at,
                     n_added,n_removed,n_modified,n_unchanged)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (law_id, v_from, v_to, computed_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 n["added"], n["removed"], n["modified"] + n["renumbered"], n["unchanged"]))
    did = cur.lastrowid
    cur.executemany("""INSERT INTO article_changes(version_diff_id,article_key,change_type,
                         from_article_id,to_article_id,similarity,diff) VALUES(?,?,?,?,?,?,?)""",
                    [(did, *r) for r in rows])
    con.commit()
    return {"version_diff_id": did, "from": v_from, "to": v_to, **n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file (default: %(default)s)")
    ap.add_argument("--law", help="law slug; diffs its two newest versions")
    ap.add_argument("--from-version", type=int)
    ap.add_argument("--to-version", type=int)
    a = ap.parse_args()
    con = sqlite3.connect(a.db); con.row_factory = sqlite3.Row
    if a.law:
        vs = [r[0] for r in con.execute(
            "SELECT lv.id FROM law_versions lv JOIN laws l ON l.id=lv.law_id "
            "WHERE l.slug=? ORDER BY lv.captured_at DESC, lv.id DESC LIMIT 2", (a.law,))]
        if len(vs) < 2:
            print(f"{a.law}: only {len(vs)} version(s) captured -- nothing to diff yet.", file=sys.stderr)
            return 2
        a.to_version, a.from_version = vs[0], vs[1]
    if not (a.from_version and a.to_version):
        print("need --law or both --from-version/--to-version", file=sys.stderr); return 2
    print(json.dumps(diff_versions(con, a.from_version, a.to_version), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

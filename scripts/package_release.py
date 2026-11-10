#!/usr/bin/env python3
"""
Package the release assets into dist/ (gitignored); they become the files of a
GitHub Release.

    python3 scripts/package_release.py [--db build/leyes-federales-mx.sqlite] [--dist dist]

Run build_db.py and verify_db.py first. Writes:

    leyes-federales-mx.sqlite.zip         the database (one file inside)
    leyes-federales-mx-blocks.zip         every law's <CODE>.blocks.jsonl, at its path under data/leyes/
    leyes-federales-mx-laws.csv           one row per law
    leyes-federales-mx-articles.csv.zip   one row per article (the CSV inside)
    SHA256SUMS                            `sha256sum -c SHA256SUMS` checks the lot

The archives are deterministic: entries are sorted and stamped with the
capture date from data/manifest.json, so the same inputs give the same bytes.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DB_BASENAME, DEFAULT_DATA, DEFAULT_DB, DEFAULT_DIST, law_dir, load_manifest  # noqa: E402
from export_csv import export  # noqa: E402


def stamp(man: dict) -> tuple[int, int, int, int, int, int]:
    d = man["_meta"]["generated_at"][:10]
    y, m, dd = (int(x) for x in d.split("-"))
    return (y, m, dd, 0, 0, 0)


def zip_files(dest: Path, entries: list[tuple[Path, str]], when) -> None:
    tmp = dest.with_name(dest.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as z:
        for src, arc in sorted(entries, key=lambda e: e[1]):
            info = zipfile.ZipInfo(arc, date_time=when)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with src.open("rb") as fin, z.open(info, "w", force_zip64=True) as fout:
                for chunk in iter(lambda: fin.read(1 << 20), b""):
                    fout.write(chunk)
    tmp.replace(dest)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="built database (default: %(default)s)")
    ap.add_argument("--dist", type=Path, default=DEFAULT_DIST, help="output folder (default: %(default)s)")
    a = ap.parse_args()

    if not a.db.exists():
        print(f"no database at {a.db}: run scripts/build_db.py first", file=sys.stderr)
        return 2
    man = load_manifest(a.data)
    when = stamp(man)
    a.dist.mkdir(parents=True, exist_ok=True)

    db_zip = a.dist / f"{DB_BASENAME}.sqlite.zip"
    zip_files(db_zip, [(a.db, f"{DB_BASENAME}.sqlite")], when)

    blocks = []
    for rec in man["laws"]:
        p = law_dir(a.data, rec["slug"]) / f"{rec['codigo_archivo']}.blocks.jsonl"
        if p.exists():
            blocks.append((p, f"data/leyes/{rec['slug']}/{p.name}"))
    if len(blocks) != len(man["laws"]):
        print(f"warning: blocks found for {len(blocks)} of {len(man['laws'])} laws", file=sys.stderr)
    zip_files(a.dist / f"{DB_BASENAME}-blocks.zip", blocks, when)

    rows = export(a.db, a.dist)
    arts = a.dist / f"{DB_BASENAME}-articles.csv"
    zip_files(a.dist / f"{DB_BASENAME}-articles.csv.zip", [(arts, arts.name)], when)
    arts.unlink()

    assets = sorted([db_zip, a.dist / f"{DB_BASENAME}-blocks.zip",
                     a.dist / f"{DB_BASENAME}-laws.csv", a.dist / f"{DB_BASENAME}-articles.csv.zip"])
    lines = [f"{sha256_of(p)}  {p.name}" for p in assets]
    (a.dist / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"assets": {p.name: p.stat().st_size for p in assets},
                      "blocks_files": len(blocks), "csv_rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

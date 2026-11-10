#!/usr/bin/env python3
"""
Regenerate every law's .md from its stored blocks, so markdown and blocks can
never drift apart after a grammar fix.

    python3 scripts/blocks_to_md.py [--only cpeum,lce] [--dry-run]

Rendering goes through mdrender.py, the same functions doc_to_md.py and
pdf_to_md.py use at conversion time, so regeneration is byte-faithful to each
law's original converter (DOC vs PDF rules, the provenance header). Needs only
Python: no textutil, no network.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_DATA, law_dir, load_manifest, parse_only, select  # noqa: E402
from mdrender import header_meta, to_markdown  # noqa: E402


def render_law(data: Path, rec: dict) -> tuple[Path, str] | None:
    d = law_dir(data, rec["slug"])
    code = rec["codigo_archivo"]
    bl, cj = d / f"{code}.blocks.jsonl", d / "convert.json"
    if not bl.exists() or not cj.exists():
        return None
    conv = json.loads(cj.read_text(encoding="utf-8"))
    kind = conv.get("source_kind") or "doc"
    with bl.open(encoding="utf-8") as f:
        blocks = [json.loads(l) for l in f]
    return d / f"{code}.md", to_markdown(conv.get("title") or code, header_meta(rec, kind), kind, blocks)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--only", default="", help="comma-separated slugs or short names")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    a = ap.parse_args()

    man = load_manifest(a.data)
    n, changed, missing = 0, [], 0
    for rec in select(man["laws"], parse_only(a.only)):
        out = render_law(a.data, rec)
        if out is None:
            missing += 1
            continue
        md_path, md_text = out
        n += 1
        old = md_path.read_text(encoding="utf-8") if md_path.exists() else None
        if old == md_text:
            continue
        changed.append(rec["slug"])
        if not a.dry_run:
            md_path.write_text(md_text, encoding="utf-8")

    print(f"laws rendered: {n} · markdown files changed: {len(changed)} · without blocks: {missing}"
          + ("  (dry run)" if a.dry_run else ""))
    if changed and a.dry_run:
        print("would change:", ", ".join(changed[:20]) + (" …" if len(changed) > 20 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

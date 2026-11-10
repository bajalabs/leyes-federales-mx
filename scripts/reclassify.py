#!/usr/bin/env python3
"""
Replay block classification over the STORED blocks after a grammar fix in
patterns.py: no textutil, no pdftotext, no network.

    python3 scripts/reclassify.py [--only ccf,lisr] [--dry-run]

The blocks are lossless by design (text + style features are stored), so
classification is a pure function of stored data and can be replayed whenever
the grammar improves. Rewrites the kind field in each <CODE>.blocks.jsonl and
the kind counts in convert.json, and prints a per-law before/after report so an
unexpected movement is visible before build_db.py runs. Then regenerate the
markdown with blocks_to_md.py.
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_BUILD, DEFAULT_DATA, law_dir, load_manifest, parse_only, select  # noqa: E402
from doc_to_md import classify as classify_doc   # noqa: E402
from pdf_to_md import classify as classify_pdf   # noqa: E402


def reclassify_block(b: dict) -> str:
    sty = b.get("style") or {}
    if sty.get("src") == "pdf":
        return classify_pdf(b["text"], sty.get("indent") or 0)
    return classify_doc(b["text"], sty, sty.get("bold_ratio") or 0.0, b["kind"] == "table")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--only", default="", help="comma-separated slugs or short names")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    ap.add_argument("--report", type=Path, default=DEFAULT_BUILD / "reclassify-delta.json",
                    help="JSON report path (default: %(default)s)")
    a = ap.parse_args()

    man = load_manifest(a.data)
    report, moved = [], 0
    for rec in select(man["laws"], parse_only(a.only)):
        d = law_dir(a.data, rec["slug"])
        code = rec["codigo_archivo"]
        bl, cj = d / f"{code}.blocks.jsonl", d / "convert.json"
        if not bl.exists() or not cj.exists():
            continue
        with bl.open(encoding="utf-8") as f:
            blocks = [json.loads(l) for l in f]
        before = Counter(b["kind"] for b in blocks)
        changed = 0
        for b in blocks:
            k = reclassify_block(b)
            if k != b["kind"]:
                b["kind"] = k
                changed += 1
        if changed == 0:
            continue
        after = Counter(b["kind"] for b in blocks)
        moved += 1
        delta = {k: after.get(k, 0) - before.get(k, 0) for k in sorted(set(before) | set(after))}
        report.append({"slug": rec["slug"], "changed_blocks": changed,
                       "delta": {k: v for k, v in delta.items() if v},
                       "articles": [before.get("article", 0), after.get("article", 0)]})
        if not a.dry_run:
            with bl.open("w", encoding="utf-8") as f:
                for b in blocks:
                    f.write(json.dumps(b, ensure_ascii=False) + "\n")
            conv = json.loads(cj.read_text(encoding="utf-8"))
            conv["kinds"] = dict(after)
            cj.write_text(json.dumps(conv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"laws with classification changes: {moved}" + ("  (dry run)" if a.dry_run else ""))
    for r in sorted(report, key=lambda r: -(r["articles"][1] - r["articles"][0])):
        a0, a1 = r["articles"]
        arrow = f"articles {a0} -> {a1}" + (f"  ({a1 - a0:+d})" if a1 != a0 else "")
        print(f"  {r['slug']:<30} blocks={r['changed_blocks']:<5} {arrow:<24} {r['delta']}")
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

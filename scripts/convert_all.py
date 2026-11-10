#!/usr/bin/env python3
"""
Batch conversion: every law's official .doc -> <CODE>.md + <CODE>.blocks.jsonl.

    python3 scripts/convert_all.py [--only cpeum,lce] [--skip-existing] [--jobs 4]

Reads the source files fetch.py downloaded to data/leyes/<slug>/source/ and
writes next to them. The DOC path (doc_to_md.py) is primary; a health gate
scores every conversion for mojibake and falls back to the PDF (pdf_to_md.py)
when the Word file cannot be parsed. Needs macOS (`textutil`) for the DOC path
and `pdftotext` (poppler) for the fallback.

Writes each law's convert.json (which edition was used, block counts) and
rebuilds data/conversion-report.json from ALL convert.json files on disk, so a
filtered run never drops the laws it did not touch.
"""
from __future__ import annotations
import argparse, json, re, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_DATA, law_dir, load_manifest, parse_only, select  # noqa: E402
from mdrender import header_meta  # noqa: E402

# textutil silently "succeeds" on Word files it cannot really parse: it dumps the
# raw OLE2 stream decoded as Mac-Roman. Healthy laws score <= 0.15 markers per 1k
# chars; the three broken ones score 1.4-6.1. 1.0 sits in the empty middle.
MOJIBAKE = re.compile(r"[ÃÂ�\x00-\x08\x0e-\x1f]|CI[”]N|·mara|Ûn\b|[˛ˇ°±‡œ–](?=[A-Za-z])")
MOJIBAKE_LIMIT = 1.0


def health(out_dir: Path, code: str) -> float:
    """Mojibake markers per 1000 chars over the first 400 blocks."""
    jl = out_dir / f"{code}.blocks.jsonl"
    if not jl.exists():
        return 999.0
    txt = []
    with jl.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 400:
                break
            txt.append(json.loads(line)["text"])
    t = "\n".join(txt)
    return len(MOJIBAKE.findall(t)) / max(len(t), 1) * 1000


def job(args):
    from doc_to_md import convert as convert_doc
    from pdf_to_md import convert as convert_pdf
    slug, code, src_dir, outdir, meta_doc, meta_pdf = args
    t0 = time.time()
    out, src = Path(outdir), Path(src_dir)
    used, score, err = "doc", None, None
    try:
        r = convert_doc(src / f"{code}.doc", out, code, meta_doc)
        score = health(out, code)
        if score > MOJIBAKE_LIMIT:                      # DOC unreadable -> PDF fallback
            err = f"doc mojibake {score:.2f}/1k > {MOJIBAKE_LIMIT}"
            raise ValueError(err)
    except Exception as e:
        err = err or f"{type(e).__name__}: {e}"
        try:
            r = convert_pdf(src / f"{code}.pdf", out, code, meta_pdf)
            used, score = "pdf", health(out, code)
        except Exception as e2:
            return {"slug": slug, "ok": False, "source_kind": None,
                    "error": f"doc: {err} | pdf: {type(e2).__name__}: {e2}",
                    "trace": traceback.format_exc()[-400:], "secs": round(time.time() - t0, 2)}
    r.update(slug=slug, ok=True, source_kind=used, mojibake_per_1k=round(score, 3),
             fallback_reason=err if used == "pdf" else None, secs=round(time.time() - t0, 2))
    (out / "convert.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return r


def write_report(data: Path, man: dict, failures: list[dict]) -> dict:
    ok = []
    for rec in man["laws"]:
        cj = law_dir(data, rec["slug"]) / "convert.json"
        if cj.exists():
            ok.append(json.loads(cj.read_text(encoding="utf-8")))
    summary = {"total": len(man["laws"]), "ok": len(ok), "failed": len(failures),
               "via_doc": sum(1 for r in ok if r["source_kind"] == "doc"),
               "via_pdf_fallback": sum(1 for r in ok if r["source_kind"] == "pdf"),
               "pdf_fallbacks": [{"slug": r["slug"], "reason": r["fallback_reason"]}
                                 for r in ok if r["source_kind"] == "pdf"],
               "failures": [{"slug": b["slug"], "error": b["error"]} for b in failures],
               "total_blocks": sum(r["blocks"] for r in ok),
               "total_articles": sum(r["kinds"].get("article", 0) for r in ok),
               "total_annotations": sum(r["kinds"].get("annotation", 0) for r in ok)}
    (data / "conversion-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--only", default="", help="comma-separated slugs or short names")
    ap.add_argument("--skip-existing", action="store_true", help="skip laws that already have blocks")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    man = load_manifest(a.data)
    tasks = []
    for rec in select(man["laws"], parse_only(a.only)):
        f = rec["files"].get("doc") or {}
        if f.get("status") not in ("ok", "cached"):
            continue
        code = rec["codigo_archivo"]
        d = law_dir(a.data, rec["slug"])
        if a.skip_existing and (d / f"{code}.blocks.jsonl").exists():
            continue
        if not (d / "source" / f"{code}.doc").exists():
            print(f"  -- {rec['slug']}: source/{code}.doc missing, run fetch.py first", file=sys.stderr)
            continue
        tasks.append((rec["slug"], code, str(d / "source"), str(d),
                      header_meta(rec, "doc"), header_meta(rec, "pdf")))

    print(f"converting {len(tasks)} laws with {a.jobs} workers", flush=True)
    bad, done = [], 0
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for fut in as_completed([ex.submit(job, t) for t in tasks]):
            r = fut.result(); done += 1
            if r["ok"]:
                arts = r["kinds"].get("article", 0) + r["kinds"].get("article_ordinal", 0)
                tag = "" if r["source_kind"] == "doc" else f"  <- PDF FALLBACK ({r['fallback_reason']})"
                print(f"[{done}/{len(tasks)}] {r['slug']:<34} blocks={r['blocks']:<6} arts={arts:<5} {r['secs']}s{tag}",
                      flush=True)
            else:
                bad.append(r)
                print(f"[{done}/{len(tasks)}] {r['slug']:<34} FAILED {r['error']}", flush=True)

    summary = write_report(a.data, man, bad)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("failures", "pdf_fallbacks")}, indent=2))
    if summary["pdf_fallbacks"]:
        print("PDF fallbacks:", json.dumps(summary["pdf_fallbacks"], ensure_ascii=False, indent=2))
    if bad:
        print("FAILURES:", json.dumps(summary["failures"], ensure_ascii=False, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
PDF fallback converter -- used ONLY where the .doc path fails.

DOC is the primary source for this corpus (see the README). But textutil cannot
parse three of the Word files (LIGIE_2022, 25 MB; PEF_2026 and PEF_2025, the
budget decrees): it emits raw OLE2 bytes decoded as Mac-Roman, which shows up as
1.4-6.1 mojibake markers per 1k chars, against at most 0.15 for every healthy
law. For those, this module rebuilds the document from `pdftotext -layout`.

It costs what the DOC/PDF comparison measured: page furniture must be stripped by pattern
(4 running-header lines + page numbers per page) and wrapped lines reflowed back
into paragraphs. That is strictly worse than the .doc path, which is exactly why
it is the fallback and not the default.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

from patterns import (ART_RE, ART_ORD_RE, HEAD_RE, TRANS_RE, SPACED_TRANS_RE,
                      DISPOSICIONES_TRANS_RE, BARE_ORD_RE,
                      ANNOT_TEXT_RE as ANNOT_RE)
from mdrender import header_md, render_pdf_block, with_text_reform

HEADER_PATS = [
    re.compile(r"C[ÁA]MARA DE DIPUTADOS DEL H\. CONGRESO DE LA UNI[ÓO]N", re.I),
    re.compile(r"^\s*Secretar[íi]a General\s*$", re.I),
    re.compile(r"^\s*Secretar[íi]a de Servicios Parlamentarios\s*$", re.I),
    re.compile(r"[ÚU]ltima Reforma DOF", re.I),
    re.compile(r"Nuevo (Presupuesto|Reglamento|C[óo]digo|Ley|Decreto) DOF", re.I),
    re.compile(r"^\s*\d+\s+de\s+\d+\s*$"),
]
PAGENUM = re.compile(r"^\s*\d{1,4}\s*$")
BREAK_RE = re.compile(r"^\s*(Art[íi]culo\s|[IVXLCDM]{1,7}\s*[.\-)]\s|[a-z]\s*\)\s|\d{1,3}\s*[.\-)]\s)")


def pdftotext(pdf: Path) -> str:
    p = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {pdf.name}: {p.stderr.strip()}")
    return p.stdout


def strip_furniture(raw: str) -> list[str]:
    """Drop the per-page running header/footer band, keep the body."""
    out: list[str] = []
    for page in raw.split("\f"):
        lines = page.split("\n")
        # header band: scan only the top 6 lines so a real body line is never eaten
        start = 0
        for i, l in enumerate(lines[:6]):
            if any(p.search(l) for p in HEADER_PATS) or (i < 2 and l.strip() and l.startswith(" " * 30)):
                start = i + 1
        end = len(lines)
        for i in range(len(lines) - 1, max(len(lines) - 4, 0) - 1, -1):
            if PAGENUM.match(lines[i]) or any(p.search(lines[i]) for p in HEADER_PATS):
                end = i
        out.extend(lines[start:end])
        out.append("")           # page boundary is at least a paragraph boundary
    return out


def reflow(lines: list[str]) -> list[tuple[str, int]]:
    """Join wrapped lines back into paragraphs. Returns (text, leading_indent)."""
    paras: list[tuple[str, int]] = []
    buf: list[str] = []
    indent = 0

    def flush():
        nonlocal buf, indent
        if buf:
            t = " ".join(buf)
            t = re.sub(r"(?<=[a-záéíóúñ])-\s+(?=[a-záéíóúñ])", "", t)   # de-hyphenate
            t = re.sub(r"\s{2,}", " ", t).strip()
            if t:
                paras.append((t, indent))
        buf = []

    for l in lines:
        if not l.strip():
            flush(); continue
        lead = len(l) - len(l.lstrip())
        if BREAK_RE.match(l) or HEAD_RE.match(l) or TRANS_RE.match(l):
            flush(); indent = lead
        elif not buf:
            indent = lead
        buf.append(l.strip())
    flush()
    return paras


def classify(text: str, indent: int) -> str:
    if ART_RE.match(text):
        return "article"
    if ART_ORD_RE.match(text):
        return "article_ordinal"
    if TRANS_RE.match(text) or SPACED_TRANS_RE.match(text):
        return "transitorio_heading"
    if DISPOSICIONES_TRANS_RE.match(text) and len(text) < 200:
        return "transitorio_heading"
    if BARE_ORD_RE.match(text):
        return "ordinal_lead"
    if ANNOT_RE.match(text):
        return "annotation"
    if len(text) < 200 and (HEAD_RE.match(text) or (indent >= 25 and text.isupper())):
        return "heading"
    return "body"


def convert(pdf: Path, out_dir: Path, code: str, meta: dict | None = None) -> dict:
    lines = strip_furniture(pdftotext(pdf))
    paras = reflow(lines)
    blocks, md = [], []
    title = (meta or {}).get("nombre") or code
    for i, (t, ind) in enumerate(paras, 1):
        k = classify(t, ind)
        blocks.append({"i": i, "kind": k, "text": t, "md": t,
                       "style": {"cls": None, "size": None, "color": None,
                                 "align": "center" if ind >= 25 else "justify",
                                 "font": None, "bold_ratio": 0.0, "indent": ind, "src": "pdf"}})
        md.append(render_pdf_block(k, t))

    md = header_md(title, with_text_reform(meta, blocks), "pdf") + md
    out_dir.mkdir(parents=True, exist_ok=True)
    md_text = re.sub(r"\n{3,}", "\n\n", "\n".join(md)).strip() + "\n"
    (out_dir / f"{code}.md").write_text(md_text, encoding="utf-8")
    with (out_dir / f"{code}.blocks.jsonl").open("w", encoding="utf-8") as f:
        for b in blocks:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    from collections import Counter
    return {"title": title, "blocks": len(blocks), "kinds": dict(Counter(b["kind"] for b in blocks)),
            "md_chars": len(md_text)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--code", required=True)
    a = ap.parse_args()
    print(json.dumps(convert(Path(a.pdf), Path(a.out), a.code), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

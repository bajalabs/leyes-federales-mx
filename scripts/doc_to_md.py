#!/usr/bin/env python3
"""
Convert a diputados.gob.mx .doc (OLE2 Word) into Markdown + a lossless block JSONL.

Why DOC and not PDF (measured on CPEUM, 414 pp / 136 articles; see the README):
  DOC : 136 article-start paragraphs for 136 articles (1:1, zero false positives)
        0 lines of page furniture, 0 hyphenation, 0 mojibake
  PDF : 207 article-start lines for the same 136 articles (71 false positives from
        line wrapping) and ~2,900 junk tokens from 414 running headers/footers.

The .doc also carries semantics the PDF has thrown away. diputados styles
reform provenance as blue 8px right-aligned text, headings as centred bold, and
article leads as <b>Artículo N</b>. That lets us separate NORMATIVE text from
EDITORIAL annotation mechanically instead of guessing.

Pipeline:  .doc --textutil--> Cocoa HTML --parse--> blocks --emit--> .md + .blocks.jsonl

Requires `textutil`, which ships with macOS. On Linux and Windows use the
stored blocks instead (reclassify.py, blocks_to_md.py, build_db.py), or the PDF
fallback in pdf_to_md.py.
"""
from __future__ import annotations
import argparse, html as H, json, re, subprocess, sys, tempfile
from pathlib import Path

# One pattern vocabulary for the whole pipeline -- see patterns.py. Never
# re-derive these regexes here: private copies are how a suffix-truncation bug
# once survived in two places.
from patterns import (ART_RE, ART_ORD_RE, HEAD_RE, ANNOT_TEXT_RE, TRANS_RE,
                      SPACED_TRANS_RE, DISPOSICIONES_TRANS_RE, BARE_ORD_RE, mark_furniture)
from mdrender import to_markdown

# ── style vocabulary observed in the diputados corpus ────────────────────────
ANNOT_COLORS = {"#0000ff", "#595959", "#181818"}   # reform provenance / editorial
NOTE_COLORS  = {"#008000", "#cc3300"}              # header notes / invalidation warnings


def textutil_html(doc: Path) -> str:
    """.doc -> Cocoa HTML. textutil writes UTF-8 when asked."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.html"
        p = subprocess.run(
            ["textutil", "-convert", "html", "-encoding", "UTF-8", "-output", str(out), str(doc)],
            capture_output=True, text=True,
        )
        if p.returncode != 0 or not out.exists():
            raise RuntimeError(f"textutil failed for {doc.name}: {p.stderr.strip() or p.stdout.strip()}")
        return out.read_text(encoding="utf-8", errors="replace")


def parse_css(html: str) -> dict[str, dict]:
    out = {}
    for cls, body in re.findall(r"p\.(p\d+)\s*\{([^}]*)\}", html):
        m_size = re.search(r"font:\s*([\d.]+)px", body)
        m_col = re.search(r"color:\s*(#[0-9a-fA-F]{6})", body)
        m_al = re.search(r"text-align:\s*(\w+)", body)
        m_fnt = re.search(r"font:\s*[\d.]+px\s+([^;}]+)", body)
        out[cls] = {
            "size": float(m_size.group(1)) if m_size else None,
            "color": (m_col.group(1).lower() if m_col else None),
            "align": (m_al.group(1) if m_al else "default"),
            "font": (m_fnt.group(1).strip().strip("'") if m_fnt else None),
        }
    return out


# Word .doc payloads carry NUL/control bytes (notably in the <title>).
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _inline_to_md(frag: str) -> str:
    """Keep bold/italic/underline as markdown; drop the rest."""
    s = frag
    s = re.sub(r"<\s*b\s*>(.*?)<\s*/\s*b\s*>", lambda m: _wrap(m.group(1), "**"), s, flags=re.S | re.I)
    s = re.sub(r"<\s*i\s*>(.*?)<\s*/\s*i\s*>", lambda m: _wrap(m.group(1), "_"), s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = CTRL_RE.sub("", H.unescape(s).replace(" ", " "))
    return re.sub(r"[ \t]+", " ", s).strip()


def _wrap(inner: str, mark: str) -> str:
    txt = re.sub(r"<[^>]+>", "", inner)
    txt = CTRL_RE.sub("", H.unescape(txt).replace(" ", " "))
    core = txt.strip()
    if not core:
        return txt
    lead = txt[: len(txt) - len(txt.lstrip())]
    trail = txt[len(txt.rstrip()):]
    return f"{lead}{mark}{core}{mark}{trail}"


def _plain(frag: str) -> str:
    s = re.sub(r"<[^>]+>", "", frag)
    s = CTRL_RE.sub("", H.unescape(s).replace(" ", " "))
    return re.sub(r"[ \t]+", " ", s).strip()


def bold_ratio(frag: str) -> float:
    total = len(_plain(frag))
    if not total:
        return 0.0
    bold = sum(len(_plain(m)) for m in re.findall(r"<\s*b\s*>(.*?)<\s*/\s*b\s*>", frag, re.S | re.I))
    return bold / total


def classify(text: str, sty: dict, br: float, in_table: bool) -> str:
    """Order matters. Article leads are decided FIRST and on paragraph position,
    not on bold: the source .doc is inconsistent about bolding the lead (10 of
    CPEUM's 136 articles are not bold), but paragraph boundaries are reliable, so
    a mid-sentence cross-reference can never open a paragraph."""
    if in_table:
        return "table"
    if not text:
        return "blank"
    col, align, size = sty.get("color"), sty.get("align"), sty.get("size") or 10.0

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

    small_editorial = size <= 9.0 and (col in ANNOT_COLORS or align == "right")
    if small_editorial or ANNOT_TEXT_RE.match(text):
        return "annotation"
    if col in NOTE_COLORS:
        return "note"
    if align == "center" and br > 0.5 and len(text) < 200:
        return "heading"
    if HEAD_RE.match(text) and len(text) < 200 and (align == "center" or br > 0.5):
        return "heading"
    return "body"


def convert(doc: Path, out_dir: Path, code: str, meta: dict | None = None) -> dict:
    html = textutil_html(doc)
    css = parse_css(html)
    title = _plain(re.search(r"<title>(.*?)</title>", html, re.S).group(1)) if re.search(r"<title>(.*?)</title>", html, re.S) else code

    # mark table regions so their paragraphs get flagged
    table_spans = [(m.start(), m.end()) for m in re.finditer(r"<table.*?</table>", html, re.S | re.I)]

    def in_table(pos: int) -> bool:
        return any(a <= pos < b for a, b in table_spans)

    blocks = []

    idx = 0
    for m in re.finditer(r'<p class="(p\d+)"[^>]*>(.*?)</p>', html, re.S):
        cls, body = m.group(1), m.group(2)
        sty = css.get(cls, {})
        tbl = in_table(m.start())
        # split soft line breaks into logical lines but keep them in one block
        segs = re.split(r"<br\s*/?>", body, flags=re.I)
        lines_md = [_inline_to_md(s) for s in segs]
        lines_tx = [_plain(s) for s in segs]
        text = "\n".join(l for l in lines_tx if l).strip()
        if not text:
            continue
        br = bold_ratio(body)
        kind = classify(text, sty, br, tbl)
        idx += 1
        style = {"cls": cls, **sty, "bold_ratio": round(br, 3)}
        if tbl:
            style["in_table"] = True       # kept so a replay can reclassify without the HTML
        blocks.append({
            "i": idx, "kind": kind, "text": text,
            "md": "\n".join(l for l in lines_md if l),
            "style": style,
        })

    # the Word file's headers and footers, emitted after the body
    mark_furniture(blocks)
    # markdown emission goes through mdrender, the same path blocks_to_md.py uses
    out_dir.mkdir(parents=True, exist_ok=True)
    md_text = to_markdown(title, meta, "doc", blocks)
    (out_dir / f"{code}.md").write_text(md_text, encoding="utf-8")
    with (out_dir / f"{code}.blocks.jsonl").open("w", encoding="utf-8") as f:
        for b in blocks:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")

    from collections import Counter
    return {"title": title, "blocks": len(blocks), "kinds": dict(Counter(b["kind"] for b in blocks)),
            "md_chars": len(md_text)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--code", required=True)
    a = ap.parse_args()
    print(json.dumps(convert(Path(a.doc), Path(a.out), a.code), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Markdown rendering for the pipeline — the one place that knows how
blocks become a .md file.

doc_to_md.py uses it at conversion time; blocks_to_md.py uses it to regenerate
every committed .md from the stored blocks after a classifier fix. Same code
path both times, so the two can never drift.

Rendering is source-kind specific on purpose: the DOC and PDF converters emit
slightly different markdown (heading levels, article bolding, the header's
closing line), and regeneration must stay byte-faithful to what each law's
original conversion produced.
"""
from __future__ import annotations
import re

from patterns import ultima_reforma_in_text

HEAD_LEVEL = {"libro": 2, "titulo": 2, "capitulo": 3, "seccion": 4, "apartado": 4}


def _bare(md_text: str) -> str:
    """Drop inline emphasis markers -- a heading is already emphasised by its #."""
    return re.sub(r"\*\*|__|(?<!\w)_|_(?!\w)", "", md_text).strip()


def heading_level(text: str) -> int:
    t = (text.replace("Í", "I").replace("í", "i").replace("Ó", "O").replace("ó", "o")
             .replace("Á", "A").replace("á", "a").lower().strip("*_ "))
    for key, lvl in HEAD_LEVEL.items():
        if t.startswith(key):
            return lvl
    return 3


def header_meta(rec: dict, source_kind: str) -> dict:
    """The provenance a law's header cites, from its manifest record: the
    official detail page, the DOF dates, and the URL + sha256 of the file the
    text was converted from."""
    f = (rec.get("files") or {}).get(source_kind) or {}
    return {"url_detalle": rec.get("url_detalle"), "dof_original": rec.get("dof_original"),
            "ultima_reforma": rec.get("ultima_reforma"), "estado_vigencia": rec.get("estado_vigencia"),
            "resolved_url": f.get("resolved_url"), "sha256": f.get("sha256"),
            "nombre": rec.get("nombre")}


def header_md(title: str, meta: dict | None, source_kind: str) -> list[str]:
    """The title + provenance blockquote at the top of every law's .md.

    meta mirrors what convert_all.py builds: url_detalle/dof_original/
    ultima_reforma/estado_vigencia plus the resolved_url + sha256 of the source
    file the text was converted from (the .doc, or the .pdf for a fallback law).
    Callers pass meta through with_text_reform() first.
    """
    md = [f"# {title}\n"]
    if meta:
        sha = (meta.get("sha256") or "")[:16]
        closer = ("> _Convertido desde el .doc oficial (Word) por leyes-federales-mx._\n"
                  if source_kind != "pdf" else
                  "> _Convertido desde el **PDF** oficial (fallback: el .doc de esta ley no es legible)._\n")
        md.append(
            "> **Fuente:** [{det}]({det})  \n"
            "> **DOF original:** {dofo} · **Última reforma:** {ref} · **Vigencia:** {vig}  \n"
            "> **Origen:** `{url}` · sha256 `{sha}`  \n".format(
                det=meta.get("url_detalle"), dofo=meta.get("dof_original"),
                ref=meta.get("ultima_reforma"), vig=meta.get("estado_vigencia"),
                url=meta.get("resolved_url"), sha=sha) + closer)
    return md


def render_doc_block(kind: str, text: str, rendered: str) -> str:
    """One block -> markdown fragment, DOC-path rules (doc_to_md.py)."""
    if kind == "heading":
        return f"\n{'#' * heading_level(text)} {_bare(rendered)}\n"
    if kind == "transitorio_heading":
        return f"\n## {_bare(rendered)}\n"
    if kind == "annotation":
        return f"\n> _{_bare(rendered)}_\n"
    if kind == "note":
        return f"\n> **Nota:** {_bare(rendered)}\n"
    if kind == "article_ordinal":
        return f"\n{rendered}\n"
    if kind == "table":
        return f"| {rendered} |"
    return f"\n{rendered}\n"


def render_pdf_block(kind: str, text: str) -> str:
    """One block -> markdown fragment, PDF-path rules (pdf_to_md.py)."""
    if kind == "heading":
        return f"\n### {text}\n"
    if kind == "transitorio_heading":
        return f"\n## {text}\n"
    if kind == "annotation":
        return f"\n> _{text}_\n"
    if kind == "article":
        return f"\n**{text.split('.')[0]}.**{text.split('.', 1)[1] if '.' in text else ''}\n"
    return f"\n{text}\n"


def with_text_reform(meta: dict | None, blocks: list[dict]) -> dict | None:
    """The header's "Última reforma" is the date the edition itself prints when
    it prints one; the Cámara's index value (manifest.json) otherwise."""
    if not meta:
        return meta
    found = ultima_reforma_in_text(b["text"] for b in blocks)
    return {**meta, "ultima_reforma": found} if found else meta


def to_markdown(title: str, meta: dict | None, source_kind: str, blocks: list[dict]) -> str:
    md = header_md(title, with_text_reform(meta, blocks), source_kind)
    for b in blocks:
        if (b.get("style") or {}).get("src") == "pdf":
            md.append(render_pdf_block(b["kind"], b["text"]))
        else:
            # The stored "md" field joins soft line breaks with "\n"; emission
            # renders them as markdown hard breaks ("  \n") — same as
            # doc_to_md.py does at conversion time.
            rendered = "  \n".join((b.get("md") or b["text"]).split("\n"))
            md.append(render_doc_block(b["kind"], b["text"], rendered))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(md)).strip() + "\n"

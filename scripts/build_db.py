#!/usr/bin/env python3
"""
Build the SQLite database from the stored blocks: laws, versions, divisions,
articles, article parts, reform annotations, the citation graph and full-text
search.

    python3 scripts/build_db.py                    # all laws with blocks on disk
    python3 scripts/build_db.py --sample           # the committed CI sample (6 laws)
    python3 scripts/build_db.py --only cpeum,lce --db /tmp/two.sqlite

Input : data/manifest.json + data/leyes/<slug>/<CODE>.blocks.jsonl
Output: build/leyes-federales-mx.sqlite (override with --db or LEYES_DB)

Every capture of a law becomes a law_version: the current one from the law's
folder, earlier ones from history/<date>/ (see fetch.py --recapture), and
consecutive captures are diffed into version_diffs/article_changes. Writes a
fresh file (the schema is not migrated in place); the full corpus builds in
about 20 seconds. With --append it adds versions to an existing
database instead, which is how two captures of a law end up side by side for
diff_versions.py (see CONTRIBUTING.md). The extractor is a single forward pass over
the block stream. It works because the converters already classified every
paragraph; this stage only maintains the division stack and decides what each
block attaches to.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sqlite3, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_DATA, DEFAULT_DB, SCHEMA, law_dir, load_manifest, parse_only, select  # noqa: E402
from diff_versions import diff_versions  # noqa: E402
# One pattern vocabulary for the whole pipeline -- see patterns.py.
from patterns import (ART_RE, ART_ORD_RE, DIV_RE, FRAC_RE, INC_RE, NUM_RE,  # noqa: E402
                      DOF_DATE, ACTION_RE, TARGET_RE, MULTA_TARGET_RE, DIV_KIND,
                      DEPTH, SUFFIX_SEG, DECRETO_RE, DISPOSICIONES_TRANS_RE,
                      BARE_ORD_RE, article_key, deaccent, display_suffix,
                      ultima_reforma_in_text)

CONVERTER = "leyes-federales-mx 1.0.0 (doc_to_md + build_db + patterns)"


def sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def norm_dof(raw: str | None) -> str | None:
    """'DOF 02/06/2026' -> '2026-06-02'."""
    if not raw:
        return None
    m = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", raw)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def law_tipo(nombre: str) -> str:
    n = deaccent(nombre.lower())
    for pat, t in (("constitucion", "constitucion"), ("codigo", "codigo"), ("reglamento", "reglamento"),
                   ("estatuto", "estatuto"), ("decreto", "decreto"), ("ley", "ley")):
        if n.startswith(pat) or f" {pat} " in n[:40]:
            return t
    return "otro"


def split_parts(paras: list[str]) -> list[tuple[str, str | None, str]]:
    """Classify each paragraph of an article body as párrafo / fracción / inciso / numeral."""
    out = []
    for p in paras:
        m = FRAC_RE.match(p)
        if m and len(m.group(1)) <= 9:
            out.append(("fraccion", m.group(1), p)); continue
        m = INC_RE.match(p)
        if m:
            out.append(("inciso", m.group(1) + ")", p)); continue
        m = NUM_RE.match(p)
        if m:
            out.append(("numeral", m.group(1) + ".", p)); continue
        out.append(("parrafo", None, p))
    return out


def parse_annotation(text: str) -> tuple[str | None, str | None, list[str]]:
    tm = TARGET_RE.match(text) or MULTA_TARGET_RE.match(text)
    am = ACTION_RE.search(text)
    dates = [f"{y}-{mo}-{d}" for d, mo, y in DOF_DATE.findall(text)]
    target = deaccent(tm.group(1).lower()).rstrip("s") if tm else None
    action = deaccent(am.group(1).lower()) if am else None
    if action:
        # collapse whitespace inside multi-word actions ("declarado invalido")
        action = re.sub(r"\s+", " ", action)
    return target, action, dates


# ── citation graph (cross_references) ────────────────────────────────────────
# Statutory text is a web of references; these patterns extract the edges.
# Matching runs on a deaccented, lower-cased COPY of each article body —
# deaccent() and lower() are length-preserving, so span indices map 1:1 back
# to the original text for the verbatim quote.

_SELF_NOUNS = r"ley|c[oó]digo|reglamento|estatuto|ordenamiento|legislaci[oó]n|decreto"

# "artículo 27 de esta Ley" · "artículos 5o. y 6o. del presente Código" (the
# number + suffix variant; suffix uses the SAME grammar as article leads).
XREF_SELF_NUM = re.compile(
    r"art[ií]culos?\s+(\d{1,4})(?:o\.|º|°)?"
    r"((?:" + SUFFIX_SEG + r")*)"
    r"\s+(?:de\s+(?:esta|este|la\s+presente|el\s+presente)\s+(?:" + _SELF_NOUNS + r"))",
    re.I)

# "artículo 27 constitucional" · "artículo 27 de la Constitución" — from any
# law other than CPEUM these point at the Constitution's article.
XREF_CONST_NUM = re.compile(
    r"art[ií]culos?\s+(\d{1,4})(?:o\.|º|°)?"
    r"((?:" + SUFFIX_SEG + r")*)"
    r"\s+(?:constitucional(?:es)?|de\s+la\s+(?:presente\s+)?constituci[oó]n)",
    re.I)

# law-level constitution mentions (no article number).
XREF_CONST_LAW = re.compile(r"\b(?:la|esta|nuestra)\s+constituci[oó]n\b", re.I)

CPEUM_SLUG = "001-cpeum"


class CitationExtractor:
    """Extracts statutory cross-references from one law's articles.

    law_catalog: list of (law_id, slug, normalised nombre) for every law in the
    build — made once, reused for every law. The source law's own name is
    excluded from its mentions (self-name quotes are noise, not edges).
    """

    def __init__(self, law_catalog: list[tuple[int, str, str]]):
        self.by_slug = {slug: (lid, norm) for lid, slug, norm in law_catalog}
        self.catalog = law_catalog
        # longest-first alternation so "Ley Federal del Trabajo" wins over "Ley Federal"
        names = sorted((norm for _, _, norm in law_catalog if norm), key=len, reverse=True)
        self.name_re = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)") if names else None

    def for_law(self, law_id: int, slug: str, articles: list[dict],
                keys: set[str], numeros: dict[int, str]) -> list[dict]:
        """articles: extractor article dicts; keys: article_key set of this law;
        numeros: numero_int -> article_key (first non-transitorio occurrence)."""
        out: list[dict] = []
        own_norm = next((norm for lid, s, norm in self.catalog if s == slug), None)
        cpeum = self.by_slug.get(CPEUM_SLUG)

        def key_for(numero: int, suffix: str) -> tuple[str | None, bool]:
            k = article_key(str(numero), suffix, None, False, "")
            if k in keys:
                return k, True
            return numeros.get(numero), numeros.get(numero) is not None

        for a in articles:
            text = a["text"]
            norm = deaccent(text.lower())
            seen: set[tuple] = set()

            def add(start: int, end: int, kind: str, target_law, target_key, resolved):
                key = (start, end, kind)
                if key in seen:
                    return
                seen.add(key)
                out.append({"article": a["idx"], "seq": len(out), "quote": text[start:end],
                            "ref_kind": kind, "target_law_id": target_law,
                            "target_article_key": target_key, "resolved": int(resolved)})

            for m in XREF_SELF_NUM.finditer(norm):
                numero = int(m.group(1))
                tk, ok = key_for(numero, m.group(2) or "")
                add(m.start(), m.end(), "self-article", law_id, tk, ok)

            if slug != CPEUM_SLUG and cpeum:
                for m in XREF_CONST_NUM.finditer(norm):
                    tk = str(int(m.group(1)))
                    add(m.start(), m.end(), "constitution", cpeum[0], tk, True)
                for m in XREF_CONST_LAW.finditer(norm):
                    add(m.start(), m.end(), "constitution", cpeum[0], None, True)

            if self.name_re:
                for m in self.name_re.finditer(norm):
                    name = m.group(1)
                    if name == own_norm:
                        continue
                    target = next(((lid, s) for lid, s, norm2 in self.catalog if norm2 == name), None)
                    if target and target[1] != slug:
                        add(m.start(), m.end(), "law", target[0], None, True)
        return out


class Extractor:
    """Forward pass over the classified block stream."""

    def __init__(self):
        self.divisions: list[dict] = []
        self.articles: list[dict] = []
        self.annotations: list[dict] = []
        self.stack: list[dict] = []          # open division tree
        self.cur_art: dict | None = None
        self.in_transitorio = False
        self.decree_group = ""
        self.trans_n = 0
        self._decree_pending = False         # a DECRETO lead already opened the next group
        self._decree_body = False            # inside the decree's normative articles
                                             # (between the DECRETO lead and its TRANSITORIOS)
        self._pending_div: dict | None = None  # a division awaiting its rubric line

    def _close_article(self):
        if self.cur_art:
            body = [p for p in self.cur_art["paras"] if p]
            self.cur_art["text"] = "\n\n".join(body)
            self.articles.append(self.cur_art)
            self.cur_art = None

    def _push_division(self, heading: str, seq: int):
        m = DIV_RE.match(heading)
        if m:
            kind = DIV_KIND.get(deaccent(m.group(1).lower()), "otro")
            ordinal = m.group(2).strip() or None
        else:
            kind, ordinal = "otro", None
        depth = DEPTH[kind]
        while self.stack and DEPTH[self.stack[-1]["kind"]] >= depth:
            self.stack.pop()
        d = {"idx": len(self.divisions), "parent": self.stack[-1]["idx"] if self.stack else None,
             "kind": kind, "ordinal_label": ordinal, "heading": heading, "rubric": None,
             "depth": depth, "seq": seq,
             "path": "/".join(re.sub(r"[^a-z0-9]+", "-", deaccent(x["heading"].lower())).strip("-")
                              for x in self.stack + [{"heading": heading}])}
        self.divisions.append(d)
        self.stack.append(d)
        self._pending_div = d if kind != "otro" else None

    def feed(self, b: dict):
        kind, text, seq = b["kind"], b["text"], b["i"]

        if kind == "heading":
            # "DISPOSICIONES TRANSITORIAS…" ends a decree's normative body.
            if self.in_transitorio and DISPOSICIONES_TRANS_RE.match(text):
                self._decree_body = False
            # A bare rubric line right after "Capítulo I" names that division.
            if self._pending_div is not None and not DIV_RE.match(text) and self._pending_div["rubric"] is None:
                self._pending_div["rubric"] = text
                self._pending_div = None
                return
            self._close_article()
            self._push_division(text, seq)
            return

        if kind == "transitorio_heading":
            self._close_article()
            self.in_transitorio = True
            if self._decree_pending:
                # the DECRETO lead already opened this group -- don't double-count
                self._decree_pending = False
            else:
                self.trans_n += 1
                self.decree_group = f"{self.trans_n:02d}"
            self._decree_body = False
            self.stack.clear()
            self._pending_div = None
            return

        if kind in ("article", "article_ordinal") or (kind == "ordinal_lead" and self.in_transitorio):
            self._close_article()
            numero = suffix = ordinal = None
            if kind == "article":
                m = ART_RE.match(text)
                numero, suffix = m.group(1), (m.group(2) or "")
            elif kind == "article_ordinal":
                m = ART_ORD_RE.match(text)
                ordinal, suffix = m.group(1), (m.group(2) or "")
            else:  # ordinal_lead: bare "PRIMERO.- …" inside a TRANSITORIOS zone
                ordinal = BARE_ORD_RE.match(text).group(1)
            label = re.split(r"(?<=[.\-:])\s", text, maxsplit=1)[0][:80].strip()
            self.cur_art = {
                "idx": len(self.articles), "division": self.stack[-1]["idx"] if self.stack else None,
                "article_key": article_key(numero, suffix, ordinal, self.in_transitorio,
                                           self.decree_group, "d" if self._decree_body else ""),
                "numero_int": int(numero) if numero else None,
                "suffix": display_suffix(suffix), "label": label, "seq": seq,
                # An ordinal label ("Artículo Primero") does NOT by itself mean
                # transitorio -- several pre-1970 laws number their whole body that
                # way. Only an actual TRANSITORIOS heading flips this.
                "is_transitorio": int(self.in_transitorio),
                "decree_group": self.decree_group or None, "paras": [text], "text": "",
            }
            self._pending_div = None
            return

        if kind == "annotation":
            target, action, dates = parse_annotation(text)
            self.annotations.append({
                "seq": seq, "article": self.cur_art["idx"] if self.cur_art else None,
                "division": None if self.cur_art else (self.stack[-1]["idx"] if self.stack else None),
                "target_kind": target, "action": action, "dof_dates": json.dumps(dates), "text": text})
            return

        if kind in ("body", "table", "ordinal_lead"):
            # ordinal_lead outside a TRANSITORIOS zone is an enumeration paragraph
            # and joins the surrounding body text.
            self._pending_div = None
            # A reform decree printed inside the TRANSITORIOS zone ("DECRETO por
            # el que se reforma…") opens a new decree group: its own transitorios
            # follow. Without this, two decrees' "Artículo Primero" collide in
            # one group (the consolidated .doc merges them under one heading).
            if kind == "body" and self.in_transitorio and DECRETO_RE.match(text):
                self._close_article()
                self.trans_n += 1
                self.decree_group = f"{self.trans_n:02d}"
                self._decree_pending = True
                self._decree_body = True
                return
            if self.cur_art:
                self.cur_art["paras"].append(text)
            return
        # 'note' / 'blank' are preamble furniture -- intentionally dropped.

    def finish(self):
        self._close_article()
        return self


def upsert_law(con: sqlite3.Connection, corpus_id: int, rec: dict) -> int:
    """Stable-identity pass: every law row exists before any article is loaded,
    so cross-law citations can resolve regardless of ingest order."""
    cur = con.cursor()
    cur.execute("""INSERT INTO laws(corpus_id,slug,numero,nombre,nombre_corto,codigo_archivo,tipo,
                                    estado_vigencia,dof_original,url_detalle)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(corpus_id,slug) DO UPDATE SET
                     nombre=excluded.nombre, estado_vigencia=excluded.estado_vigencia,
                     url_detalle=excluded.url_detalle""",
                (corpus_id, rec["slug"], rec["numero"], rec["nombre"], rec["nombre_corto"],
                 rec["codigo_archivo"], law_tipo(rec["nombre"]), rec["estado_vigencia"],
                 rec.get("dof_original"), rec.get("url_detalle")))
    return cur.execute("SELECT id FROM laws WHERE corpus_id=? AND slug=?",
                       (corpus_id, rec["slug"])).fetchone()[0]


def ingest_law(con: sqlite3.Connection, law_id: int, rec: dict, data: Path, source_kind: str,
               extractor: CitationExtractor,
               force_kind: str | None = None, md_dir: Path | None = None) -> dict | None:
    code = rec["codigo_archivo"]
    mdir = md_dir or law_dir(data, rec["slug"])
    # convert.json records which edition actually produced the blocks -- the
    # quality gate falls back to PDF for laws whose .doc textutil cannot parse.
    cj = mdir / "convert.json"
    if force_kind:
        source_kind = force_kind
    elif cj.exists():
        source_kind = json.loads(cj.read_text(encoding="utf-8")).get("source_kind", source_kind)
    f = rec["files"].get(source_kind) or {}
    if f.get("status") not in ("ok", "cached"):
        return None
    bl = mdir / f"{code}.blocks.jsonl"
    if not bl.exists():
        return None
    with bl.open(encoding="utf-8") as fh:
        blocks = [json.loads(l) for l in fh]

    cur = con.cursor()
    full_text = "\n".join(b["text"] for b in blocks)
    # the edition's own "Última reforma publicada DOF …" wins over the index value
    ultima = ultima_reforma_in_text(b["text"] for b in blocks) or rec.get("ultima_reforma")
    cur.execute("""INSERT OR IGNORE INTO law_versions(law_id,captured_at,ultima_reforma,reforma_date,
                     ultima_reforma_indice,source_kind,resolved_url,source_sha256,source_bytes,
                     converter,text_sha256)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (law_id, rec.get("fetched_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 ultima, norm_dof(ultima), rec.get("ultima_reforma"), source_kind,
                 f.get("resolved_url"), f.get("sha256"), f.get("bytes"), CONVERTER, sha(full_text)))
    lv = cur.execute("""SELECT id FROM law_versions WHERE law_id=? AND source_kind=? AND source_sha256=?""",
                     (law_id, source_kind, f.get("sha256"))).fetchone()[0]
    # idempotent re-ingest
    for t in ("cross_references", "blocks", "annotations", "articles", "divisions"):
        cur.execute(f"DELETE FROM {t} WHERE law_version_id=?", (lv,))

    cur.executemany("INSERT INTO blocks(law_version_id,seq,kind,text,style) VALUES(?,?,?,?,?)",
                    [(lv, b["i"], b["kind"], b["text"], json.dumps(b.get("style"), ensure_ascii=False)) for b in blocks])

    ex = Extractor()
    for b in blocks:
        ex.feed(b)
    ex.finish()

    div_ids: dict[int, int] = {}
    for d in ex.divisions:
        cur.execute("""INSERT INTO divisions(law_version_id,parent_id,kind,ordinal_label,heading,rubric,depth,seq,path)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (lv, div_ids.get(d["parent"]), d["kind"], d["ordinal_label"], d["heading"],
                     d["rubric"], d["depth"], d["seq"], d["path"]))
        div_ids[d["idx"]] = cur.lastrowid

    # latest parsed DOF date per article (annotations feed it) -> last_reform_date
    reform: dict[int, str] = {}
    for an in ex.annotations:
        if an["article"] is None:
            continue
        dates = json.loads(an["dof_dates"])
        if dates and max(dates) > reform.get(an["article"], ""):
            reform[an["article"]] = max(dates)

    art_ids: dict[int, int] = {}
    for a in ex.articles:
        cur.execute("""INSERT INTO articles(law_version_id,law_id,division_id,article_key,numero_int,suffix,
                         label,seq,is_transitorio,decree_group,text,text_sha256,char_count,last_reform_date)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (lv, law_id, div_ids.get(a["division"]), a["article_key"], a["numero_int"], a["suffix"],
                     a["label"], a["seq"], a["is_transitorio"], a["decree_group"],
                     a["text"], sha(a["text"]), len(a["text"]), reform.get(a["idx"])))
        aid = cur.lastrowid
        art_ids[a["idx"]] = aid
        parts = split_parts(a["paras"])
        cur.executemany("INSERT INTO article_parts(article_id,kind,label,seq,text,text_sha256) VALUES(?,?,?,?,?,?)",
                        [(aid, k, lbl, i + 1, txt, sha(txt)) for i, (k, lbl, txt) in enumerate(parts)])

    cur.executemany("""INSERT INTO annotations(law_version_id,article_id,division_id,seq,target_kind,action,dof_dates,text)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    [(lv, art_ids.get(an["article"]), div_ids.get(an["division"]), an["seq"],
                      an["target_kind"], an["action"], an["dof_dates"], an["text"]) for an in ex.annotations])

    # citation graph: self-article refs resolve against this law's key set
    keys = {a["article_key"] for a in ex.articles}
    numeros: dict[int, str] = {}
    for a in ex.articles:
        if not a["is_transitorio"] and a["numero_int"] is not None:
            numeros.setdefault(a["numero_int"], a["article_key"])
    xrefs = extractor.for_law(law_id, rec["slug"], ex.articles, keys, numeros)
    cur.executemany("""INSERT INTO cross_references(law_version_id,article_id,seq,quote,ref_kind,
                         target_law_id,target_article_key,resolved)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    [(lv, art_ids.get(x["article"]), x["seq"], x["quote"], x["ref_kind"],
                      x["target_law_id"], x["target_article_key"], x["resolved"]) for x in xrefs])

    con.commit()
    return {"law_id": law_id, "version_id": lv, "divisions": len(ex.divisions),
            "articles": len(ex.articles), "annotations": len(ex.annotations),
            "blocks": len(blocks), "cross_references": len(xrefs)}


def captures(rec: dict, data: Path) -> list[tuple[dict, Path]]:
    """Every capture of a law, oldest first, with the folder holding its blocks:
    each entry of meta.json's previous_captures (history/<date>/), then the
    current capture (the law's own folder)."""
    d = law_dir(data, rec["slug"])
    out = []
    for prev in rec.get("previous_captures") or []:
        cap = {**rec, "files": prev["files"], "fetched_at": prev.get("fetched_at"),
               "ultima_reforma": prev.get("ultima_reforma", rec.get("ultima_reforma"))}
        out.append((cap, d / prev["history"]))
    out.append((rec, d))
    return out


def build(data: Path, db: Path, want: set[str] | None = None, source_kind: str = "doc",
          force_kind: str | None = None, md_dir: Path | None = None, quiet: bool = False,
          append: bool = False) -> dict:
    """Build a fresh database at db from the blocks under data (or, with append,
    add versions to an existing one). Returns the totals."""
    man = load_manifest(data)
    recs = select(man["laws"], want or set())
    db.parent.mkdir(parents=True, exist_ok=True)
    if append:
        if not db.exists():
            raise FileNotFoundError(f"--append needs an existing database at {db}")
        target = db
    else:
        target = db.with_name(db.name + ".tmp")
        target.unlink(missing_ok=True)
    con = sqlite3.connect(target)
    con.execute("PRAGMA synchronous = OFF")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT OR IGNORE INTO jurisdictions(code,name) VALUES('MX','Estados Unidos Mexicanos')")
    con.execute("INSERT OR IGNORE INTO corpora(jurisdiction,slug,name,source_url) VALUES(?,?,?,?)",
                ("MX", man["_meta"]["corpus"],
                 "Leyes Federales Vigentes (Cámara de Diputados del H. Congreso de la Unión)",
                 man["_meta"]["source"]))
    corpus_id = con.execute("SELECT id FROM corpora WHERE jurisdiction='MX' AND slug=?",
                            (man["_meta"]["corpus"],)).fetchone()[0]

    # pass 1: every law's stable identity exists before any article is loaded,
    # so cross-law citations resolve regardless of ingest order
    law_ids = {rec["slug"]: upsert_law(con, corpus_id, rec) for rec in recs}
    con.commit()
    catalog = [(law_ids[rec["slug"]], rec["slug"], re.sub(r"\s+", " ", deaccent(rec["nombre"].lower())).strip())
               for rec in recs]
    extractor = CitationExtractor(catalog)

    tot = {"laws": 0, "versions": 0, "articles": 0, "divisions": 0, "annotations": 0,
           "cross_references": 0, "skipped": 0, "errors": 0, "version_diffs": 0}
    for rec in recs:
        built = 0
        # oldest capture first, so the current one gets the highest version id
        for cap, cap_dir in ([(rec, md_dir)] if md_dir else captures(rec, data)):
            label = f"{rec['slug']} ({cap.get('fetched_at', '')[:10]})"
            try:
                r = ingest_law(con, law_ids[rec["slug"]], cap, data, source_kind, extractor,
                               force_kind=force_kind, md_dir=cap_dir)
            except Exception as e:
                print(f"  !! {label}: {type(e).__name__}: {e}", file=sys.stderr)
                tot["errors"] += 1
                continue
            if not r:
                if not quiet:
                    print(f"  -- {label}: no blocks on disk, skipped", file=sys.stderr)
                tot["skipped"] += 1
                continue
            built += 1
            tot["versions"] += 1
            for k in ("articles", "divisions", "annotations", "cross_references"):
                tot[k] += r[k]
        tot["laws"] += 1 if built else 0
    # change tracking: diff every pair of consecutive captures of a law
    for (law_id,) in con.execute("SELECT law_id FROM law_versions GROUP BY law_id HAVING count(*) > 1").fetchall():
        vs = con.execute("SELECT id, captured_at FROM law_versions WHERE law_id=? ORDER BY captured_at, id",
                         (law_id,)).fetchall()
        for (v_from, _), (v_to, at) in zip(vs, vs[1:]):
            diff_versions(con, v_from, v_to, computed_at=at)
            tot["version_diffs"] += 1
    con.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
    con.commit()
    con.execute("ANALYZE")
    con.commit()
    if not append:
        con.execute("VACUUM")
    con.close()
    if not append:
        target.replace(db)
    return tot


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="output SQLite file (default: %(default)s)")
    ap.add_argument("--only", default="", help="comma-separated slugs or short names")
    ap.add_argument("--sample", action="store_true", help="build only the CI sample listed in data/sample.txt")
    ap.add_argument("--append", action="store_true",
                    help="add versions to the existing --db instead of writing a fresh file")
    ap.add_argument("--source-kind", default="doc", help="edition assumed when convert.json is missing")
    ap.add_argument("--force-source-kind", default="",
                    help="experiments: treat the blocks as this edition, ignoring convert.json")
    ap.add_argument("--md-dir", type=Path, default=None,
                    help="experiments: read blocks from this folder instead of data/leyes/<slug>/")
    a = ap.parse_args()

    t0 = time.time()
    tot = build(a.data, a.db, parse_only(a.only, a.sample), a.source_kind,
                a.force_source_kind or None, a.md_dir, append=a.append)
    tot["seconds"] = round(time.time() - t0, 1)
    tot["db"] = str(a.db)
    print(json.dumps(tot, indent=2))
    return 0 if tot["laws"] and not tot["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())

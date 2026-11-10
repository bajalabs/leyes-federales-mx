#!/usr/bin/env python3
"""
The article grammar: one pattern vocabulary shared by every pipeline stage.

doc_to_md.py and pdf_to_md.py (block classification) and build_db.py (key
derivation) all import from here and never keep private copies. Two private
copies once hid the same bug in two places: the suffix chain stopped after one
level, so 195-Z-1 and 195-Z collapsed into one article_key (278 collision
groups corpus-wide). One grammar, one owner.

Suffix grammar, measured across the 319-law corpus on 2026-08-26:

    Bis-family word, optionally numbered      8 Bis · 119 Bis 1 · 77 BIS 35
    dash-joined single letter or number       113-F · 1298-A · 58-1 · 195-Z-1
    space-joined single letter, chain-only    77 Bis 35 A

The guards keep prose out of the suffix. "Artículo 1o.- Los actos..." and
"Artículo 3o. El Instituto..." must NOT read the leading L/E of the body as
suffixes, while "Artículo 113-F. Será aplicable..." keeps its F:

  - a dash-joined letter only counts when standalone (no letter follows it);
  - a space-joined letter only counts when a hard terminator (. : - end)
    follows it immediately — and only inside an already-open suffix chain.
"""
from __future__ import annotations
import re

# Upper-case-only classes even under re.I (scoped inline flag). Ñ is a
# first-class letter in Mexican statute numbering (Artículo 195-Ñ).
_UC = r"(?-i:[A-ZÑ])"
_NOT_WORDISH = r"(?![A-Za-záéíóúüñÁÉÍÓÚÜÑ])"

# Bis-family ordinal words (case-insensitive match; re-cased for display).
# The corpus prints a zoo of Latin forms: the standard Bis/Ter family, the LFD
# nominatives (257 Quintus / Sextus / Séptimus / Octavus), the laero/lac
# counting past ten (78 Undecies … 73 Octodecies, incl. Sexties-with-t and
# accented "Sexíes" spellings), and oddities like Novodecies / Novenus.
BIS_WORD = (r"Bis|Ter|Qu[áa]ter|Quinqu[ií]es|Quintus|Sextus|S[ée]ptimus|Octavus|Nonus|Novenus|"
            r"Sex(?:t)?[ií]es|Sept[ií]es|Oct[ií]es|Non[ií]es|Dec[ií]es|"
            r"Undec[ií]es|Duodec[ií]es|Terdec[ií]es|Quaterdec[ií]es|Quinquiesdec[ií]es|"
            r"Sexiesdec[ií]es|Septdec[ií]es|Octodec[ií]es|Nov(?:o|em)dec[ií]es")

# One suffix segment. Order matters: word first, then dash-joined, then the
# tightly-guarded space-joined letter. Words join by space OR dash ("8 Bis"
# and "223-Bis" are both real); prose never starts with "-Bis", so the dash
# form needs no extra guard. Exported (SUFFIX_SEG) so the citation extractor
# can parse referenced article numbers with the same grammar.
#
# Dash-joined letters allow ONE OR TWO letters — lieps prints "26-LL" — with
# the wordish guard keeping "-Los" prose out. Space-joined letters ("228 a.",
# LGTOC; "78 e.") are lowercase OR uppercase, guarded two ways so Spanish
# prose never parses as a suffix: the letter must be immediately terminated
# (. : - end) — "Artículo 5 a falta de…" rejects — or followed by space + a
# suffix word ("228 a bis").
_CHAIN_LETTER = rf"\s+(?-i:[A-ZÑa-zñ])(?=\.|:|\-|$|\s+(?:{BIS_WORD})\b)"
SUFFIX_SEG = (
    r"(?:"
    rf"(?:\s+|-)\s*(?:{BIS_WORD})(?:\s+\d{{1,4}})?"              # Bis · Bis 35 · -Bis
    rf"|\s*-\s*(?:{_UC}{{1,2}}{_NOT_WORDISH}|\d{{1,4}}(?!\d))"  # -F · -LL · -1
    rf"|{_CHAIN_LETTER}"                                        # ' a.' · 'e' in '228 e bis'
    r")"
)

# An article lead: paragraph STARTS with "Artículo <digits>[o.|º][ suffix…]".
# The trailing terminator accepts end-of-paragraph ($): the Reglamento del
# Senado styles headers as bare paragraphs ("Artículo 10", no punctuation),
# and rejecting those silently dropped ~390 articles. Requiring a
# DIGIT is what separates a real article from the editorial annotations
# ("Artículo reformado DOF …"), which never carry a number.
ART_RE = re.compile(
    r"^\s*Art[íi]culo\s+"
    r"(\d+)"                                # 1: number
    r"(?:o\.|º|°)?"                         # ordinal marker, ATTACHED only (1o., 3º).
                                            # Spaced "228 o." is LGTOC's letter suffix,
                                            # handled by the chain below.
    r"(" + SUFFIX_SEG + r"*)"               # 2: suffix chain (may be empty)
    r"\s*(?:\.|\-|:|\s|$)",                 # terminator
    re.I,
)

# Roman/ordinal-word article leads used inside TRANSITORIOS and reform decrees.
# Ordinal grammar measured on the corpus: units, teens (undécimo/duodécimo),
# tens up to centésimo, and the compound form the DOF actually prints —
# "ARTÍCULO DÉCIMO PRIMERO", "CUADRAGÉSIMO NOVENO". The tens+unit compound
# must be ONE key ("decimo-primero"), not eight copies of "decimo".
_ORD_UNIT = r"Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|S[ée]ptimo|Octavo|Noveno"
_ORD_TENS = (r"D[ée]cimo|Vig[ée]simo|Trig[ée]simo|Cuadrag[ée]simo|Quincuag[ée]simo|"
             r"Sexag[ée]simo|Septuag[ée]simo|Octog[ée]simo|Nonag[ée]simo|Cent[ée]simo")
ART_ORD_RE = re.compile(
    r"^\s*Art[íi]culo\s+((?:" + _ORD_TENS + r")(?:\s+(?:" + _ORD_UNIT + r"))?"
    r"|Und[ée]cimo|Duod[ée]cimo|" + _ORD_UNIT + r"|[UÚ]nico|[IVXLC]+)"
    r"((?:" + SUFFIX_SEG + r")*)"          # ordinal articles take Bis too: VIGÉSIMO BIS
    r"\b",
    re.I,
)

# Division leads: Título/Capítulo/Sección/Libro/Apartado.
HEAD_RE = re.compile(
    r"^\s*(T[ÍI]TULO|CAP[ÍI]TULO|SECCI[ÓO]N|LIBRO|APARTADO|T[íi]tulo|Cap[íi]tulo|Secci[óo]n|Libro)\b",
)

# Editorial provenance lines. Shape is "<subject> <participle> DOF <date>" —
# e.g. "Artículo reformado DOF 14-08-2001", "Fracción adicionada DOF 26-03-2019".
# The subject is NEVER followed by a number, which keeps
# "Artículo 47. El Estado del (sic DOF 05-02-1917) Nayarit…" out of this bucket.
ANNOT_TEXT_RE = re.compile(
    r"^\s*(?:art[íi]culos?|p[áa]rrafos?|fracci[óo]n|fracciones|incisos?|cap[íi]tulo|t[íi]tulo|secci[óo]n|"
    r"apartado|denominaci[óo]n|ep[íi]grafe|nota|fe de erratas|reforma|adici[óo]n)\b"
    r"(?!\s*\d)"
    r"[^.]{0,120}?"
    r"\b(reformad[oa]s?|adicionad[oa]s?|derogad[oa]s?|recorrid[oa]s?|renumerad[oa]s?|"
    r"reubicad[oa]s?|invalidad[oa]s?|publicad[oa]s?|erratas)\b",
    re.I,
)

TRANS_RE = re.compile(r"^\s*(ART[ÍI]CULOS?\s+)?TRANSITORIOS?\b|^\s*Transitorios?\s*$", re.I)

# Reform-decree lead inside a TRANSITORIOS zone: the consolidated .doc prints
# each reform decree with its own transitorios under the law's transitorio
# section — ~2,600 of these across 248 laws. Each one starts a new decree_group
# for ordinal-article identity. Lead wording varies: "DECRETO por el que…",
# "DECRETO mediante el cual…", "DECRETO que reforma…".
DECRETO_RE = re.compile(
    r"^\s*DECRETO\s+(?:por\s+el\s+(?:que|cual)|mediante\s+el\s+(?:cual|que)|que)\b", re.I)

# "DISPOSICIONES TRANSITORIAS DE LA LEY…" ends a decree's normative body and
# opens its transitorios (lgsmime styles it as a heading, not TRANSITORIOS).
DISPOSICIONES_TRANS_RE = re.compile(r"^\s*DISPOSICI[ÓO]N(?:ES)?\s+TRANSITORI", re.I)

# TRANSITORIOS spelled out letter-spaced ("T R A N S I T O R I O S") — 17 laws.
SPACED_TRANS_RE = re.compile(
    r"^\s*(?:A\s*R\s*T\s*[IÍ]\s*C\s*[UÚ]\s*L\s*O\s*S?\s+)?"
    r"T\s*R\s*A\s*N\s*S\s*I\s*T\s*O\s*R\s*I\s*O\s*S?\s*$",
    re.I,
)

# Bare-ordinal article leads: "PRIMERO.- …" without the word "Artículo".
# The DOMINANT transitorio style in the corpus (~10,190 paragraphs). Zone-
# gated in the extractor (ordinal_lead kind): outside a TRANSITORIOS zone a
# bare ordinal is an enumeration, not an article.
_ORD_UNIT_U = r"PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO"
BARE_ORD_RE = re.compile(
    r"^\s*(" + _ORD_UNIT_U +
    r"|D[ÉE]CIMO(?:\s+(?:" + _ORD_UNIT_U + r"))?"
    r"|VIG[ÉE]SIMO(?:\s+(?:" + _ORD_UNIT_U + r"))?"
    r"|[UÚ]NICO)\s*[.\-:]",
    re.I,
)

# Division parser (build_db).
DIV_RE = re.compile(r"^\s*(Libro|T[íi]tulo|Cap[íi]tulo|Secci[óo]n|Apartado)\s+(.{0,60}?)\s*$", re.I)

# Article-body part classification (build_db).
FRAC_RE = re.compile(r"^\s*([IVXLCDM]{1,9})\s*[.\-–)]\s+(.*)$")
INC_RE = re.compile(r"^\s*([a-z])\s*[)\.]\s+(.*)$")
NUM_RE = re.compile(r"^\s*(\d{1,3})\s*[.\-)]\s+(.*)$")

# Annotation parsing (build_db).
DOF_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
# Order matters: longer phrase alternatives first. "declarado inválido" (SCJN)
# and the bare adjective "inválido/inválida" are separate buckets from the
# participle "invalidado". "original" marks the as-published text (CPEUM 1917).
ACTION_RE = re.compile(
    r"\b(reformad[oa]s?|adicionad[oa]s?|derogad[oa]s?|recorrid[oa]s?|renumerad[oa]s?|"
    r"reubicad[oa]s?|invalidad[oa]s?|fe de erratas|publicad[oa]s?|modificad[oa]s?|"
    r"abrogad[oa]s?|actualizad[oa]s?|compilad[oa]s?|"
    r"declarad[oa]s?\s+inv[áa]lid[oa]s?|inv[áa]lid[oa]s?|derog[óo]|original)\b",
    re.I,
)
TARGET_RE = re.compile(
    r"^\s*(art[íi]culos?|p[áa]rrafos?|fracci[óo]n|fracciones|incisos?|cap[íi]tulo|t[íi]tulo|"
    r"secci[óo]n|apartado|denominaci[óo]n|ep[íi]grafe|nota|libro)\b",
    re.I,
)
# "Multa de la fracción compilada por resolución miscelánea fiscal DOF …" —
# the annotation's real target is the part named after "Multa de/del".
MULTA_TARGET_RE = re.compile(
    r"^\s*multa\s+de[l]?\s+(?:la|el|los|las)\s+"
    r"(art[íi]culo|fracci[óo]n|inciso|p[áa]rrafo|cantidad)\b",
    re.I,
)

# The edition's own statement of its latest reform, printed in its first lines:
# "Última reforma publicada DOF 29-12-2025", "Últimas reformas publicadas DOF
# 02-06-2026", "Última reforma publicada 14-11-2025". It describes the text
# actually captured, so it wins over the Cámara's index, which lags.
ULTIMA_REFORMA_RE = re.compile(
    r"[ÚU]ltimas?\s+reformas?\s+publicadas?\s+(?:en\s+el\s+)?(?:DOF\s+)?(\d{2})[-/](\d{2})[-/](\d{4})", re.I)


def ultima_reforma_in_text(texts, limit: int = 40) -> str | None:
    """'DOF 02/06/2026' from the first `limit` paragraphs, in the index's format; None if absent."""
    for i, t in enumerate(texts):
        if i >= limit:
            break
        m = ULTIMA_REFORMA_RE.search(t)
        if m:
            return f"DOF {m.group(1)}/{m.group(2)}/{m.group(3)}"
    return None


# ── page furniture ─────────────────────────────────────────────────────────
# textutil emits a Word file's headers and footers AFTER the body: the Cámara's
# logo (EMBED Word.Picture.8), its running header (the law's title, "CÁMARA DE
# DIPUTADOS DEL H. CONGRESO DE LA UNIÓN", "Secretaría General", "Secretaría de
# Servicios Parlamentarios", "Última Reforma DOF …") and the page-number fields
# ("PAGE", "PAGE1 de NUMPAGES416"). Files with a separate even-page header add
# the DOF's own running head, with or without its field code ("PAGE \*
# MERGEFORMAT2 (Primera Sección) DIARIO OFICIAL Viernes 4 de junio de 2010").
# None of it is text of the law. Measured on the 2026 captures: every such
# paragraph sits in the last 25 blocks of its file; field codes elsewhere
# ("EMBED Equation.3 : Cuota prevista…", image imports) are content and stay.
LOGO_RE = re.compile(r"^\s*EMBED\s+Word\.Picture\.\d+\s*$")
PAGE_FIELD_RE = re.compile(r"^\s*(?:P[áa]gina\s+)?PAGE(?![A-Za-zÁÉÍÓÚáéíóúÑñ])")   # PAGE, PAGE1 de NUMPAGES9
FIELD_TOKEN_RE = re.compile(r"\\\*\s*MERGEFORMAT|NUMPAGES|DocVariable")          # field codes inside a line
DOF_HEAD_RE = re.compile(
    r"^\s*(?:\([^)]{1,40}\)\s+)?(?:DocVariable\s+\w+\s+)?DIARIO\s+OFICIAL\s+\w+\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\s*$"
    r"|^\s*\w+\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\s+DIARIO\s+OFICIAL(?:\s+\([^)]{1,40}\))?\s*$")
FURNITURE_WINDOW = 40          # how far from the end the trailing zone may start
FURNITURE_MAX_CHARS = 300      # header and footer lines are short (a long law title runs to ~260)
FURNITURE_MAX_SIZE = 9.0       # running-header rows are set in 5-9 pt


def is_field(text: str) -> bool:
    """The logo, a page-number field, or a line carrying a Word field code."""
    return bool(LOGO_RE.match(text) or PAGE_FIELD_RE.match(text) or FIELD_TOKEN_RE.search(text))


def _furniture_zone_ok(zone: list[dict]) -> bool:
    """A zone is furniture when it opens with a Word field or a DOF running head,
    holds at least one Word field, and every paragraph in it is one of those or
    a small header row that follows the logo."""
    if not zone or not (is_field(zone[0]["text"]) or DOF_HEAD_RE.match(zone[0]["text"])):
        return False
    after_logo, fields = False, 0
    for b in zone:
        t = b["text"]
        if len(t) > FURNITURE_MAX_CHARS:
            return False
        if LOGO_RE.match(t):
            after_logo, fields = True, fields + 1
        elif is_field(t):
            fields += 1
        elif DOF_HEAD_RE.match(t):
            pass
        elif after_logo and ((b.get("style") or {}).get("size") or 99) <= FURNITURE_MAX_SIZE:
            pass
        else:
            return False
    return fields > 0


def furniture_start(blocks: list[dict]) -> int | None:
    """Index of the first block of the trailing page furniture, or None."""
    for s in range(max(0, len(blocks) - FURNITURE_WINDOW), len(blocks)):
        if _furniture_zone_ok(blocks[s:]):
            return s
    return None


def mark_furniture(blocks: list[dict]) -> int:
    """Set kind='furniture' on the trailing page furniture. Returns how many changed."""
    s = furniture_start(blocks)
    changed = 0
    for b in blocks[s:] if s is not None else []:
        if b["kind"] != "furniture":
            b["kind"] = "furniture"
            changed += 1
    return changed


def ends_with_furniture(text: str) -> bool:
    """True when an article's last paragraph is a Word field or a running-header line."""
    last = (text or "").rstrip().rsplit("\n", 1)[-1].strip()
    return bool(is_field(last) or DOF_HEAD_RE.match(last)
                or last in ("CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
                            "Secretaría de Servicios Parlamentarios"))


DIV_KIND = {"libro": "libro", "titulo": "titulo", "capitulo": "capitulo",
            "seccion": "seccion", "apartado": "apartado"}
DEPTH = {"libro": 0, "titulo": 1, "capitulo": 2, "seccion": 3, "apartado": 4, "otro": 5}
SUFFIX_ORD = {"bis": 1, "ter": 2, "quater": 3, "quáter": 3, "quinquies": 4, "sexies": 5,
              "septies": 6, "octies": 7, "nonies": 8, "decies": 9}


def deaccent(s: str) -> str:
    for a, b in zip("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN"):
        s = s.replace(a, b)
    return s


def suffix_tokens(raw: str) -> list[str]:
    """' Bis 35 A' -> ['bis','35','a'] · '-Z-1' -> ['z','1'] · '' -> []."""
    s = re.sub(r"\s+", " ", (raw or "").strip())
    s = re.sub(r"\s*-\s*", "-", s)
    if not s:
        return []
    return [t.lower() for t in re.split(r"[\s-]+", s) if t]


def display_suffix(raw: str) -> str | None:
    """' Bis 35 A' -> 'Bis 35 A' · '-Z-1' -> 'Z-1' · '' -> None."""
    s = re.sub(r"\s+", " ", (raw or "").strip())
    s = re.sub(r"\s*-\s*", "-", s).strip("- ")
    return s or None


def article_key(numero: str | None, suffix: str, ordinal: str | None,
                transitorio: bool, group: str, sub: str = "") -> str:
    """Stable article identity across captures.

    Numeric: '<n>' + one dash-joined token per suffix segment
        195 + Z-1  -> '195-z-1'      (distinct from '195-z')
        77 + Bis 35 A -> '77-bis-35-a'
    Ordinal: the deaccented ordinal word(s), dash-joined ('decimo-primero').
    Transitorio-zone articles are prefixed with their decree group:
    'T[03]:primero'. Decree-BODY articles (the reform decree's own articles,
    printed between the DECRETO lead and its TRANSITORIOS heading) carry a
    'd' sub-phase so they never collide with the decree's transitorios:
    'T[04]:d:primero' vs 'T[04]:primero'.
    """
    if numero is not None:
        base = numero
    else:
        base = re.sub(r"\s+", "-", deaccent((ordinal or "?").lower()))
    toks = suffix_tokens(suffix)
    k = base + ("-" + "-".join(toks) if toks else "")
    if not transitorio:
        return k
    return f"T[{group}]:{sub + ':' if sub else ''}{k}"

**English** · [Español](README.es.md)

# leyes-federales-mx

[![CI](https://github.com/bajalabs/leyes-federales-mx/actions/workflows/ci.yml/badge.svg)](https://github.com/bajalabs/leyes-federales-mx/actions/workflows/ci.yml)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data: CC0-1.0](https://img.shields.io/badge/data-CC0--1.0-lightgrey.svg)](LICENSE-DATA)
[![Latest release](https://img.shields.io/github/v/release/bajalabs/leyes-federales-mx)](https://github.com/bajalabs/leyes-federales-mx/releases/latest)

The 319 Mexican federal laws published by the Cámara de Diputados, converted from the official Word files into structured, searchable data — Markdown you can read on GitHub, a SQLite database with full-text search, and CSV — for developers, researchers, journalists and lawyers who need Mexican law as data.

Every article knows its law, its place in the hierarchy (libro, título, capítulo, sección), its fracciones and incisos, the reforms that touched it with their dates in the Diario Oficial de la Federación (DOF), and the other articles and laws it cites. Every law is pinned by sha256 to the official file it came from.

## What is inside

Capture of 26 August 2026, from [diputados.gob.mx/LeyesBiblio](https://www.diputados.gob.mx/LeyesBiblio/index.htm):

| | |
|---|---|
| laws | **319**: 310 in force (vigentes), 4 repealed (abrogadas), 5 struck down by the Supreme Court (invalidadas) |
| kinds | 1 constitution, 9 codes, 301 laws, 3 regulations, 1 statute and 4 others (the 2025 and 2026 federal budgets, the Navy's general ordinance, a tax law) |
| source files | 638 (one .doc and one .pdf per law), 417 MB, every one pinned by URL and sha256 |
| articles | **59,540**: 42,721 regular articles and 16,819 transitory (transitorio) articles |
| article parts | 205,939 párrafos, fracciones, incisos and numerales |
| divisions | 10,264 libros, títulos, capítulos, secciones and apartados |
| reform annotations | 37,483 ("Artículo reformado DOF 14-08-2001"), 99.82% parsed into an action and ISO dates |
| citations | 30,029 cross-references between articles and laws, 99.95% resolved to their target |
| blocks | 287,779 classified paragraphs: the lossless record everything else is derived from |
| normative text | 46.6 million characters |

## Quick start

You need Python 3.12 or newer and nothing else (the standard library only). The `sqlite3` command-line tool is handy for queries; macOS ships it, and on Debian or Ubuntu it is `apt install sqlite3`.

**Read a law.** Every law is a Markdown file in [`data/leyes/`](data/leyes): the Constitution is [`data/leyes/001-cpeum/CPEUM.md`](data/leyes/001-cpeum/CPEUM.md).

**Query the database.** Download it from the [latest release](https://github.com/bajalabs/leyes-federales-mx/releases/latest):

```bash
curl -LO https://github.com/bajalabs/leyes-federales-mx/releases/latest/download/leyes-federales-mx.sqlite.zip
python3 -m zipfile -e leyes-federales-mx.sqlite.zip .
sqlite3 leyes-federales-mx.sqlite "SELECT label, substr(text, 1, 120) FROM v_articles
  WHERE law_slug = '001-cpeum' AND numero_int = 1 AND is_transitorio = 0;"
```

**Build it yourself.** From a clone, rebuild the database from the released blocks in about 20 seconds and run the verification gate:

```bash
git clone https://github.com/bajalabs/leyes-federales-mx.git
cd leyes-federales-mx
python3 -m unittest                                   # the test suite, about 2 seconds
python3 scripts/build_db.py --sample                  # 6 laws from the committed sample, offline
python3 scripts/verify_db.py --sample
curl -LO https://github.com/bajalabs/leyes-federales-mx/releases/latest/download/leyes-federales-mx-blocks.zip
python3 -m zipfile -e leyes-federales-mx-blocks.zip .   # unpacks into data/leyes/
python3 scripts/build_db.py                           # all 319 laws -> build/leyes-federales-mx.sqlite
python3 scripts/verify_db.py                          # PASS, with a JSON receipt in build/verify.json
```

`uv run scripts/build_db.py` works too. Every path and URL has a flag and an environment variable (`--data`/`LEYES_DATA_DIR`, `--db`/`LEYES_DB`, `LEYES_BUILD_DIR`, `LEYES_DIST_DIR`, `LEYES_BASE_URL`, `LEYES_USER_AGENT`); run any script with `--help`.

## Release assets

| File | What it is |
|---|---|
| `leyes-federales-mx.sqlite.zip` | the database (282 MB unpacked) |
| `leyes-federales-mx-blocks.zip` | every law's `<CODE>.blocks.jsonl`, at its path under `data/leyes/` |
| `leyes-federales-mx-laws.csv` | one row per law: names, status, dates, source URL and sha256, counts |
| `leyes-federales-mx-articles.csv.zip` | one row per article: law, key, label, hierarchy, last reform date, full text |
| `SHA256SUMS` | check the downloads with `sha256sum -c SHA256SUMS` (or `shasum -a 256 -c`) |

The CSV files are UTF-8 with standard quoting; article texts keep their paragraph breaks inside quoted fields.

## Layout

```
leyes-federales-mx/
├── data/
│   ├── manifest.json            every law: names, status, dates, and the URL + sha256 + size of its .doc and .pdf
│   ├── conversion-report.json   which edition (DOC or PDF fallback) produced each law
│   ├── sample.txt               the 6 laws whose blocks are committed, for CI
│   └── leyes/<numero>-<nombre_corto>/       e.g. 001-cpeum, 035-lce, 314a-pef_2025
│       ├── <CODE>.md            the law in Markdown, with a provenance header
│       ├── meta.json            this law's manifest entry
│       ├── convert.json         edition used, block counts, mojibake score
│       ├── <CODE>.blocks.jsonl  classified paragraphs (release asset; gitignored)
│       └── source/              the official .doc and .pdf (fetched on demand; gitignored)
├── db/schema.sql                the SQLite schema: tables, views, full-text index
├── scripts/                     the pipeline, standard-library Python
├── tests/                       python3 -m unittest
├── build/                       the database and receipts (gitignored)
└── dist/                        release assets (gitignored)
```

Folder names are `<numero>-<nombre_corto>` as the Cámara lists them; the three lettered numbers (`060 A`, `120 A`, `314 A`) become `060a`, `120a`, `314a`. `<CODE>` is the Cámara's file code (`CPEUM`, `LAdua`, `28`).

## Schema

```
jurisdictions ─< corpora ─< laws ─< law_versions ─┬─< divisions          (self-referencing tree)
                                                   ├─< articles ─< article_parts
                                                   ├─< annotations      (reform notes, DOF dates)
                                                   ├─< cross_references (the citation graph)
                                                   └─< blocks           (lossless landing zone)

law_versions ─< version_diffs ─< article_changes     (change tracking between captures)
articles_fts                                          (FTS5 full-text index over articles)
```

| Table or view | What a row is |
|---|---|
| `laws` | a law's stable identity: `slug` (`001-cpeum`), `nombre`, `tipo`, `estado_vigencia`, `dof_original` |
| `law_versions` | one captured edition: `source_kind` (`doc`/`pdf`), `resolved_url`, `source_sha256`, `ultima_reforma` |
| `articles` | `article_key` is the identity across editions: `'27'`, `'15-bis'`, `'195-z-1'`, `'77-bis-35-a'`, `'T[03]:primero'` (transitorio of the third decree block), `'T[04]:d:primero'` (an article in the body of a reform decree). `text` is normative text only; `last_reform_date` is the latest DOF date among its annotations |
| `article_parts` | `kind` is `parrafo`, `fraccion`, `inciso` or `numeral`, with its `label` (`I`, `a)`, `1.`) |
| `annotations` | the editorial reform notes, kept out of the normative text: `target_kind`, `action` (`reformado`, `adicionado`, `derogado`, …), `dof_dates` (JSON array of ISO dates) |
| `cross_references` | a citation found in an article, with the verbatim `quote`: `ref_kind` is `self-article` ("artículo 27 de esta Ley"), `constitution` ("artículo 131 constitucional") or `law` (another law named in full) |
| `blocks` | every classified paragraph with its style features, so the derived tables can be rebuilt without converting again |
| `v_laws`, `v_articles`, `v_toc`, `v_reformas` | one-hop views over the current (latest) version of each law |

`articles_fts` is accent-insensitive: `importacion` matches `importación`.

## Query cookbook

```sql
-- an article with its place in the hierarchy
SELECT law_slug, label, division_heading, division_rubric, last_reform_date
FROM v_articles
WHERE law_slug = '001-cpeum' AND numero_int = 27 AND is_transitorio = 0;

-- full-text search across all 319 laws (accent-insensitive)
SELECT l.nombre_corto, a.label, snippet(articles_fts, 1, '«', '»', '…', 12) AS hit
FROM articles_fts f
JOIN articles a ON a.id = f.rowid
JOIN laws l     ON l.id = a.law_id
WHERE articles_fts MATCH '"comercio exterior"'
ORDER BY rank LIMIT 20;

-- the table of contents of a law
SELECT printf('%.*c', depth * 2, ' ') || heading AS heading, rubric, descendant_article_count
FROM v_toc WHERE law_slug = '035-lce' ORDER BY seq;

-- the fracciones of an article
SELECT p.kind, p.label, p.text
FROM article_parts p JOIN v_articles a ON a.id = p.article_id
WHERE a.law_slug = '035-lce' AND a.article_key = '4' ORDER BY p.seq;

-- reform pressure: the articles amended most often
SELECT l.nombre_corto, a.label, count(*) AS reforms
FROM annotations n
JOIN articles a ON a.id = n.article_id
JOIN laws l     ON l.id = a.law_id
GROUP BY a.id ORDER BY reforms DESC LIMIT 20;

-- everything amended in 2026, corpus-wide
SELECT law_slug, article_label, action, dof_dates
FROM v_reformas WHERE dof_dates LIKE '%"2026-%';

-- what Article 27 of the Constitution cites
SELECT quote, target_article_key FROM cross_references
WHERE article_id = (SELECT id FROM v_articles
                    WHERE law_slug = '001-cpeum' AND numero_int = 27 AND is_transitorio = 0);

-- the laws other laws cite most
SELECT t.slug, count(*) AS citations
FROM cross_references x
JOIN laws t         ON t.id = x.target_law_id
JOIN law_versions v ON v.id = x.law_version_id
WHERE v.law_id <> t.id
GROUP BY t.id ORDER BY citations DESC LIMIT 10;

-- laws no longer in force
SELECT slug, nombre, estado_vigencia, ultima_reforma FROM v_laws WHERE estado_vigencia <> 'vigente';

-- what changed between two captures (after a second capture; see CONTRIBUTING.md)
SELECT article_key, change_type, round(similarity, 3), substr(diff, 1, 200)
FROM article_changes c JOIN version_diffs d ON d.id = c.version_diff_id
WHERE d.law_id = (SELECT id FROM laws WHERE slug = '001-cpeum')
  AND change_type IN ('modified', 'added', 'removed');
```

`sqlite3 -json` or `-csv` turns any of these into JSON or CSV. [Datasette](https://datasette.io) and [DB Browser for SQLite](https://sqlitebrowser.org) open the file as it is.

## How it is built

```
fetch.py ──> source/<CODE>.doc, .pdf ──> convert_all.py ──> <CODE>.blocks.jsonl ──> build_db.py ──> SQLite ──> verify_db.py
 (sha256 check against manifest.json)    (doc_to_md.py,        + <CODE>.md             (patterns.py)              (the gate)
                                          pdf_to_md.py fallback)
```

1. **Fetch.** [`scripts/fetch.py`](scripts/fetch.py) downloads each law's `.doc` and `.pdf` from the Cámara de Diputados and checks it against the sha256 in `data/manifest.json`. The Cámara overwrites a file in place at every reform and moves repealed laws under `/abro/`, so each download walks a ladder of known URL spellings and records the one that answered.
2. **Convert.** [`scripts/convert_all.py`](scripts/convert_all.py) turns each `.doc` into HTML with macOS `textutil` and classifies every paragraph ([`doc_to_md.py`](scripts/doc_to_md.py)): article lead, transitory lead, heading, reform annotation, note, table or body. A health gate scores each conversion for mojibake and falls back to the PDF ([`pdf_to_md.py`](scripts/pdf_to_md.py), `pdftotext -layout`) when the Word file cannot be read.
3. **Build.** [`scripts/build_db.py`](scripts/build_db.py) makes one forward pass over each law's blocks: it keeps the division stack, opens a new article at each lead, splits article bodies into parts, attaches annotations, parses their DOF dates, and extracts citations. One grammar, [`scripts/patterns.py`](scripts/patterns.py), serves every stage: article numbers with suffix chains (`8 Bis`, `195-Z-1`, `77 Bis 35 A`, `26-LL`, `257 Quintus`), ordinal transitorios (`DÉCIMO PRIMERO`), decree boundaries inside transitory zones.
4. **Verify.** [`scripts/verify_db.py`](scripts/verify_db.py) is the regression gate: referential integrity, no duplicate article keys among regular articles, a tripwire that every article header in the Markdown became an article, numbering gaps, annotation parse rate at least 99%, full-text parity, totals against the manifest, and article-count floors for laws that once regressed.

When the grammar improves, [`reclassify.py`](scripts/reclassify.py) replays classification over the stored blocks and [`blocks_to_md.py`](scripts/blocks_to_md.py) regenerates the Markdown: no conversion, no network, any operating system. [`diff_versions.py`](scripts/diff_versions.py) compares two captures article by article, and [`package_release.py`](scripts/package_release.py) writes the release assets.

**Reproducible.** On 10 November 2026, re-downloading the official files for two laws whose pins still matched and converting them again produced Markdown and blocks byte-identical to the committed ones.

### Why the Word file and not the PDF

The Cámara publishes every law as PDF and as Word. The PDF has thrown away the styling that tells editorial notes from normative text, and its fixed-width lines put mid-sentence cross-references at the start of a line, where they look like new articles. Measured on the Constitution (414 pages, 136 articles) in the August 2026 capture:

| | DOC | PDF |
|---|---|---|
| article boundaries found | **136 (exact)** | 207 (71 false) |
| page-furniture lines to strip | **0** | 1,656 |
| reform annotations recovered | **975** | 120 |

In the Word file the Cámara sets reform notes in small blue right-aligned type and headings centred in bold, so classification is mechanical. Three Word files cannot be parsed by `textutil` (the 2022 tariff law, LIGIE, and the 2025 and 2026 federal budgets); those come from the PDF, and `law_versions.source_kind` says so.

## Known issues

- **A snapshot, not a live feed.** The texts are the 26 August 2026 capture. On 10 November 2026, 317 of the 319 `.doc` files on the Cámara's site were still byte-identical to the pins; the Constitution and the LIGIE had been republished since. Run `python3 scripts/fetch.py` to see the current state; the release notes of each version give its capture date.
- **New laws are not picked up automatically.** The list of laws comes from the Cámara's index as read on 8 March 2026. Reformed laws are refreshed by `fetch.py --recapture`; a law published after that date needs an entry in the manifest by hand until an index reader is written.
- **Two dates of last reform.** `law_versions.ultima_reforma` is the date the edition itself prints ("Últimas reformas publicadas DOF 02-06-2026") for the 250 laws that print one, and the index value otherwise; `ultima_reforma_indice` keeps the index value. They differ for 31 laws because the index lags. `articles.last_reform_date` comes from the annotations of each article.
- **Conversion needs macOS.** `textutil` ships only with macOS. Rebuilding the database, regenerating Markdown and replaying the grammar run anywhere from the stored blocks.
- **Three laws come from the PDF** (LIGIE 2022, PEF 2025, PEF 2026) and have no reform annotations, since the PDF cannot tell them from body text. They are dominated by tables, where that matters least.
- **Tables are flattened.** A table becomes one `| … |` line per paragraph; columns are not reconstructed.
- **Article parts are labelled by pattern.** Roman-numeral fracciones and lettered incisos are reliable; deeply nested or table-embedded lists fall back to `parrafo`.
- **Duplicate keys in transitory zones.** 333 groups of repeated `article_key` remain inside transitory zones, where Supreme Court invalidation resolutions repeat PRIMERO/SEGUNDO/TERCERO under one heading with no decree boundary. Regular articles have none (a gate in `verify_db.py`); `diff_versions.py` matches the residue by position.
- **Numbering holes in the OGA** (290) are renumberings in the source itself, checked against the official file.
- **Citations are found by pattern**: references to an article of the same law, to the Constitution, and to other laws named in full. Abbreviations and loose references ("la Ley", "el Reglamento") are not resolved; 14 of the 30,029 references found name an article number the law does not have.
- **One capture per law so far**, so `version_diffs` is empty. The diff engine works (comparing the DOC and PDF editions of the LCE gives 33 modified and 104 unchanged articles); real change tracking starts with the second capture.
- **Not an official publication, not legal advice.** The authoritative text is the one published in the [Diario Oficial de la Federación](https://www.dof.gob.mx). Check the official file before relying on any text here; its URL and sha256 are in the header of every law.

## Licence

Code (scripts, tests, schema, workflows): [MIT](LICENSE). Data (Markdown, metadata, database, blocks, CSV): [CC0 1.0](LICENSE-DATA), dedicated to the public domain.

The texts of Mexican laws are not subject to copyright: article 14, fracción VIII of the Ley Federal del Derecho de Autor excludes legislative texts, and requires that a published text match the official one. The sha256 pins exist so that anyone can check that it does. See [LICENSE-DATA](LICENSE-DATA).

## How to cite

Cite the law itself by its official name and DOF publication. To cite this dataset, use the metadata in [CITATION.cff](CITATION.cff) (GitHub shows a "Cite this repository" button), for example:

> Baja Labs (2026). *leyes-federales-mx: the Mexican federal laws as structured data* (version 1.0.0, capture of 2026-08-26) [Data set]. https://github.com/bajalabs/leyes-federales-mx

## Contributing

Reports of a wrong article, a missed reform note or a broken citation are the most useful contribution: open a [data error](https://github.com/bajalabs/leyes-federales-mx/issues/new?template=data-error.yml) with the law and the article. Fixes go into the grammar, never into the Markdown by hand. [CONTRIBUTING.md](CONTRIBUTING.md) explains how to build, test, refresh the corpus and propose a change; [SECURITY.md](SECURITY.md) how to report a vulnerability; [CHANGELOG.md](CHANGELOG.md) what changed.

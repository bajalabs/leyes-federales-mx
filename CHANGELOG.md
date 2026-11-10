# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a new capture of the corpus is a
minor version; a change to the schema that breaks existing queries is a major
version.

## [1.0.0] - 2026-11-10

First public release.

### Data

- Capture of 26 August 2026 of the 319 federal laws listed by the Cámara de
  Diputados: 310 vigentes, 4 abrogadas, 5 invalidadas.
- 638 official source files (.doc and .pdf) pinned by URL and sha256 in
  `data/manifest.json`; 316 laws converted from the Word file, 3 from the PDF.
- 59,540 articles (42,721 regular, 16,819 transitorios), 205,939 article
  parts, 10,264 divisions, 37,483 reform annotations (99.82% parsed),
  30,029 citations (99.95% resolved), 287,779 blocks.
- `law_versions.ultima_reforma` takes the date each edition prints itself
  when it prints one (250 laws); the index value is kept in
  `ultima_reforma_indice`.

### Pipeline

- Fetch with sha256 verification and `--recapture`, DOC conversion with a
  PDF fallback, grammar replay over stored blocks, Markdown regeneration,
  SQLite build with FTS5, verification gate, version diffing, CSV export and
  release packaging. Python standard library only.
- Tests for the grammar, classification, rendering, build, verification and
  fetch; CI builds and verifies a six-law sample on every pull request.

[1.0.0]: https://github.com/bajalabs/leyes-federales-mx/releases/tag/v1.0.0

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
- Second capture on 10 November 2026 of the two laws republished since: the
  Constitution (reform of DOF 07/10/2026 to articles 82, 116 and 122: 7
  articles added, 4 modified, 924 unchanged) and the LIGIE 2022 (a tariff
  decree: 2 added, 81 unchanged). Both captures are kept as versions and
  diffed into `version_diffs` and `article_changes`.
- 638 official source files (.doc and .pdf) pinned by URL and sha256 in
  `data/manifest.json`, plus the 4 files of the earlier capture; 316 laws
  converted from the Word file, 3 from the PDF.
- Current text: 59,549 articles (42,721 regular, 16,828 transitorios),
  205,957 article parts, 10,278 divisions, 37,487 reform annotations
  (99.82% parsed), 30,031 citations (99.95% resolved), 287,829 blocks.
- `law_versions.ultima_reforma` takes the date each edition prints itself
  when it prints one (250 laws); the index value is kept in
  `ultima_reforma_indice`.

### Pipeline

- Fetch with sha256 verification and `--recapture` (which keeps the
  previous capture), DOC conversion with a
  PDF fallback, grammar replay over stored blocks, Markdown regeneration,
  SQLite build with FTS5, verification gate, version diffing, CSV export and
  release packaging. Python standard library only.
- Tests for the grammar, classification, rendering, build, verification and
  fetch; CI builds and verifies a six-law sample on every pull request.

[1.0.0]: https://github.com/bajalabs/leyes-federales-mx/releases/tag/v1.0.0

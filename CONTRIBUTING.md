# Contributing

Thank you for helping. The most valuable contributions are reports and fixes
that make the data match the official text more closely. Issues and pull
requests are welcome in English or Spanish.

## Ground rules

- **Never edit the Markdown or the blocks by hand.** They are outputs of the
  pipeline. A wrong article boundary, a missed reform note or a broken
  citation is fixed in the grammar (`scripts/patterns.py`) or in the stage
  that uses it, then replayed over every law.
- **Every change keeps the gate green.** `scripts/verify_db.py` must pass on
  the full corpus, and any movement in the counts must be explained in the
  pull request.
- **Standard library only.** The pipeline runs on Python 3.12+ with no
  packages to install. Conversion also needs `curl`, macOS `textutil` and
  poppler's `pdftotext`.

## Set up

```bash
git clone https://github.com/bajalabs/leyes-federales-mx.git
cd leyes-federales-mx
python3 -m unittest
curl -LO https://github.com/bajalabs/leyes-federales-mx/releases/latest/download/leyes-federales-mx-blocks.zip
python3 -m zipfile -e leyes-federales-mx-blocks.zip .
python3 scripts/build_db.py && python3 scripts/verify_db.py
```

## Fix the grammar

1. Reproduce the problem with a test in `tests/` (most belong in
   `tests/test_patterns.py` or `tests/test_classify.py`).
2. Change `scripts/patterns.py` (or the classifier or extractor that uses it).
3. Replay it over the stored blocks and regenerate the Markdown; no
   conversion and no network are needed:

   ```bash
   python3 scripts/reclassify.py          # prints a per-law before/after report
   python3 scripts/blocks_to_md.py
   python3 scripts/build_db.py && python3 scripts/verify_db.py
   python3 -m unittest
   ```

4. Open a pull request with the reclassify report and the verify counts
   before and after. The Markdown diff it produces is the evidence; the
   updated blocks are published with the next release.

## Refresh the corpus

The Cámara de Diputados overwrites a law's file at every reform. To bring
the corpus up to date (macOS), with the release's blocks unpacked first so
the previous capture can be kept:

```bash
python3 scripts/fetch.py                       # which pinned files still match; exits 1 if any changed
python3 scripts/fetch.py --recapture           # adopt the changed files and re-pin them
python3 scripts/convert_all.py --only cpeum    # convert every law that was recaptured
python3 scripts/build_db.py && python3 scripts/verify_db.py
```

A recapture never loses the previous capture: its pins move to
`previous_captures` in the law's `meta.json`, and its blocks and
`convert.json` move to `data/leyes/<slug>/history/<date>/`. `build_db.py`
builds every capture as a `law_version` and diffs consecutive ones into
`version_diffs` and `article_changes`. Until a recaptured law is converted,
`verify_db.py` fails on purpose. After the conversion, `git diff data/`
shows exactly which laws changed and how.

## Cut a release

```bash
python3 scripts/build_db.py && python3 scripts/verify_db.py
python3 scripts/package_release.py             # dist/: database, blocks, CSV, SHA256SUMS
```

Tag the commit (`v1.1.0`), attach every file in `dist/` to the GitHub
Release, and note the capture date and the verify counts in the release
notes and in `CHANGELOG.md`.

## Report a data error

Open a [data error issue](https://github.com/bajalabs/leyes-federales-mx/issues/new?template=data-error.yml)
with the law's folder name, the article, what the data says and what the
official text says. A link to the Cámara page or the DOF publication helps.

## Pull requests

Keep them small and focused, with tests. CI runs the test suite and builds
and verifies the sample database on every pull request.

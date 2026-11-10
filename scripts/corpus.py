#!/usr/bin/env python3
"""
Paths, defaults and manifest helpers shared by every pipeline step.

Every default can be overridden on the command line or through an environment
variable, so nothing here needs editing when you move the data or the database:

    LEYES_DATA_DIR   the corpus folder (manifest.json + leyes/)   default: ./data
    LEYES_DB         the SQLite file build_db.py writes            default: ./build/leyes-federales-mx.sqlite
    LEYES_BUILD_DIR  receipts and other build scratch              default: ./build
    LEYES_DIST_DIR   release assets                                default: ./dist
"""
from __future__ import annotations
import json, os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "db" / "schema.sql"
SAMPLE_LIST = REPO / "data" / "sample.txt"

DB_BASENAME = "leyes-federales-mx"


def _env_path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v) if v else default


DEFAULT_DATA = _env_path("LEYES_DATA_DIR", REPO / "data")
DEFAULT_BUILD = _env_path("LEYES_BUILD_DIR", REPO / "build")
DEFAULT_DB = _env_path("LEYES_DB", DEFAULT_BUILD / f"{DB_BASENAME}.sqlite")
DEFAULT_DIST = _env_path("LEYES_DIST_DIR", REPO / "dist")


def load_manifest(data: Path) -> dict:
    return json.loads((Path(data) / "manifest.json").read_text(encoding="utf-8"))


def law_dir(data: Path, slug: str) -> Path:
    """data/leyes/<numero>-<nombre_corto>/ holds meta.json, convert.json, <CODE>.md, <CODE>.blocks.jsonl."""
    return Path(data) / "leyes" / slug


def sample_slugs() -> list[str]:
    """The laws whose blocks are committed to git: the CI sample (data/sample.txt)."""
    return [l.split("#", 1)[0].strip() for l in SAMPLE_LIST.read_text(encoding="utf-8").splitlines()
            if l.split("#", 1)[0].strip()]


def parse_only(only: str, sample: bool = False) -> set[str]:
    """--only takes slugs ('001-cpeum') or short names ('cpeum'), comma-separated."""
    want = {s.strip() for s in (only or "").split(",") if s.strip()}
    if sample:
        want |= set(sample_slugs())
    return want


def select(laws: list[dict], want: set[str]) -> list[dict]:
    if not want:
        return list(laws)
    return [r for r in laws if r["slug"] in want or r["nombre_corto"] in want]

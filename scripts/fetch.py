#!/usr/bin/env python3
"""
Download the official sources (.doc and .pdf) of every law and check them
against the sha256 pinned in data/manifest.json.

    python3 scripts/fetch.py                       # all 319 laws, both editions
    python3 scripts/fetch.py --only cpeum,lce      # a few laws
    python3 scripts/fetch.py --kinds doc           # only the Word editions
    python3 scripts/fetch.py --recapture           # accept upstream changes and re-pin

Files land in data/leyes/<slug>/source/<CODE>.<ext> (gitignored). Each file
ends in one of these states:

    match      byte-identical to the file this corpus was built from
    cached     already on disk and matching its pin; not downloaded again
    changed    the Cámara de Diputados now serves different bytes: the law was
               reformed (or re-published) after the capture. The download is
               discarded unless --recapture is given.
    failed     no candidate URL answered with a valid file

With --recapture a changed file is kept and becomes the new pin: meta.json and
manifest.json are rewritten with its resolved URL, size and sha256. Convert,
build and verify after a recapture (see CONTRIBUTING.md).

The Cámara overwrites a law's file in place at every reform, and abrogated laws
move under /abro/. Every download therefore walks a fallback ladder (pinned URL,
index URL, the usual /doc/ and /abro/ spellings) and records the URL that
actually answered.

Needs `curl`. The base URL and the User-Agent can be overridden:

    LEYES_BASE_URL    default https://www.diputados.gob.mx/LeyesBiblio
    LEYES_USER_AGENT  default leyes-federales-mx/<version> (+<repository URL>)
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus import DEFAULT_DATA, law_dir, load_manifest, parse_only, select  # noqa: E402

VERSION = "1.0.0"
BASE = os.environ.get("LEYES_BASE_URL", "https://www.diputados.gob.mx/LeyesBiblio").rstrip("/")
UA = os.environ.get("LEYES_USER_AGENT",
                    f"leyes-federales-mx/{VERSION} (+https://github.com/bajalabs/leyes-federales-mx)")
MAGIC = {"pdf": b"%PDF", "doc": b"\xd0\xcf\x11\xe0"}   # OLE2 compound file for .doc


def candidates(rec: dict, kind: str, base: str = BASE) -> list[str]:
    """Fallback ladder of URLs for one law and edition. First valid answer wins."""
    f = rec["files"].get(kind) or {}
    code, short = rec["codigo_archivo"], rec["nombre_corto"]
    out = [f.get("resolved_url"), f.get("index_url"),
           f"{base}/{kind}/{code}.{kind}",
           f"{base}/{kind}/{short.upper()}.{kind}",
           f"{base}/abro/{short}/{short.upper()}_abro.{kind}",
           f"{base}/abro/{short}/{code}_abro.{kind}",
           f"{base}/abro/{short}/{code}.{kind}"]
    seen, uniq = set(), []
    for u in out:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def magic_ok(p: Path, kind: str) -> bool:
    with p.open("rb") as f:
        return f.read(8).startswith(MAGIC[kind])


def curl_get(url: str, dest: Path, timeout: int = 300) -> tuple[int, str]:
    """Download url to dest. Returns (http_code, content_type); dest exists only on HTTP 200."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    p = subprocess.run(
        ["curl", "-sSL", "--max-time", str(timeout), "-A", UA,
         "--retry", "3", "--retry-delay", "2", "--retry-connrefused",
         "-o", str(tmp), "-w", "%{http_code}\t%{content_type}", url],
        capture_output=True, text=True,
    )
    parts = (p.stdout or "").split("\t")
    try:
        code = int(parts[0])
    except (ValueError, IndexError):
        code = 0
    ctype = parts[1] if len(parts) > 1 else ""
    if code == 200 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(dest)
    else:
        tmp.unlink(missing_ok=True)
    return code, ctype


def fetch_file(rec: dict, kind: str, data: Path, recapture: bool, force: bool) -> tuple[str, dict]:
    """-> (state, new file entry). The entry differs from the pinned one only on recapture."""
    pinned = dict(rec["files"].get(kind) or {})
    code = rec["codigo_archivo"]
    dest = law_dir(data, rec["slug"]) / "source" / f"{code}.{kind}"
    rel = f"leyes/{rec['slug']}/source/{code}.{kind}"

    if dest.exists() and not force and sha256_of(dest) == pinned.get("sha256"):
        return "cached", pinned

    incoming = dest.with_name(dest.name + ".incoming")
    last = None
    for rank, url in enumerate(candidates(rec, kind)):
        http, ctype = curl_get(url, incoming)
        last = http
        if http != 200 or not incoming.exists():
            continue
        if not magic_ok(incoming, kind):
            incoming.unlink(missing_ok=True)
            last = f"{http}/not-a-{kind}"
            continue
        digest = sha256_of(incoming)
        if digest == pinned.get("sha256"):
            incoming.replace(dest)
            return "match", pinned
        if not recapture:
            incoming.unlink(missing_ok=True)
            return "changed", pinned
        incoming.replace(dest)
        entry = {"kind": kind, "index_url": pinned.get("index_url"), "status": "ok",
                 "resolved_url": url, "http_code": http, "fallback_rank": rank, "content_type": ctype,
                 "bytes": dest.stat().st_size, "sha256": digest, "path": rel}
        return "changed", entry
    incoming.unlink(missing_ok=True)
    return "failed", {**pinned, "last_http_code": last}


def fetch_law(rec: dict, data: Path, kinds: list[str], recapture: bool, force: bool) -> tuple[dict, dict]:
    states, changed = {}, False
    for kind in kinds:
        state, entry = fetch_file(rec, kind, data, recapture, force)
        states[kind] = state
        if recapture and state == "changed":
            rec["files"][kind] = entry
            changed = True
    if changed:
        rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (law_dir(data, rec["slug"]) / "meta.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec, states


def write_manifest(data: Path, man: dict) -> None:
    """Rebuild manifest.json from the per-law meta.json files (the durable record),
    so a filtered run never drops the laws it did not touch."""
    laws = []
    for rec in man["laws"]:
        m = law_dir(data, rec["slug"]) / "meta.json"
        laws.append(json.loads(m.read_text(encoding="utf-8")) if m.exists() else rec)
    files = [f for r in laws for f in r["files"].values()]
    man["_meta"].update(
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        laws=len(laws),
        files_ok=sum(1 for f in files if f.get("status") in ("ok", "cached")),
        files_failed=sum(1 for f in files if f.get("status") == "failed"),
        total_bytes=sum(f.get("bytes") or 0 for f in files))
    man["laws"] = laws
    (data / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="corpus folder (default: %(default)s)")
    ap.add_argument("--only", default="", help="comma-separated slugs or short names")
    ap.add_argument("--kinds", default="doc,pdf", help="editions to fetch (default: %(default)s)")
    ap.add_argument("--jobs", type=int, default=4, help="parallel downloads (default: %(default)s); be gentle")
    ap.add_argument("--recapture", action="store_true", help="keep changed files and re-pin them")
    ap.add_argument("--force", action="store_true", help="download even when a matching file is on disk")
    a = ap.parse_args()

    kinds = [k.strip() for k in a.kinds.split(",") if k.strip() in MAGIC]
    man = load_manifest(a.data)
    laws = select(man["laws"], parse_only(a.only))
    tally: dict[str, list[str]] = {"match": [], "cached": [], "changed": [], "failed": []}
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(fetch_law, r, a.data, kinds, a.recapture, a.force) for r in laws]
        for i, f in enumerate(as_completed(futs), 1):
            rec, states = f.result()
            for kind, s in states.items():
                tally[s].append(f"{rec['slug']}.{kind}")
            print(f"[{i}/{len(laws)}] {rec['slug']:<34} "
                  + " ".join(f"{k}={s}" for k, s in states.items()), flush=True)

    if a.recapture and tally["changed"]:
        write_manifest(a.data, man)
    print(json.dumps({k: len(v) for k, v in tally.items()}))
    for s in ("changed", "failed"):
        if tally[s]:
            print(f"{s}: {', '.join(sorted(tally[s]))}")
    if tally["changed"] and not a.recapture:
        print("changed files were not kept: the official text moved on since the capture. "
              "Re-run with --recapture to adopt them.", file=sys.stderr)
    return 1 if tally["failed"] or (tally["changed"] and not a.recapture) else 0


if __name__ == "__main__":
    sys.exit(main())

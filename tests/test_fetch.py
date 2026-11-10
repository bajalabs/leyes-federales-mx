"""fetch.py checks every download against its pinned sha256. Served from a
local HTTP server, so the test needs curl but no internet."""
import functools
import hashlib
import http.server
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from tests import REPO  # noqa: F401
from fetch import candidates, fetch_file

OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("curl"), "curl is required")
class PinnedDownloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.www = tempfile.TemporaryDirectory()
        handler = functools.partial(Quiet, directory=cls.www.name)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.www.cleanup()

    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        self.pinned = OLE + b"texto original"
        (Path(self.www.name) / "X.doc").write_bytes(self.pinned)
        self.rec = {"slug": "999-x", "nombre_corto": "x", "codigo_archivo": "X",
                    "files": {"doc": {"kind": "doc", "status": "ok", "resolved_url": f"{self.base}/X.doc",
                                      "sha256": hashlib.sha256(self.pinned).hexdigest()}}}
        self.dest = self.data / "leyes" / "999-x" / "source" / "X.doc"

    def test_match_keeps_the_file(self):
        state, _ = fetch_file(self.rec, "doc", self.data, recapture=False, force=False)
        self.assertEqual(state, "match")
        self.assertEqual(self.dest.read_bytes(), self.pinned)
        state, _ = fetch_file(self.rec, "doc", self.data, recapture=False, force=False)
        self.assertEqual(state, "cached")

    def test_changed_upstream_is_discarded_without_recapture(self):
        (Path(self.www.name) / "X.doc").write_bytes(OLE + b"texto reformado")
        state, entry = fetch_file(self.rec, "doc", self.data, recapture=False, force=False)
        self.assertEqual(state, "changed")
        self.assertFalse(self.dest.exists())
        self.assertEqual(entry["sha256"], self.rec["files"]["doc"]["sha256"])

    def test_recapture_repins(self):
        new = OLE + b"texto reformado"
        (Path(self.www.name) / "X.doc").write_bytes(new)
        state, entry = fetch_file(self.rec, "doc", self.data, recapture=True, force=False)
        self.assertEqual(state, "changed")
        self.assertEqual(entry["sha256"], hashlib.sha256(new).hexdigest())
        self.assertEqual(entry["path"], "leyes/999-x/source/X.doc")
        self.assertEqual(self.dest.read_bytes(), new)

    def test_not_a_word_file_fails(self):
        (Path(self.www.name) / "X.doc").write_bytes(b"<html>not found</html>")
        rec = {**self.rec, "files": {"doc": {**self.rec["files"]["doc"]}}}
        state, _ = fetch_file(rec, "doc", self.data, recapture=False, force=False)
        self.assertEqual(state, "failed")


class Ladder(unittest.TestCase):
    def test_fallback_ladder_order_and_dedup(self):
        rec = {"codigo_archivo": "LCE", "nombre_corto": "lce",
               "files": {"doc": {"resolved_url": "https://h/doc/LCE.doc", "index_url": "https://h/doc/LCE.doc"}}}
        urls = candidates(rec, "doc", base="https://h")
        self.assertEqual(urls[0], "https://h/doc/LCE.doc")
        self.assertEqual(len(urls), len(set(urls)))
        self.assertIn("https://h/abro/lce/LCE_abro.doc", urls)


if __name__ == "__main__":
    unittest.main()

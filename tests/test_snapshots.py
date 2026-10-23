import importlib.util
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_lite import write_indexes

class SnapshotTests(unittest.TestCase):
    def test_light_and_full_have_matching_generation_and_complexes(self):
        snapshot = {"meta": {"generated": "today"}, "complexes": [
            {"id": "a", "results": {"school": {"walk": {"path": [[1, 2]], "dist_m": 20,
             "shortest": {"path": [[3, 4]]}, "risk_segments": []}}}}]}
        with TemporaryDirectory() as tmp:
            write_indexes(tmp, snapshot)
            full = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            lite = json.loads((Path(tmp) / "index-lite.json").read_text(encoding="utf-8"))
            self.assertEqual(full["meta"], lite["meta"])
            self.assertEqual(full["complexes"][0]["id"], lite["complexes"][0]["id"])
            self.assertEqual(lite["complexes"][0]["results"]["school"]["walk"], {"dist_m": 20})

    def test_invalid_numbers_preserve_previous_files(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text("old")
            with self.assertRaises(ValueError):
                write_indexes(tmp, {"value": float("nan")})
            self.assertEqual(path.read_text(), "old")

class PreviewSecurityTests(unittest.TestCase):
    def test_private_paths_and_traversal_are_not_served(self):
        spec = importlib.util.spec_from_file_location("preview", ROOT / "serve.py")
        preview = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preview)
        server = ThreadingHTTPServer(("127.0.0.1", 0), preview.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            for path in ("/.env", "/.env.local", "/data/raw/apartments_checkpoint.json",
                         "/web/../.env", "/web/%2e%2e/.env", "/.git/config"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
            with urlopen(base + "/web/") as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if __name__ == "__main__":
    unittest.main()


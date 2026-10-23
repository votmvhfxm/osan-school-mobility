import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location("collector", Path(__file__).parents[1] / "scripts/fetch_apartments.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class CollectionTests(unittest.TestCase):
    def test_all_pages_even_when_server_caps_page_size(self):
        pages = [{"response": {"body": {"totalCount": 3, "items": [{"kaptCode": "a"}, {"kaptCode": "b"}]}}},
                 {"response": {"body": {"totalCount": 3, "items": {"item": [{"kaptCode": "c"}]}}}}]
        with patch.object(m, "request_json", side_effect=pages):
            self.assertEqual(len(m.fetch_list("key")), 3)

    def test_repeated_page_is_failure(self):
        page = {"response": {"body": {"totalCount": 3, "items": [{"kaptCode": "a"}]}}}
        with patch.object(m, "request_json", return_value=page):
            with self.assertRaises(RuntimeError):
                m.fetch_list("key")

    def test_429_retries_without_leaking_key(self):
        import io
        response = io.BytesIO(b'{"response": {"header": {"resultCode": "00"}}}')
        with patch.object(m, "urlopen", side_effect=[HTTPError("secret", 429, "", {}, None), response]) as request, patch.object(m.time, "sleep"):
            m.request_json("https://example.com", {"key": "secret"})
            self.assertEqual(request.call_count, 2)

    def test_partial_preserves_csv_and_resume_uses_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            raw = data / "raw"
            raw.mkdir()
            original = b"old complete dataset"
            (data / "complexes.csv").write_bytes(original)
            items = [{"kaptCode": "a", "kaptName": "A"}, {"kaptCode": "b", "kaptName": "B"}]
            detail = {"response": {"body": {"item": {"doroJuso": "road", "kaptAddr": "parcel"}}}}
            with patch.object(m, "DATA", data), patch.object(m, "RAW", raw), patch.object(m, "load_env", return_value={"DATA_GO_KR_KEY": "k", "VWORLD_API_KEY": "v"}), patch.object(m, "fetch_list", return_value=items):
                with patch.object(m, "request_json", return_value=detail), patch.object(m, "geocode", side_effect=[(37.15, 127.05), None, None]):
                    with self.assertRaises(SystemExit):
                        m.main()
                self.assertEqual((data / "complexes.csv").read_bytes(), original)
                self.assertEqual(json.loads((data / "apartments_fetch_status.json").read_text())["mapped"], 1)
                with patch.object(m, "request_json", side_effect=AssertionError("details should resume")), patch.object(m, "geocode", return_value=(37.16, 127.06)) as geo:
                    m.main()
                    self.assertEqual(geo.call_count, 1)
                self.assertTrue(json.loads((data / "apartments_fetch_status.json").read_text())["complete"])
                self.assertEqual(len((data / "complexes.csv").read_text(encoding="utf-8-sig").splitlines()), 3)

    def test_parcel_fallback_and_invalid_coordinates(self):
        with patch.object(m, "request_json", return_value={"response": {"status": "OK", "result": {"point": {"y": "0", "x": "0"}}}}):
            self.assertIsNone(m.geocode("address", "key", "parcel"))

if __name__ == "__main__":
    unittest.main()


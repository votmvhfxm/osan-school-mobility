import importlib.util
import io
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import fetch_bus as bus

class BusCacheTests(unittest.TestCase):
    def setUp(self):
        bus.API_CACHE = {}
        bus.FAILURES.clear()

    def test_fresh_cache_avoids_api(self):
        key = bus.cache_key("path", {"stationId": "1"})
        bus.API_CACHE[key] = {"fetched_at": time.time(), "body": {"value": 1}}
        with patch.object(bus.requests, "get") as get:
            self.assertEqual(bus.call("path", stationId="1"), {"value": 1})
            get.assert_not_called()

    def test_legacy_and_expired_cache_are_refreshed(self):
        key = bus.cache_key("path", {})
        response = Mock(status_code=200)
        response.json.return_value = {"response": {"msgHeader": {"resultCode": 0}, "msgBody": {"value": 2}}}
        for old in ({"value": 1}, {"fetched_at": 0, "body": {"value": 1}}):
            bus.API_CACHE[key] = old
            with patch.object(bus.requests, "get", return_value=response), patch.object(bus, "save_cache"), patch.object(bus.time, "sleep"):
                self.assertEqual(bus.call("path"), {"value": 2})
                self.assertIn("fetched_at", bus.API_CACHE[key])

    def test_errors_do_not_print_secret_request_url(self):
        output = io.StringIO()
        with patch.object(bus.requests, "get", side_effect=bus.requests.RequestException("https://example.com?serviceKey=SECRET_VALUE")), patch.object(bus.time, "sleep"), redirect_stdout(output):
            self.assertIsNone(bus.call("path"))
        self.assertNotIn("SECRET_VALUE", output.getvalue())
        self.assertEqual(len(bus.FAILURES), 1)

if __name__ == "__main__":
    unittest.main()


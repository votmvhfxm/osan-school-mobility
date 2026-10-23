import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import fetch_public as public

class PublicCollectionTests(unittest.TestCase):
    def test_failed_later_page_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "crosswalk.json"
            out.write_text("previous complete file", encoding="utf-8")
            response = Mock()
            response.json.return_value = {"response": {"body": {"totalCount": 2000, "items": [{"rdnmadr": "오산"}]}}}
            with patch.object(public, "RAW", Path(tmp)), patch.object(public, "get", side_effect=[response, None]):
                with self.assertRaises(RuntimeError):
                    public.standard_paged("example", "crosswalk.json", lambda row: True)
            self.assertEqual(out.read_text(encoding="utf-8"), "previous complete file")


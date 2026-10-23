import importlib.util
from http.client import RemoteDisconnected
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("apartments",Path(__file__).parents[1]/"scripts/fetch_apartments.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ApartmentRefreshTests(unittest.TestCase):
    def test_connection_closed_is_retried(self):
        with patch.object(m,"urlopen",side_effect=[RemoteDisconnected("closed"),io.BytesIO(b'{"response":{"header":{"resultCode":"00"}}}')]) as request,patch.object(m.time,"sleep"):
            m.request_json("https://example.com",{"key":"private"})
            self.assertEqual(request.call_count,2)

    def test_only_unchanged_verified_address_reuses_coordinates(self):
        previous={"address":"경기 오산시 도로 10","lat":"37.15","lon":"127.05","coord_source":"vworld"}
        self.assertEqual(m.reusable_coordinates(previous,"경기 오산시 도로  10"),(37.15,127.05))
        self.assertIsNone(m.reusable_coordinates(previous,"경기 오산시 다른도로 20"))
        self.assertIsNone(m.reusable_coordinates({**previous,"coord_source":"estimated"},previous["address"]))



    def test_recent_completed_run_reuses_details_but_expires(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            raw=data/"raw"
            raw.mkdir()
            checkpoint=raw/"apartments_checkpoint.json"
            detail={"doroJuso":"road", "kaptName":"Apartment"}
            checkpoint.write_text(json.dumps({"complete":True,"started_at":time.time(),
                "details":{"a":detail},"coords":{"a":[37.15,127.05]}}))
            with patch.object(m,"DATA",data),patch.object(m,"RAW",raw),patch.object(m,"load_env",return_value={"DATA_GO_KR_KEY":"k","VWORLD_API_KEY":"v"}),patch.object(m,"fetch_list",return_value=[{"kaptCode":"a"}]):
                with patch.object(m,"request_json",side_effect=AssertionError("recent details should be reused")):
                    m.main()
                cached=json.loads(checkpoint.read_text())
                cached["started_at"]=time.time()-7*3600
                checkpoint.write_text(json.dumps(cached))
                with patch.object(m,"request_json",return_value={"response":{"body":{"item":detail}}}) as request:
                    m.main()
                    self.assertEqual(request.call_count,1)

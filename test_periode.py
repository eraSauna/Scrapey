import datetime
import json
import os
import unittest
from unittest.mock import patch

from periode import extract_periode_config, parse_results
from supa import build_location_rows, build_rows, verify_results, write_results


class PeriodeTest(unittest.TestCase):
    def test_extract_config(self):
        html = '<script>var periodeData = {"ajaxUrl":"https://example.test/ajax","nonce":"abc"};</script>'
        self.assertEqual(extract_periode_config(html)["nonce"], "abc")

    def test_known_and_new_location_are_parsed(self):
        data = {
            "date": "2026-09-20",
            "locations": [
                {"id": "amsterdam-marineterrein", "name": "Amsterdam Marineterrein"},
                {"id": "wijk-aan-zee", "name": "Wijk aan Zee"},
            ],
            "saunas": [
                {
                    "id": "uDw4a2pDUAyQ3XXonN2o",
                    "location_id": "amsterdam-marineterrein",
                    "name": "Björk",
                    "capacity": 6,
                    "price": 18.5,
                    "permalink": "https://kuuma.nl/boek-nu/marineterrein-bjork/",
                    "slots": [
                        {"time": "07:00", "available": 4, "price": 18.5, "type": "drop-in"},
                        {"time": "08:30", "available": 6, "price": 18.5, "type": "drop-in"},
                    ],
                },
                {
                    "id": "future-service",
                    "location_id": "wijk-aan-zee",
                    "name": "Wijk aan Zee",
                    "capacity": 8,
                    "price": 19,
                    "permalink": "https://kuuma.nl/boek-nu/wijk-aan-zee/",
                    "slots": [
                        {"time": "09:00", "available": 5, "price": 19, "type": "drop-in"},
                        {"time": "10:00", "available": 1, "price": 100, "type": "prive"},
                    ],
                },
            ],
        }
        results = parse_results(data)
        self.assertEqual([r["key"] for r in results], ["ams-bjork", "wijk-aan-zee"])
        self.assertFalse(results[0]["discovered"])
        self.assertTrue(results[1]["discovered"])
        self.assertEqual(results[1]["slots"], [{"time": "09:00", "available": 5, "price": 19.0}])

        locations = build_location_rows(results)
        self.assertEqual(locations[1]["bookeo_a"], "periode:wijk-aan-zee")
        self.assertEqual(locations[1]["slots"], ["09:00"])

        rows = build_rows(results, __import__("datetime").date(2026, 9, 20), "ochtend")
        self.assertEqual(rows[0]["location_key"], "ams-bjork")
        self.assertEqual(rows[0]["max_capaciteit"], 6)
        self.assertEqual(rows[0]["beschikbaar_ochtend"], 4)
        self.assertEqual(rows[-1]["location_key"], "wijk-aan-zee")

    def test_impossible_availability_fails_loudly(self):
        data = {
            "date": "2026-09-20",
            "locations": [],
            "saunas": [{
                "id": "new", "location_id": "new", "name": "New", "capacity": 6,
                "price": 18.5,
                "slots": [{"time": "10:00", "available": 7, "type": "drop-in"}],
            }],
        }
        with self.assertRaisesRegex(RuntimeError, "buiten bereik"):
            parse_results(data)

    @patch("supa.verify_results")
    @patch("supa._upsert")
    def test_location_is_upserted_before_slots(self, upsert, verify):
        result = {
            "key": "amsterdam-aan-t-ij", "naam": "Amsterdam Aan 't IJ",
            "capacity": 6, "price": 18.5, "slug": "boek-sauna-amsterdam-aan-t-ij",
            "provider_location_id": "amsterdam-aan-t-ij",
            "provider_service_id": "7fC6AcqCG9i1q9sYLExl",
            "slots": [{"time": "07:00", "available": 5, "price": 18.5}],
            "error": None,
        }
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "secret"}):
            write_results([result], datetime.date(2026, 9, 20), "ochtend")
        self.assertEqual(upsert.call_args_list[0].args[2], "locaties")
        self.assertEqual(upsert.call_args_list[1].args[2], "slot_beschikbaarheid")
        self.assertEqual(upsert.call_args_list[1].args[3][0]["beschikbaar_ochtend"], 5)
        verify.assert_called_once()

    @patch("supa.urllib.request.urlopen")
    def test_read_back_detects_all_expected_slots(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps([
            {"location_key": "amsterdam-aan-t-ij", "slot_time": "07:00"}
        ]).encode()
        result = {
            "key": "amsterdam-aan-t-ij", "error": None,
            "slots": [{"time": "07:00", "available": 5, "price": 18.5}],
        }
        verify_results("https://example.supabase.co", "secret", [result], datetime.date(2026, 9, 21))


if __name__ == "__main__":
    unittest.main()

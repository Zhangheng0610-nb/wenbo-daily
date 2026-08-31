"""Regression tests for daily discovery and legacy evidence isolation."""
import unittest
from unittest.mock import patch

from automation.daily_discovery import SOURCE_SCANS, duplicate_relation, parse_date, run


class DailyDiscoveryTests(unittest.TestCase):
    def test_date_parser_accepts_common_public_url_forms(self):
        self.assertEqual(parse_date("https://example.test/2026/8/31/article"), __import__("datetime").date(2026, 8, 31))
        self.assertEqual(parse_date("https://example.test/20260831/a"), __import__("datetime").date(2026, 8, 31))

    def test_same_day_duplicate(self):
        a = {"title": "某遗址公布新发现", "url": "https://a.test/1", "publishedDate": "2026-08-31", "entity": "某遗址", "eventType": "archaeology"}
        b = {"title": "某遗址发布考古新成果", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "某遗址", "eventType": "archaeology"}
        self.assertEqual(duplicate_relation(b, a)[0], "same_day_duplicate")

    def test_historical_duplicate(self):
        old = {"title": "某遗址公布新发现", "url": "https://a.test/1", "publishedDate": "2026-08-30", "entity": "某遗址", "eventType": "archaeology"}
        new = {"title": "媒体报道某遗址考古情况", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "某遗址", "eventType": "archaeology"}
        self.assertEqual(duplicate_relation(new, old)[0], "historical_duplicate")

    def test_new_development_is_not_suppressed(self):
        old = {"title": "某展览即将开展", "url": "https://a.test/1", "publishedDate": "2026-08-30", "entity": "某展览", "eventType": "exhibition"}
        new = {"title": "某展览正式开幕", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "某展览", "eventType": "exhibition"}
        self.assertEqual(duplicate_relation(new, old)[0], "new_development")

    def test_different_sites_are_not_duplicates(self):
        a = {"title": "甲遗址发现古墓", "url": "https://a.test/1", "publishedDate": "2026-08-31", "entity": "甲遗址", "eventType": "archaeology"}
        b = {"title": "乙遗址发现古墓", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "乙遗址", "eventType": "archaeology"}
        self.assertIsNone(duplicate_relation(b, a))

    def test_syndicated_english_titles_are_event_duplicates(self):
        a = {"title": "Egyptian queen's 673-diamond necklace stolen from Vienna museum", "url": "https://a.test/1", "publishedDate": "2026-08-30"}
        b = {"title": "Thieves plunder 673 diamond necklace from Vienna Museum", "url": "https://b.test/2", "publishedDate": "2026-08-31"}
        self.assertEqual(duplicate_relation(b, a)[0], "historical_duplicate")

    def test_all_source_scans_run_even_when_early_results_exist(self):
        calls = []

        def fake_scan(spec, _start, _end):
            calls.append(spec["sourceId"])
            return ({"sourceId": spec["sourceId"], "status": "checked", "rawResults": 0, "windowResults": 0}, [])

        with patch("automation.daily_discovery.scan_page", side_effect=fake_scan):
            audit = run(__import__("datetime").date(2026, 8, 31), execute_query_search=False)
        self.assertEqual(calls, [spec["sourceId"] for spec in SOURCE_SCANS])
        self.assertEqual(audit["summary"]["sourceScansAttempted"], len(SOURCE_SCANS))


if __name__ == "__main__":
    unittest.main()

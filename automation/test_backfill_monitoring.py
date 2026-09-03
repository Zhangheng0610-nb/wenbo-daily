"""Regression tests for fixed-panel source scanning and ingestion."""
import unittest
from datetime import date
from unittest.mock import patch

from automation import backfill_monitoring as monitoring


class FixedPanelMonitoringTests(unittest.TestCase):
    def test_ncha_column_722_same_day_article_is_captured(self):
        current = (
            '<a href="http://www.ncha.gov.cn/art/2026/9/3/art_722_204652.html">'
            '广西壮族自治区党委书记陈刚在南宁调研文化和文物保护工作时强调</a>'
        )
        older = '<a href="/art/2026/8/30/art_722_204570.html">金石探文明</a>'
        with patch.object(monitoring, "fetch", side_effect=[current, older]):
            rows, complete, _note = monitoring.crawl_ncha(
                date(2026, 9, 3), date(2026, 9, 3)
            )
        self.assertTrue(complete)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-09-03")
        self.assertEqual(rows[0]["url"], "http://www.ncha.gov.cn/art/2026/9/3/art_722_204652.html")

    def test_same_source_same_day_normalized_title_is_one_event(self):
        rows = [
            {
                "sourceId": "xinhua-wenbo",
                "date": "2026-09-03",
                "title": "习近平和彭丽媛同埃及总统塞西夫妇共同参观大埃及博物馆",
                "url": "https://www.news.cn/photo/20260903/one/c.html",
            },
            {
                "sourceId": "xinhua-wenbo",
                "date": "2026-09-03",
                "title": "习近平和彭丽媛同埃及总统塞西夫妇共同参观大埃及博物馆！",
                "url": "https://www.news.cn/politics/20260903/two/c.html",
            },
        ]
        unique, duplicates = monitoring.deduplicate_monitoring_rows(rows)
        self.assertEqual(len(unique), 1)
        self.assertEqual(duplicates, 1)
        self.assertEqual(
            unique[0]["_duplicateProvenance"][0]["url"],
            rows[1]["url"],
        )

    def test_same_source_different_action_is_not_merged(self):
        rows = [
            {
                "sourceId": "xinhua-wenbo",
                "date": "2026-09-03",
                "title": "某博物馆开馆",
                "url": "https://www.news.cn/a/c.html",
            },
            {
                "sourceId": "xinhua-wenbo",
                "date": "2026-09-03",
                "title": "某博物馆公布年度报告",
                "url": "https://www.news.cn/b/c.html",
            },
        ]
        unique, duplicates = monitoring.deduplicate_monitoring_rows(rows)
        self.assertEqual(len(unique), 2)
        self.assertEqual(duplicates, 0)

    def test_different_fixed_sources_remain_separate_at_ingestion(self):
        rows = [
            {
                "sourceId": "ncha",
                "date": "2026-09-03",
                "title": "同一文博事件",
                "url": "http://www.ncha.gov.cn/art/2026/9/3/art_722_1.html",
            },
            {
                "sourceId": "xinhua-wenbo",
                "date": "2026-09-03",
                "title": "同一文博事件",
                "url": "https://www.news.cn/20260903/event/c.html",
            },
        ]
        unique, duplicates = monitoring.deduplicate_monitoring_rows(rows)
        self.assertEqual(len(unique), 2)
        self.assertEqual(duplicates, 0)


if __name__ == "__main__":
    unittest.main()

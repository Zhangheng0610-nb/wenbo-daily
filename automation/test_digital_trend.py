#!/usr/bin/env python3
"""Regression tests for the daily digital-trend incremental merge."""
import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import digital_trend as trend


ROOT = Path(__file__).resolve().parents[1]


class IncrementalTrendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / 'digital-data.json').read_text(encoding='utf-8'))

    def digest_records(self):
        url = '/art/2026/8/31/art_722_204999.html'
        return [
            {
                'title': '一周文物动态摘编（8.25-8.31）',
                'source_page_title': '一周文物动态摘编（8.25-8.31）',
                'digest_title': '三维扫描记录遗址信息',
                'digest_body': '项目使用三维扫描记录遗址信息。',
                'date': date(2026, 8, 31), 'url': url, 'from_digest': True,
                'level': 'tech', 'matched_keywords': ['三维扫描'],
            },
            {
                'title': '一周文物动态摘编（8.25-8.31）',
                'source_page_title': '一周文物动态摘编（8.25-8.31）',
                'digest_title': '数字博物馆上线公共服务',
                'digest_body': '数字博物馆上线，为公众提供线上服务。',
                'date': date(2026, 8, 31), 'url': url, 'from_digest': True,
                'level': 'core', 'matched_keywords': ['数字博物馆'],
            },
        ]

    def test_new_digest_page_adds_page_and_two_items(self):
        old = copy.deepcopy(self.fixture)
        records = self.digest_records()
        data, added, duplicates = trend.merge_incremental_data(
            old, records, [{'date': date(2026, 8, 31), 'title': records[0]['title'], 'url': records[0]['url']}],
            date(2026, 8, 31), '2026-08-31T07:00:00+08:00',
            digest_extra_count=2, digest_article_count=1,
        )
        self.assertEqual(added, 2)
        self.assertEqual(duplicates, 0)
        self.assertEqual(data['stats']['content_item_count'], len(self.fixture['content_items']) + 2)
        self.assertEqual(data['stats']['digital_source_pages'], len(self.fixture['source_pages']) + 1)
        self.assertEqual(len(data['source_pages']), len(self.fixture['source_pages']) + 1)
        self.assertEqual(data['stats']['source_unique_pages'], self.fixture['stats']['source_unique_pages'] + 1)
        self.assertEqual(len({item['content_item_id'] for item in data['content_items']}), len(self.fixture['content_items']) + 2)
        topics = {item['display_title']: item['topics'] for item in data['content_items'][-2:]}
        self.assertEqual(topics['三维扫描记录遗址信息'], ['AI、三维扫描与科技考古'])
        self.assertEqual(topics['数字博物馆上线公共服务'], ['数字博物馆与公共服务'])

    def test_existing_page_and_item_are_not_added_twice(self):
        old = copy.deepcopy(self.fixture)
        records = self.digest_records()
        first, _, _ = trend.merge_incremental_data(
            old, records, [{'date': date(2026, 8, 31), 'title': records[0]['title'], 'url': records[0]['url']}],
            date(2026, 8, 31), '2026-08-31T07:00:00+08:00',
            digest_extra_count=2, digest_article_count=1,
        )
        second, added, duplicates = trend.merge_incremental_data(
            first, records, [], date(2026, 8, 31), '2026-08-31T07:01:00+08:00',
        )
        self.assertEqual(added, 0)
        self.assertEqual(duplicates, 2)
        self.assertEqual(second['stats']['content_item_count'], len(self.fixture['content_items']) + 2)
        self.assertEqual(second['stats']['digital_source_pages'], len(self.fixture['source_pages']) + 1)

    def test_digest_items_keep_separate_topic_evidence(self):
        entities = trend.content_item_entities(self.digest_records())
        entities = [dict(item, topics=trend.classify_topics(item['digest_title'] + item.get('digest_body', '')))
                     for item in entities]
        self.assertNotEqual(entities[0]['topics'], entities[1]['topics'])
        self.assertEqual(entities[0]['source_url'], entities[1]['source_url'])

    def test_iso_week_key_is_shared(self):
        for value, expected in (
            (date(2020, 12, 29), '2020-W53'),
            (date(2020, 12, 31), '2020-W53'),
            (date(2021, 1, 1), '2020-W53'),
            (date(2021, 1, 4), '2021-W01'),
        ):
            self.assertEqual(trend._source_bucket_key(value, 'week'), expected)

    def test_coverage_distinguishes_no_update_from_failure(self):
        old_dir = trend.DIGITAL_MONITOR_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            trend.DIGITAL_MONITOR_DIR = temp_dir
            try:
                no_update = trend._write_incremental_coverage(
                    date(2026, 8, 31), '2026-08-31T07:00:00+08:00',
                    window_start=date(2026, 8, 25), status='scan_success_no_update',
                )
                failed = trend._write_incremental_coverage(
                    date(2026, 9, 1), '2026-09-01T07:00:00+08:00',
                    window_start=date(2026, 8, 26), status='fetch_failed', fetch_failed=1,
                )
            finally:
                trend.DIGITAL_MONITOR_DIR = old_dir
        self.assertEqual(no_update['status'], 'scan_success_no_update')
        self.assertEqual(failed['status'], 'fetch_failed')
        self.assertNotEqual(no_update['status'], failed['status'])

    def test_fetch_failure_writes_failure_ledger(self):
        old_data_path = trend.DATA_PATH
        old_monitor_dir = trend.DIGITAL_MONITOR_DIR
        old_fetch = trend.fetch
        with tempfile.TemporaryDirectory() as temp_dir:
            trend.DATA_PATH = str(Path(temp_dir) / 'digital-data.json')
            trend.DIGITAL_MONITOR_DIR = str(Path(temp_dir) / 'monitor')
            trend.fetch = lambda *args, **kwargs: None
            try:
                with self.assertRaises(trend.IncrementalScanError):
                    trend.run_incremental(date(2026, 9, 2))
                ledger = json.loads((Path(temp_dir) / 'monitor' / '2026-09-02.json').read_text(encoding='utf-8'))
            finally:
                trend.fetch = old_fetch
                trend.DATA_PATH = old_data_path
                trend.DIGITAL_MONITOR_DIR = old_monitor_dir
        self.assertEqual(ledger['status'], 'fetch_failed')
        self.assertEqual(ledger['fetchFailed'], 1)


if __name__ == '__main__':
    unittest.main()

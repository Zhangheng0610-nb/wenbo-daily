"""Morning scans must recover yesterday without inventing yesterday's checks."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from automation import backfill_monitoring as monitoring
from automation import daily_discovery as discovery

class ContinuityTests(unittest.TestCase):
    def test_overlap_retains_publication_date_and_prior_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yesterday = monitoring.empty_day(date(2026, 9, 6))
            yesterday['coverage'][0].update(mode='operational', status='failed', checkedAt='2026-09-06T07:15:00+08:00')
            path = root / '2026-09-06.json'
            path.write_text(json.dumps(yesterday))
            rows = [monitoring.candidate('ncha', date(2026, 9, 6), '河北文物保护修缮工程完成', 'https://www.ncha.gov.cn/art/2026/9/6/art_722_1.html')]
            outcomes = {s: {'complete': True, 'status':'checked', 'rawCount':1, 'eligibleCount':1} for s, _ in monitoring.CRAWLERS}
            with patch.object(monitoring, 'MONITORING', root):
                monitoring.merge_write(date(2026,9,1), date(2026,9,7), rows, outcomes, mode='operational', checked_at='2026-09-07T07:15:00+08:00')
                monitoring.merge_write(date(2026,9,1), date(2026,9,7), rows, outcomes, mode='operational', checked_at='2026-09-07T08:15:00+08:00')
            recovered = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(recovered['coverage'], yesterday['coverage'])
            self.assertEqual(len(recovered['items']), 1)
            self.assertEqual(recovered['items'][0]['date'], '2026-09-06')
            self.assertEqual(recovered['items'][0]['observationDate'], '2026-09-07')
            self.assertEqual(recovered['items'][0]['observedAt'], '2026-09-07T07:15:00+08:00')
            self.assertEqual(json.loads((root/'2026-09-07.json').read_text(encoding='utf-8'))['scanAudit']['lateArrivalCount'], 1)
            self.assertFalse((root/'2026-09-01.json').exists())

    def test_radar_recovers_yesterday_without_redating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            today = {'date': '2026-09-07', 'runType': 'live', 'items': []}
            item = monitoring.as_record(monitoring.candidate('ncha', date(2026,9,6), '河北文物保护修缮工程完成', 'https://www.ncha.gov.cn/art/2026/9/6/art_722_1.html'), 1, origin='fixed-panel-monitoring', run_type='live')
            (root/'2026-09-07.json').write_text(json.dumps(today), encoding='utf-8')
            (root/'2026-09-06.json').write_text(json.dumps({'items': [item]}), encoding='utf-8')
            with patch.object(discovery, 'MONITORING_DIR', root), patch.object(discovery, 'ROOT', root):
                records, audit = discovery.load_fixed_panel_radar(date(2026,9,7))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['publishedDate'], '2026-09-06')
            self.assertEqual(audit['targetDate'], '2026-09-07')

    def test_mixed_origin_requires_real_later_observation(self):
        from automation.validate_project import is_late_observation
        record = {'origin': 'archive-backfill', 'observedAt': '2026-09-07T13:36:43+08:00', 'observationDate': '2026-09-07'}
        self.assertTrue(is_late_observation(record, '2026-09-06'))
        self.assertFalse(is_late_observation(record, '2026-09-07'))
        self.assertFalse(is_late_observation({'origin': 'archive-backfill'}, '2026-09-06'))
        self.assertFalse(is_late_observation(dict(record, observationDate='2026-09-08'), '2026-09-06'))

    def test_empty_or_undated_index_is_not_success(self):
        spec = discovery.SOURCE_SCANS[0]
        for page in ('<html>challenge</html>', '<a href="/news/story">考古新发现</a>'):
            with patch.object(discovery, 'fetch', return_value=page):
                status, rows = discovery.scan_page(spec, date(2026,9,1), date(2026,9,7))
            self.assertEqual(status['status'], 'parse_failed')
            self.assertEqual(rows, [])

    def test_unesco_visible_english_date_is_discoverable(self):
        page = '<a href="/en/articles/heritage-protection">News World Heritage protection 4 September 2026</a>'
        spec = next(s for s in discovery.SOURCE_SCANS if s['sourceId'] == 'unesco-news')
        with patch.object(discovery, 'fetch', return_value=page):
            status, rows = discovery.scan_page(spec, date(2026,9,1), date(2026,9,7))
        self.assertEqual(status['status'], 'checked')
        self.assertEqual(rows[0]['publishedDate'], '2026-09-04')
        self.assertIsNone(discovery.parse_date('31 February 2026'))

    def test_old_dated_index_is_valid_empty_window(self):
        with patch.object(discovery, 'fetch', return_value='<a href="/2026/08/01/a.html">文物保护</a>'):
            status, rows = discovery.scan_page(discovery.SOURCE_SCANS[0], date(2026,9,1), date(2026,9,7))
        self.assertEqual(status['status'], 'checked')
        self.assertEqual(status['outsideWindow'], 1)

if __name__ == '__main__':
    unittest.main()

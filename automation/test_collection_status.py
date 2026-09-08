import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from automation.ingestion_health import collection_observations
from automation import backfill_monitoring as monitor


class NewspaperCoverageTests(unittest.TestCase):
    def test_all_editions_and_dedup(self):
        root = 'http://www.zhongguowenwubao.com'
        article = '/portal/DigitPager/paperDetail/publishdate/2026-09-01/paperId/1/id/'
        edition = '/DigitPager/paper/id/2/publishdate/2026-09-01'
        first = f'<a href="{article}1">文物保护一</a><a href="{edition}">第二版</a>'
        second = f'<a href="{article}1">文物保护一</a><a href="{article}2">文物保护二</a>'
        with patch.object(monitor, 'fetch', side_effect=lambda url: second if '/paper/id/' in url else first):
            rows, complete, _ = monitor.crawl_cultural_relics_news(date(2026,9,1), date(2026,9,1))
        self.assertTrue(complete)
        self.assertEqual(len(rows), 2)

    def test_empty_shell_is_not_valid_no_issue(self):
        for page, expected in [('<html>challenge</html>', False), ('您请求的日期报纸不存在', True)]:
            with patch.object(monitor, 'fetch', return_value=page):
                rows, complete, _ = monitor.crawl_cultural_relics_news(date(2026,9,1), date(2026,9,1))
            self.assertEqual(complete, expected)
            self.assertEqual(rows, [])

    def test_failed_edition_retains_first_page_but_not_complete(self):
        first = '<a href="/DigitPager/paper/id/2/publishdate/2026-09-01">第二版</a><a href="/paperDetail/publishdate/2026-09-01/id/1">文物保护</a>'
        with patch.object(monitor, 'fetch', side_effect=[first, RuntimeError('timeout')]):
            rows, complete, _ = monitor.crawl_cultural_relics_news(date(2026,9,1), date(2026,9,1))
        self.assertEqual(len(rows), 1)
        self.assertFalse(complete)


class CollectionStatusTests(unittest.TestCase):
    def test_latest_failed_attempt_survives_and_replay_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for day, kind, status in [('08','live','success'),('09','live','failed'),('10','replay','success')]:
                p=root/'content/监测'/f'2026-09-{day}.json'
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({'coverage':[{'sourceId':'ncha','mode':'operational','runType':kind,'status':status,'checkedAt':f'2026-09-{day}T07:13:00+08:00'}]}),encoding='utf-8')
            self.assertEqual(collection_observations(root)['panel'][0]['status'],'failed')

    @unittest.skipUnless(shutil.which('node'), 'Node required for browser logic')
    def test_rebuild_failure_and_future_cannot_be_green(self):
        script = r"""
const assert=require('node:assert/strict');
const S=require('./lib/collection-status.js');
const now=new Date('2026-09-08T08:00:00+08:00');
const good=['success','no_update'];
assert.equal(S.attempt({checkedAt:'2026-09-08T07:13:00+08:00',status:'no_update'},now,good).level,'ready');
assert.equal(S.attempt({checkedAt:'2026-09-01T07:13:00+08:00',status:'success',generated:'2026-09-08'},now,good).level,'failed');
assert.equal(S.attempt({checkedAt:'2026-09-08T07:13:00+08:00',status:'failed'},now,good).level,'failed');
assert.equal(S.attempt({checkedAt:'2026-09-09T07:13:00+08:00',status:'success'},now,good).level,'failed');
assert.equal(S.assess({},['ncha'],now).level,'failed');
"""
        subprocess.run(['node','-e',script], cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True,text=True)

class CrossPlatformEvidenceTests(unittest.TestCase):
    def test_only_crlf_is_normalized_and_content_changes_still_fail(self):
        from automation.validate_candidates import _sha256
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'audit.json'
            p.write_bytes(b'{\n"event": 1\n}\n')
            canonical=_sha256(p,'lf-normalized-v1')
            p.write_bytes(b'{\r\n"event": 1\r\n}\r\n')
            self.assertEqual(canonical,_sha256(p,'lf-normalized-v1'))
            self.assertNotEqual(canonical,_sha256(p))
            p.write_bytes(b'{\r\n"event": 2\r\n}\r\n')
            self.assertNotEqual(canonical,_sha256(p,'lf-normalized-v1'))
            with self.assertRaises(ValueError):
                _sha256(p,'ignore-everything')

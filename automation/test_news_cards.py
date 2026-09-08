from datetime import date
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from automation import daily_discovery as D

class OfficialNewsCardsTests(unittest.TestCase):
    def test_month_forms_and_invalid_dates(self):
        for value in ['September 3, 2026','3 September 2026','3 Sep 2026','Sep. 3, 2026']:
            self.assertEqual(D.parse_date(value),date(2026,9,3))
        self.assertIsNone(D.parse_date('February 30, 2026'))

    def test_iccrom_date_stays_with_card_and_undated_not_inherited(self):
        spec=next(s for s in D.SOURCE_SCANS if s['sourceId']=='iccrom-news')
        page='<article class="node--type-news"><a href="/news/one"></a><div class="date">3 Sep 2026</div><h3>Heritage protection</h3><p>Event held 2 July 2020</p></article><article class="node--type-news"><a href="/news/two"></a><h3>Undated museum news</h3></article>'
        with patch.object(D,'fetch',return_value=page):
            status,rows=D.scan_page(spec,date(2026,9,2),date(2026,9,8))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['publishedDate'],'2026-09-03')
        self.assertEqual(rows[0]['publicationDateBasis'],'source_listing')
        self.assertNotIn('articleVerified',rows[0])
        self.assertEqual(status['undatedLinks'],1)

    def test_icom_future_external_and_navigation_excluded(self):
        spec=next(s for s in D.SOURCE_SCANS if s['sourceId']=='icom-news')
        page='<a href="/en/news/ok/" class="news-abstract"><p>September 3, 2026</p><h2>AI in museums</h2></a><a href="/en/news/future/" class="news-abstract"><p>September 9, 2026</p><h2>Future</h2></a><a href="https://other.test/news/" class="news-abstract"><p>September 3, 2026</p><h2>Offsite</h2></a><a href="/en/news/">September 8, 2026 navigation</a>'
        with patch.object(D,'fetch',return_value=page):
            status,rows=D.scan_page(spec,date(2026,9,2),date(2026,9,8))
        self.assertEqual([r['title'] for r in rows],['AI in museums'])
        self.assertEqual(status['latestPublishedDate'],'2026-09-03')
        self.assertEqual(status['outsideWindow'],1)

class RadarBridgeTests(unittest.TestCase):
    def test_missing_today_does_not_hide_recent_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'2026-09-06.json'
            base={'recordId':'one','date':'2026-09-06','title':'数字文物保护','origin':'archive-backfill','observedAt':'2026-09-07T07:13:00+08:00','observationDate':'2026-09-07','sources':[{'url':'https://www.ncha.gov.cn/art/2026/9/6/one.html'}]}
            p.write_text(json.dumps({'items':[base]}),encoding='utf-8')
            with patch.object(D,'ROOT',root),patch.object(D,'MONITORING_DIR',root):
                rows,audit=D.load_fixed_panel_radar(date(2026,9,8))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['publishedDate'],'2026-09-06')
            self.assertFalse(audit['todayAvailable'])
            self.assertEqual(audit['status'],'scan_success_with_update')

    def test_archive_without_real_observation_and_future_replay_excluded(self):
        base={'recordId':'one','date':'2026-09-06','title':'文物保护','origin':'archive-backfill','sources':[{'url':'https://www.ncha.gov.cn/one.html'}]}
        for extra in [{},{'observedAt':'2026-09-09T07:13:00+08:00','observationDate':'2026-09-09'}, {'observedAt':'2026-09-07junk','observationDate':'2026-09-07'}, {'observedAt':'2026-09-07T07:13:00+08:00','observationDate':'2026-09-07','runType':'replay'}]:
            rows,_=D.fixed_panel_radar_records(date(2026,9,6),{'items':[dict(base,**extra)]},observation_cutoff=date(2026,9,8))
            self.assertEqual(rows,[])

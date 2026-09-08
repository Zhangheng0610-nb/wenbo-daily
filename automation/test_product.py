"""Regression checks for application evidence and the shared publishing layer."""
from datetime import datetime
from pathlib import Path
import unittest
from build import parse_jobs, build_jobs_html, extract_deadline_datetime
from automation.recruitment_dates import application_status
from automation.product import decorate, safe_url

ROOT = Path(__file__).resolve().parents[1]

class ProductTests(unittest.TestCase):
    def test_application_window_is_not_publication_or_payment_date(self):
        now = datetime.fromisoformat('2026-09-06T12:00:00+08:00')
        self.assertEqual(application_status('2026-09-15 至 2026-10-20', now)[0], 'upcoming')
        self.assertEqual(extract_deadline_datetime('2026-09-11 18:00（缴费至2026-09-13 24:00）'), '2026-09-11T18:00:00+08:00')
        self.assertIsNone(extract_deadline_datetime('2026-09-01发布'))
        self.assertIsNone(extract_deadline_datetime('2026-02-31'))
        self.assertIsNone(extract_deadline_datetime('2026-09-13 17:00（当地时间）'))

    def test_london_summer_and_winter_deadlines(self):
        self.assertEqual(extract_deadline_datetime('2026-09-13 17:00（英国时间）'), '2026-09-13T17:00:00+01:00')
        self.assertEqual(extract_deadline_datetime('2026-12-13 17:00（英国时间）'), '2026-12-13T17:00:00+00:00')
        now = datetime.fromisoformat('2026-09-13T18:00:00+08:00')
        self.assertEqual(application_status('2026-09-13 17:00（英国时间）', now)[0], 'open')

    def test_real_recruitment_preserves_application_and_secondary_evidence(self):
        data = parse_jobs(ROOT/'content/招聘/jobs.md')
        items = [i for s in data['sections'] for i in s['items']]
        palace = next(i for i in items if i['institution']=='故宫博物院')
        self.assertEqual(palace['deadline'], '2026-09-15 至 2026-10-20')
        self.assertIn('gugongboshihou@dpm.org.cn', palace['application'])
        gansu = next(i for i in items if i['institution']=='甘肃省省直文博单位')
        self.assertEqual(len(gansu['links']),2)
        html=build_jobs_html(data)
        self.assertIn('wwj.gansu.gov.cn',html)
        self.assertIn('不提供签证担保',html)

    def test_unsafe_job_content_cannot_create_markup(self):
        data = parse_jobs(ROOT/'content/招聘/jobs.md')
        item=data['sections'][0]['items'][0]
        item['institution']='<script>alert(1)</script>'
        item['link_url']='javascript:alert(1)'
        html=build_jobs_html(data)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertNotIn('href="javascript:',html)
        self.assertEqual(safe_url('https://example.org/a'), 'https://example.org/a')

    def test_nested_routes_and_idempotent_shell(self):
        base='<html><head><title>测试</title></head><body><main>正文</main><footer></footer></body></html>'
        html=decorate(base,'reports/2026-09-06.html')
        self.assertRegex(html, r'href="../assets/product\.css\?v=[0-9a-f]{12}"')
        self.assertIn('href="../jobs.html"',html)
        self.assertEqual(html.count('id="product-main"'),1)
        self.assertEqual(decorate(html,'reports/2026-09-06.html'),html)

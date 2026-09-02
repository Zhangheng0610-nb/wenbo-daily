"""Regression tests for daily report section labels and render order."""
import re
import tempfile
import unittest
from pathlib import Path

from build import (
    _daily_render_section,
    _daily_section_label,
    build_report_html,
    parse_md,
)


ROOT = Path(__file__).resolve().parents[1]


class DailyReportRenderingTests(unittest.TestCase):
    def test_scope_display_mapping_keeps_regional_and_international_distinct(self):
        self.assertEqual(_daily_render_section('domestic'), 'domestic')
        self.assertEqual(_daily_render_section('regional'), 'international')
        self.assertEqual(_daily_render_section('international'), 'international')
        self.assertEqual(_daily_section_label('domestic'), '🇨🇳 国内要闻')
        self.assertEqual(_daily_section_label('regional'), '🌏 国际/区域交流')
        self.assertEqual(_daily_section_label('international'), '🌏 国际/区域交流')

    def test_explicit_toc_is_the_single_editorial_order(self):
        path = ROOT / 'content' / '日报' / '2026-09-02.md'
        markdown = path.read_text(encoding='utf-8')
        self.assertIn('## 🇨🇳 国内要闻', markdown)
        self.assertIn('## 🌏 国际/区域交流', markdown)
        self.assertNotIn('## 🌍 国际要闻', markdown)
        data = parse_md(path)
        expected_titles = [
            '云南楚雄立法保护元谋人遗址 条例今起施行',
            '中埃联合考古队在塞赫迈特神庙遗址发现重要遗迹',
            '彭丽媛同吉尔吉斯斯坦总统扎帕罗夫夫人扎帕罗娃参观吉尔吉斯共和国国家历史博物馆',
            '上海文物局发文加强博物馆陈列展览内容审核工作，明确核查重点',
            '美国“9·11”国家纪念博物馆推出25周年特展',
        ]
        self.assertEqual([item['title'] for item in data['ordered_items']], expected_titles)
        self.assertEqual(
            [item['id'] for item in data['ordered_items']],
            [item['id'] for item in data['toc_items']],
        )

    def test_mixed_scope_html_uses_same_labels_and_order(self):
        items = [
            {'id': 'item1', 'number': 1, 'title': '国内事项', 'section': 'domestic', 'sources': [], 'tags': [], 'body': 'a', 'commentary': ''},
            {'id': 'item2', 'number': 2, 'title': '区域事项', 'section': 'regional', 'sources': [], 'tags': [], 'body': 'b', 'commentary': ''},
            {'id': 'item3', 'number': 3, 'title': '国际事项', 'section': 'international', 'sources': [], 'tags': [], 'body': 'c', 'commentary': ''},
        ]
        data = {
            'title': '每日文博资讯 | 2026-09-03',
            'date': '2026-09-03',
            'weekday': '周四',
            'domestic': [items[0]],
            'international': [items[1], items[2]],
            'ordered_items': items,
            'toc_items': [{'id': item['id'], 'title': item['title']} for item in items],
            'trends': [],
            'notes': [],
            'date_modified': None,
            'domestic_count': 1,
            'international_count': 2,
        }
        html = build_report_html(data)
        self.assertEqual(re.findall(r'<h3 id="(item\d+)">', html), ['item1', 'item2', 'item3'])
        self.assertEqual(re.findall(r'href="#(item\d+)"', html), ['item1', 'item2', 'item3'])
        self.assertEqual(html.count('🇨🇳 国内要闻'), 1)
        self.assertEqual(html.count('🌏 国际/区域交流'), 1)
        self.assertNotIn('国际要闻</h2>', html)

    def test_historical_fixtures_keep_body_and_toc_order(self):
        for name in ('2026-08-28.md', '2026-08-30.md'):
            path = ROOT / 'content' / '日报' / name
            data = parse_md(path)
            expected_ids = [item['id'] for item in data['ordered_items']]
            html = build_report_html(data)
            self.assertEqual(re.findall(r'<h3 id="(item\d+)">', html), expected_ids, name)
            self.assertEqual(re.findall(r'href="#(item\d+)"', html), expected_ids, name)


if __name__ == '__main__':
    unittest.main()

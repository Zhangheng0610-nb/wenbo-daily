"""Regression tests for daily report section labels and render order."""
import re
import tempfile
import unittest
from pathlib import Path

from build import (
    _daily_render_section,
    _daily_section_label,
    build_report_html,
    build_homepage,
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

    def test_international_display_title_is_separate_from_original_title(self):
        markdown = """# 🏛️ 每日文博资讯 | 2026年09月04日（周五）

---
## 📑 目录
1. [特朗普政府威胁切断联邦机构对史密森学会的支持](#item1)

---
## 🌏 国际/区域交流

<!-- originalTitle: Trump administration threatens to cut federal agencies' support for Smithsonian -->
### 1. 特朗普政府威胁切断联邦机构对史密森学会的支持
📎 [ABC News: Trump admin threatens support for Smithsonian](https://abcnews.com/article)

ABC News报道史密森学会相关公共文化政策变化。

> **点评：** 联邦支持安排会影响国家级博物馆的借展、采购与公共服务。
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '2026-09-04.md'
            path.write_text(markdown, encoding='utf-8')
            data = parse_md(path)

        item = data['ordered_items'][0]
        self.assertEqual(item['displayTitle'], '特朗普政府威胁切断联邦机构对史密森学会的支持')
        self.assertEqual(item['title'], item['displayTitle'])
        self.assertEqual(item['originalTitle'], "Trump administration threatens to cut federal agencies' support for Smithsonian")
        html = build_report_html(data)
        self.assertIn('###', markdown)  # the source remains Markdown, not a renderer translation
        self.assertIn('1. 特朗普政府威胁切断联邦机构对史密森学会的支持', html)
        self.assertNotIn('<h3 id="item1">1. Trump administration', html)
        self.assertIn('ABC News: Trump admin threatens support for Smithsonian', html)

    def test_chinese_canonical_title_is_not_relocalized(self):
        markdown = """# 🏛️ 每日文博资讯 | 2026年09月04日（周五）

---
## 🌏 国际/区域交流

### 1. 中国建筑师马岩松主持设计的卢卡斯叙事艺术博物馆将在洛杉矶开馆
中文来源：内容。
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '2026-09-04.md'
            path.write_text(markdown, encoding='utf-8')
            item = parse_md(path)['ordered_items'][0]
        self.assertEqual(item['displayTitle'], item['originalTitle'])
        self.assertEqual(item['displayTitle'], '中国建筑师马岩松主持设计的卢卡斯叙事艺术博物馆将在洛杉矶开馆')

    def test_homepage_consumes_the_same_display_title(self):
        item = {
            'id': 'item1', 'number': 1,
            'title': '特朗普政府威胁切断联邦机构对史密森学会的支持',
            'displayTitle': '特朗普政府威胁切断联邦机构对史密森学会的支持',
            'originalTitle': "Trump administration threatens to cut federal agencies' support for Smithsonian",
            'section': 'international', 'sources': [], 'tags': [], 'body': '正文', 'commentary': ''
        }
        report = {
            'date': '2026-09-04', 'weekday': '周五', 'title': '每日文博资讯 | 2026-09-04',
            'domestic': [], 'international': [item], 'ordered_items': [item],
            'toc_items': [{'id': 'item1', 'title': item['displayTitle']}],
            'trends': [], 'notes': [], 'date_modified': None,
            'domestic_count': 0, 'international_count': 1,
        }
        html = build_homepage([report], [], [], None, None)
        self.assertIn('特朗普政府威胁切断联邦机构对史密森学会的支持', html)
        self.assertNotIn('Trump administration threatens to cut federal agencies', html)


if __name__ == '__main__':
    unittest.main()

"""Regression tests for the static archive search matching rules."""
import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SearchTests(unittest.TestCase):
    def _node(self):
        bundled = Path(r"C:\Users\张衡\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
        return str(bundled) if bundled.exists() else "node"

    def _run_render_search(self, query, expected_fragment='reports/2026-08-29.html#item3', params=''):
        source = (ROOT / "search.html").read_text(encoding="utf-8")
        script = r'''
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[1], 'utf8');
const scriptStart = html.lastIndexOf('<script>');
const scriptEnd = html.indexOf('</script>', scriptStart);
if (scriptStart < 0 || scriptEnd < 0) throw new Error('search script missing');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {value: '', textContent: '', innerHTML: ''});
  return elements.get(id);
}
const context = {
  console,
  URLSearchParams,
  location: {search: process.argv[4] || ''},
  Set,
  Array,
  Math,
  RegExp,
  String,
  Boolean,
  document: {
    getElementById: element,
    querySelectorAll: () => []
  },
  fetch: () => Promise.resolve({ok: true, json: () => Promise.resolve([])})
};
vm.createContext(context);
vm.runInContext(html.slice(scriptStart + '<script>'.length, scriptEnd), context);
const data = [{
  path: 'reports/2026-08-29.html',
  date: '2026-08-29',
  type: 'daily',
      items: [{
        id: 'item3',
        title: '中外联合考古工作会议在长春召开',
        displayTitle: '中外联合考古工作会议在长春召开',
        originalTitle: 'Sino-foreign joint archaeology conference held in Changchun',
        body: '长春考古会议发布行业信息。',
        tags: ['政策行业', '考古'],
        sources: [{name: '测试来源', url: 'https://example.com/source'}]
      }, {
        id: 'item-smithsonian',
        title: '特朗普政府威胁切断联邦机构对史密森学会的支持',
        displayTitle: '特朗普政府威胁切断联邦机构对史密森学会的支持',
        originalTitle: 'Trump administration threatens to cut federal agencies support for Smithsonian',
        body: '史密森学会联邦支持安排发生变化。',
        tags: ['博物馆治理'],
        sources: [{name: 'ABC News original English headline', url: 'https://example.com/abc'}]
      }]
}];
data.push({...data[0],date:'2026-09-05',path:'reports/2026-09-05.html',items:[{...data[0].items[0],title:'新增行业动态',body:'长春考古会议后续消息'}]});
context.renderSearch(data, process.argv[2]);
const result = element('results');
if (!result.innerHTML.includes(process.argv[3])) throw new Error('expected result missing');
process.stdout.write(result.innerHTML);
'''
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [self._node(), "-e", script, str(ROOT / "search.html"), query, expected_fragment, params],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        ).stdout

    def test_date_range_is_inclusive_and_does_not_return_older_issues(self):
        output = self._run_render_search('考古', 'reports/2026-09-05.html#item3', '?from=2026-09-05&to=2026-09-05')
        self.assertNotIn('reports/2026-08-29.html', output)

    def test_sort_switch_changes_order_without_losing_matches(self):
        latest = self._run_render_search('考古')
        relevance = self._run_render_search('考古', params='?sort=relevance')
        self.assertLess(latest.index('2026-09-05.html'), latest.index('2026-08-29.html'))
        self.assertLess(relevance.index('2026-08-29.html'), relevance.index('2026-09-05.html'))

    def test_empty_query_browses_and_inverted_dates_show_recovery(self):
        self.assertIn('2026-09-05.html', self._run_render_search(''))
        self.assertIn('请调整收录日期范围', self._run_render_search('', '请调整收录日期范围', '?from=2026-09-06&to=2026-09-01'))
        self.assertIn('2026-08-29.html', self._run_render_search('考古', params='?type=invalid&from=2026-02-31'))

    def test_render_search_queries_do_not_throw_and_return_expected_item(self):
        for query in ("政策行业", "长春考古会议", "考古", "长春考古会议"):
            output = self._run_render_search(query)
            self.assertIn("reports/2026-08-29.html#item3", output)

    def test_render_search_passes_query_groups_to_matches(self):
        source = (ROOT / "search.html").read_text(encoding="utf-8")
        self.assertIn("if (!matches(itemText(item), groups)) return;", source)
        self.assertNotIn("matches(itemText(item), words)", source)
        self.assertIn("const groups = queryGroups(query);", source)

    def test_render_errors_are_distinguished_from_index_load_errors(self):
        source = (ROOT / "search.html").read_text(encoding="utf-8")
        self.assertIn("Search rendering failed:", source)
        self.assertIn("搜索功能运行异常，请刷新重试。", source)
        self.assertIn("Search index loading failed:", source)
        self.assertIn("搜索索引暂时不可用。", source)

    def test_generated_search_keeps_report_identity_for_duplicate_titles(self):
        source = (ROOT / "search.html").read_text(encoding="utf-8")
        self.assertIn("const key = record.path + '#' + (item.id || compact(item.title));", source)
        self.assertIn("保留不同报告记录", source)

    def test_complete_phrase_does_not_match_only_a_generic_fragment(self):
        for query in ('长春考古会议', '长春 考古 会议', '中外联合考古'):
            self.assertIn('reports/2026-08-29.html#item3', self._run_render_search(query))
        # Sharing 考古/会议 does not make a different institution/city a hit.
        for query in ('北京考古会议', '长春 博物馆'):
            self.assertIn('没有找到匹配条目', self._run_render_search(query, '没有找到匹配条目'))

    def test_history_index_contains_longchun_record(self):
        payload = json.loads((ROOT / "search-index.json").read_text(encoding="utf-8"))
        matches = []
        for record in payload:
            for item in record.get("items") or []:
                if item.get("title") == "中外联合考古工作会议在长春召开":
                    matches.append((record.get("date"), record.get("path"), item.get("id")))
        self.assertTrue(any(row[0] == "2026-08-29" for row in matches), matches)

    def test_original_english_title_is_searchable_while_display_stays_chinese(self):
        output = self._run_render_search('Smithsonian', 'reports/2026-08-29.html#item-smithsonian')
        self.assertIn('reports/2026-08-29.html#item-smithsonian', output)
        self.assertIn('特朗普政府威胁切断联邦机构对史密森学会的支持', output)
        self.assertNotIn('Trump administration threatens to cut federal agencies support for Smithsonian', output)

    def test_generated_search_index_keeps_display_and_original_title_fields(self):
        payload = json.loads((ROOT / 'search-index.json').read_text(encoding='utf-8'))
        item = next(
            item for record in payload if record.get('path') == 'reports/2026-09-04.html'
            for item in record.get('items', []) if '史密森' in item.get('title', '')
        )
        self.assertEqual(item['title'], '特朗普政府威胁切断联邦机构对史密森学会的支持')
        self.assertEqual(item.get('displayTitle', item['title']), item['title'])
        self.assertEqual(item['originalTitle'], "Trump administration threatens to cut federal agencies' support for Smithsonian")


if __name__ == "__main__":
    unittest.main()

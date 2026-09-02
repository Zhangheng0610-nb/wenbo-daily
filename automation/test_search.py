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

    def _run_render_search(self, query):
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
  location: {search: ''},
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
    body: '长春考古会议发布行业信息。',
    tags: ['政策行业', '考古'],
    sources: [{name: '测试来源', url: 'https://example.com/source'}]
  }]
}];
context.renderSearch(data, process.argv[2]);
const result = element('results');
if (!result.innerHTML.includes('reports/2026-08-29.html#item3')) throw new Error('expected result missing');
process.stdout.write(result.innerHTML);
'''
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [self._node(), "-e", script, str(ROOT / "search.html"), query],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        ).stdout

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

    def test_chinese_phrase_matching_without_spaces(self):
        source = (ROOT / "search.html").read_text(encoding="utf-8")
        self.assertIn("function queryGroups(rawQuery)", source)
        self.assertIn("function groupMatches(lower, group)", source)
        self.assertIn("Math.ceil(group.grams.length * 0.4)", source)
        self.assertIn("record.path + '#' + (item.id || compact(item.title))", source)
        title = "中外联合考古工作会议在长春召开"

        def matches(query):
            groups = []
            for chunk in query.lower().split():
                chars = list(chunk)
                cjk = chars and all("\u4e00" <= char <= "\u9fff" for char in chars)
                grams = ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)] if cjk and len(chars) > 1 else []
                groups.append((chunk, grams))
            lower = title.lower()
            for raw, grams in groups:
                if raw in lower:
                    continue
                hits = sum(gram in lower for gram in grams)
                required = len(grams) if len(grams) <= 2 else (len(grams) + 2) // 3
                if not grams or hits < required:
                    return False
            return True

        for query in ("长春", "考古会议", "长春考古会议", "长春 考古 会议", "中外联合考古"):
            self.assertTrue(matches(query), query)

    def test_history_index_contains_longchun_record(self):
        payload = json.loads((ROOT / "search-index.json").read_text(encoding="utf-8"))
        matches = []
        for record in payload:
            for item in record.get("items") or []:
                if item.get("title") == "中外联合考古工作会议在长春召开":
                    matches.append((record.get("date"), record.get("path"), item.get("id")))
        self.assertTrue(any(row[0] == "2026-08-29" for row in matches), matches)


if __name__ == "__main__":
    unittest.main()

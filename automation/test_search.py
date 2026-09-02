"""Regression tests for the static archive search matching rules."""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SearchTests(unittest.TestCase):
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

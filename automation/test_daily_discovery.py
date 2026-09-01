"""Regression tests for daily discovery and legacy evidence isolation."""
import unittest
from unittest.mock import patch

from automation.daily_discovery import (
    SOURCE_SCANS,
    aggregate_event_candidates,
    build_final_editorial_pool,
    duplicate_relation,
    evidence_upgrade_queries,
    editorial_priority,
    is_relevant_record,
    load_history,
    metadata_urls,
    parse_date,
    resolve_evidence_attempt,
    run_evidence_upgrade,
    run,
    unwrap_redirect_url,
)


class DailyDiscoveryTests(unittest.TestCase):
    def test_date_parser_accepts_common_public_url_forms(self):
        self.assertEqual(parse_date("https://example.test/2026/8/31/article"), __import__("datetime").date(2026, 8, 31))
        self.assertEqual(parse_date("https://example.test/20260831/a"), __import__("datetime").date(2026, 8, 31))

    def test_same_day_duplicate(self):
        a = {"title": "某遗址公布新发现", "url": "https://a.test/1", "publishedDate": "2026-08-31", "entity": "某遗址", "eventType": "archaeology"}
        b = {"title": "某遗址发布考古新成果", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "某遗址", "eventType": "archaeology"}
        self.assertEqual(duplicate_relation(b, a)[0], "same_day_duplicate")

    def test_historical_duplicate(self):
        old = {"title": "某遗址公布新发现", "url": "https://a.test/1", "publishedDate": "2026-08-30", "entity": "某遗址", "eventType": "archaeology"}
        new = {"title": "媒体报道某遗址考古情况", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "某遗址", "eventType": "archaeology"}
        self.assertEqual(duplicate_relation(new, old)[0], "historical_duplicate")

    def test_policy_variants_share_named_instrument_identity(self):
        old = {"title": "文化和旅游部修订《博物馆藏品管理办法》：六章六十三条", "url": "https://a.test/1", "publishedDate": "2026-08-29"}
        new = {"title": "《博物馆藏品管理办法》政策解读", "url": "https://b.test/2", "publishedDate": "2026-08-31"}
        self.assertEqual(duplicate_relation(new, old)[0], "historical_duplicate")

    def test_historical_title_shortening_matches_published_event(self):
        old = {
            "title": "中国语言资源保护工程成果展示馆开馆：全球首座语言资源主题馆落子长沙",
            "body": "8月24日，中国语言资源保护工程成果展示馆在湖南省博物馆开馆。",
            "url": "https://a.test/1",
            "publishedDate": "2026-08-26",
        }
        new = {
            "title": "中国语言资源保护工程成果展示馆开馆",
            "url": "https://b.test/2",
            "publishedDate": "2026-09-01",
        }
        self.assertEqual(duplicate_relation(new, old)[0], "historical_duplicate")

    def test_same_entity_new_database_is_not_opening_duplicate(self):
        old = {
            "title": "中国语言资源保护工程成果展示馆开馆",
            "url": "https://a.test/1",
            "publishedDate": "2026-08-26",
        }
        new = {
            "title": "中国语言资源保护工程成果展示馆发布新数据库",
            "url": "https://b.test/2",
            "publishedDate": "2026-09-01",
        }
        self.assertIsNone(duplicate_relation(new, old))

    def test_same_institution_different_security_event_is_not_opening_duplicate(self):
        old = {
            "title": "中国国家博物馆新馆开馆",
            "url": "https://a.test/1",
            "publishedDate": "2026-08-26",
        }
        new = {
            "title": "中国国家博物馆发生藏品失窃",
            "url": "https://b.test/2",
            "publishedDate": "2026-09-01",
        }
        self.assertIsNone(duplicate_relation(new, old))

    def test_published_daily_is_the_historical_authority(self):
        history = load_history(__import__("datetime").date(2026, 9, 1))
        current = {
            "title": "中国语言资源保护工程成果展示馆开馆",
            "url": "https://new.test/language-hall",
            "publishedDate": "2026-09-01",
        }
        matches = [
            (relation, row)
            for row in history
            if (relation := duplicate_relation(current, row))
            and relation[0] == "historical_duplicate"
            and "语言资源保护工程成果展示馆" in row.get("title", "")
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1].get("historicalSource"), "published_daily_markdown")

    def test_final_editorial_pool_is_event_level_and_publishable_only(self):
        pool = build_final_editorial_pool({
            "pool": [
                {"eventId": "event-a", "title": "A", "candidateDisposition": "evidence_qualified"},
                {"eventId": "event-b", "title": "B", "candidateDisposition": "needs_verification"},
                {"eventId": "event-a", "title": "A duplicate report", "candidateDisposition": "evidence_qualified"},
            ]
        }, historical_duplicate_count=2)
        self.assertEqual(pool["rawQualifiedEvents"], 2)
        self.assertEqual(pool["canonicalUniqueEvents"], 1)
        self.assertEqual(pool["historicalDuplicates"], 2)
        self.assertEqual(pool["editoriallyReviewed"], 0)
        self.assertTrue(all(row.get("candidateDisposition") == "evidence_qualified" for row in pool["events"]))

    def test_new_development_is_not_suppressed(self):
        old = {"title": "某展览即将开展", "url": "https://a.test/1", "publishedDate": "2026-08-30", "entity": "某展览", "eventType": "exhibition"}
        new = {"title": "某展览正式开幕", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "某展览", "eventType": "exhibition"}
        self.assertEqual(duplicate_relation(new, old)[0], "new_development")

    def test_different_sites_are_not_duplicates(self):
        a = {"title": "甲遗址发现古墓", "url": "https://a.test/1", "publishedDate": "2026-08-31", "entity": "甲遗址", "eventType": "archaeology"}
        b = {"title": "乙遗址发现古墓", "url": "https://b.test/2", "publishedDate": "2026-08-31", "entity": "乙遗址", "eventType": "archaeology"}
        self.assertIsNone(duplicate_relation(b, a))

    def test_museum_exhibition_vocabulary_counts_as_relevant(self):
        self.assertTrue(is_relevant_record({"title": "某文明大展落幕 接待访客逾67万人次"}))

    def test_editorial_priority_is_independent_of_source_tier(self):
        important = editorial_priority({"title": "某遗址发现重要考古新成果", "sourceDomain": "news.google.com"})
        routine = editorial_priority({"title": "某博物馆官网发布周末讲座安排", "sourceDomain": "museum.example"})
        self.assertGreater(important["score"], routine["score"])
        self.assertIn(important["label"], {"medium", "high"})

    def test_routine_activity_does_not_erase_substantive_discovery(self):
        result = editorial_priority({"title": "某遗址考古发掘成果发布暨专家讲座"})
        self.assertIn("substantive_archaeological_discovery_or_new_knowledge", result["reasons"])
        self.assertNotEqual(result["label"], "low")

    def test_heritage_recognition_is_relevant_and_prioritized(self):
        record = {"title": "某地获批国家历史文化名城"}
        self.assertTrue(is_relevant_record(record))
        result = editorial_priority(record)
        self.assertIn("heritage_recognition_or_world_heritage_update", result["reasons"])

    def test_archaeological_research_result_gets_substantive_signal(self):
        result = editorial_priority({"title": "某遗址研究揭示古人类迁徙新认识"})
        self.assertIn("substantive_archaeological_discovery_or_new_knowledge", result["reasons"])

    def test_syndicated_reports_share_one_event_candidate(self):
        events = aggregate_event_candidates([
            {"title": "香港“古埃及文明大展”落幕 接待访客逾67万人次 - chinanews.com.cn", "url": "https://a.test/1", "publishedDate": "2026-08-31", "scope": "domestic", "discoverySourceType": "query_search"},
            {"title": "「古埃及文明大展」闭幕 9个半月逾67万访客 - 星島頭條", "url": "https://b.test/2", "publishedDate": "2026-08-31", "scope": "domestic", "discoverySourceType": "query_search"},
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reportCount"], 2)

    def test_shortened_event_title_stays_in_same_event_group(self):
        events = aggregate_event_candidates([
            {"title": "香港古埃及文明大展落幕", "url": "https://a.test/1", "publishedDate": "2026-08-31", "scope": "domestic"},
            {"title": "古埃及展迎来67万访客", "url": "https://b.test/2", "publishedDate": "2026-09-01", "scope": "domestic"},
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reportCount"], 2)

    def test_generic_policy_or_archaeology_words_do_not_merge_events(self):
        events = aggregate_event_candidates([
            {"title": "重庆市文物事业发展十五五规划征求意见", "url": "https://a.test/1", "publishedDate": "2026-08-31", "scope": "domestic"},
            {"title": "博物馆藏品管理办法正式施行", "url": "https://b.test/2", "publishedDate": "2026-08-31", "scope": "domestic"},
        ])
        self.assertEqual(len(events), 2)

    def test_event_id_collision_is_resolved_without_merging_reports(self):
        events = aggregate_event_candidates([
            {"title": "政策解读", "url": "https://a.test/1", "publishedDate": "2026-08-31", "scope": "domestic"},
            {"title": "政策解读", "url": "https://b.test/2", "publishedDate": "2026-08-31", "scope": "domestic"},
        ])
        self.assertEqual(len(events), 2)
        self.assertEqual(len({event["eventId"] for event in events}), 2)

    @patch("automation.daily_discovery._execute_one_query")
    @patch("automation.daily_discovery.resolve_evidence_url")
    def test_evidence_upgrade_executes_and_qualifies_event(self, resolve_url, execute_query):
        execute_query.return_value = ([{
            "title": "香港古埃及文明大展落幕 接待访客逾67万人次",
            "url": "https://news.google.com/rss/articles/test",
            "publishedDate": "2026-08-31",
        }], {"actualQuery": "香港古埃及文明大展 官方原文", "executedAt": "2026-09-01T07:00:00+08:00", "success": True, "returnedResultCount": 1, "acceptedRawCount": 1})
        resolve_url.return_value = ("https://www.chinanews.com.cn/dwq/2026/08-31/10687546.shtml", "香港古埃及文明大展落幕，接待访客逾67万人次。", None)
        event = {
            "eventId": "event-test",
            "title": "香港古埃及文明大展落幕",
            "representativeTitle": "香港古埃及文明大展落幕",
            "publishedDate": "2026-08-31",
            "scope": "domestic",
            "candidateDisposition": "needs_verification",
            "editorialPriorityLabel": "high",
            "editorialPriorityScore": 76,
        }
        result = run_evidence_upgrade(__import__("datetime").date(2026, 9, 1), [event])
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["qualified"], 1)
        self.assertTrue(event["evidenceUpgradeAttempted"])
        self.assertEqual(event["evidenceUpgradeResult"], "qualified")
        self.assertEqual(event["evidenceTierAfterUpgrade"], "A")

    def test_syndicated_english_titles_are_event_duplicates(self):
        a = {"title": "Egyptian queen's 673-diamond necklace stolen from Vienna museum", "url": "https://a.test/1", "publishedDate": "2026-08-30"}
        b = {"title": "Thieves plunder 673 diamond necklace from Vienna Museum", "url": "https://b.test/2", "publishedDate": "2026-08-31"}
        self.assertEqual(duplicate_relation(b, a)[0], "historical_duplicate")

    def test_evidence_queries_prefer_named_event_anchor_over_metrics(self):
        queries = evidence_upgrade_queries({
            "representativeTitle": "香港“古埃及文明大展”落幕 接待访客逾67万人次 170种文创带来超3300万收入",
            "scope": "domestic",
            "sourceDomains": ["chinanews.com.cn"],
        })
        self.assertIn("古埃及文明大展", queries)
        self.assertIn("site:chinanews.com.cn 古埃及文明大展", queries)
        anchor_queries = [query for query in queries if query.startswith("site:") or query == "古埃及文明大展"]
        self.assertFalse(any("种文创" in query or "万人次" in query for query in anchor_queries))

    def test_bing_redirect_unwraps_only_embedded_http_target(self):
        wrapped = "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fexample.test%2Farticle"
        resolved, changed = unwrap_redirect_url(wrapped)
        self.assertTrue(changed)
        self.assertEqual(resolved, "https://example.test/article")

    def test_article_metadata_exposes_canonical_and_original_urls(self):
        body = (
            '<link rel="canonical" href="/news/1">'
            '<meta property="og:url" content="https://example.test/news/1">'
            '<meta name="original-source" content="https://publisher.test/story">'
        )
        self.assertEqual(
            metadata_urls("https://example.test/page", body),
            ["https://example.test/news/1", "https://publisher.test/story"],
        )

    @patch("automation.daily_discovery.resolve_evidence_url")
    def test_evidence_resolution_attempt_has_auditable_method_fields(self, resolve_url):
        resolve_url.return_value = (
            "https://www.chinanews.com.cn/dwq/2026-08-31/10687546.shtml",
            "古埃及文明大展落幕，接待访客逾67万人次。",
            None,
        )
        event = {"representativeTitle": "香港古埃及文明大展落幕", "scope": "domestic"}
        report = {"title": "香港古埃及文明大展落幕", "url": "https://example.test/story"}
        outcome, source = resolve_evidence_attempt(event, report, "existing_report")
        self.assertEqual(outcome["attempts"][0]["method"], "existing_report")
        self.assertTrue(outcome["attempts"][0]["articleMatched"])
        self.assertEqual(source["tier"], "A")

    def test_all_source_scans_run_even_when_early_results_exist(self):
        calls = []

        def fake_scan(spec, _start, _end):
            calls.append(spec["sourceId"])
            return ({"sourceId": spec["sourceId"], "status": "checked", "rawResults": 0, "windowResults": 0}, [])

        with patch("automation.daily_discovery.scan_page", side_effect=fake_scan):
            audit = run(__import__("datetime").date(2026, 8, 31), execute_query_search=False)
        self.assertEqual(calls, [spec["sourceId"] for spec in SOURCE_SCANS])
        self.assertEqual(audit["summary"]["sourceScansAttempted"], len(SOURCE_SCANS))


if __name__ == "__main__":
    unittest.main()

"""Regression tests for daily discovery and legacy evidence isolation."""
import unittest
from unittest.mock import patch

from automation.daily_discovery import (
    QUERY_FAMILIES,
    SOURCE_SCANS,
    article_level_provisional_b,
    aggregate_event_candidates,
    build_final_editorial_pool,
    build_query_family_summary,
    clean_discovery_title,
    duplicate_relation,
    evidence_matches_event,
    evidence_sources_qualified,
    evidence_upgrade_queries,
    event_match_details,
    editorial_priority,
    has_specific_event_anchor,
    is_relevant_record,
    load_history,
    metadata_urls,
    parse_date,
    publisher_search_results,
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

    def test_unquoted_policy_title_matches_published_event(self):
        old = {
            "title": "文化和旅游部修订《博物馆藏品管理办法》：六章六十三条，11月1日起施行",
            "body": "文化和旅游部发布《博物馆藏品管理办法》政策解读。",
            "url": "https://a.test/1",
            "publishedDate": "2026-08-29",
        }
        new = {
            "title": "博物馆藏品管理办法",
            "url": "https://b.test/2",
            "publishedDate": "2026-08-28",
        }
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

    def test_exact_historical_title_matches_across_source_and_report_date(self):
        old = {
            "title": "中外联合考古工作会议在长春召开",
            "url": "https://wwj.zhengzhou.gov.cn/wwyw/10222851.jhtml",
            "publishedDate": "2026-08-29",
        }
        new = {
            "title": "中外联合考古工作会议在长春召开",
            "url": "https://www.ncha.gov.cn/art/2026/8/27/art_722_204540.html",
            "publishedDate": "2026-09-02",
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

    def test_high_level_cultural_diplomacy_is_high_priority(self):
        result = editorial_priority({
            "title": "彭丽媛同吉尔吉斯斯坦总统扎帕罗夫夫人扎帕罗娃参观吉尔吉斯共和国国家历史博物馆",
            "sourceDomains": ["ws.china-embassy.gov.cn", "chinanews.com.cn"],
            "publishedDate": "2026-08-31",
        }, __import__("datetime").date(2026, 9, 2))
        self.assertTrue(result["highLevelCulturalDiplomacy"])
        self.assertEqual(result["label"], "high")
        self.assertIn("high_level_cultural_diplomacy", result["reasons"])

    def test_local_leader_museum_visit_is_not_cultural_diplomacy(self):
        result = editorial_priority({"title": "某市市长参观地方博物馆", "publishedDate": "2026-09-01"})
        self.assertFalse(result["highLevelCulturalDiplomacy"])
        self.assertNotEqual(result["label"], "high")

    def test_national_figure_without_wenbo_substance_is_not_cultural_diplomacy(self):
        result = editorial_priority({"title": "国家主席出席国际经济论坛", "publishedDate": "2026-09-01"})
        self.assertFalse(result["highLevelCulturalDiplomacy"])

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

    @patch("automation.daily_discovery.resolve_evidence_url")
    def test_unregistered_direct_article_can_be_provisional_b(self, resolve_url):
        resolve_url.return_value = (
            "https://credible.example/2026/09/02/museum-project",
            "<html><head><title>某博物馆发布重要展览新成果</title>"
            "<meta property=\"article:published_time\" content=\"2026-09-02\">"
            "<meta property=\"og:site_name\" content=\"示例新闻\"></head>"
            "<body>某博物馆发布重要展览新成果。文章介绍了新的考古研究、文物保护材料和展陈安排，"
            "并说明了项目的具体时间、地点、参与机构与公开事实。该页面为媒体正文页面，"
            "不是搜索结果页或转载导航页。</body></html>",
            None,
        )
        event = {"representativeTitle": "某博物馆发布重要展览新成果", "scope": "domestic"}
        report = {"title": "某博物馆发布重要展览新成果", "url": "https://credible.example/2026/09/02/museum-project", "publishedDate": "2026-09-02", "sourceDomain": "示例新闻"}
        outcome, source = resolve_evidence_attempt(event, report, "existing_report")
        self.assertEqual(source["tier"], "provisional_B")
        self.assertTrue(source["articleVerified"])
        self.assertTrue(outcome["attempts"][-1]["articleMatched"])
        self.assertTrue(evidence_sources_qualified(event, [source]))

    def test_high_risk_claim_needs_more_than_one_provisional_b(self):
        event = {"title": "某博物馆发生藏品盗窃", "scope": "domestic"}
        source = {
            "url": "https://credible.example/story",
            "tier": "provisional_B",
            "articleVerified": True,
        }
        self.assertFalse(evidence_sources_qualified(event, [source]))

    @patch("automation.daily_discovery.SEARCH_OPENER.open")
    def test_known_publisher_search_returns_direct_article(self, open_url):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, *_args):
                return self.payload.encode("utf-8")

        payload = (
            '<script>var docArr = [{"createtime":"2026-08-31 22:19:34",'
            '"content_without_tag":"某博物馆新展落幕，接待访客逾67万人次",'
            '"url":"http:\\/\\/www.chinanews.com.cn\\/cul\\/2026\\/08-31\\/10687546.shtml"}];</script>'
        )
        open_url.return_value = FakeResponse(payload)
        rows, audit = publisher_search_results(
            {"representativeTitle": "某博物馆新展落幕", "scope": "domestic"},
            {"sourceDomain": "chinanews.com.cn"},
            __import__("datetime").date(2026, 8, 27),
            __import__("datetime").date(2026, 9, 2),
        )
        self.assertTrue(audit["success"])
        self.assertEqual(audit["backend"], "publisher-search")
        self.assertEqual(len(rows), 1)
        self.assertIn("10687546", rows[0]["url"])

    def test_event_match_handles_same_event_title_variants(self):
        event = {"representativeTitle": "中埃联合考古队在塞赫迈特神庙遗址有新发现"}
        result = {"title": "中埃联合考古队新发现一批重要遗迹和文物 - 新华网"}
        details = event_match_details(event, result)
        self.assertTrue(details["matched"])
        self.assertIn("compatible_event_action", details["reasons"])

    def test_event_match_handles_autonomous_prefecture_and_action_variants(self):
        event = {"representativeTitle": "云南楚雄立法保护元谋人遗址 条例今起施行"}
        result = {"title": "《楚雄彝族自治州元谋人遗址保护条例》9月1日正式施行 - 新华网"}
        self.assertTrue(evidence_matches_event(event, result, ""))

    def test_event_match_handles_policy_title_without_exact_words(self):
        event = {"representativeTitle": "上海文物局发文加强博物馆陈列展览内容审核工作，明确核查重点"}
        result = {"title": "上海市文物局关于加强博物馆陈列展览内容审核工作的通知 - thepaper.cn"}
        self.assertTrue(evidence_matches_event(event, result, ""))

    def test_clean_title_removes_transport_publisher_suffixes(self):
        self.assertEqual(
            clean_discovery_title("中埃联合考古队新发现一批重要遗迹和文物 - 新华网"),
            "中埃联合考古队新发现一批重要遗迹和文物",
        )
        self.assertEqual(clean_discovery_title("标题_ 文博资讯"), "标题")
        self.assertEqual(clean_discovery_title("标题 - Sohu"), "标题")

    def test_event_match_does_not_merge_same_institution_different_action(self):
        event = {"representativeTitle": "中国语言资源保护工程成果展示馆开馆"}
        result = {"title": "中国语言资源保护工程成果展示馆发布新数据库"}
        self.assertFalse(evidence_matches_event(event, result, ""))

    def test_event_match_does_not_merge_different_sites_with_generic_words(self):
        event = {"representativeTitle": "甲遗址发现古墓"}
        result = {"title": "乙遗址发现古墓"}
        self.assertFalse(evidence_matches_event(event, result, ""))

    def test_same_event_with_different_action_labels_is_one_candidate(self):
        events = aggregate_event_candidates([
            {
                "title": "中埃联合考古队在塞赫迈特神庙遗址发现重要遗迹",
                "url": "https://a.test/1",
                "publishedDate": "2026-09-01",
                "scope": "international",
            },
            {
                "title": "中埃联合考古队在塞赫迈特神庙遗址有新发现",
                "url": "https://b.test/2",
                "publishedDate": "2026-09-01",
                "scope": "international",
            },
        ])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reportCount"], 2)

    def test_generic_exact_title_does_not_become_historical_identity(self):
        old = {"title": "会议召开", "url": "https://a.test/1", "publishedDate": "2026-09-01"}
        new = {"title": "会议召开", "url": "https://b.test/2", "publishedDate": "2026-09-02"}
        self.assertFalse(has_specific_event_anchor(old))
        self.assertIsNone(duplicate_relation(new, old))

    @patch("automation.daily_discovery.publisher_search_results")
    @patch("automation.daily_discovery.resolve_evidence_url")
    @patch("automation.daily_discovery._execute_one_query")
    def test_known_source_domain_wrapper_uses_publisher_search(self, execute_query, resolve_url, publisher_search):
        execute_query.return_value = ([], {
            "actualQuery": "site:chinanews.com.cn 元谋人遗址",
            "executedAt": "2026-09-02T07:00:00+08:00",
            "success": True,
            "returnedResultCount": 0,
            "acceptedRawCount": 0,
        })
        publisher_search.return_value = ([{
            "title": "《楚雄彝族自治州元谋人遗址保护条例》9月1日正式施行",
            "url": "https://www.chinanews.com.cn/sh/2026/09-01/10688160.shtml",
            "publishedDate": "2026-09-01",
            "sourceDomain": "chinanews.com.cn",
        }], {"actualQuery": "site:chinanews.com.cn 元谋人遗址", "success": True})
        resolve_url.return_value = (
            "https://www.chinanews.com.cn/sh/2026/09-01/10688160.shtml",
            "<html><title>《楚雄彝族自治州元谋人遗址保护条例》9月1日正式施行</title>"
            "<body>条例正式施行，正文介绍元谋人遗址保护范围、管理职责和相关法律责任。</body></html>",
            None,
        )
        event = {
            "eventId": "event-yuanmou",
            "representativeTitle": "云南楚雄立法保护元谋人遗址 条例今起施行",
            "sourceDomains": ["chinanews.com.cn"],
            "publishedDate": "2026-09-01",
            "scope": "domestic",
            "candidateDisposition": "needs_verification",
            "editorialPriorityLabel": "high",
            "editorialPriorityScore": 70,
        }
        result = run_evidence_upgrade(__import__("datetime").date(2026, 9, 2), [event])
        self.assertEqual(result["qualified"], 1)
        self.assertTrue(publisher_search.called)
        self.assertEqual(event["evidenceTierAfterUpgrade"], "A")

    @patch("automation.daily_discovery._execute_one_query")
    def test_unmatched_relevant_result_returns_one_level_resolver_candidate(self, execute_query):
        execute_query.return_value = ([{
            "title": "另一博物馆发布重要藏品保护项目",
            "url": "https://example.test/other",
            "publishedDate": "2026-09-02",
            "sourceDomain": "example.test",
        }], {"actualQuery": "某遗址考古成果 官方原文", "success": True})
        event = {
            "eventId": "event-parent",
            "representativeTitle": "某遗址考古成果公布",
            "publishedDate": "2026-09-02",
            "scope": "domestic",
            "candidateDisposition": "needs_verification",
            "editorialPriorityLabel": "high",
            "editorialPriorityScore": 70,
        }
        result = run_evidence_upgrade(__import__("datetime").date(2026, 9, 2), [event])
        self.assertTrue(result["resolverDiscoveredCandidates"])
        candidate = result["resolverDiscoveredCandidates"][0]
        self.assertEqual(candidate["resolverDepth"], 1)
        self.assertEqual(candidate["resolverParentEventId"], "event-parent")

    def test_query_families_cover_recall_benchmark_semantics(self):
        queries = {query for family in QUERY_FAMILIES for query in family["queries"]}
        self.assertTrue(any("特殊津贴" in query for query in queries))
        self.assertTrue(any("入馆" in query and "证件" in query for query in queries))
        self.assertTrue(any("古建筑" in query and "修缮" in query for query in queries))
        self.assertTrue(any("烈士墓葬" in query for query in queries))
        self.assertTrue(any("natural history museum" in query for query in queries))
        self.assertTrue(any("fossil" in query and "exhibition" in query for query in queries))

    def test_recall_expansion_families_are_executable_and_auditable(self):
        family_ids = {family["id"] for family in QUERY_FAMILIES}
        self.assertTrue({
            "heritage-professionals",
            "museum-operations",
            "modern-heritage",
            "international-loans",
            "local-heritage-governance",
        } <= family_ids)
        self.assertIn("mct-national-museum", {spec["sourceId"] for spec in SOURCE_SCANS})
        reports = [{
            "title": "某遗址发布考古新发现",
            "url": "https://example.test/archaeology",
            "publishedDate": "2026-09-01",
            "queryFamily": "modern-heritage",
            "scope": "domestic",
        }]
        events = aggregate_event_candidates(reports)
        summary = build_query_family_summary(
            reports,
            [{
                "queryFamily": "modern-heritage",
                "success": True,
                "returnedResultCount": 1,
                "acceptedRawCount": 1,
            }],
            events,
            [{"eventId": events[0]["eventId"], "candidateDisposition": "needs_verification"}],
        )
        self.assertEqual(summary["modern-heritage"]["queriesAttempted"], 1)
        self.assertEqual(summary["modern-heritage"]["firstDiscoveryEventCount"], 1)
        self.assertEqual(summary["modern-heritage"]["evidenceUpgradeCandidates"], 1)

    def test_family_scope_prevents_industry_talent_result_from_early_drop(self):
        reports = [{
            "title": "中宣部公示2026享受政府特殊津贴推荐人选（40人）",
            "url": "https://example.test/talent",
            "publishedDate": "2026-09-01",
            "queryFamily": "heritage-professionals",
            "scope": "domestic",
        }]
        event = aggregate_event_candidates(reports)[0]
        self.assertIn("heritage-professionals", event["queryFamilies"])
        self.assertTrue(is_relevant_record(event))

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

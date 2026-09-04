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
    evaluate_candidate_pool,
    fixed_panel_radar_records,
    has_specific_event_anchor,
    is_relevant_record,
    load_history,
    museum_collection_or_public_incident,
    metadata_urls,
    parse_date,
    publisher_search_results,
    public_salience,
    resolve_evidence_attempt,
    run_evidence_upgrade,
    run,
    build_audit,
    infer_editorial_scope,
    parse_bing_html,
    query_audit_status,
    _execute_one_query,
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

    def test_historical_archaeology_repeat_does_not_use_generic_new_discovery_marker(self):
        old = {
            "title": "中埃联合考古队在塞赫迈特神庙遗址发现重要遗迹",
            "url": "https://a.test/old",
            "publishedDate": "2026-09-02",
        }
        repeat = {
            "title": "中埃联合考古队新发现一批重要遗迹和文物",
            "url": "https://b.test/repeat",
            "publishedDate": "2026-09-04",
        }
        self.assertEqual(duplicate_relation(repeat, old)[0], "historical_duplicate")

    def test_substantive_follow_up_requires_explicit_evidence(self):
        old = {
            "title": "某遗址公布考古成果",
            "url": "https://a.test/old",
            "publishedDate": "2026-09-02",
            "entity": "某遗址",
            "eventType": "archaeology",
        }
        follow_up = {
            "title": "某遗址公布后续考古成果",
            "url": "https://b.test/new",
            "publishedDate": "2026-09-04",
            "entity": "某遗址",
            "eventType": "archaeology",
            "substantiveNewDevelopment": True,
            "newDevelopmentEvidence": "官方公布第二阶段发掘结果",
        }
        self.assertEqual(duplicate_relation(follow_up, old)[0], "new_development")

    def test_query_provider_failure_status_is_not_clean(self):
        self.assertEqual(query_audit_status([{"success": False}]), "failed")
        self.assertEqual(query_audit_status([{"success": True}, {"success": False}]), "partial")
        self.assertEqual(query_audit_status([{"success": False} for _ in range(126)]), "failed")

    def test_historical_event_stays_duplicate_across_consecutive_runs(self):
        canonical = {
            "eventId": "event-stable",
            "title": "中埃联合考古队在塞赫迈特神庙遗址发现重要遗迹",
            "url": "https://a.test/2026-09-02",
            "publishedDate": "2026-09-02",
        }
        repeat_1 = {
            "eventId": "event-stable",
            "title": "中埃联合考古队新发现一批重要遗迹和文物",
            "url": "https://b.test/2026-09-03",
            "publishedDate": "2026-09-03",
        }
        repeat_2 = dict(repeat_1, url="https://c.test/2026-09-04", publishedDate="2026-09-04")
        self.assertEqual(duplicate_relation(repeat_1, canonical)[0], "historical_duplicate")
        self.assertEqual(duplicate_relation(repeat_2, canonical)[0], "historical_duplicate")

    def test_non_xml_provider_response_keeps_diagnostic_metadata(self):
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __init__(self, payload, url):
                self.payload = payload
                self.url = url

            def read(self):
                return self.payload

            def geturl(self):
                return self.url

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        family = {"id": "policy-governance", "scope": "domestic"}
        backend = {"id": "bing-news-rss", "name": "Bing News RSS", "base": "https://www.bing.com/news/search"}
        with patch(
            "automation.daily_discovery.SEARCH_OPENER.open",
            side_effect=[
                FakeResponse(b"<!doctype html><title>challenge</title>", "https://cn.bing.com/"),
                FakeResponse(b"<!doctype html><title>no result cards</title>", "https://cn.bing.com/search"),
            ],
        ):
            rows, audit = _execute_one_query(
                family,
                backend,
                "文物 政策",
                __import__("datetime").date(2026, 9, 1),
                __import__("datetime").date(2026, 9, 4),
            )
        self.assertEqual(rows, [])
        self.assertFalse(audit["success"])
        self.assertEqual(audit["httpStatus"], 200)
        self.assertEqual(audit["contentType"], "text/html; charset=utf-8")
        self.assertGreater(audit["responseBytes"], 0)
        self.assertEqual(audit["parserFailureType"], "non_xml_response")
        self.assertEqual(audit["providerFallback"], "bing-web-html")
        self.assertGreater(audit["fallbackResponseBytes"], 0)

    def test_bing_html_fallback_parses_dated_discovery_links(self):
        html = (
            '<ol id="b_results"><li class="b_algo"><h2><a href="https://example.com/2026/09/03/story">'
            '某博物馆发布考古成果</a></h2><div class="b_caption"><p>某地报道</p></div></li></ol>'
        )
        rows, returned, undated = parse_bing_html(
            html,
            family={"id": "archaeology-heritage", "scope": "domestic"},
            backend={"id": "bing-news-rss", "name": "Bing News RSS"},
            query="考古",
            start=__import__("datetime").date(2026, 9, 1),
            end=__import__("datetime").date(2026, 9, 4),
        )
        self.assertEqual(returned, 1)
        self.assertEqual(undated, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["discoveredVia"], "bing-news-html-fallback")

    def test_event_scope_uses_event_semantics_not_publisher_nationality(self):
        cross_border = [{
            "title": "新华社：中埃联合考古队参观埃及国家博物馆并公布考古成果",
            "scope": "domestic",
        }]
        foreign_report_of_china = [{
            "title": "China museum publishes a domestic collection report",
            "scope": "international",
        }]
        cross_border_without_explicit_location = [{
            "title": "中埃联合考古队公布神庙遗址阶段性成果",
            "scope": "domestic",
        }]
        domestic_joint_meeting = [{
            "title": "国家文物局与中国地震局联合召开全国文物地震安全工作交流会",
            "scope": "domestic",
        }]
        self.assertEqual(infer_editorial_scope(cross_border, ["domestic"], []), "international")
        self.assertEqual(infer_editorial_scope(cross_border_without_explicit_location, ["domestic"], []), "international")
        self.assertEqual(infer_editorial_scope(domestic_joint_meeting, ["domestic"], []), "domestic")
        self.assertEqual(infer_editorial_scope(foreign_report_of_china, ["international"], []), "domestic")

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

    def test_fixed_panel_radar_accepts_only_same_day_monitoring_items(self):
        from datetime import date
        records, audit = fixed_panel_radar_records(date(2026, 9, 3), {
            "runType": "live",
            "items": [
                {
                    "date": "2026-09-03",
                    "origin": "fixed-panel-monitoring",
                    "recordId": "monitor-today",
                    "title": "国家级博物馆与外国总统参观展览并开展国际交流",
                    "scope": "unassigned",
                    "themes": ["博物馆", "国际交流"],
                    "sources": [{"name": "新华网文博", "url": "https://www.news.cn/politics/20260903/story.html"}],
                },
                {
                    "date": "2026-09-02",
                    "origin": "fixed-panel-monitoring",
                    "recordId": "monitor-yesterday",
                    "title": "昨天的博物馆消息",
                    "sources": [{"name": "新华网文博", "url": "https://www.news.cn/politics/20260902/story.html"}],
                },
                {
                    "date": "2026-09-03",
                    "origin": "query-search",
                    "recordId": "not-monitoring",
                    "title": "不属于固定监测的线索",
                    "sources": [{"name": "搜索", "url": "https://example.test/story"}],
                },
            ],
        })
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["monitoringRecordId"], "monitor-today")
        self.assertEqual(records[0]["discoverySourceType"], "fixed_panel_radar")
        self.assertEqual(records[0]["discoverySource"], "新华网文博固定源监测")
        self.assertEqual(audit["seedCount"], 1)

    def test_fixed_panel_radar_merges_with_query_report_and_recomputes_scope(self):
        from datetime import date
        radar, _ = fixed_panel_radar_records(date(2026, 9, 3), {
            "items": [{
                "date": "2026-09-03",
                "origin": "fixed-panel-monitoring",
                "recordId": "monitor-egypt",
                "title": "习近平和彭丽媛同埃及总统塞西夫妇共同参观大埃及博物馆",
                "scope": "unassigned",
                "themes": ["博物馆", "文化遗产", "国际交流"],
                "tags": ["博物馆", "国际交流"],
                "sources": [{"name": "新华网文博", "url": "https://www.news.cn/politics/leaders/20260903/story.html"}],
            }],
        })
        query = {
            "title": "习近平和彭丽媛同埃及总统塞西夫妇共同参观大埃及博物馆",
            "url": "https://news.google.com/rss/articles/example",
            "publishedDate": "2026-09-03",
            "scope": "domestic",
            "discoverySourceType": "query_search",
            "sourceDomain": "chinanews.com.cn",
        }
        events = aggregate_event_candidates([query, radar[0]])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reportCount"], 2)
        self.assertEqual(events[0]["scope"], "international")
        self.assertEqual(sum("fixed_panel_radar" == row.get("discoverySourceType") for row in events[0]["discoveryReports"]), 1)

    def test_fixed_panel_radar_preserves_provenance_when_url_already_seen(self):
        from datetime import date
        url = "https://www.news.cn/politics/leaders/20260903/story.html"
        records, radar_audit = fixed_panel_radar_records(date(2026, 9, 3), {
            "runType": "live",
            "items": [{
                "date": "2026-09-03",
                "origin": "fixed-panel-monitoring",
                "recordId": "monitor-same-url",
                "title": "某国家博物馆发布国际交流展览成果",
                "themes": ["博物馆", "国际交流"],
                "sources": [{"name": "固定源", "url": url}],
            }],
        })
        radar_audit["_records"] = records
        audit = build_audit(
            date(2026, 9, 3),
            [{"title": "某国家博物馆发布国际交流展览成果", "url": url, "publishedDate": "2026-09-03"}],
            [], [], [], False, radar_audit,
        )
        events = audit["candidateEvaluation"]["eventCandidates"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reportCount"], 2)
        self.assertEqual(sum(row.get("discoverySourceType") == "fixed_panel_radar" for row in events[0]["discoveryReports"]), 1)

    @patch("automation.daily_discovery.load_history")
    def test_fixed_panel_radar_does_not_bypass_historical_dedup(self, load_history):
        from datetime import date
        load_history.return_value = [{
            "title": "某国家博物馆发布国际交流展览成果",
            "url": "https://archive.example/published",
            "publishedDate": "2026-09-02",
        }]
        records, radar_audit = fixed_panel_radar_records(date(2026, 9, 3), {
            "runType": "live",
            "items": [{
                "date": "2026-09-03",
                "origin": "fixed-panel-monitoring",
                "recordId": "monitor-historical",
                "title": "某国家博物馆发布国际交流展览成果",
                "themes": ["博物馆", "国际交流"],
                "sources": [{"name": "固定源", "url": "https://fixed.example/story"}],
            }],
        })
        radar_audit["_records"] = records
        audit = build_audit(date(2026, 9, 3), [], [], [], [], False, radar_audit)
        self.assertEqual(len(audit["records"]), 1)
        self.assertEqual(audit["records"][0]["duplicateStatus"], "historical_duplicate")
        self.assertEqual(audit["candidateEvaluation"]["eventCandidates"], [])
        self.assertEqual(audit["candidateEvaluation"]["summary"]["candidateEvaluationPool"], 0)

    def test_fixed_panel_radar_does_not_bypass_evidence_gate(self):
        from datetime import date
        records, _ = fixed_panel_radar_records(date(2026, 9, 3), {
            "items": [{
                "date": "2026-09-03",
                "origin": "fixed-panel-monitoring",
                "recordId": "monitor-unknown",
                "title": "某博物馆发布重要文物保护进展",
                "scope": "province",
                "themes": ["博物馆", "文物保护"],
                "sources": [{"name": "固定源", "url": "https://unknown.example/story"}],
            }],
        })
        events = aggregate_event_candidates(records)
        evaluation = evaluate_candidate_pool(date(2026, 9, 3), events)
        self.assertEqual(evaluation["records"][0]["candidateDisposition"], "needs_verification")
        self.assertNotEqual(evaluation["records"][0]["candidateDisposition"], "selected")

    def test_fixed_panel_radar_diplomacy_enters_review_with_direct_a_evidence(self):
        from datetime import date
        records, radar_audit = fixed_panel_radar_records(date(2026, 9, 3), {
            "runType": "live",
            "items": [{
                "date": "2026-09-03",
                "origin": "fixed-panel-monitoring",
                "recordId": "monitor-egypt-a",
                "title": "习近平和彭丽媛同埃及总统塞西夫妇共同参观大埃及博物馆",
                "scope": "unassigned",
                "themes": ["博物馆", "文化遗产", "国际交流"],
                "tags": ["博物馆", "国际交流"],
                "sources": [{"name": "新华网文博", "url": "https://www.news.cn/politics/leaders/20260903/800e09d7185c45e4800776e340ee9d38/c.html"}],
            }],
        })
        radar_audit["_records"] = records
        audit = build_audit(date(2026, 9, 3), [], [], [], [], False, radar_audit)
        events = audit["candidateEvaluation"]["finalEditorialPool"]["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["scope"], "international")
        self.assertEqual(events[0]["candidateDisposition"], "evidence_qualified")
        self.assertEqual(events[0]["evidenceTierAfterUpgrade"], "A")
        self.assertTrue(events[0]["evidenceSources"])
        self.assertIn("high_level_cultural_diplomacy", events[0]["editorialReasons"])
        self.assertEqual(audit["fixedPanelRadar"]["fixedRadarNewToDaily"], 1)
        self.assertEqual(audit["fixedPanelRadar"]["fixedRadarEvidenceQualified"], 1)

    def test_local_leader_museum_visit_is_not_cultural_diplomacy(self):
        result = editorial_priority({"title": "某市市长参观地方博物馆", "publishedDate": "2026-09-01"})
        self.assertFalse(result["highLevelCulturalDiplomacy"])
        self.assertNotEqual(result["label"], "high")

    def test_national_figure_without_wenbo_substance_is_not_cultural_diplomacy(self):
        result = editorial_priority({"title": "国家主席出席国际经济论坛", "publishedDate": "2026-09-01"})
        self.assertFalse(result["highLevelCulturalDiplomacy"])

    def test_museum_collection_public_incident_requires_three_anchors(self):
        self.assertTrue(museum_collection_or_public_incident({
            "title": "博物馆科研标本受损，馆方回应",
        }))
        self.assertTrue(museum_collection_or_public_incident({
            "title": "博物馆展厅化石被游客破坏",
        }))
        self.assertFalse(museum_collection_or_public_incident({
            "title": "博物馆周末亲子活动开放报名",
        }))

    def test_public_incident_gets_high_priority_without_title_specific_rule(self):
        result = editorial_priority({
            "title": "两孩子在展厅内手抓、脚踢标本 国家动物博物馆强烈谴责",
            "publishedDate": "2026-08-30",
        }, __import__("datetime").date(2026, 9, 1))
        self.assertTrue(result["museumCollectionOrPublicIncident"])
        self.assertEqual(result["label"], "high")
        self.assertIn("museum_collection_or_public_incident", result["reasons"])

    def test_public_salience_counts_independent_publishers_not_report_count(self):
        reports = [
            {"title": "同一事件报道", "sourceDomain": "news.cn", "url": "https://news.cn/a"},
            {"title": "同一事件转载", "sourceDomain": "news.cn", "url": "https://news.cn/b"},
            {"title": "同一事件镜像", "sourceDomain": "www.news.cn", "url": "https://www.news.cn/c"},
        ]
        salience = public_salience({"title": "普通博物馆参观", "discoveryReports": reports})
        self.assertEqual(salience["independentCoverageCount"], 1)
        self.assertEqual(salience["level"], "normal")

    def test_public_salience_requires_substantive_wenbo_signal_for_priority_boost(self):
        record = {
            "title": "明星参观国家博物馆",
            "publishedDate": "2026-08-31",
            "discoveryReports": [
                {"title": "明星参观国家博物馆", "sourceDomain": "news.cn"},
                {"title": "明星打卡国家博物馆", "sourceDomain": "people.com.cn"},
                {"title": "明星现身博物馆", "sourceDomain": "thepaper.cn"},
                {"title": "明星参观博物馆", "sourceDomain": "川观新闻"},
                {"title": "明星参观博物馆", "sourceDomain": "cnr.cn"},
            ],
        }
        result = editorial_priority(record, __import__("datetime").date(2026, 9, 1))
        self.assertEqual(result["publicSalience"]["level"], "sustained_public_attention")
        self.assertNotIn("sustained_public_attention", result["reasons"])
        self.assertNotEqual(result["label"], "high")

    def test_cross_media_attention_adds_only_to_substantive_incident(self):
        result = editorial_priority({
            "title": "博物馆标本遭游客破坏并受损",
            "discoveryReports": [
                {"title": "博物馆标本遭游客破坏", "sourceDomain": "news.cn"},
                {"title": "标本受损引发讨论", "sourceDomain": "thepaper.cn"},
                {"title": "游客破坏标本", "sourceDomain": "川观新闻"},
            ],
        })
        self.assertTrue(result["museumCollectionOrPublicIncident"])
        self.assertEqual(result["publicSalience"]["level"], "cross_media_attention")
        self.assertIn("cross_media_attention", result["reasons"])

    def test_public_salience_marks_multi_day_follow_up_as_sustained(self):
        salience = public_salience({
            "title": "博物馆藏品受损事件",
            "discoveryReports": [
                {"title": "事件回应", "sourceDomain": "news.cn", "publishedDate": "2026-08-30"},
                {"title": "事件进展", "sourceDomain": "thepaper.cn", "publishedDate": "2026-08-31"},
            ],
        })
        self.assertEqual(salience["level"], "sustained_public_attention")
        self.assertEqual(salience["coverageDates"], ["2026-08-30", "2026-08-31"])

    def test_national_animal_museum_regression_is_not_low(self):
        result = editorial_priority({
            "title": "国家动物博物馆就破坏珍贵标本事件发布严正回应",
            "discoveryReports": [
                {"title": "两孩子在博物馆不断用手抓、用脚踢标本", "sourceDomain": "川观新闻"},
                {"title": "家长拒不承认破坏珍贵蛇标本", "sourceDomain": "thepaper.cn"},
            ],
            "evidenceSources": [
                {"name": "人民网：国家动物博物馆回应", "url": "https://people.com.cn/a", "tier": "A"},
                {"name": "央视：国家动物博物馆回应", "url": "https://cctv.com/a", "tier": "A"},
                {"name": "央广：国家动物博物馆回应", "url": "https://cnr.cn/a", "tier": "A"},
            ],
            "publishedDate": "2026-08-30",
        }, __import__("datetime").date(2026, 9, 1))
        self.assertTrue(result["museumCollectionOrPublicIncident"])
        self.assertEqual(result["publicSalience"]["independentCoverageCount"], 5)
        self.assertEqual(result["publicSalience"]["level"], "sustained_public_attention")
        self.assertEqual(result["label"], "high")

    def test_historical_duplicate_cannot_be_rescued_by_public_salience(self):
        from datetime import date
        record = {
            "title": "博物馆藏品受损事件",
            "publishedDate": "2026-08-31",
            "duplicateStatus": "historical_duplicate",
            "duplicateOf": "2026-08-30#item1",
            "discoveryReports": [
                {"title": "事件报道", "sourceDomain": "news.cn"},
                {"title": "事件跟进", "sourceDomain": "thepaper.cn"},
                {"title": "事件回应", "sourceDomain": "cnr.cn"},
            ],
        }
        evaluated = __import__("automation.daily_discovery", fromlist=["evaluate_candidate_pool"]).evaluate_candidate_pool(date(2026, 9, 1), [record])
        self.assertEqual(evaluated["records"][0]["candidateDisposition"], "rejected")

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

    @patch("automation.daily_discovery._execute_one_query")
    def test_evidence_upgrade_queue_has_no_fixed_top_n_and_skips_low_priority(self, execute_query):
        execute_query.return_value = ([], {
            "actualQuery": "event evidence official source",
            "executedAt": "2026-09-04T07:00:00+08:00",
            "success": True,
            "returnedResultCount": 0,
            "acceptedRawCount": 0,
        })
        events = [
            {
                "eventId": f"event-high-{index}",
                "representativeTitle": f"重要文博政策事项{index}",
                "publishedDate": "2026-09-04",
                "scope": "international" if index == 1 else "domestic",
                "candidateDisposition": "needs_verification",
                "editorialPriorityLabel": "high",
                "editorialPriorityScore": 90 - index,
            }
            for index in range(3)
        ]
        events.append({
            "eventId": "event-medium",
            "representativeTitle": "重要博物馆项目",
            "publishedDate": "2026-09-04",
            "scope": "domestic",
            "candidateDisposition": "needs_verification",
            "editorialPriorityLabel": "medium",
            "editorialPriorityScore": 60,
        })
        events.append({
            "eventId": "event-low",
            "representativeTitle": "普通活动通知",
            "publishedDate": "2026-09-04",
            "scope": "domestic",
            "candidateDisposition": "needs_verification",
            "editorialPriorityLabel": "low",
            "editorialPriorityScore": 30,
        })

        result = run_evidence_upgrade(__import__("datetime").date(2026, 9, 4), events)

        self.assertEqual(result["attempted"], 4)
        self.assertEqual(
            {event["eventId"] for event in events if event.get("evidenceUpgradeAttempted")},
            {"event-high-0", "event-high-1", "event-high-2", "event-medium"},
        )
        self.assertFalse(events[-1].get("evidenceUpgradeAttempted", False))

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
        self.assertTrue(any("museum" in query and "government support" in query for query in queries))
        self.assertTrue(any("museum" in query and "federal funding" in query for query in queries))

    def test_recall_expansion_families_are_executable_and_auditable(self):
        family_ids = {family["id"] for family in QUERY_FAMILIES}
        self.assertTrue({
            "heritage-professionals",
            "museum-operations",
            "modern-heritage",
            "international-loans",
            "international-museum-governance",
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

    def test_international_museum_governance_relevance_is_generic(self):
        target = {
            "title": "Trump administration threatens to cut federal agencies' support for Smithsonian",
            "queryFamily": "international-museum-governance",
            "scope": "international",
            "sourceDomain": "reuters.com",
            "publishedDate": "2026-09-04",
        }
        self.assertTrue(is_relevant_record(target))
        priority = editorial_priority(target, __import__("datetime").date(2026, 9, 4))
        self.assertGreaterEqual(priority["score"], 70)
        self.assertIn("museum_or_cultural_institution_governance", priority["reasons"])

        generic_politics = {
            "title": "Federal agencies receive new grants",
            "queryFamily": "international-museum-governance",
            "scope": "international",
            "sourceDomain": "example.gov",
        }
        self.assertFalse(is_relevant_record(generic_politics))

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

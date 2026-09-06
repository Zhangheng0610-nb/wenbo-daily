"""Regression tests for the auditable recruitment discovery layer."""
import unittest
from datetime import date

from automation.recruitment_discovery import (
    build_candidate,
    candidate_identity,
    deduplicate_candidates,
    expand_umbrella_rows,
    is_recruitment_candidate,
    publishable_recruitment_candidate,
    radar_lead_candidate,
    rolling_window,
)
from automation.governance import recruitment_source_info


class RecruitmentDiscoveryTests(unittest.TestCase):
    def test_taizhou_museum_direct_title_is_recalled(self):
        title = "浙江省台州市博物馆2026年9月公开招聘1名安全和设备管理岗位人员公告"
        self.assertTrue(is_recruitment_candidate(title, ""))
        candidate = build_candidate({"title": title, "url": "https://example.test/detail"})
        self.assertIn("台州市博物馆", candidate["institution"])

    def test_umbrella_notice_expands_museum_rows(self):
        rows = [
            ["招聘单位名称", "岗位代码", "岗位名称", "招聘人数"],
            ["云南省花灯剧院", "001", "财务管理", 1],
            ["云南省博物馆", "002", "文创开发与销售", 1],
            ["云南省博物馆", "003", "陈列展览形式设计", 1],
        ]
        candidates = expand_umbrella_rows(rows, {
            "title": "2026年下半年云南省文化和旅游厅直属事业单位公开招聘人员公告",
            "url": "https://hrss.yn.gov.cn/notice",
        })
        self.assertEqual([row["position"] for row in candidates], ["文创开发与销售", "陈列展览形式设计"])

    def test_same_position_reposts_form_one_entity(self):
        common = {"institution": "台州市博物馆", "position": "安全和设备管理岗位", "deadline": "2026-09-13"}
        rows = [
            {**common, "candidateId": "a", "verificationSource": "https://www.tzrc.cn/detail", "verificationStatus": "verified"},
            {**common, "candidateId": "b", "verificationSource": "https://www.gaoxiaojob.com/detail", "verificationStatus": "pending"},
        ]
        merged = deduplicate_candidates(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["verificationSource"], "https://www.tzrc.cn/detail")
        self.assertEqual(len(merged[0]["duplicateProvenance"]), 1)

    def test_search_result_without_detail_is_not_publishable(self):
        candidate = {
            "verificationStatus": "verified",
            "verificationSource": "https://example.test/search?q=museum",
            "verificationPageType": "search_results",
            "position": "讲解员",
            "institution": "某博物馆",
            "deadline": "2026-09-13",
        }
        self.assertFalse(publishable_recruitment_candidate(candidate))

    def test_discovery_only_wechat_is_a_lead_not_evidence(self):
        candidate = radar_lead_candidate({
            "name": "行业招聘汇总",
            "type": "industry_wechat",
            "url": "https://mp.weixin.qq.com/s/example",
            "discoveryOnly": True,
        }, "博物馆招聘汇总")
        self.assertEqual(candidate["verificationStatus"], "pending")
        self.assertEqual(candidate["decision"], "pending")
        self.assertFalse(publishable_recruitment_candidate(candidate))

    def test_rolling_overlap_recovers_late_indexed_result(self):
        start, end = rolling_window(date(2026, 9, 6), date(2026, 9, 4), overlap_days=7)
        self.assertEqual(start, date(2026, 8, 29))
        self.assertEqual(end, date(2026, 9, 6))
        self.assertGreaterEqual(date(2026, 9, 3), start)

    def test_unrelated_recruitment_is_filtered(self):
        self.assertFalse(is_recruitment_candidate("某市医院招聘护士", "医疗卫生岗位"))

    def test_generic_exhibition_job_fair_is_filtered(self):
        self.assertFalse(is_recruitment_candidate("民营企业综合专场招聘会开幕", "现场设置展览展示专区"))

    def test_candidate_identity_includes_batch_not_repost_url(self):
        a = {"institution": "云南省博物馆", "position": "陈列展览形式设计", "recruitmentBatch": "2026年下半年", "deadline": "2026-09-11"}
        b = {**a, "verificationSource": "https://another.example/repost"}
        self.assertEqual(candidate_identity(a), candidate_identity(b))

    def test_verified_recruitment_hosts_have_truthful_labels(self):
        self.assertEqual(recruitment_source_info("https://wuhouci.net.cn/bwggg-detail/1")["kind"], "official")
        self.assertEqual(recruitment_source_info("https://www.tzrc.cn/zxDetail?id=1")["kind"], "employment")


if __name__ == "__main__":
    unittest.main()

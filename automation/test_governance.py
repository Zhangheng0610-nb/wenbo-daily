"""Regression tests for opt-in official WeChat source governance."""
import unittest
import json
import tempfile
from unittest.mock import patch
from pathlib import Path

from automation.governance import (
    OFFICIAL_WECHAT_ACCOUNTS,
    OFFICIAL_WECHAT_REGISTRY_PATH,
    official_wechat_account,
    source_info,
    source_link_html,
    validate_official_wechat_registry,
    wechat_evidence_issues,
)
from automation.validate_candidates import validate


def account(biz, name, institution, tier, institution_type="机构"):
    return {
        "biz": biz,
        "accountName": name,
        "institution": institution,
        "institutionType": institution_type,
        "sourceTier": tier,
        "verifiedEvidence": "https://official.example/verify",
        "officialSite": "https://official.example/",
        "originalOnly": True,
        "verifiedAt": "2026-09-02",
        "notes": "identity and originality verified",
    }


class WeChatGovernanceTests(unittest.TestCase):
    def test_registry_schema_is_valid(self):
        self.assertEqual(validate_official_wechat_registry(OFFICIAL_WECHAT_REGISTRY_PATH), [])

    def test_institutional_account_is_publishable_a(self):
        with patch.dict(OFFICIAL_WECHAT_ACCOUNTS, {
                "A==": account("A==", "某博物馆", "某博物馆", "A", "博物馆")}, clear=True):
            info = source_info("https://mp.weixin.qq.com/s?__biz=A==&mid=1")
            self.assertEqual(info["tier"], "A")
            self.assertFalse(info["blocked"])
            self.assertIn("机构官方公众号", info["label"])

    def test_government_account_is_publishable_a(self):
        with patch.dict(OFFICIAL_WECHAT_ACCOUNTS, {
                "G==": account("G==", "某文物局", "某文物局", "A", "政府主管部门")}, clear=True):
            self.assertEqual(
                source_info("https://mp.weixin.qq.com/s?__biz=G==&mid=2")["tier"], "A")

    def test_media_account_inherits_b(self):
        with patch.dict(OFFICIAL_WECHAT_ACCOUNTS, {
                "B==": account("B==", "某日报", "某日报社", "B", "媒体")}, clear=True):
            info = source_info("https://mp.weixin.qq.com/s?__biz=B==&mid=3")
            self.assertEqual(info["tier"], "B")
            self.assertFalse(info["blocked"])
            self.assertIn("媒体官方公众号", info["label"])

    def test_industry_radar_is_discovery_only(self):
        with patch.dict(OFFICIAL_WECHAT_ACCOUNTS, {
                "R==": account("R==", "文博圈", "文博圈", "discovery_only", "行业媒体")}, clear=True):
            info = source_info("https://mp.weixin.qq.com/s?__biz=R==&mid=4")
            self.assertEqual(info["tier"], "C")
            self.assertEqual(info["sourceTier"], "discovery_only")
            self.assertTrue(info["blocked"])

    def test_unknown_or_lookalike_account_stays_blocked(self):
        with patch.dict(OFFICIAL_WECHAT_ACCOUNTS, {}, clear=True):
            info = source_info("https://mp.weixin.qq.com/s?__biz=not-registered&mid=5")
            self.assertEqual(info["tier"], "C")
            self.assertTrue(info["blocked"])

    def test_registered_account_does_not_make_repost_original(self):
        with patch.dict(OFFICIAL_WECHAT_ACCOUNTS, {
                "A==": account("A==", "某博物馆", "某博物馆", "A", "博物馆")}, clear=True):
            url = "https://mp.weixin.qq.com/s?__biz=A==&mid=6"
            self.assertTrue(wechat_evidence_issues(
                {"url": url, "articleOriginal": False}, selected=True))
            self.assertEqual(wechat_evidence_issues(
                {"url": url, "articleOriginal": True}, selected=True), [])

    def test_shanxi_museum_official_article_is_institutional_a(self):
        url = ("https://mp.weixin.qq.com/s?__biz=MjM5NDIzMDUwMQ=="
               "&mid=2651083261&idx=1&sn=c6599ba01b78c907dffaa0799d6fd9bf")
        account_record = official_wechat_account(url)
        self.assertIsNotNone(account_record)
        self.assertEqual(account_record["institution"], "山西博物院")
        self.assertEqual(source_info(url)["tier"], "A")
        self.assertEqual(wechat_evidence_issues(
            {"url": url, "articleOriginal": True}, selected=True), [])

    def test_source_label_names_institutional_account(self):
        url = ("https://mp.weixin.qq.com/s?__biz=MjM5NDIzMDUwMQ=="
               "&mid=2651083261&idx=1&sn=c6599ba01b78c907dffaa0799d6fd9bf")
        html = source_link_html({"name": "微信文章", "url": url})
        self.assertIn("山西博物院官方公众号", html)

    def test_candidate_validator_enforces_article_original_for_selected_wechat(self):
        url = ("https://mp.weixin.qq.com/s?__biz=MjM5NDIzMDUwMQ=="
               "&mid=2651083261&idx=1&sn=c6599ba01b78c907dffaa0799d6fd9bf")
        candidate = {
            "candidateId": "candidate-wechat-test",
            "title": "山西博物院调整入馆方式",
            "publishedDate": "2026-08-30",
            "discoveredAt": "2026-08-30T08:00:00+08:00",
            "discoverySource": "山西博物院",
            "discoverySourceType": "source_scan",
            "discoveryUrl": url,
            "publisher": "山西博物院",
            "evidenceSources": [{
                "name": "山西博物院官方公众号",
                "url": url,
                "tier": "A",
                "articleOriginal": False,
            }],
            "evidenceTier": "A",
            "topic": "博物馆与公共文化",
            "domestic": True,
            "international": False,
            "scope": "domestic",
            "decision": "selected",
            "decisionReason": "test",
            "selectedForDaily": True,
            "dedupStatus": "unique_event",
            "notes": "test",
            "dailyItemNumber": 1,
            "dailyItemTitle": "山西博物院调整入馆方式",
        }
        payload = {
            "date": "2026-08-30",
            "discoveryCompleted": True,
            "internationalDiscoveryChecked": True,
            "internationalDiscoveryStatus": "checked",
            "candidates": [candidate],
            "summary": {"discovered": 1, "selected": 1, "rejected": 0,
                        "deferred": 0, "needsVerification": 0},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            errors = validate(path)
        self.assertTrue(any("articleOriginal_true" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

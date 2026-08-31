"""Regression test for legacy digest evidence matching."""
import unittest

from build import related_digest_sources
from automation.validate_periodic_reports import ROOT, check_model


class LegacyEvidenceTests(unittest.TestCase):
    def test_unrelated_strong_match_is_not_used_as_fallback_evidence(self):
        daily = [{
            "date": "2026-08-17",
            "domestic": [{
                "title": "🔥 马王堆汉墓研究获系列新进展：T形帛画现改绘痕迹，确认全球最早丝质坐垫",
                "sources": [{"name": "新浪财经", "url": "https://cj.sina.cn/articles/view/7879923104/1d5ae15a006801hvk2?froms=ggmp&vt=4"}],
            }],
            "international": [{
                "title": "西西里罗马沉船发现大量陶罐",
                "sources": [{"name": "CNN", "url": "https://edition.cnn.com/2026/08/10/science/sicily-roman-shipwreck-scli-intl"}, {"name": "AP", "url": "https://apnews.com/article/example"}],
            }],
        }]
        title = "马王堆汉墓研究获系列新进展：T形帛画现改绘痕迹，确认全球最早丝质坐垫"
        context = "马王堆的启示是老发现新方法，T形帛画出现改绘痕迹。"
        self.assertEqual(related_digest_sources(title, daily, context), [])

    def test_periodic_validator_rejects_cross_item_highlight_evidence(self):
        model = {
            "layout": "periodic-v2", "type": "weekly", "periodKey": "2026-08-30",
            "metrics": {"publishedEvents": 0}, "dailyCounts": [], "highlights": [{
                "title": "事件A", "report": "reports/2026-08-30.html#item1",
                "sources": [{"url": "https://example.test/a"}],
            }], "evidence": [{
                "title": "事件A", "report": "reports/2026-08-30.html#item1",
                "sources": [{"url": "https://example.test/b"}],
            }],
        }
        errors = check_model(model, None, "weekly", "2026-08-30", ROOT / "missing.html")
        self.assertTrue(any("does not belong" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

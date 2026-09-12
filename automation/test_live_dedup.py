"""Human-labelled hard negatives and cross-publisher positives from the live audit.

This deliberately small challenge set detects known regressions; it is not an
estimate of precision/recall over all museum news.
"""
import json
from pathlib import Path
import unittest
from automation.daily_discovery import event_report_relation, event_actions

class LiveDedupTests(unittest.TestCase):
    def test_labelled_live_pairs(self):
        pairs=json.loads((Path(__file__).resolve().parents[1]/'audit/dedup-labelled-pairs.json').read_text(encoding='utf-8'))
        for pair in pairs:
            with self.subTest(left=pair['left']['title'], right=pair['right']['title']):
                self.assertEqual(bool(event_report_relation(pair['left'], pair['right'])), pair['sameEvent'])

    def test_english_action_word_boundaries(self):
        self.assertNotIn('closure', event_actions('A museum moves closer to reality'))
        self.assertNotEqual(event_actions('A museum will close'), event_actions('A museum moves closer to reality'))

    def test_shared_document_with_distinct_policy_or_segment_is_not_one_event(self):
        base={'url':'https://example.org/digest','publishedDate':'2026-09-06'}
        self.assertIsNone(event_report_relation(dict(base,title='《博物馆藏品管理办法》解读'),dict(base,title='《地下文物埋藏区划定指南》解读')))
        self.assertIsNone(event_report_relation(dict(base,title='博物馆动态',contentItemId='digest-a'),dict(base,title='博物馆动态',contentItemId='digest-b')))

    def test_source_date_is_not_replaced_by_later_repost_date(self):
        from automation.daily_discovery import aggregate_event_candidates
        title='《深圳市非国有博物馆扶持资金管理办法》政策解读'
        events=aggregate_event_candidates([
            {'title':title,'url':'https://example.gov.cn/original','publishedDate':'2026-09-01'},
            {'title':title,'url':'https://example.com/repost','publishedDate':'2026-09-06'},
        ])
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['publishedDate'],'2026-09-01')
        self.assertEqual(events[0]['latestReportedDate'],'2026-09-06')
        self.assertEqual(events[0]['firstReportedDate'],'2026-09-01')

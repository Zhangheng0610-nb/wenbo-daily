import unittest
from datetime import date
from unittest.mock import patch
from automation.daily_discovery import build_audit


class HistoryPrecedenceTests(unittest.TestCase):
    def test_same_batch_repeat_cannot_hide_published_root(self):
        old={'title':'全国文物地震安全工作交流会召开','publishedDate':'2026-09-04',
             'url':'https://www.ncha.gov.cn/art/2026/9/4/old.html',
             'historicalSource':'published_daily_markdown','historicalCanonicalEventId':'published-root'}
        rows=[dict(old,url='https://www.ncha.gov.cn/art/2026/9/6/'+str(i)+'.html',publishedDate='2026-09-06') for i in range(2)]
        for r in rows:
            r.pop('historicalSource');r.pop('historicalCanonicalEventId')
        with patch('automation.daily_discovery.load_history',return_value=[old]), patch('automation.daily_discovery.load_recent_editorial_rejections',return_value=[]):
            audit=build_audit(date(2026,9,7),rows,[],[],perform_evidence_upgrade=False)
        self.assertEqual([r['duplicateStatus'] for r in audit['records']],['historical_duplicate']*2)
        self.assertEqual([r['duplicateOf'] for r in audit['records']],['published-root']*2)
        self.assertEqual(audit['summary']['uniqueEvents'],0)

    def test_shared_bilateral_team_does_not_merge_explicitly_different_sites(self):
        from automation.daily_discovery import duplicate_relation, event_match_details
        a={'title':'中埃联合考古队在塞赫迈特神庙遗址发现重要遗迹','publishedDate':'2026-09-06'}
        b={'title':'中埃联合考古新突破：阿齐兹遗址发现神庙遗迹','publishedDate':'2026-08-29'}
        self.assertIsNone(duplicate_relation(a,b))
        self.assertFalse(event_match_details(a,b)['matched'])
        shortened=dict(b,title='中埃联合考古队新发现一批重要遗迹和文物')
        self.assertTrue(event_match_details(a,shortened)['matched'])


if __name__=='__main__': unittest.main()

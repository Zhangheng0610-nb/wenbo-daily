import unittest
from datetime import date
from unittest.mock import patch
from automation.daily_discovery import scan_sources


class SourceBatchTests(unittest.TestCase):
    def test_source_exception_does_not_abort_healthy_sources(self):
        specs=[{'sourceId':name,'name':name,'scope':'domestic','url':'https://example.test/'+name} for name in ('broken','healthy')]
        def scan(spec,start,end):
            if spec['sourceId']=='broken': raise ValueError('invalid markup')
            return {'sourceId':'healthy','status':'checked'},[{'title':'real lead'}]
        with patch('automation.daily_discovery.scan_page',side_effect=scan):
            statuses,records=scan_sources(specs,date(2026,9,1),date(2026,9,7))
        self.assertEqual([s['sourceId'] for s in statuses],['broken','healthy'])
        self.assertEqual(statuses[0]['status'],'parse_failed')
        self.assertEqual(records,[{'title':'real lead'}])
        for status in statuses:
            self.assertTrue(status['checkedAt'])
            self.assertTrue(status['completedAt'])
            self.assertGreaterEqual(status['elapsedSeconds'],0)
            self.assertEqual(status['windowEnd'],'2026-09-07')

    def test_empty_specs_do_not_invent_checks(self):
        self.assertEqual(scan_sources([],date(2026,9,1),date(2026,9,7)),([],[]))


if __name__=='__main__': unittest.main()

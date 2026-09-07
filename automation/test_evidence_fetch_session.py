import unittest
from unittest.mock import patch
from automation.daily_discovery import evidence_fetch_session, resolve_evidence_url


class EvidenceSessionTests(unittest.TestCase):
    def test_one_fetch_per_url_within_pass_and_fresh_next_pass(self):
        with patch('automation.daily_discovery._fetch_evidence_url',return_value=('https://a.test','body',None)) as fetch:
            with evidence_fetch_session():
                resolve_evidence_url('https://a.test');resolve_evidence_url('https://a.test')
            self.assertEqual(fetch.call_count,1)
            with evidence_fetch_session(): resolve_evidence_url('https://a.test')
            self.assertEqual(fetch.call_count,2)

    def test_failed_document_is_not_retried_for_each_digest_item(self):
        with patch('automation.daily_discovery._fetch_evidence_url',return_value=('https://a.test','','timeout')) as fetch:
            with evidence_fetch_session():
                a=resolve_evidence_url('https://a.test');b=resolve_evidence_url('https://a.test')
            self.assertEqual(a,b)
            self.assertEqual(fetch.call_count,1)


if __name__=='__main__': unittest.main()

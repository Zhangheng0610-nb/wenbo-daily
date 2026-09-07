from datetime import datetime,timedelta,timezone
import unittest
from automation.opportunity_evidence import evidence_for,signature
from automation.product import job_id

class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,9,7,tzinfo=timezone.utc)
  self.item={'institution':'博物馆','position':'修复','deadline':'2026-09-15','application':'原文邮箱','link_url':'https://example.org/job'}
  self.record={'jobId':job_id(self.item),'signature':signature(self.item),'outcome':'supported','fields':['deadline','application'],'sourceUrl':'https://example.org/job','checkedAt':self.now.isoformat(),'reviewAfter':(self.now+timedelta(days=3)).isoformat()}
 def test_future_deadline_is_not_verification(self):
  self.assertEqual(evidence_for(self.item,self.now,[])['state'],'missing')
 def test_supported_evidence_expires(self):
  self.assertEqual(evidence_for(self.item,self.now,[self.record])['state'],'recent')
  self.assertEqual(evidence_for(self.item,self.now+timedelta(days=3),[self.record])['state'],'stale')
 def test_changed_application_cannot_reuse_verification(self):
  self.assertEqual(evidence_for(dict(self.item,application='changed'),self.now,[self.record])['state'],'changed')
 def test_failed_fetch_never_becomes_verified(self):
  self.assertEqual(evidence_for(self.item,self.now,[dict(self.record,outcome='unavailable')])['state'],'unavailable')
 def test_future_verification_cannot_appear_current(self):
  self.assertEqual(evidence_for(self.item,self.now-timedelta(days=1),[self.record])['state'],'stale')

 def test_partial_evidence_is_not_complete_application_check(self):
  self.assertEqual(evidence_for(self.item,self.now,[dict(self.record,fields=['deadline'])])['state'],'incomplete')

import json
import tempfile
import unittest
from pathlib import Path
from datetime import date,timedelta
from automation.recruitment_sources import query_plan,REGIONS,scan_directory,navigational_url,inline_digest_records
from automation.recruitment_discovery import build_candidate,deduplicate_candidates,expand_umbrella_rows,_source_coverage,persistent_review_queue

class RecruitmentSourcesTests(unittest.TestCase):
 def test_every_region_is_visited_in_seven_days_with_overlap(self):
  plans=[query_plan(date(2026,9,9)+timedelta(days=i),{}, {'sources':[]}) for i in range(7)]
  self.assertEqual({p['region'] for plan in plans for p in plan if 'region' in p},set(REGIONS))
  self.assertTrue(all(p['lookbackDays']>=30 for plan in plans for p in plan))
  self.assertEqual(len({p['region'] for p in query_plan(date(2026,9,9),{}, {'sources':[]},full_sweep=True) if 'region' in p}),31)
 def test_same_host_search_runs_once_but_preserves_source_references(self):
  registry={'sources':[{'url':'https://example.org/a','active':True},{'url':'https://example.org/b','active':True}]}
  tasks=[p for p in query_plan(date(2026,9,9),{},registry) if p['family']=='registered_radar']
  self.assertEqual(len(tasks),1);self.assertEqual(len(tasks[0]['sourceUrls']),2)
 def test_direct_scan_keeps_undated_notices_not_navigation(self):
  source={'name':'directory','url':'https://www.gaoxiaojob.com/hotword/x'}
  html='<a href="/announcement/detail/1.html">某博物馆2026年招聘</a><a href="/job?keyword=博物馆">查看更多博物馆招聘职位</a>'
  rows,audit=scan_directory(source,lambda _:html,checked_at='2026-09-09T08:00:00+08:00')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['publishedDate'],'');self.assertEqual(rows[0]['verificationStatus'],'pending')
 def test_empty_or_blocked_is_not_no_vacancies(self):
  source={'name':'directory','url':'https://example.org'}
  _,a=scan_directory(source,lambda _:'<p>访问验证 验证码</p>',checked_at='now');self.assertEqual(a['status'],'failed')
  _,a=scan_directory(source,lambda _:'<p>招聘列表由脚本加载</p>',checked_at='now');self.assertEqual(a['status'],'partial')
 def test_search_success_does_not_claim_directory_checked(self):
  audits=[{'recruitmentQueryFamily':'professional_recruitment','success':True,'acceptedRawCount':0}]
  rows=_source_coverage(audits,{'sources':[{'name':'A','active':True,'url':'https://example.org','type':'professional_recruitment_site'}]})
  self.assertEqual(rows[-1]['status'],'not_checked')
  rows=_source_coverage([{'recruitmentQueryFamily':'official_institution','success':False}],{'sources':[]})
  self.assertEqual(rows[0]['result'],'unknown')
 def test_same_role_different_batches_or_codes_do_not_merge(self):
  a=build_candidate({'title':'某博物馆2025年招聘讲解员','institution':'某博物馆','position':'讲解员'})
  b=build_candidate({'title':'某博物馆2026年招聘讲解员','institution':'某博物馆','position':'讲解员'})
  self.assertEqual(len(deduplicate_candidates([a,b])),2)
  rows=expand_umbrella_rows([['招聘单位','岗位名称','岗位代码'],['某博物馆','管理','001'],['某博物馆','管理','002']],{'title':'2026年招聘'})
  self.assertEqual(len(deduplicate_candidates(rows)),2)
 def test_inline_notices_sharing_url_stay_separate_and_unverified(self):
  source={'name':'digest','url':'https://example.org/digest'}
  rows=inline_digest_records('【上海】某博物馆 一、岗位 二、报名时间：2026年9月15日。请发x@example.org 【浙江】另一个博物馆 一、岗位 实习生',source,'now')
  self.assertEqual(len(rows),2);self.assertEqual(rows[0]['applicationHints'],['x@example.org'])
  self.assertEqual(rows[1]['verificationStatus'],'pending')
  self.assertEqual(len(deduplicate_candidates([build_candidate(r) for r in rows])),2)
 def test_pending_survives_empty_run_and_explicit_rejection_survives_rediscovery(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)/'content/招聘/发现';folder.mkdir(parents=True)
   candidate=build_candidate({'title':'某博物馆招聘讲解员'})
   (folder/'2026-09-08.json').write_text(json.dumps({'date':'2026-09-08','candidates':[candidate]}))
   q=persistent_review_queue(tmp,{'date':'2026-09-09','candidates':[]})
   self.assertEqual(q['pendingCount'],1)
   (folder/'2026-09-08.json').write_text(json.dumps({'date':'2026-09-08','candidates':[{**candidate,'decision':'rejected'}]}))
   self.assertEqual(persistent_review_queue(tmp,{'date':'2026-09-09','candidates':[candidate]})['pendingCount'],0)

class RecruitmentDetailTests(unittest.TestCase):
 def test_dossier_keeps_attachment_and_application_evidence_without_verifying(self):
  from automation.recruitment_detail import inspect_detail
  html='<h1>某博物馆招聘公告</h1><p>报名时间：2026年9月9日至9月15日。报名方式：发送至jobs@example.org。</p><a href="/files/jobs.xlsx">岗位表附件</a>'+('<p>岗位资格与报名材料以本公告要求为准。</p>'*5)
  row=inspect_detail({'candidateId':'a','discoveryUrl':'https://example.org/notice'},lambda _:html,'now')
  self.assertEqual(row['status'],'readable');self.assertEqual(row['verificationStatus'],'pending')
  self.assertEqual(row['applicationEmails'],['jobs@example.org']);self.assertEqual(row['attachments'][0]['url'],'https://example.org/files/jobs.xlsx')
  self.assertTrue(row['applicationEvidence']);self.assertTrue(row['requiresAttachmentReview'])
 def test_shared_digest_fetched_once_preserving_candidate_ids(self):
  from automation.recruitment_detail import inspect_candidates
  calls=[]
  def fetch(url):calls.append(url);return '<p>公开招聘公告</p>'*40
  rows=inspect_candidates([{'candidateId':str(i),'discoveryUrl':'https://example.org/notice'} for i in range(3)],fetch,'now')
  self.assertEqual(len(calls),1);self.assertEqual(rows[0]['candidateIds'],['0','1','2'])

class UmbrellaRecallTests(unittest.TestCase):
 def test_government_search_keeps_notice_whose_museums_are_only_in_attachment(self):
  from automation.recruitment_discovery import keep_discovery_record
  row={'title':'某省2026年事业单位公开招聘公告','queryFamily':'recruitment-government_umbrella','url':'https://example.org/notice'}
  self.assertTrue(keep_discovery_record(row))
  self.assertFalse(keep_discovery_record({**row,'queryFamily':'unrelated'}))

class RecruitmentWebSearchTests(unittest.TestCase):
 def test_undated_job_keeps_snippet_without_turning_application_date_into_publication(self):
  from unittest.mock import patch,MagicMock
  from automation.recruitment_search import execute_query
  response=MagicMock();response.status=200;response.read.return_value='<li class="b_algo"><h2><a href="https://example.org/job">某博物馆招聘</a></h2><p>报名截止2026年9月15日。提供实习。</p></li>'.encode()
  response.__enter__.return_value=response
  with patch('automation.recruitment_search.SEARCH_OPENER.open',return_value=response):
   rows,audit=execute_query({'id':'recruitment-internship','scope':'domestic'},{'id':'bing-web'},'博物馆 招聘',date(2026,8,9),date(2026,9,9))
  self.assertTrue(audit['success']);self.assertEqual(rows[0]['publishedDate'],'');self.assertIn('9月15日',rows[0]['snippet'])

class RecruitmentReliabilityTests(unittest.TestCase):
 def test_irrelevant_web_response_is_failed_not_no_new_jobs(self):
  from unittest.mock import patch,MagicMock
  from automation.recruitment_search import execute_query
  response=MagicMock();response.status=200;response.read.return_value=b'<li class="b_algo"><h2><a href="https://example.org/house">House for sale</a></h2><p>House prices and property.</p></li>';response.__enter__.return_value=response
  with patch('automation.recruitment_search.SEARCH_OPENER.open',return_value=response):
   rows,audit=execute_query({'id':'recruitment-internship','scope':'domestic'},{'id':'bing-web'},'博物馆 实习',date(2026,8,9),date(2026,9,9))
  self.assertEqual(rows,[]);self.assertFalse(audit['success']);self.assertEqual(audit['failure'],'no_recruitment_relevance_in_returned_results')
 def test_queue_file_survives_when_no_daily_ledger_was_published(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)/'content/招聘';folder.mkdir(parents=True)
   candidate=build_candidate({'title':'某博物馆招聘讲解员'});candidate['firstSeen']='2026-09-08'
   (folder/'review-queue.json').write_text(json.dumps({'asOf':'2026-09-09','candidates':[candidate]}))
   queue=persistent_review_queue(tmp,{'date':'2026-09-10','candidates':[]})
   self.assertEqual(queue['pendingCount'],1);self.assertEqual(queue['candidates'][0]['firstSeen'],'2026-09-08')

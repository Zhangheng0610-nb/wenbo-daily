"""Regression coverage for body-only digital recall and institutional job discovery."""
import copy
import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock
import digital_trend as trend
from automation.digital_news import digital_news, render_digital_news
from automation.recruitment_sources import scan_directory

ROOT = Path(__file__).resolve().parents[1]


class DigitalRecallTests(unittest.TestCase):
    def test_recent_generic_title_is_admitted_by_its_own_body_and_survives_merge(self):
        old = json.loads((ROOT/'digital-data.json').read_text(encoding='utf-8'))
        generic = {'title':'某馆推出新的公众服务', 'date':date(2026,9,13), 'url':'/art/2026/9/13/fixture.html'}
        essay = {'title':'石质文物保护一域磨剑、全国攻坚', 'date':date(2026,9,13), 'url':'/essay.html'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'data.json'
            path.write_text(json.dumps(old), encoding='utf-8')
            with patch.object(trend,'DATA_PATH',str(path)), patch.object(trend,'DIGITAL_MONITOR_DIR',str(Path(tmp)/'monitor')), patch.object(trend,'fetch_recent_titles',return_value=([generic,essay],1)), patch.object(trend,'fetch',return_value='<nav>数字孪生</nav><div id="zoom"><p>博物馆启用数字导览系统，提供虚拟展厅服务。</p></div>'):
                data, audit = trend.run_incremental(date(2026,9,13))
        fresh = next(row for row in data['content_items'] if row['source_url']==generic['url'])
        self.assertIn('虚拟展厅',fresh['matched_keywords'])
        self.assertNotIn('数字孪生',fresh['matched_keywords'])
        self.assertEqual(audit['contentItemsNew'],1)
        self.assertEqual(audit['ordinaryBodyChecks'][1]['status'],'excluded_scope')

    def test_navigation_cannot_supply_a_digital_match(self):
        body = trend.html_to_text('<nav>数字化 VR</nav><div id="zoom">博物馆今天闭馆维护。</div>')
        self.assertIsNone(trend.admission_for_record('维护通知',body,allow_body_only=True))

    def test_digital_projection_keeps_event_identity_dates_and_scope(self):
        updates=[{'reportDate':'2026-09-13','publishedDate':'2026-09-11','url':'reports/2026-09-13.html#item1','documents':[{'title':'机构','url':'https://museum.example/a'}]}]
        event={'id':'event1','title':'博物馆启用数字平台','summary':'数字平台正式上线。','updates':updates}
        essay={**event,'id':'essay','title':'石质文物保护一域磨剑、全国攻坚'}
        with patch('automation.digital_news.reader_events',return_value=[event,essay]):
            data=digital_news(ROOT,[{'date':'2026-09-13'}])
        self.assertEqual(len(data['items']),1)
        self.assertEqual(data['items'][0]['eventId'],'event1')
        self.assertEqual(data['items'][0]['publishedDate'],'2026-09-11')
        self.assertNotIn('overall_share',data)
        self.assertIn('../reports/2026-09-13.html#item1',render_digital_news(data))


class InstitutionalDirectoryTests(unittest.TestCase):
    source={'name':'某博物馆招聘','institution':'某博物馆','type':'official_institution','url':'https://museum.example/jobs/','followPages':2}

    def test_short_headline_uses_institution_but_external_link_does_not(self):
        html='<a href="/notice/1">实习生招募</a><a href="https://unrelated.example/1">招聘司机</a><a href="/jobs/other/">招聘信息</a>'
        rows,_=scan_directory(self.source,lambda _:html,checked_at='now')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['institution'],'某博物馆')
        self.assertEqual(rows[0]['verificationStatus'],'pending')

    def test_next_page_recall_does_not_reenter_cycle(self):
        pages={self.source['url']:'<a href="index_2.html">下一页</a>', 'https://museum.example/jobs/index_2.html':'<a href="/notice/1">实习生招募</a><a href="/jobs/">下一页</a>'}
        calls=[]
        def fetch(url):calls.append(url);return pages[url]
        rows,audit=scan_directory(self.source,fetch,checked_at='now')
        self.assertEqual(len(rows),1);self.assertEqual(len(calls),2)
        self.assertEqual(audit['status'],'success')

    def test_recruitment_progress_is_not_a_new_vacancy(self):
        rows,audit=scan_directory(self.source,lambda _:'<a href="/notice/1">某博物馆招聘拟录用人员名单</a>',checked_at='now')
        self.assertEqual(rows,[])
        self.assertEqual(len(audit['lifecycleUpdates']),1)
        self.assertEqual(audit['result'],'workflow_updates_only')

    def test_museum_application_links_inherit_program_only_on_registered_path(self):
        source={**self.source,'applicationUrlPrefix':'https://ats.example/museum/job/','programName':'毕业生实习'}
        rows,_=scan_directory(source,lambda _:'<a href="https://ats.example/museum/job/1">Digital Content</a><a href="https://ats.example/company/job/1">Designer</a>',checked_at='now')
        self.assertEqual(len(rows),1);self.assertIn('毕业生实习',rows[0]['title'])
        self.assertEqual(rows[0]['institution'],'某博物馆')

    def test_umbrella_notice_retained_for_attachment_review(self):
        source={'name':'某省人社','url':'https://hr.example/jobs/','umbrellaNotices':True}
        rows,_=scan_directory(source,lambda _:'<a href="/notice">全省事业单位公开招聘公告</a>',checked_at='now')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['decisionReason'],'umbrella_notice_needs_attachment_inspection')

    def test_compressed_recruitment_search_decodes_before_parsing(self):
        from automation.recruitment_search import execute_query
        response=MagicMock();response.status=200;response.headers={'Content-Encoding':'gzip'}
        response.read.return_value=gzip.compress('<li class="b_algo"><h2><a href="https://museum.example/notice">某博物馆实习招募</a></h2><p>申请方式详见原文</p></li>'.encode())
        response.__enter__.return_value=response
        with patch('automation.recruitment_search.SEARCH_OPENER.open',return_value=response):
            rows,audit=execute_query({'id':'recruitment-internship','scope':'domestic'},{'id':'bing-web'},'博物馆 实习',date(2026,8,15),date(2026,9,13))
        self.assertTrue(audit['success']);self.assertEqual(len(rows),1)

class RecruitmentImportTests(unittest.TestCase):
    def test_imported_web_results_still_scan_directories(self):
        from automation.recruitment_discovery import collect_discovery_inputs
        imported={'records':[{'title':'网上公告'}],'queryAudits':[{'backend':'codex-web'}]}
        with patch('automation.recruitment_discovery.scan_directories',return_value=([{'title':'目录公告'}],[{'status':'success'}])) as scan:
            records,audits,directories=collect_discovery_inputs(date(2026,9,1),date(2026,9,13),input_data=imported)
        self.assertEqual(len(records),2);self.assertEqual(len(audits),1)
        self.assertEqual(directories,[{'status':'success'}]);scan.assert_called_once()

    def test_offline_replay_retains_directory_evidence_without_network(self):
        from automation.recruitment_discovery import collect_discovery_inputs, build_ledger
        imported={'rawRecords':[{'title':'全省事业单位公开招聘公告','url':'https://hr.example/notice','discoverySourceType':'recruitment_directory','decisionReason':'umbrella_notice_needs_attachment_inspection'}], 'directoryAudits':[{'status':'success'}]}
        with patch('automation.recruitment_discovery.scan_directories') as scan:
            records,audits,directories=collect_discovery_inputs(date(2026,9,1),date(2026,9,13),input_data=imported,no_live=True)
        scan.assert_not_called();self.assertEqual(directories,imported['directoryAudits'])
        self.assertEqual(build_ledger(date(2026,9,13),records,[])['candidateCount'],1)

class UniversityArticleTests(unittest.TestCase):
    def test_cms_article_in_form_is_readable_without_navigation(self):
        from automation.article_content import article_content
        page='<nav>另一家博物馆招聘</nav><form><input type="hidden"><div id="vsb_content_501"><p>四川大学博物馆招聘三个岗位，9月18日12:00截止。</p></div></form>'
        text,_,_=article_content(page)
        self.assertIn('三个岗位',text);self.assertNotIn('另一家',text)

    def test_hidden_or_related_cms_container_cannot_displace_actual_article(self):
        from automation.article_content import article_content
        page='<div hidden><div id="vsb_content_fake">数字平台上线</div></div><article><h1>招聘通知</h1><p>公开岗位正文。</p></article>'
        text,scope,_=article_content(page)
        self.assertEqual(scope,'article');self.assertNotIn('数字平台',text)

class DirectoryBoundaryTests(unittest.TestCase):
    def test_a_recruitment_excerpt_mentioning_review_is_still_a_lead(self):
        source={'name':'馆','institution':'某博物馆','type':'official_institution','url':'https://museum.example/jobs/'}
        rows,audit=scan_directory(source,lambda _:'<a href="/notice/1">某博物馆2026招聘公告 2026 / 09 / 13 应聘人员须通过资格审查，申请方法详见正文</a>',checked_at='now')
        self.assertEqual(len(rows),1);self.assertEqual(audit['lifecycleUpdates'],[])

    def test_pagination_does_not_fetch_non_http_protocol(self):
        source={'name':'馆','url':'https://museum.example/jobs/','followPages':2}
        calls=[]
        def fetch(url):calls.append(url);return '<a href="ftp://museum.example/jobs/two">下一页</a>'
        scan_directory(source,fetch,checked_at='now')
        self.assertEqual(calls,[source['url']])

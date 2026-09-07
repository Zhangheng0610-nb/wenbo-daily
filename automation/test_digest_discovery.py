import unittest
from datetime import date
from unittest.mock import patch
from automation.digest_discovery import digest_records, expand_batches
from automation.daily_discovery import build_audit, duplicate_relation, resolve_evidence_attempt, aggregate_event_candidates

PAGE = '''<div id="zw"><p><strong>浙江</strong></p>
<p><strong>浙江海洋遗址考古发掘取得重要发现</strong></p><p>考古团队公布海洋遗址的新发现，出土文物揭示古代港口贸易与交通历史。</p>
<p><strong>四川</strong></p><p><strong>四川石窟保护修缮工程完成</strong></p><p>四川石窟修缮完成，保护团队实施防渗和加固工程，改善遗存保存条件。</p></div>'''
PARENT = {'title':'一周文物动态摘编（8.29-9.4）', 'url':'http://www.ncha.gov.cn/art/2026/9/6/art_722_204716.html',
          'publishedDate':'2026-09-06', 'scope':'domestic', 'sourceDomain':'ncha.gov.cn', 'discoverySourceType':'source_scan'}

class DigestTests(unittest.TestCase):
    def test_regions_bodies_and_identity_are_isolated(self):
        records = digest_records(PARENT, PAGE)
        self.assertEqual(len(records),2)
        self.assertNotEqual(records[0]['contentItemId'],records[1]['contentItemId'])
        self.assertEqual(records[0]['sourceRegionLabel'],'浙江')
        self.assertNotIn('四川',records[0]['summary'])
        self.assertIsNone(records[0]['eventDate'])
        self.assertEqual(records[0]['publicationDateBasis'],'digest_publication')
        self.assertIsNone(duplicate_relation(records[0],records[1]))

    def test_same_url_children_survive_full_audit_and_parent_is_not_news(self):
        records = digest_records(PARENT,PAGE)
        with patch('automation.daily_discovery.load_history',return_value=[]), patch('automation.daily_discovery.load_recent_editorial_rejections',return_value=[]):
            audit=build_audit(date(2026,9,7),records+records,[],[],perform_evidence_upgrade=False)
            parent=build_audit(date(2026,9,7),[PARENT],[],[],perform_evidence_upgrade=False)
        self.assertEqual(len(audit['records']),2)
        self.assertEqual(audit['summary']['uniqueEvents'],2)
        self.assertFalse(parent['candidateEvaluation']['finalEditorialPool']['events'])
        self.assertFalse(audit['candidateEvaluation']['finalEditorialPool']['events'])

    def test_generic_workflows_do_not_merge_distinct_real_events(self):
        pairs = [
            ('国家文物局印发《考古出土（出水）文物移交管理办法（试行）》', '北京市文物局转发加强博物馆陈列展览内容审核工作的通知', False),
            ('中埃联合考古队在塞赫迈特神庙遗址取得重要发现', '中国考古机构首次赴南美洲开展联合考古：与秘鲁共研卡拉尔文明', False),
            ('中埃联合考古队在塞赫迈特神庙遗址取得重要发现', '希腊古城苏里亚新发现：阿尔忒弥斯雕像或指向神庙遗址', False),
            ('上海加强博物馆陈列展览内容审核', '北京市文物局转发加强博物馆陈列展览内容审核工作的通知', False),
            ('上海加强博物馆陈列展览内容审核', '上海文物局发文加强博物馆陈列展览内容审核工作，明确核查重点', True),
            ('全国文物地震安全工作交流会召开', '国家文物局与中国地震局联合召开全国文物地震安全工作交流会', True),
        ]
        for current, previous, expected in pairs:
            with self.subTest(current=current,previous=previous):
                left={'title':current,'publishedDate':'2026-09-06'}
                right={'title':previous,'publishedDate':'2026-09-04'}
                self.assertEqual(duplicate_relation(left,right) is not None,expected)

    def test_saved_candidate_keeps_segment_identity_for_later_verification(self):
        records=digest_records(PARENT,PAGE)
        with patch('automation.daily_discovery.load_history',return_value=[]), patch('automation.daily_discovery.load_recent_editorial_rejections',return_value=[]):
            audit=build_audit(date(2026,9,7),records,[],[],perform_evidence_upgrade=False)
        pool=audit['candidateEvaluation']['pool']
        self.assertTrue(pool)
        for row in pool:
            self.assertTrue(row['isDigestItem'])
            self.assertEqual(row['publicationDateBasis'],'digest_publication')
            self.assertIn(row['contentItemId'],[r['contentItemId'] for r in records])
            with patch('automation.daily_discovery.resolve_evidence_url',return_value=(PARENT['url'],'<div id="zw"></div>',None)):
                _,source=resolve_evidence_attempt(row,row,'existing_report')
            self.assertIsNone(source)

    def test_fetch_once_and_keep_discovery_provenance(self):
        radar=dict(PARENT,discoverySourceType='fixed_panel_radar')
        with patch('automation.digest_discovery.digest_records',wraps=digest_records):
            calls=[]
            batches,audits=expand_batches([[PARENT],[radar]],lambda url:(calls.append(url) or PAGE))
        self.assertEqual(len(calls),1)
        self.assertEqual(batches[1][0]['discoverySourceType'],'fixed_panel_radar')
        self.assertEqual(audits[0]['items'],2)

    def test_supplementary_phase_uses_same_digest_budget_and_cache(self):
        cache, calls = {}, []
        fetch=lambda url:(calls.append(url) or PAGE)
        first,_=expand_batches([[PARENT]],fetch,max_documents=1,document_cache=cache)
        later=dict(PARENT,discoverySourceType='supplementary_search')
        second,audits=expand_batches([[later]],fetch,max_documents=1,document_cache=cache)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(second[0]),2)
        self.assertEqual(second[0][0]['discoverySourceType'],'supplementary_search')
        self.assertEqual(audits,[])
        other=dict(PARENT,url=PARENT['url'].replace('204716','204717'))
        limited,_=expand_batches([[other]],fetch,max_documents=1,document_cache=cache)
        self.assertEqual(limited[0],[other])
        self.assertEqual(len(calls),1)

    def test_failed_parser_preserves_container_for_audit(self):
        batches,audits=expand_batches([[PARENT]],lambda _: '<html>unavailable</html>')
        self.assertEqual(batches[0],[PARENT])
        self.assertEqual(audits[0]['status'],'parse_failed')

    def test_evidence_match_never_sees_sibling_body(self):
        record=digest_records(PARENT,PAGE)[0]
        event=aggregate_event_candidates([record])[0]
        with patch('automation.daily_discovery.resolve_evidence_url',return_value=(PARENT['url'],PAGE,None)), \
             patch('automation.daily_discovery.event_match_details',return_value={'matched':True,'score':100,'reasons':[]}) as match:
            outcome,source=resolve_evidence_attempt(event,record,'existing_report')
        checked_body=match.call_args.args[2]
        self.assertNotIn('四川',checked_body)
        self.assertIn('海洋遗址',checked_body)
        self.assertEqual(source['contentItemId'],record['contentItemId'])

    def test_missing_segment_cannot_be_verified_from_other_blocks(self):
        record=digest_records(PARENT,PAGE)[0]
        with patch('automation.daily_discovery.resolve_evidence_url',return_value=(PARENT['url'],'<div id="zw"></div>',None)):
            outcome,source=resolve_evidence_attempt(record,record,'existing_report')
        self.assertIsNone(source)
        self.assertEqual(outcome['checked']['error'],'digest_segment_not_found')

if __name__=='__main__': unittest.main()

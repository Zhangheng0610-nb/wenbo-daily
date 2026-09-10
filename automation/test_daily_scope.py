import unittest
from datetime import date
from automation.daily_scope import daily_scope_rejection
from automation.daily_discovery import editorial_priority, evaluate_candidate_pool

class DailyScopeTests(unittest.TestCase):
    def test_user_examples_excluded_despite_freshness_and_editorial_praise(self):
        for title in ['石质文物保护把检测、建模和材料试验连在一起','云阳杨沙村汉墓出土铜雀名称和功用探析','分子考古学解码人与犬的同行史','内蒙古陈巴尔虎旗岗嘎墓地发掘报告']:
            with self.subTest(title=title):
                record={'title':title,'publishedDate':'2026-09-10','newDevelopment':True,'notes':'国家文物局发布，重大考古发现，推动数字化平台上线','url':'https://kaogu.cn/example.html'}
                self.assertEqual(daily_scope_rejection(record),'academic_discussion_without_industry_action')
                self.assertEqual(editorial_priority(record,date(2026,9,10))['score'],0)
    def test_broader_academic_forms_excluded(self):
        for title in ['陶瓷修复材料试验的新进展','某墓地发掘简报发布','汉代铜镜纹样考释','A new excavation report from the valley']:
            self.assertIsNotNone(daily_scope_rejection({'title':title}))
    def test_real_events_and_new_excavations_are_not_blanket_excluded(self):
        for title in ['某遗址新发现大型汉代墓葬群','国家文物局发布重大考古新发现','博物馆数字化平台正式上线','文物保护新规正式实施','某遗址发掘报告发布，遗址公园正式开放','石质文物保护工程启动：检测与材料试验同步进行']:
            self.assertIsNone(daily_scope_rejection({'title':title}),title)
    def test_representative_headline_not_rewritten_commentary(self):
        self.assertIsNotNone(daily_scope_rejection({'representativeTitle':'某墓地发掘报告','title':'重大考古新发现'}))
    def test_rejected_before_evidence_queue_even_for_official_source(self):
        record={'title':'某墓地发掘报告','publishedDate':'2026-09-10','url':'http://www.ncha.gov.cn/art/2026/9/10/art_722_204758.html','eventId':'academic-1'}
        result=evaluate_candidate_pool(date(2026,9,10),[record],previous_rejections=[])
        self.assertEqual(result['records'][0]['candidateDisposition'],'rejected')
        self.assertEqual(result['pool'],[])
        self.assertEqual(result['highPriorityEvidenceQueue'],[])
    def test_academic_section_does_not_escape_through_generic_headline(self):
        self.assertIsNotNone(daily_scope_rejection({'title':'人与犬的同行史','evidenceSources':[{'url':'http://kaogu.cssn.cn/xsqy/kycg/xslw/202609/a.shtml'}]}))
    def test_original_stone_conservation_headline_also_excluded(self):
        self.assertIsNotNone(daily_scope_rejection({'title':'风霜过隙 石壁犹存——石质文物保护一域磨剑、全国攻坚'}))

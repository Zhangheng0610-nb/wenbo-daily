import unittest
from datetime import date
from automation.industry_signals import industry_signals
from automation.daily_discovery import evaluate_candidate_pool

class IndustrySignalsTests(unittest.TestCase):
    def evaluate(self,title,**kwargs):
        return evaluate_candidate_pool(date(2026,9,11),[{'title':title,'publishedDate':'2026-09-08','scope':'international','url':'https://example.org/article',**kwargs}],previous_rejections=[])['records'][0]
    def test_real_institution_actions_survive_recall_and_get_evidence_priority(self):
        for title in ["Smithsonian Secretary Lonnie Bunch resigns amid attacks from Trump administration", "UA Museum gets federal grant to support 'Into the Wild' bus exhibits", '法国雷诺阿博物馆两幅遭窃画作被找到','爱尔兰洞穴艺术发现或将人类活动线索推前至约1.5万年前']:
            with self.subTest(title=title):
                row=self.evaluate(title)
                self.assertEqual(row['candidateDisposition'],'needs_verification')
                self.assertGreaterEqual(row['editorialPriorityScore'],55)
                self.assertEqual(row['evidenceQueueClass'],'priority')
    def test_generic_politics_and_unrelated_grants_not_rescued(self):
        for title in ['Federal Secretary resigns amid government attacks','University gets federal grant for sports','Governor appoints new secretary','Museum grants wishes for holiday visitors']:
            self.assertFalse(industry_signals({'title':title}))
    def test_publisher_and_notes_do_not_create_new_signal(self):
        self.assertFalse(industry_signals({'title':'Secretary resigns','publisher':'Smithsonian','notes':'museum funding'}))
    def test_academic_scope_still_overrides_action_terms(self):
        row=self.evaluate('博物馆拨款机制探析')
        self.assertEqual(row['candidateDisposition'],'rejected')
        self.assertEqual(row['editorialPriorityScore'],0)

    def test_same_funding_survives_prefix_source_and_numeric_format_changes(self):
        from automation.daily_discovery import historical_published_event_relation
        old={'title':'温尼伯圣博尼法斯博物馆获40万加元联邦修复资金','publishedDate':'2026-09-09','url':'https://one.example/article'}
        new={'title':'加拿大圣博尼法斯博物馆获400,000加元修复资金','publishedDate':'2026-09-11','url':'https://two.example/article'}
        self.assertEqual(historical_published_event_relation(new,old)[0],'historical_duplicate')
        self.assertIsNone(historical_published_event_relation({**new,'substantiveNewDevelopment':True},old))
    def test_distinct_funding_not_collapsed_by_new_rule(self):
        from automation.industry_signals import same_restoration_funding
        old={'title':'温尼伯圣博尼法斯博物馆获40万加元修复资金','publishedDate':'2026-09-09'}
        for title in ['加拿大圣博尼法斯博物馆获50万加元修复资金','加拿大圣博尼法斯博物馆获40万美元修复资金','加拿大圣博尼法斯博物馆获40万加元展览资金','加拿大另一家新博物馆获40万加元修复资金','加拿大圣博尼法斯博物馆追加40万加元修复资金','加拿大圣博尼法斯博物馆被取消40万加元修复资金','加拿大圣博尼法斯博物馆获500,000加元修复资金']:
            self.assertFalse(same_restoration_funding({'title':title,'publishedDate':'2026-09-11'},old),title)
        self.assertFalse(same_restoration_funding({**old,'publishedDate':'2026-10-11'},old))

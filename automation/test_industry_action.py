import copy
import unittest
import tempfile
from pathlib import Path
from automation.daily_scope import industry_action_errors as validate_action, save_action_source

def industry_action_errors(row, day):
    return validate_action(row, day, root=row.get("_testRoot"))

class IndustryActionTests(unittest.TestCase):
    def setUp(self):
        self.row = {'decision':'selected','evidenceSources':[{'url':'https://example.org/announcement','articleVerified':True}],
                    'industryAction':{'kind':'funding','actor':'某博物馆','action':'获得修复拨款','change':'资金正式获批，进入修复准备阶段',
                    'eventDate':'2026-09-10','timeBasis':'announcement_date','sourceUrl':'https://example.org/announcement',
                    'sourceExcerpt':'2026年9月10日，某博物馆宣布获得修复拨款，用于修复馆舍及更新公共展览空间。',
                    'dateExcerpt':'2026年9月10日'}}
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.row['_testRoot']=self.tmp.name
        self.row['industryAction'].update(save_action_source(self.tmp.name, 'https://example.org/announcement', self.row['industryAction']['sourceExcerpt'], '2026-09-11T08:00:00+08:00'))
    def test_supported_action_passes(self):
        self.assertEqual(industry_action_errors(self.row,'2026-09-11'),[])
    def test_new_selection_without_receipt_fails_but_discovery_is_unblocked(self):
        self.assertTrue(industry_action_errors({'decision':'selected'},'2026-09-11'))
        self.assertEqual(industry_action_errors({'decision':'needs_verification'},'2026-09-11'),[])
        self.assertEqual(industry_action_errors({'decision':'selected'},'2026-09-10'),[])
    def test_old_event_is_not_refreshed_by_a_new_article_date(self):
        self.row['publishedDate']='2026-09-11'
        self.row['industryAction']['eventDate']='2026-07-01'
        self.assertTrue(any('seven-day' in e for e in industry_action_errors(self.row,'2026-09-11')))
    def test_editorial_claim_cannot_replace_source_action(self):
        self.row['industryAction']['action']='引领行业重大变革'
        self.assertTrue(any('action must occur' in e for e in industry_action_errors(self.row,'2026-09-11')))
    def test_wrong_source_and_unverified_source_fail(self):
        for change in ['different_url','unverified']:
            row=copy.deepcopy(self.row)
            if change=='different_url':row['industryAction']['sourceUrl']='https://other.example.org/'
            else:row['evidenceSources'][0]['articleVerified']=False
            self.assertTrue(any('article-verified' in e for e in industry_action_errors(row,'2026-09-11')))
    def test_paper_publication_and_article_date_not_valid_event_types(self):
        self.row['industryAction'].update(kind='paper_publication',timeBasis='article_publication_date')
        self.assertEqual(len(industry_action_errors(self.row,'2026-09-11')),2)
    def test_unparseable_and_future_dates_fail(self):
        for value in [None,{},'yesterday','2026-09-12']:
            self.row['industryAction']['eventDate']=value
            self.assertTrue(industry_action_errors(self.row,'2026-09-11'))
    def test_invalid_field_types_fail_without_crash(self):
        for field in ['actor','action','change','sourceUrl','sourceExcerpt','dateExcerpt','kind','timeBasis']:
            row=copy.deepcopy(self.row);row['industryAction'][field]={}
            self.assertTrue(industry_action_errors(row,'2026-09-11'))

    def test_fabricated_quote_not_in_saved_source_fails(self):
        self.row['industryAction']['sourceExcerpt'] += ' 专家称这将引领行业。'
        self.assertTrue(any('retained source' in e for e in industry_action_errors(self.row,'2026-09-11')))
    def test_modified_source_snapshot_fails(self):
        path=Path(self.tmp.name)/self.row['industryAction']['sourceDocumentPath']
        path.write_text('{}',encoding='utf-8')
        self.assertTrue(any('hash mismatch' in e for e in industry_action_errors(self.row,'2026-09-11')))
    def test_windows_line_endings_preserve_source_hash(self):
        path=Path(self.tmp.name)/self.row['industryAction']['sourceDocumentPath']
        path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
        self.assertEqual(industry_action_errors(self.row,'2026-09-11'),[])

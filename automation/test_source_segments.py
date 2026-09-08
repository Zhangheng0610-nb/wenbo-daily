import copy
import unittest
from automation.source_segments import approved_shared_urls


class SharedSourceTests(unittest.TestCase):
    def setUp(self):
        self.url='http://www.ncha.gov.cn/art/2026/9/6/art_722_204716.html'
        self.items=[{'number':i,'title':str(i),'sources':[{'url':self.url}]} for i in (1,2)]
        self.candidates=[]
        self.events=[]
        for i in (1,2):
            source={'url':self.url,'contentItemId':'digest-'+str(i),'articleVerified':True,'tier':'A','publicationDateBasis':'digest_publication'}
            self.candidates.append({'eventId':str(i),'dailyItemNumber':i,'dailyItemTitle':str(i),'decision':'selected','selectedForDaily':True,'evidenceSources':[source]})
            self.events.append({'eventId':str(i),'evidenceSources':[copy.deepcopy(source)]})

    def allowed(self):
        return bool(approved_shared_urls(self.items,self.candidates,self.events))

    def test_two_verified_distinct_items_can_share_document(self): self.assertTrue(self.allowed())
    def test_same_segment_still_rejected(self):
        self.candidates[1]['evidenceSources'][0]['contentItemId']='digest-1'
        self.events[1]['evidenceSources'][0]['contentItemId']='digest-1'
        self.assertFalse(self.allowed())
    def test_unverified_item_rejected(self):
        self.candidates[1]['evidenceSources'][0]['articleVerified']=False
        self.assertFalse(self.allowed())
    def test_invented_segment_not_in_editorial_pool_rejected(self):
        self.candidates[1]['evidenceSources'][0]['contentItemId']='digest-invented'
        self.assertFalse(self.allowed())
    def test_wrong_daily_item_mapping_rejected(self):
        self.candidates[1]['dailyItemTitle']='different'
        self.assertFalse(self.allowed())
    def test_two_copies_inside_one_item_rejected(self):
        self.items[0]['sources'].append({'url':self.url})
        self.assertFalse(self.allowed())


if __name__=='__main__': unittest.main()

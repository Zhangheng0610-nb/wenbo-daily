import json,tempfile,unittest
from pathlib import Path
from automation.reader_product import reader_events
from automation.evidence_audit import audit_for,audit_html
from build import parse_md
ROOT=Path(__file__).resolve().parents[1]
class ReaderTests(unittest.TestCase):
 def test_shared_digest_url_does_not_define_event(self):
  items=[{'id':'item'+str(i),'number':i,'title':t,'body':'摘要','sources':[{'name':'汇编','url':'https://example.org/digest'}]} for i,t in enumerate(['北京闭馆','西藏闭馆'],1)]
  with tempfile.TemporaryDirectory() as root:
   events=reader_events(root,[{'date':'2026-09-06','ordered_items':items}])
  self.assertEqual(len(events),2)
  self.assertIsNone(events[0]['updates'][0]['publishedDate'])
 def test_editorial_identity_keeps_all_updates_and_separate_dates(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'content/候选').mkdir(parents=True)
   reports=[]
   for d in ['2026-09-05','2026-09-06']:
    item={'id':'item1','number':1,'title':'同一事件的进展','body':'摘要','sources':[]}
    reports.append({'date':d,'ordered_items':[item]})
    (root/'content/候选'/f'{d}.json').write_text(json.dumps({'candidates':[{'selectedForDaily':True,'dailyItemNumber':1,'dailyItemTitle':item['title'],'eventId':'event-fixture','publishedDate':'2026-09-03','newDevelopment':d.endswith('06')}]}))
   events=reader_events(root,reports)
  self.assertEqual(len(events),1);self.assertEqual(len(events[0]['updates']),2)
  self.assertEqual(events[0]['updates'][0]['reportDate'],'2026-09-06')
  self.assertEqual(events[0]['updates'][0]['publishedDate'],'2026-09-03')
 def test_historical_correction_is_bound_to_specific_item(self):
  report=parse_md(ROOT/'content/日报/2026-08-08.md')
  item=next(i for i in report['ordered_items'] if i['id']=='item4')
  record=audit_for(report['date'],item)
  self.assertEqual(record['status'],'source_mismatch');self.assertIn('北京中轴线',audit_html(record))
  with self.assertRaises(ValueError):audit_for(report['date'],dict(item,title='different article'))

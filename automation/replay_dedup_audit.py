"""Offline replay of saved live evidence; does not write production ledgers."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from automation.daily_discovery import aggregate_event_candidates,event_report_relation,now_cn

def main():
 parser=argparse.ArgumentParser();parser.add_argument('evidence',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 payload=json.loads(args.evidence.read_text());records=payload['rawRecords']
 pairs=json.loads((ROOT/'audit/dedup-labelled-pairs.json').read_text())
 results=[{'left':p['left']['title'],'right':p['right']['title'],'expectedSameEvent':p['sameEvent'],'matched':bool(event_report_relation(p['left'],p['right']))} for p in pairs]
 events=aggregate_event_candidates(records)
 result={'executedAt':now_cn(),'runType':'offline_quality_replay','notProductionRun':True,
         'evidence':str(args.evidence),'rawRecords':len(records),'eventClusters':len(events),
         'labelledPairs':results,'correctPairs':sum(r['expectedSameEvent']==r['matched'] for r in results),
         'limitation':'Small selected challenge set; not population precision/recall. Search response success is not source coverage.'}
 args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['rawRecords','eventClusters','correctPairs']}))
if __name__=='__main__':main()

"""Explicit live audit; writes separate evidence and never overwrites editorial ledgers."""
from pathlib import Path
import sys,json
from datetime import date,timedelta
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from automation.daily_discovery import execute_queries, SOURCE_SCANS, scan_page, aggregate_event_candidates, now_cn

def main():
    end=date.fromisoformat(sys.argv[1]);start=end-timedelta(days=6)
    target=ROOT/'audit'/('live-discovery-'+end.isoformat()+'.json')
    with ThreadPoolExecutor(max_workers=6) as pool:
        scans=list(pool.map(lambda spec:scan_page(spec,start,end),SOURCE_SCANS))
    records,audits=execute_queries(end,start,end)
    source_rows=[r for _,rows in scans for r in rows]
    all_rows=source_rows+records
    events=aggregate_event_candidates(all_rows)
    result={'runType':'live_quality_audit','executedAt':now_cn(),'targetWindow':[start.isoformat(),end.isoformat()],
      'notProductionRun':True,'sourceScans':[s for s,_ in scans],'queryAudits':audits,
      'rawRecords':all_rows,'events':events,
      'summary':{'queries':len(audits),'successfulQueries':sum(a['success'] for a in audits),'rawRecords':len(all_rows),'eventClusters':len(events),'sources':len(scans),'sourceResponses':sum(s['status']=='checked' for s,_ in scans)}}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['summary'],ensure_ascii=False))
if __name__=='__main__':main()

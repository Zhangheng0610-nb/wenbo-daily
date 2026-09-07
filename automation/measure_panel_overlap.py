"""Read-only per-adapter overlap audit; persist each completed result immediately."""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from automation.backfill_monitoring import CRAWLERS, TZ, allowed_backfill_row

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    parser.add_argument('--sources', nargs='+', choices=[s for s, _ in CRAWLERS], default=[s for s, _ in CRAWLERS])
    args = parser.parse_args()
    start = args.date - timedelta(days=6)
    target = ROOT / 'audit' / f'panel-overlap-{args.date}.json'
    result = {'runType': 'live_quality_audit', 'notProductionRun': True,
              'publicationWindow': [str(start), str(args.date)], 'requestedSources': args.sources,
              'sources': [], 'completed': False}
    def scan(pair):
        sid, crawler = pair
        try:
            rows, complete, note = crawler(start, args.date)
        except Exception as exc:
            rows, complete, note = [], False, str(exc)
        qualified = [r for r in rows if allowed_backfill_row(r)]
        return {'sourceId': sid, 'checkedAt': datetime.now(TZ).isoformat(), 'complete': complete,
                'note': note, 'rawRows': len(rows), 'eligibleRows': len(qualified),
                'sameDayOnlyRows': sum(r['date'] == str(args.date) for r in qualified),
                'recoveredEarlierRows': sum(r['date'] < str(args.date) for r in qualified), 'rows': rows}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(scan, pair) for pair in CRAWLERS if pair[0] in args.sources]
        for future in as_completed(futures):
            row = future.result()
            result['sources'].append(row)
            result['completed'] = len(result['sources']) == len(args.sources)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print({k: v for k, v in row.items() if k not in {'rows', 'note'}}, flush=True)
if __name__ == '__main__':
    main()

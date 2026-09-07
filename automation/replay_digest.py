"""Replay a saved official digest against historical dailies; never publishes.

python -m automation.replay_digest --html /path/page.html --date YYYY-MM-DD
"""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from automation.digest_discovery import digest_records
from automation.daily_discovery import build_audit, aggregate_event_candidates, resolve_evidence_attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--published', default='2026-09-06')
    parser.add_argument('--url', default='http://www.ncha.gov.cn/art/2026/9/6/art_722_204716.html')
    parser.add_argument('--output', default='audit/digest-expansion-replay.json')
    args = parser.parse_args()
    page = Path(args.html).read_text()
    parent = {'title':'一周文物动态摘编', 'url':args.url, 'publishedDate':args.published,
              'scope':'domestic', 'sourceDomain':'ncha.gov.cn', 'discoverySourceType':'source_scan'}
    records = digest_records(parent, page)
    audit = build_audit(date.fromisoformat(args.date), records, [], [], perform_evidence_upgrade=False)
    rows = []
    for raw, record in zip(records, audit['records']):
        with patch('automation.daily_discovery.resolve_evidence_url', return_value=(args.url, page, None)):
            _, source = resolve_evidence_attempt(aggregate_event_candidates([raw])[0], raw, 'existing_report')
        rows.append({k:record.get(k) for k in ('title','contentItemId','sourceRegionLabel','duplicateStatus',
                     'duplicateReason','duplicateOfTitle','eventDate','publicationDateBasis')} | {
                     'bodyCharacters':len(raw['summary']),
                     'bodySHA256':hashlib.sha256(raw['summary'].encode()).hexdigest(),
                     'isolatedEvidenceMatched':source is not None})
    result = {'mode':'offline replay of saved real HTML; real semantic matcher, mocked transport; no publication',
              'targetDate':args.date, 'url':args.url,'documentSHA256':hashlib.sha256(page.encode()).hexdigest(),
              'summary':audit['summary'], 'items':rows, 'candidateEvaluation':audit['candidateEvaluation']}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    for row in rows:
        print(row['duplicateStatus'], row['title'], '->', row['duplicateOfTitle'])


if __name__ == '__main__':
    main()

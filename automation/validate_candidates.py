"""Validate the auditable daily editorial candidate ledger."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = ROOT / 'content' / '候选'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from automation.governance import canonical_url, source_info
REQUIRED = {
    'candidateId', 'title', 'publishedDate', 'discoveredAt',
    'discoverySource', 'discoverySourceType', 'discoveryUrl',
    'publisher', 'evidenceSources', 'evidenceTier', 'topic',
    'domestic', 'international', 'scope', 'decision', 'decisionReason',
    'selectedForDaily', 'dedupStatus', 'notes',
}
DECISIONS = {'selected', 'rejected', 'deferred', 'needs_verification'}
# Keep the two earlier ledger vocabularies readable; new discovery audits use
# the explicit event-level values below.  Historical ledgers are not silently
# rewritten just to satisfy the newer validator.
DUPLICATE_STATUSES = {'unique_event', 'same_day_duplicate', 'historical_duplicate', 'new_development', 'possible_duplicate', 'unique_opportunity', 'unresolved', 'not_selected'}
DISCOVERY_AUDIT_REQUIRED_FROM = date(2026, 8, 31)


def valid_url(value):
    parsed = urlparse(value or '')
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def validate_discovery_audit(ledger_path, payload):
    """Validate the separate broad-discovery audit without mixing it into map data."""
    errors = []
    try:
        ledger_date = date.fromisoformat(payload.get('date', ''))
    except (TypeError, ValueError):
        return ['cannot validate discovery audit for invalid ledger date']
    ref = payload.get('discoveryAuditPath')
    if ledger_date >= DISCOVERY_AUDIT_REQUIRED_FROM and not ref:
        return ['daily ledger needs discoveryAuditPath from 2026-08-31 onward']
    if not ref:
        return errors
    audit_path = (ROOT / ref).resolve()
    if ROOT not in audit_path.parents or not audit_path.exists():
        return [f'discovery audit missing: {ref}']
    try:
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return [f'invalid discovery audit: {exc}']
    if audit.get('schema') != 'daily-discovery-v1':
        errors.append('discovery audit schema must be daily-discovery-v1')
    if audit.get('date') != payload.get('date'):
        errors.append('discovery audit date does not match ledger')
    scans = audit.get('sourceScans')
    if not isinstance(scans, list) or not scans:
        errors.append('discovery audit needs sourceScans')
    else:
        for scan in scans:
            if scan.get('status') == 'no_update':
                errors.append(f'discovery scan cannot use no_update: {scan.get("sourceId", "?")}')
            if scan.get('status') not in {'checked', 'fetch_failed', 'parse_failed', 'blocked'}:
                errors.append(f'invalid discovery scan status: {scan.get("sourceId", "?")}')
    if not isinstance(audit.get('queryFamilies'), list) or not audit.get('queryFamilies'):
        errors.append('discovery audit needs queryFamilies')
    query_audits = audit.get('queryAudits')
    if audit.get('queryAuditStatus') == 'checked':
        if not isinstance(query_audits, list) or not query_audits:
            errors.append('checked discovery audit needs queryAudits')
        else:
            for index, query in enumerate(query_audits, 1):
                required_query_fields = {'queryFamily', 'actualQuery', 'executedAt', 'success', 'returnedResultCount', 'acceptedRawCount'}
                missing = sorted(required_query_fields - set(query))
                if missing:
                    errors.append(f'query audit {index}: missing fields: {", ".join(missing)}')
                if not isinstance(query.get('success'), bool):
                    errors.append(f'query audit {index}: success must be boolean')
                for field in ('returnedResultCount', 'acceptedRawCount'):
                    if not isinstance(query.get(field), int) or query[field] < 0:
                        errors.append(f'query audit {index}: {field} must be a non-negative integer')
                if query.get('acceptedRawCount', 0) > query.get('returnedResultCount', 0):
                    errors.append(f'query audit {index}: acceptedRawCount exceeds returnedResultCount')
    elif query_audits not in (None, [],):
        errors.append('queryAudits require queryAuditStatus=checked')
    records = audit.get('records')
    if not isinstance(records, list):
        errors.append('discovery audit records must be a list')
    else:
        for index, record in enumerate(records, 1):
            status = record.get('duplicateStatus', 'unique_event')
            if status not in DUPLICATE_STATUSES:
                errors.append(f'discovery record {index}: invalid duplicateStatus')
            if status in {'same_day_duplicate', 'historical_duplicate', 'possible_duplicate'} and not record.get('duplicateOf'):
                errors.append(f'discovery record {index}: duplicateOf required for {status}')
    summary = audit.get('summary') or {}
    if isinstance(records, list) and summary.get('rawResults') != len(records):
        errors.append('discovery summary rawResults does not match records')
    return errors


def validate(path, report_path=None):
    errors = []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return [f'invalid JSON: {exc}']
    try:
        date.fromisoformat(payload.get('date', ''))
    except (TypeError, ValueError):
        errors.append('invalid ledger date')
    candidates = payload.get('candidates')
    if not isinstance(candidates, list):
        return errors + ['candidates must be a list']
    if payload.get('discoveryCompleted') is not True:
        errors.append('discoveryCompleted must be true')
    if payload.get('internationalDiscoveryChecked') is not True:
        errors.append('internationalDiscoveryChecked must be true')
    if payload.get('internationalDiscoveryStatus') not in {'checked', 'partial', 'failed'}:
        errors.append('internationalDiscoveryStatus must be checked, partial, or failed')
    errors.extend(validate_discovery_audit(path, payload))
    ids = set()
    for index, candidate in enumerate(candidates, 1):
        label = f'candidate {index}'
        missing = sorted(REQUIRED - set(candidate))
        if missing:
            errors.append(f'{label}: missing fields: {", ".join(missing)}')
        candidate_id = candidate.get('candidateId')
        if candidate_id in ids:
            errors.append(f'{label}: duplicate candidateId {candidate_id}')
        ids.add(candidate_id)
        if candidate.get('decision') not in DECISIONS:
            errors.append(f'{label}: invalid decision')
        if candidate.get('dedupStatus', 'unique_event') not in DUPLICATE_STATUSES:
            errors.append(f'{label}: invalid dedupStatus')
        if candidate.get('dedupStatus') in {'same_day_duplicate', 'historical_duplicate', 'possible_duplicate'} and not candidate.get('duplicateOf'):
            errors.append(f'{label}: duplicateOf required for {candidate.get("dedupStatus")}')
        if not isinstance(candidate.get('selectedForDaily'), bool):
            errors.append(f'{label}: selectedForDaily must be boolean')
        elif candidate['selectedForDaily'] != (candidate.get('decision') == 'selected'):
            errors.append(f'{label}: selectedForDaily disagrees with decision')
        scope = candidate.get('scope')
        if scope not in {'domestic', 'regional', 'international'}:
            errors.append(f'{label}: scope must be domestic, regional, or international')
        else:
            expected_domestic = scope == 'domestic'
            expected_international = scope == 'international'
            if candidate.get('domestic') is not expected_domestic:
                errors.append(f'{label}: domestic flag disagrees with scope')
            if candidate.get('international') is not expected_international:
                errors.append(f'{label}: international flag disagrees with scope')
        if not valid_url(candidate.get('discoveryUrl')):
            errors.append(f'{label}: invalid discoveryUrl')
        evidence = candidate.get('evidenceSources')
        if not isinstance(evidence, list):
            errors.append(f'{label}: evidenceSources must be a list')
            evidence = []
        if candidate.get('decision') == 'selected':
            if not evidence:
                errors.append(f'{label}: selected candidate needs evidence source')
            if not isinstance(candidate.get('dailyItemNumber'), int) or candidate['dailyItemNumber'] < 1:
                errors.append(f'{label}: selected candidate needs dailyItemNumber')
            if not isinstance(candidate.get('dailyItemTitle'), str) or not candidate['dailyItemTitle'].strip():
                errors.append(f'{label}: selected candidate needs dailyItemTitle')
        for source in evidence:
            if not isinstance(source, dict) or not valid_url(source.get('url')):
                errors.append(f'{label}: invalid evidence source URL')
                continue
            actual = source_info(source['url'])
            if actual['blocked'] or actual['tier'] not in {'A', 'B'}:
                errors.append(f'{label}: evidence source is not currently publishable: {source["url"]}')
            elif source.get('tier') != actual['tier']:
                errors.append(
                    f'{label}: evidence tier mismatch for {source["url"]}: '
                    f'ledger={source.get("tier")!r}, governance={actual["tier"]!r}'
                )
    summary = payload.get('summary') or {}
    expected = {
        'discovered': len(candidates),
        'selected': sum(c.get('decision') == 'selected' for c in candidates),
        'rejected': sum(c.get('decision') == 'rejected' for c in candidates),
        'deferred': sum(c.get('decision') == 'deferred' for c in candidates),
        'needsVerification': sum(c.get('decision') == 'needs_verification' for c in candidates),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f'summary {key}={summary.get(key)!r} != {value}')
    if report_path and not errors:
        from build import parse_md
        report = parse_md(report_path)
        report_items = {item['number']: item for item in report['domestic'] + report['international']}
        selected = [c for c in candidates if c.get('decision') == 'selected']
        numbers = [c.get('dailyItemNumber') for c in selected]
        if len(numbers) != len(set(numbers)):
            errors.append('selected dailyItemNumber values must be unique')
        if len(selected) != len(report_items):
            errors.append(f'selected candidates {len(selected)} != daily report items {len(report_items)}')
        for candidate in selected:
            number = candidate.get('dailyItemNumber')
            item = report_items.get(number)
            if not item:
                errors.append(f'{candidate["candidateId"]}: daily item {number} is missing')
                continue
            if item.get('title') != candidate.get('dailyItemTitle'):
                errors.append(
                    f'{candidate["candidateId"]}: daily title does not match item {number}'
                )
            report_urls = {canonical_url(s.get('url', '')) for s in item.get('sources') or []}
            evidence_urls = {canonical_url(s.get('url', '')) for s in candidate.get('evidenceSources') or []}
            if report_urls != evidence_urls:
                errors.append(
                    f'{candidate["candidateId"]}: daily sources do not match evidence sources'
                )
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    args = parser.parse_args()
    path = LEDGER_DIR / f'{args.date}.json'
    errors = validate(path) if path.exists() else [f'missing ledger: {path.relative_to(ROOT)}']
    if errors:
        print('CANDIDATE LEDGER FAILED')
        print('\n'.join(errors))
        return 1
    print(f'CANDIDATE LEDGER OK: {path.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

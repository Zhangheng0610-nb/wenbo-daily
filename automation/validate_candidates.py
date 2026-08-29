"""Validate the auditable daily editorial candidate ledger."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = ROOT / 'content' / '候选'
REQUIRED = {
    'candidateId', 'title', 'publishedDate', 'discoveredAt',
    'discoverySource', 'discoverySourceType', 'discoveryUrl',
    'publisher', 'evidenceSources', 'evidenceTier', 'topic',
    'domestic', 'international', 'decision', 'decisionReason',
    'selectedForDaily', 'dedupStatus', 'notes',
}
DECISIONS = {'selected', 'rejected', 'deferred', 'needs_verification'}


def valid_url(value):
    parsed = urlparse(value or '')
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def validate(path):
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
        if not isinstance(candidate.get('selectedForDaily'), bool):
            errors.append(f'{label}: selectedForDaily must be boolean')
        elif candidate['selectedForDaily'] != (candidate.get('decision') == 'selected'):
            errors.append(f'{label}: selectedForDaily disagrees with decision')
        if not valid_url(candidate.get('discoveryUrl')):
            errors.append(f'{label}: invalid discoveryUrl')
        evidence = candidate.get('evidenceSources')
        if not isinstance(evidence, list):
            errors.append(f'{label}: evidenceSources must be a list')
            evidence = []
        if candidate.get('decision') == 'selected' and not evidence:
            errors.append(f'{label}: selected candidate needs evidence source')
        for source in evidence:
            if not isinstance(source, dict) or not valid_url(source.get('url')):
                errors.append(f'{label}: invalid evidence source URL')
            if source.get('tier') not in {'A', 'B'}:
                errors.append(f'{label}: evidence source must be A or B')
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

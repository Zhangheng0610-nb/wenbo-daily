"""One bounded supplementary discovery pass when the editorial supply is thin."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

TARGET_CANDIDATES = 5
QUERIES = {
    'domestic': ('site:gov.cn 文物 保护', 'site:chinanews.com.cn 考古 发现',
                 'site:news.cn 博物馆 开馆', 'site:gov.cn 文物 数字化'),
    'international': ('"heritage emergency"', '"documentary heritage"',
                      'archaeological discovery', 'museum repatriation'),
}


def recovery_plan(preview):
    events = preview.get('candidateEvaluation', {}).get('finalEditorialPool', {}).get('events', [])
    counts = {scope: sum(e.get('scope', 'domestic') == scope for e in events)
              for scope in QUERIES}
    reasons = []
    if len(events) < TARGET_CANDIDATES:
        reasons.append('fewer_than_five_qualified_candidates')
    missing = [scope for scope, count in counts.items() if not count]
    if missing:
        reasons.append('scope_has_no_qualified_candidate')
    scopes = list(QUERIES) if len(events) < TARGET_CANDIDATES else missing
    return {'required': bool(reasons), 'reasons': reasons, 'qualifiedBefore': len(events),
            'scopeCountsBefore': counts, 'scopes': scopes, 'maxPasses': 1,
            'targetCandidates': TARGET_CANDIDATES, 'publicationQuota': False}


def execute_recovery(required_date, plan, backends, execute_one):
    jobs = [( {'id': 'supply-recovery-' + scope, 'scope': scope}, backend, query)
            for scope in plan['scopes'] for query in QUERIES[scope] for backend in backends]
    def search(job):
        family, backend, query = job
        try:
            return execute_one(family, backend, query, required_date - timedelta(days=6), required_date)
        except Exception as exc:
            return [], {'queryFamily': family['id'], 'scope': family['scope'],
                        'backend': backend.get('id'), 'actualQuery': query,
                        'executedAt': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                        'success': False, 'failure': f'{type(exc).__name__}: {exc}',
                        'returnedResultCount': 0, 'acceptedRawCount': 0}
    records, audits = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for found, audit in pool.map(search, jobs):
            records.extend(found)
            audits.append(audit)
    return records, audits

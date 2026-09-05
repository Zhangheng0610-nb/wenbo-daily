"""Validate the auditable daily editorial candidate ledger."""
import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = ROOT / 'content' / '候选'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from automation.governance import (
    canonical_url,
    source_info,
    validate_official_wechat_registry,
    wechat_evidence_issues,
)
from automation.daily_discovery import (
    evidence_claim_risk,
    historical_published_event_relation,
    load_history,
)
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
DUPLICATE_STATUSES = {'unique_event', 'same_day_duplicate', 'historical_duplicate', 'derivative_commentary', 'new_development', 'possible_duplicate', 'unique_opportunity', 'unresolved', 'not_selected'}
DISCOVERY_AUDIT_REQUIRED_FROM = date(2026, 8, 31)
FINAL_EDITORIAL_POOL_REQUIRED_FROM = date(2026, 9, 2)


def _resolved_path(root, reference):
    if not isinstance(reference, str) or not reference:
        return None
    path = (root / reference).resolve()
    if root not in path.parents or not path.exists():
        return None
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _final_pool_ids(replay):
    pool = replay.get('finalEditorialPool') if isinstance(replay, dict) else None
    rows = pool.get('events') if isinstance(pool, dict) else None
    if not isinstance(rows, list):
        return None
    return {row.get('eventId') for row in rows if isinstance(row, dict) and row.get('eventId')}


def _previous_rejection_exclusion_allowed(candidate):
    """Allow only an explicit rejected-event guard row outside the editorial pool."""
    return (
        isinstance(candidate, dict)
        and candidate.get('decision') == 'rejected'
        and candidate.get('decisionReason') == 'previous_editorial_rejection'
        and candidate.get('previousEditorialRejection') is True
        and bool(candidate.get('previousEditorialRejectionOf'))
        and bool(candidate.get('previousEditorialRejectionDate'))
        and bool(candidate.get('previousEditorialRejectionReason'))
    )


EDITORIAL_REPLAY_REVISION_TYPES = {
    'same_day_editorial_revision',
    'historical_editorial_correction',
}


def validate_editorial_input(ledger_path, payload, root=None):
    """Validate the single editorial input selected for this ledger.

    The immutable morning discovery audit remains independently validated by
    ``validate_discovery_audit``.  A same-day revision or historical editorial
    correction may point the editor at one explicit replay artifact, but it
    may not silently merge two pools.
    """
    root = root or ROOT
    errors = []
    discovery_ref = payload.get('discoveryAuditPath')
    editorial_ref = payload.get('editorialInputPath') or discovery_ref
    if not editorial_ref:
        return errors, None
    revision = payload.get('revision') or {}
    revision_type = revision.get('revisionType')
    if revision_type in EDITORIAL_REPLAY_REVISION_TYPES and not payload.get('editorialInputPath'):
        errors.append(f'{revision_type} needs an explicit editorialInputPath')
    if editorial_ref == discovery_ref:
        return errors, None
    if revision_type not in EDITORIAL_REPLAY_REVISION_TYPES:
        errors.append(
            'editorialInputPath may differ from discoveryAuditPath only for '
            'same_day_editorial_revision or historical_editorial_correction'
        )
        return errors, None
    if revision.get('discoveryAuditUnchanged') is not True:
        errors.append(f'{revision_type} must declare discoveryAuditUnchanged=true')
    if revision.get('editorialInputPath') not in (None, editorial_ref):
        errors.append('revision editorialInputPath disagrees with ledger')
    replay_path = _resolved_path(root, editorial_ref)
    if replay_path is None:
        errors.append(f'editorial input missing: {editorial_ref}')
        return errors, None
    try:
        replay = json.loads(replay_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f'invalid editorial replay: {exc}')
        return errors, None
    if replay.get('schema') != 'daily-editorial-replay-v1':
        errors.append('editorial replay schema must be daily-editorial-replay-v1')
    if replay.get('date') != payload.get('date'):
        errors.append('editorial replay date does not match ledger')
    if replay.get('baseDiscoveryAuditPath') != discovery_ref:
        errors.append('editorial replay baseDiscoveryAuditPath does not match ledger discoveryAuditPath')
    if replay.get('discoveryAuditUnchanged') is not True:
        errors.append('editorial replay must declare discoveryAuditUnchanged=true')
    base_path = _resolved_path(root, discovery_ref)
    if base_path is None:
        errors.append(f'editorial replay base discovery audit missing: {discovery_ref}')
    else:
        expected_hash = replay.get('baseDiscoveryAuditSha256')
        if not isinstance(expected_hash, str) or expected_hash.lower() != _sha256(base_path):
            errors.append('editorial replay baseDiscoveryAuditSha256 does not match immutable discovery audit')
    query_audits = replay.get('queryAudits')
    if not isinstance(query_audits, list) or not query_audits:
        errors.append('editorial replay needs auditable queryAudits')
    else:
        for index, query in enumerate(query_audits, 1):
            required = {'queryFamily', 'actualQuery', 'executedAt', 'success', 'returnedResultCount', 'acceptedRawCount'}
            missing = sorted(required - set(query)) if isinstance(query, dict) else sorted(required)
            if missing:
                errors.append(f'editorial replay query audit {index}: missing fields: {", ".join(missing)}')
    evidence = replay.get('evidenceQualification')
    if not isinstance(evidence, dict) or evidence.get('status') != 'completed':
        errors.append('editorial replay needs completed evidenceQualification provenance')
    pool = replay.get('finalEditorialPool')
    pool_ids = _final_pool_ids(replay)
    if not isinstance(pool, dict) or pool_ids is None:
        errors.append('editorial replay needs finalEditorialPool.events')
    else:
        events = pool.get('events')
        if len(pool_ids) != len(events):
            errors.append('editorial replay finalEditorialPool eventIds must be unique and non-empty')
        if pool.get('canonicalUniqueEvents') != len(events):
            errors.append('editorial replay canonicalUniqueEvents does not match events')
        if pool.get('editoriallyReviewed') != len(events):
            errors.append('editorial replay finalEditorialPool must record every reviewed event')
        for index, event in enumerate(events, 1):
            if not isinstance(event, dict) or not event.get('eventId'):
                errors.append(f'editorial replay event {index}: eventId required')
                continue
            if event.get('evidenceTierAfterUpgrade') not in {'A', 'B', 'provisional_B'}:
                errors.append(f'editorial replay event {index}: publishable evidence required')
            if not isinstance(event.get('evidenceSources'), list) or not event.get('evidenceSources'):
                errors.append(f'editorial replay event {index}: evidenceSources required')
    return errors, pool_ids


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
    if audit.get('queryAuditStatus') in {'checked', 'partial', 'failed'}:
        if not isinstance(query_audits, list) or not query_audits:
            errors.append('executed discovery audit needs queryAudits')
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
            if status in {'same_day_duplicate', 'historical_duplicate', 'derivative_commentary', 'possible_duplicate'} and not record.get('duplicateOf'):
                errors.append(f'discovery record {index}: duplicateOf required for {status}')
    summary = audit.get('summary') or {}
    if isinstance(records, list) and summary.get('rawResults') != len(records):
        errors.append('discovery summary rawResults does not match records')
    evaluation = audit.get('candidateEvaluation') or {}
    if evaluation:
        # The finalEditorialPool migration starts on 2026-09-02.  Earlier
        # production audits may contain the older, report-level
        # candidateEvaluation shape; validate their discovery coverage above,
        # but do not reinterpret that historical snapshot with the new
        # event-level counters and queue schema.
        if ledger_date < FINAL_EDITORIAL_POOL_REQUIRED_FROM:
            return errors
        evaluation_summary = evaluation.get('summary') or {}
        final_pool = evaluation.get('finalEditorialPool')
        if ledger_date >= FINAL_EDITORIAL_POOL_REQUIRED_FROM:
            if not isinstance(final_pool, dict):
                errors.append('discovery audit needs finalEditorialPool from 2026-09-02 onward')
            else:
                final_events = final_pool.get('events')
                final_ids = [row.get('eventId') for row in final_events or [] if isinstance(row, dict)]
                if not isinstance(final_events, list):
                    errors.append('finalEditorialPool.events must be a list')
                if len(final_ids) != len(set(final_ids)):
                    errors.append('finalEditorialPool eventIds must be unique')
                if final_pool.get('canonicalUniqueEvents') != len(set(final_ids)):
                    errors.append('finalEditorialPool canonicalUniqueEvents does not match events')
                if not isinstance(final_pool.get('rawQualifiedEvents'), int) or final_pool.get('rawQualifiedEvents', 0) < len(final_events or []):
                    errors.append('finalEditorialPool rawQualifiedEvents must cover canonical events')
                if final_pool.get('editoriallyReviewed') != 0:
                    errors.append('new discovery audit finalEditorialPool must start pending with editoriallyReviewed=0')
                for index, row in enumerate(final_events or [], 1):
                    if not row.get('eventId'):
                        errors.append(f'finalEditorialPool event {index}: eventId required')
                    if row.get('candidateDisposition') != 'evidence_qualified':
                        errors.append(f'finalEditorialPool event {index}: event must be evidence_qualified')
        elif final_pool is not None and not isinstance(final_pool, dict):
            errors.append('finalEditorialPool must be an object when present')
        for field in ('candidateEvaluationPool', 'evidenceQualified', 'needsVerification',
                      'highPriorityCandidates', 'highPriorityEvidenceQueue',
                      'highPriorityNeedsVerification', 'evidenceUpgradeAttempted',
                      'rejected', 'deferred'):
            value = evaluation_summary.get(field)
            if not isinstance(value, int) or value < 0:
                errors.append(f'candidate evaluation summary {field} must be a non-negative integer')
        queue_count = len(evaluation.get('highPriorityEvidenceQueue') or [])
        if evaluation_summary.get('highPriorityEvidenceQueue') != queue_count:
            errors.append('candidate evaluation highPriorityEvidenceQueue count does not match queue')
        if evaluation_summary.get('highPriorityNeedsVerification') != queue_count:
            errors.append('candidate evaluation highPriorityNeedsVerification count does not match queue')
        event_candidates = evaluation.get('eventCandidates') or []
        event_ids = [row.get('eventId') for row in event_candidates]
        if isinstance(records, list) and evaluation_summary.get('rawRecords') != len(records):
            errors.append('candidate evaluation rawRecords does not match discovery records')
        if evaluation_summary.get('eventCandidateCount') != len(event_candidates):
            errors.append('candidate evaluation eventCandidateCount does not match eventCandidates')
        event_report_count = sum(row.get('reportCount', 0) for row in event_candidates)
        if evaluation_summary.get('deduplicatedReports') != event_report_count:
            errors.append('candidate evaluation deduplicatedReports does not match event reports')
        if len(event_ids) != len(set(event_ids)):
            errors.append('candidate evaluation eventIds must be unique')
        known_event_ids = set(event_ids)
        for index, row in enumerate(event_candidates, 1):
            if not row.get('eventId'):
                errors.append(f'event candidate {index}: eventId required')
            if not isinstance(row.get('reportCount'), int) or row['reportCount'] < 1:
                errors.append(f'event candidate {index}: reportCount must be positive')
            reports = row.get('discoveryReports')
            if not isinstance(reports, list) or len(reports) != row.get('reportCount'):
                errors.append(f'event candidate {index}: discoveryReports/reportCount mismatch')
        for index, row in enumerate(evaluation.get('pool') or [], 1):
            if row.get('eventId') not in known_event_ids:
                errors.append(f'candidate evaluation pool {index}: unknown eventId')
            score = row.get('editorialPriorityScore')
            label = row.get('editorialPriorityLabel')
            reasons = row.get('editorialReasons')
            if not isinstance(score, (int, float)) or not 0 <= score <= 100:
                errors.append(f'candidate evaluation pool {index}: invalid editorialPriorityScore')
            if label not in {'high', 'medium', 'low'}:
                errors.append(f'candidate evaluation pool {index}: invalid editorialPriorityLabel')
            if not isinstance(reasons, list) or not reasons:
                errors.append(f'candidate evaluation pool {index}: editorialReasons required')
            if row.get('evidenceUpgradeAttempted') is True:
                attempts = row.get('evidenceResolutionAttempts')
                if not isinstance(attempts, list) or not attempts:
                    errors.append(f'candidate evaluation pool {index}: evidenceResolutionAttempts required after upgrade')
                else:
                    required_attempt_fields = {'method', 'inputUrl', 'resolvedUrl', 'domain', 'fetchStatus', 'articleMatched', 'evidenceTier'}
                    for attempt_index, attempt in enumerate(attempts, 1):
                        if not isinstance(attempt, dict):
                            errors.append(f'candidate evaluation pool {index} evidence attempt {attempt_index}: object required')
                            continue
                        missing_attempt_fields = sorted(required_attempt_fields - set(attempt))
                        if missing_attempt_fields:
                            errors.append(
                                f'candidate evaluation pool {index} evidence attempt {attempt_index}: '
                                f'missing fields: {", ".join(missing_attempt_fields)}'
                            )
                        if attempt.get('method') not in {
                            'existing_report', 'redirect_unwrap', 'native_index',
                            'domain_search', 'official_search', 'broad_search',
                            'alternate_source',
                        }:
                            errors.append(f'candidate evaluation pool {index} evidence attempt {attempt_index}: invalid method')
                        if not isinstance(attempt.get('articleMatched'), bool):
                            errors.append(f'candidate evaluation pool {index} evidence attempt {attempt_index}: articleMatched must be boolean')
        for queue_name in ('highPriorityEvidenceQueue', 'mediumPriorityEvidenceQueue'):
            queue_ids = [row.get('eventId') for row in (evaluation.get(queue_name) or [])]
            if len(queue_ids) != len(set(queue_ids)):
                errors.append(f'{queue_name} must contain unique eventIds')
            if not set(queue_ids).issubset(known_event_ids):
                errors.append(f'{queue_name} contains unknown eventId')
        if evaluation_summary.get('mediumPriorityEvidenceQueueEvents') != len(evaluation.get('mediumPriorityEvidenceQueue') or []):
            errors.append('candidate evaluation medium queue count does not match queue')
        pool_rows = evaluation.get('pool') or []
        if evaluation_summary.get('evidenceQualified') != sum(row.get('candidateDisposition') == 'evidence_qualified' for row in pool_rows):
            errors.append('candidate evaluation evidenceQualified does not match pool')
        if evaluation_summary.get('needsVerification') != sum(row.get('candidateDisposition') == 'needs_verification' for row in pool_rows):
            errors.append('candidate evaluation needsVerification does not match pool')
    return errors


def validate(path, report_path=None):
    errors = []
    errors.extend(f'official WeChat registry: {error}'
                  for error in validate_official_wechat_registry())
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
    editorial_input_errors, editorial_pool_ids = validate_editorial_input(path, payload)
    errors.extend(editorial_input_errors)
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
        if candidate.get('dedupStatus') in {'same_day_duplicate', 'historical_duplicate', 'derivative_commentary', 'possible_duplicate'} and not candidate.get('duplicateOf'):
            errors.append(f'{label}: duplicateOf required for {candidate.get("dedupStatus")}')
        if not isinstance(candidate.get('selectedForDaily'), bool):
            errors.append(f'{label}: selectedForDaily must be boolean')
        elif candidate['selectedForDaily'] != (candidate.get('decision') == 'selected'):
            errors.append(f'{label}: selectedForDaily disagrees with decision')
        if candidate.get('decision') == 'selected' and candidate.get('dedupStatus') in {
            'same_day_duplicate', 'historical_duplicate', 'derivative_commentary'
        }:
            errors.append(f'{label}: selected candidate cannot have {candidate.get("dedupStatus")}')
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
        try:
            ledger_date = date.fromisoformat(payload.get('date', ''))
        except (TypeError, ValueError):
            ledger_date = None
        if ledger_date and ledger_date >= FINAL_EDITORIAL_POOL_REQUIRED_FROM:
            if not candidate.get('eventId'):
                errors.append(f'{label}: eventId required from 2026-09-02 onward')
            if not candidate.get('finalEditorialDecision'):
                errors.append(f'{label}: finalEditorialDecision required from 2026-09-02 onward')
            if not candidate.get('finalEditorialReason'):
                errors.append(f'{label}: finalEditorialReason required from 2026-09-02 onward')
        evidence_a = False
        evidence_b_hosts = set()
        for source in evidence:
            if not isinstance(source, dict) or not valid_url(source.get('url')):
                errors.append(f'{label}: invalid evidence source URL')
                continue
            actual = source_info(source['url'])
            for issue in wechat_evidence_issues(
                    source, selected=candidate.get('decision') == 'selected'):
                errors.append(f'{label}: {issue}: {source["url"]}')
            if actual['blocked']:
                errors.append(f'{label}: evidence source is not currently publishable: {source["url"]}')
            elif source.get('tier') in {'A', 'B'} and source.get('tier') != actual['tier']:
                errors.append(
                    f'{label}: evidence tier mismatch for {source["url"]}: '
                    f'ledger={source.get("tier")!r}, governance={actual["tier"]!r}'
                )
            elif source.get('tier') == 'provisional_B':
                if actual['tier'] != 'C' or not source.get('articleVerified'):
                    errors.append(f'{label}: provisional_B evidence must retain article-level verification: {source["url"]}')
                if evidence_claim_risk(candidate) == 'high':
                    errors.append(f'{label}: high-risk claim cannot rely on a single provisional_B source: {source["url"]}')
            elif source.get('tier') not in {'A', 'B'}:
                errors.append(f'{label}: evidence source has invalid publishable tier: {source["url"]}')
            if actual['tier'] == 'A' and not actual['blocked']:
                evidence_a = True
            elif source.get('tier') == 'B' and actual['tier'] == 'B' and not actual['blocked']:
                evidence_b_hosts.add(actual.get('host', ''))
        if candidate.get('decision') == 'selected' and evidence_claim_risk(candidate) == 'high':
            if not evidence_a and len({host for host in evidence_b_hosts if host}) < 2:
                errors.append(f'{label}: high-risk selected claim needs A evidence or two independent B domains')
        if candidate.get('decision') == 'selected' and ledger_date:
            current = dict(candidate)
            current['title'] = candidate.get('title', '')
            current['url'] = candidate.get('discoveryUrl', '')
            try:
                historical_rows = load_history(ledger_date)
            except Exception:
                historical_rows = []
            for previous in reversed(historical_rows):
                relation = historical_published_event_relation(current, previous)
                if relation and relation[0] in {'historical_duplicate', 'derivative_commentary'}:
                    errors.append(
                        f'{label}: selected candidate matches published history '
                        f'{previous.get("historicalItemId") or previous.get("title", "")}'
                    )
                    break
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
    if ledger_date and ledger_date >= FINAL_EDITORIAL_POOL_REQUIRED_FROM and not errors:
        pool_ids = editorial_pool_ids
        if pool_ids is None:
            ref = payload.get('discoveryAuditPath')
            audit_path = _resolved_path(ROOT, ref)
            try:
                audit_payload = json.loads(audit_path.read_text(encoding='utf-8'))
                pool_events = ((audit_payload.get('candidateEvaluation') or {}).get('finalEditorialPool') or {}).get('events') or []
                pool_ids = {row.get('eventId') for row in pool_events if isinstance(row, dict)}
            except (AttributeError, OSError, json.JSONDecodeError):
                # The detailed missing/invalid-audit error is emitted by
                # validate_discovery_audit; avoid masking it with a second error.
                pool_ids = set()
        for candidate in candidates:
            # A historical duplicate is intentionally excluded from the
            # publishable editorial pool, but remains auditable in the daily
            # ledger so the correction/rejection is explicit.  This is not a
            # bypass for selected or otherwise unresolved candidates.
            historical_exclusion = (
                candidate.get('decision') == 'rejected'
                and candidate.get('dedupStatus') in {'historical_duplicate', 'derivative_commentary'}
                and bool(candidate.get('duplicateOf'))
            )
            previous_rejection_exclusion = _previous_rejection_exclusion_allowed(candidate)
            if candidate.get('eventId') not in pool_ids and not historical_exclusion and not previous_rejection_exclusion:
                errors.append(f'{candidate.get("candidateId", "candidate")}: eventId is not in editorialInput finalEditorialPool')
    if report_path and not errors:
        from build import parse_md
        report = parse_md(report_path)
        report_items = {
            item['number']: item
            for item in (report.get('ordered_items') or report['domestic'] + report['international'])
        }
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

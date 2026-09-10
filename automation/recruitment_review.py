"""Durable, evidence-bound editorial decisions for recruitment discovery."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

# Exclude observation timestamps; include facts that can change eligibility.
SNAPSHOT_FIELDS = (
    'institution', 'position', 'positionCode', 'recruitmentBatch',
    'announcementTitle', 'discoveryUrl', 'sourceSectionKey', 'publishedDate',
    'deadline', 'deadlineHints', 'applicationHints', 'targetPage',
)


def review_signature(candidate: dict) -> str:
    facts = {key: candidate.get(key) or '' for key in SNAPSHOT_FIELDS}
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def apply_review_decisions(root: Path, candidates: list[dict], as_of: str) -> tuple[list[dict], list[dict]]:
    path = Path(root) / 'content/招聘/review-decisions.json'
    decisions = json.loads(path.read_text(encoding='utf-8')).get('decisions', []) if path.exists() else []
    by_signature = {}
    for decision in decisions:
        if decision.get('decision') not in ('rejected', 'duplicate'):
            raise ValueError('Queue review supports rejected/duplicate only; publication uses the evidence workflow')
        if not all(decision.get(k) for k in ('signature', 'reason', 'evidence', 'reviewedAt')):
            raise ValueError('Review decision requires signature, reason, evidence and reviewedAt')
        if decision['reviewedAt'][:10] <= as_of:
            by_signature[decision['signature']] = decision
    result, applied = [], []
    for candidate in candidates:
        decision = by_signature.get(review_signature(candidate))
        if decision and candidate.get('decision') == 'pending':
            candidate = {**candidate, 'decision': decision['decision'], 'decisionReason': decision['reason']}
            applied.append({'candidateId': candidate.get('candidateId'), 'decision': decision['decision'],
                            'reason': decision['reason'], 'reviewedAt': decision['reviewedAt'],
                            'signature': decision['signature']})
        result.append(candidate)
    return result, applied

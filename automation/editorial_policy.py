"""Reject explicit technical quotas masquerading as news-value decisions.

This is a narrow publishing guard, not automatic editorial ranking. It does
not force publication, suppress real duplicate checks, or judge vague prose.
"""
import re

RULES = (
    ('shared_document_quota', r'同一来源\s*URL\s*不重复|为避免重复来源\s*URL|来源\s*URL\s*复用|不在日报重复使用该页'),
    ('publisher_quota', r'同源国际条目过密|为避免同源[^。；]{0,12}(?:过密|重复)|国际版面已选入|同源竞争|同一专业来源的有界覆盖|同一专业来源已有[^。；]{0,35}入选'),
    ('fixed_story_quota', r'五条日报|已选够(?:若干|\d+|[一二三四五六七八九十]+)条|达到(?:\d+|[一二三四五六七八九十]+)条上限'),
)


def rejection_policy_issues(candidate):
    if candidate.get('decision') != 'rejected':
        return []
    if candidate.get('dedupStatus') in {'historical_duplicate', 'same_day_duplicate', 'derivative_commentary'}:
        return []
    # Do not confuse an evidence-quality rejection with a qualified event
    # excluded by a technical quota. Existing validators handle bad evidence.
    if candidate.get('evidenceTier') not in {'A', 'B', 'provisional_B'}:
        return []
    reason = ' '.join(str(candidate.get(k) or '') for k in ('decisionReason','finalEditorialReason'))
    return [code for code, pattern in RULES if re.search(pattern, reason, re.I)]


def review_policy_audit(ledger):
    flagged = []
    for candidate in ledger.get('candidates', []):
        issues = rejection_policy_issues(candidate)
        if issues:
            flagged.append({'eventId':candidate.get('eventId'),'title':candidate.get('title'),
                            'issues':issues,'reason':candidate.get('finalEditorialReason') or candidate.get('decisionReason')})
    return {'date':ledger.get('date'), 'flaggedCount':len(flagged), 'events':flagged,
            'definition':'Explicit disallowed quota reasons; review the decision, never auto-select the story.'}

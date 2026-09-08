"""Approve shared article URLs only for independently verified document items."""
from collections import defaultdict
from automation.governance import canonical_url


def approved_shared_urls(items, candidates, authoritative_events):
    by_url = defaultdict(list)
    for item in items:
        for source in item.get('sources') or []:
            url = canonical_url(source.get('url', ''))
            if url:
                by_url[url].append(item)
    events = {e.get('eventId'): e for e in authoritative_events if e.get('eventId')}
    approved = set()
    for url, uses in by_url.items():
        if len(uses) < 2:
            continue
        segment_ids, event_ids = set(), set()
        for item in uses:
            selected = [c for c in candidates if c.get('decision') == 'selected'
                        and c.get('selectedForDaily') is True
                        and c.get('dailyItemNumber') == item.get('number')
                        and c.get('dailyItemTitle') == item.get('title')]
            if len(selected) != 1:
                break
            candidate = selected[0]
            event_id = candidate.get('eventId')
            evidence = [s for s in candidate.get('evidenceSources', [])
                        if canonical_url(s.get('url', '')) == url]
            if len(evidence) != 1 or event_id not in events or event_id in event_ids:
                break
            source = evidence[0]
            segment = source.get('contentItemId')
            if not isinstance(segment, str) or not segment.startswith('digest-') or segment in segment_ids:
                break
            if source.get('articleVerified') is not True or source.get('tier') not in {'A', 'B', 'provisional_B'}:
                break
            if source.get('publicationDateBasis') != 'digest_publication':
                break
            proven = any(canonical_url(s.get('url', '')) == url
                         and s.get('contentItemId') == segment
                         and s.get('articleVerified') is True
                         and s.get('publicationDateBasis') == 'digest_publication'
                         for s in events[event_id].get('evidenceSources', []))
            if not proven:
                break
            segment_ids.add(segment)
            event_ids.add(event_id)
        else:
            approved.add(url)
    return approved

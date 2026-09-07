"""Trace editor-labelled reference events through a saved discovery audit.

Labels and aliases are independent of production event matching. This measures
only the supplied reference set, never claims comprehensive news recall.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def normalize(text):
    return re.sub(r'\W+', '', str(text).lower())


def url_key(url):
    p = urlsplit(url or '')
    return urlunsplit(('', p.netloc.lower().removeprefix('www.'), p.path.rstrip('/'), '', ''))


def matches(reference, row):
    title = normalize(row.get('representativeTitle') or row.get('title', ''))
    aliases = reference.get('titleAliases', [])
    title_match = any(normalize(alias) in title for alias in aliases if normalize(alias))
    # A shared digest URL alone does not identify a news item.
    url_match = not reference.get('sharedDocument') and any(
        url_key(url) == url_key(row.get('url', '')) for url in reference.get('urls', []) if url
    )
    return bool(title_match or url_match)


def evaluate(references, audit):
    evaluation = audit.get('candidateEvaluation', {})
    rows = []
    for ref in references['events']:
        discovered = [r for r in audit.get('records', []) if matches(ref, r)]
        events = [e for e in evaluation.get('eventCandidates', []) if matches(ref, e) or
                  any(matches(ref, r) for r in e.get('discoveryReports', []))]
        ids = {e.get('eventId') for e in events if e.get('eventId')}
        pool = [e for e in evaluation.get('pool', []) if matches(ref, e) or e.get('eventId') in ids]
        final = [e for e in evaluation.get('finalEditorialPool', {}).get('events', [])
                 if matches(ref, e) or e.get('eventId') in ids]
        suppressed = bool(discovered) and all(r.get('duplicateStatus') == 'historical_duplicate' for r in discovered)
        if not discovered and not events:
            stage = 'not_discovered'
        elif suppressed:
            stage = 'historical_suppression'
        elif final:
            stage = 'final_pool'
        elif pool:
            stage = 'candidate_pool'
        else:
            stage = 'before_candidate_pool'
        expected = ref['expected']
        targets = {normalize(r.get('duplicateOfTitle', '')) for r in discovered if r.get('duplicateOfTitle')}
        expected_targets = {normalize(t) for t in ref.get('expectedHistoricalTitles', [])}
        passed = ((stage == 'historical_suppression' and bool(targets) and targets <= expected_targets)
                  if expected == 'suppress_repeat' else stage == 'final_pool')
        if expected == 'suppress_repeat' and stage == 'not_discovered':
            passed = None  # An absent repeat cannot test duplicate classification.
        rows.append({'id':ref['id'], 'title':ref['title'], 'scope':ref['scope'], 'expected':expected,
                     'stage':stage,'expectationMet':passed,'discoveredReports':len(discovered),
                     'eventIds':sorted(ids), 'duplicateTargets':sorted({r.get('duplicateOfTitle','') for r in discovered if r.get('duplicateOfTitle')}),
                     'candidateDecisions':[{k:e.get(k) for k in ('candidateDisposition','filterReasons','evidenceUpgradeResult','evidenceFailureReason')} for e in pool]})
    return {'targetDate':audit.get('date'), 'referenceSet':references['name'],
            'limitation':'Small curated diagnostic set, not overall recall; final pool is not publication.',
            'referenceCount':len(rows),'expectationsMet':sum(r['expectationMet'] is True for r in rows),
            'assessedCount':sum(r['expectationMet'] is not None for r in rows),
            'events':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', required=True)
    parser.add_argument('--audit', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(Path(args.references).read_text(encoding='utf-8')),
                      json.loads(Path(args.audit).read_text(encoding='utf-8')))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for row in result['events']:
        print(row['stage'], row['title'])


if __name__ == '__main__':
    main()

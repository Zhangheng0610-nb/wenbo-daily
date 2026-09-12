"""Product scope gate: industry developments, not a bibliography feed.

Use the news headline, not source reputation, publication date or an editor's
impact commentary. This conservative lexical guard complements editorial review.
"""
import re

ACADEMIC_PATTERNS = (
    r'名称.{0,8}功用', r'探析|考释|辨析|刍议|试论|浅谈|学术探讨',
    r'发掘(?:简报|报告)', r'分子考古学.*(?:解码|同行史)',
    r'石质文物保护.*(?:检测|建模|材料试验|一域磨剑|全国攻坚)',
    r'(?:研究|考古学).{0,12}(?:解码|演化史|起源问题)',
    r'(?:保护|修复).{0,16}(?:方法介绍|技术综述|实验研究|材料试验)',
    r'新书|书讯|书评|论文解读|研究综述',
    r'\b(?:excavation report|book review|literature review|methodological review)\b',
)
# A concrete action must be in the headline itself. Generic "发布/研究/发现"
# cannot rescue a routine paper/report; a source name or notes cannot rescue it.
ACTION_PATTERNS = (
    r'(?:博物馆|博物院|遗址公园|新馆).{0,18}(?:正式开放|正式开馆|获批建设)',
    r'(?:保护工程|修复工程|考古项目|数字平台|数字化平台).{0,12}(?:启动|获批|验收|上线|启用)',
    r'(?:启动|获批|验收|上线|启用).{0,12}(?:保护工程|修复工程|考古项目|数字平台|数字化平台)',
)


def daily_scope_rejection(record: dict) -> str | None:
    title = str(record.get('representativeTitle') or record.get('title') or '')
    urls = [str(record.get(k) or '') for k in ('url', 'discoveryUrl')]
    urls.extend(str(source.get('url') or '') for source in record.get('evidenceSources', []) if isinstance(source, dict))
    academic_section = any('/kycg/xslw/' in url or '/kycg/jbbg/' in url for url in urls)
    if not academic_section and not any(re.search(pattern, title, re.I) for pattern in ACADEMIC_PATTERNS):
        return None
    if any(re.search(pattern, title, re.I) for pattern in ACTION_PATTERNS):
        return None
    return 'academic_discussion_without_industry_action'


INDUSTRY_ACTION_REQUIRED_FROM = '2026-09-11'
INDUSTRY_ACTION_KINDS = frozenset({
    'policy', 'funding', 'institution_operation', 'project_milestone',
    'exhibition', 'repatriation', 'security_incident', 'archaeological_discovery',
    'heritage_designation', 'international_cooperation',
})


def industry_action_errors(candidate: dict, ledger_date: str, root=None) -> list[str]:
    """Check source-grounded action receipts at publication, not at discovery.

This validates provenance/shape, not truth or semantic entailment. Editors must
read the source; an authenticated source can still report a non-news topic.
"""
    from datetime import date
    from pathlib import Path
    import json
    import hashlib
    from automation.governance import canonical_url
    if candidate.get('decision') != 'selected':
        return []
    proof = candidate.get('industryAction')
    if ledger_date < INDUSTRY_ACTION_REQUIRED_FROM and proof is None:
        return []
    if not isinstance(proof, dict):
        return ['industryAction required: identify the recent action in source text']
    errors = []
    if not isinstance(proof.get('kind'), str) or proof['kind'] not in INDUSTRY_ACTION_KINDS:
        errors.append('industryAction.kind must describe an industry event, not academic publication')
    for field in ('actor', 'action', 'change', 'sourceUrl', 'sourceExcerpt', 'dateExcerpt'):
        if not isinstance(proof.get(field), str) or not proof[field].strip():
            errors.append(f'industryAction.{field} required')
    excerpt = proof.get('sourceExcerpt') if isinstance(proof.get('sourceExcerpt'), str) else ''
    normalized = lambda value: re.sub(r'\s+', ' ', value).strip().casefold()
    for field in ('actor', 'action', 'dateExcerpt'):
        value = proof.get(field)
        if isinstance(value, str) and value.strip() and normalized(value) not in normalized(excerpt):
            errors.append(f'industryAction.{field} must occur in the source excerpt')
    if len(excerpt.strip()) < 20:
        errors.append('industryAction.sourceExcerpt too short to establish an event')
    if proof.get('timeBasis') not in ('event_date', 'announcement_date'):
        errors.append('industryAction.timeBasis must be event_date or announcement_date, not article publication date')
    try:
        event_date = date.fromisoformat(proof.get('eventDate', ''))
        age = (date.fromisoformat(ledger_date) - event_date).days
        if not 0 <= age <= 6:
            errors.append('industryAction.eventDate outside the seven-day event window; identify a recent new development')
    except (TypeError, ValueError):
        errors.append('industryAction.eventDate must be an ISO calendar date')
    url = proof.get('sourceUrl')
    sources = candidate.get('evidenceSources')
    if not isinstance(sources, list):
        sources = []
    verified_urls = {canonical_url(source['url']) for source in sources
                     if isinstance(source, dict) and isinstance(source.get('url'), str)
                     and source.get('articleVerified') is True}
    if not isinstance(url, str) or canonical_url(url) not in verified_urls:
        errors.append('industryAction.sourceUrl must reference article-verified evidence for this candidate')
    # Match the quote against a retained document, not against an editor's
    # newly written summary. Normalize line endings for Chinese Windows.
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    try:
        reference = proof.get('sourceDocumentPath')
        if not isinstance(reference, str) or not reference:
            raise ValueError('sourceDocumentPath required')
        path = (root / reference).resolve()
        if not path.is_relative_to(root.resolve()) or path.suffix != '.json':
            raise ValueError('sourceDocumentPath must be a repository JSON document')
        raw = path.read_text(encoding='utf-8').replace('\r\n', '\n')
        if hashlib.sha256(raw.encode('utf-8')).hexdigest() != proof.get('sourceDocumentSha256'):
            raise ValueError('source document hash mismatch')
        document = json.loads(raw)
        if canonical_url(document.get('url', '')) != canonical_url(url or ''):
            raise ValueError('source document URL does not match sourceUrl')
        text = document.get('text')
        if not isinstance(text, str) or not excerpt.strip() or normalized(excerpt) not in normalized(text):
            raise ValueError('sourceExcerpt must occur in retained source text')
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        errors.append(f'industryAction evidence: {exc}')
    return errors


def save_action_source(root, url: str, text: str, retrieved_at: str) -> dict:
    """Persist already fetched article text; performs no fetch or verification."""
    import hashlib
    import json
    from pathlib import Path
    if not url.startswith(('https://', 'http://')) or not text.strip():
        raise ValueError('HTTP source URL and nonempty article text required')
    raw = json.dumps({'url': url, 'retrievedAt': retrieved_at, 'text': text.replace('\r\n', '\n')},
                     ensure_ascii=False, indent=2) + '\n'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    relative = f'audit/action-sources/{digest}.json'
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the hash independent of the host OS newline convention.  In
    # particular, a Windows text-mode write would turn the LF-normalized
    # payload above into CRLF and make the retained-source receipt fail its
    # own line-ending regression test.
    path.write_bytes(raw.encode('utf-8'))
    return {'sourceDocumentPath': relative, 'sourceDocumentSha256': digest}

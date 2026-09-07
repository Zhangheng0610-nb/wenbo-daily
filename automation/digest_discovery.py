"""Expand a bounded set of official digests into separately traceable leads."""
import hashlib
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from automation.digest_content import digest_blocks


def is_digest_container(record):
    return not record.get('isDigestItem') and bool(re.search(r'一周文物动态摘编|每周文物动态摘编', record.get('title', '')))


def digest_records(parent, page):
    result = []
    for block in digest_blocks(page):
        body = ' '.join(block['body']).strip()
        if not body:
            continue
        identity = '|'.join((parent['url'].rstrip('/'), block['region'], block['title']))
        segment = 'digest-' + hashlib.sha256(identity.encode()).hexdigest()[:20]
        result.append(dict(parent, title=block['title'], summary=body, contentItemId=segment,
                           isDigestItem=True, sourceDocumentTitle=parent['title'],
                           publicationDateBasis='digest_publication', eventDate=None,
                           eventDateStatus='requires_editorial_verification',
                           sourceRegionLabel=block['region']))
    return result


def expand_batches(batches, fetcher, max_documents=3, document_cache=None):
    # A run may discover digests in both initial and supplementary search.
    # Share the same fetch budget/cache across those phases, never across runs.
    documents = document_cache if document_cache is not None else {}
    audits = []
    for batch in batches:
        for record in batch:
            url = record.get('url', '')
            if not is_digest_container(record) or url in documents:
                continue
            parts = urlsplit(url)
            if parts.hostname not in {'www.ncha.gov.cn', 'ncha.gov.cn'} or not parts.path.startswith('/art/'):
                continue
            if len(documents) >= max_documents:
                continue
            audit = {'url':url,'checkedAt':datetime.now(timezone(timedelta(hours=8))).isoformat(),
                     'status':'fetch_failed','items':0}
            try:
                children = digest_records(record, fetcher(url))
                audit.update(status='expanded' if children else 'parse_failed', items=len(children))
            except Exception as exc:
                children = []
                audit['failure'] = f'{type(exc).__name__}: {exc}'
            documents[url] = children
            audits.append(audit)
    expanded = []
    for batch in batches:
        rows = []
        for record in batch:
            children = documents.get(record.get('url')) if is_digest_container(record) else None
            if children:
                fields = ('title', 'summary', 'publishedDate', 'contentItemId', 'isDigestItem',
                          'sourceDocumentTitle', 'publicationDateBasis', 'eventDate', 'eventDateStatus', 'sourceRegionLabel')
                rows.extend(dict(record, **{k: child[k] for k in fields}) for child in children)
            else:
                rows.append(record)
        expanded.append(rows)
    return expanded, audits

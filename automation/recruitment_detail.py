"""Bounded public-page dossiers for the editorial recruitment queue.

Extracts application/attachment evidence without converting a fetched page
into a verified job. Date fragments are evidence, not inferred deadlines.
"""
import re
from html import unescape
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit
from automation.recruitment_sources import DirectoryLinks,navigational_url


def inspect_detail(candidate,fetcher,checked_at):
    url=candidate.get('discoveryUrl','')
    result={'candidateId':candidate.get('candidateId'),'url':url,'checkedAt':checked_at,'status':'failed','verificationStatus':'pending','evidenceScope':'source_document_not_individual_position'}
    if urlsplit(url).scheme not in ('http','https') or navigational_url(url):
        return {**result,'error':'not_a_detail_url'}
    try:
        html=fetcher(url)
        if any(s in html[:15000] for s in ('环境异常','访问验证','验证码','Access Denied')):raise ValueError('access_challenge')
        clean=re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ',html,flags=re.S|re.I)
        text=re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',clean)))
        if len(text)<100:raise ValueError('insufficient_text')
        parser=DirectoryLinks();parser.feed(html)
        attachments=[]
        for href,title in parser.links:
            absolute=urljoin(url,href)
            if urlsplit(absolute).scheme not in ('http','https'):continue
            if re.search(r'\.(?:pdf|xlsx?|docx?|csv)(?:$|[?#])',absolute,re.I) or any(x in title for x in ('岗位表','职位表','报名表','附件')):
                attachments.append({'title':title[:120],'url':absolute})
        result.update(status='readable',applicationEmails=sorted(set(re.findall(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text))),
                      applicationEvidence=re.findall(r'(?:报名(?:截止)?时间|报名方式|应聘方式|投递方式|申请截止)[：:]?[^。]{0,180}',text)[:8],attachments=attachments[:20],
                      requiresAttachmentReview=bool(attachments))
        return result
    except Exception as exc:return {**result,'error':f'{type(exc).__name__}: {str(exc)[:200]}'}


def inspect_candidates(candidates,fetcher,checked_at,limit=12):
    # Cache per source URL: one digest may describe many independent employers.
    unique={}
    for c in candidates:
        url=c.get('discoveryUrl','')
        if url and not navigational_url(url):unique.setdefault(url,c)
        if len(unique)>=limit:break
    if limit<=0:return []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda c:inspect_detail(c,fetcher,checked_at),unique.values()))
    for result in results:
        result['candidateIds']=[c.get('candidateId') for c in candidates if c.get('discoveryUrl')==result['url']]
    return results

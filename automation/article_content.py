"""Keep article prose separate from navigation, ads and related stories."""
import re
from functools import lru_cache
from urllib.parse import urljoin, urlsplit
from automation.news_cards import CardParser

OMIT_TAGS = {'script','style','noscript','svg','nav','footer','aside','form','button','head','template'}
OMIT_CLASS = re.compile(r'^(?:recommended(?:-|$)|related(?:-|$)|more-to-discover$|footer-discover$|header-share$|share-socials$|screen-reader-text$)')


def walk(node):
    stack=[node]
    while stack:
        n=stack.pop()
        if isinstance(n,str):continue
        yield n
        stack.extend(reversed(n['children']))


def ignored(node, allow_form=False):
    attrs=node['attrs']
    return ((node['tag'] in OMIT_TAGS and not (allow_form and node['tag']=='form')) or 'hidden' in attrs or attrs.get('aria-hidden')=='true'
            or any(OMIT_CLASS.search(c) for c in (attrs.get('class') or '').split()))


def prose(node):
    parts=[];stack=[node]
    while stack:
        n=stack.pop()
        if isinstance(n,str):parts.append(n)
        elif not ignored(n):stack.extend(reversed(n['children']))
    return ' '.join(' '.join(parts).split())


@lru_cache(maxsize=4)
def article_content(body):
    parser=CardParser();parser.feed(body or '')
    # Some university CMS templates wrap their article in a form. Allow that
    # wrapper while locating a known body, but still prune hidden/navigation trees.
    all_nodes=[];stack=[parser.root]
    while stack:
        node=stack.pop()
        if isinstance(node,str) or ignored(node,allow_form=True):continue
        all_nodes.append(node)
        stack.extend(reversed(node['children']))
    articles=[n for n in all_nodes if n['tag']=='article' and not ignored(n)]
    headed=[n for n in articles if any(c['tag']=='h1' for c in walk(n))]
    mains=[n for n in all_nodes if n['tag']=='main' and not ignored(n)]
    cms=[n for n in all_nodes if n['attrs'].get('id','').startswith('vsb_content_') or 'v_news_content' in (n['attrs'].get('class') or '').split()]
    root=cms[0] if cms else headed[0] if headed else articles[0] if len(articles)==1 else mains[0] if len(mains)==1 else parser.root
    citations=[]
    stack=[root]
    while stack:
        node=stack.pop()
        if isinstance(node,str) or ignored(node):continue
        if node['tag']=='p':
            context=prose(node)
            if re.search(r'\breports?\b|according to|据.{0,20}报道',context,re.I):
                for anchor in walk(node):
                    if anchor['tag']=='a' and not ignored(anchor) and anchor['attrs'].get('href'):
                        citations.append((prose(anchor),anchor['attrs']['href'],context[:450]))
        stack.extend(reversed(node['children']))
    return prose(root),root['tag'],tuple(citations)


def article_citations(body,base_url):
    result=[];seen=set();base_host=urlsplit(base_url).hostname
    for label,href,context in article_content(body)[2]:
        url=urljoin(base_url,href);parts=urlsplit(url)
        if parts.scheme not in ('http','https') or not parts.hostname or parts.hostname==base_host or url in seen:
            continue
        seen.add(url)
        result.append({'name':label,'url':url,'context':context,'status':'unverified_citation'})
    return result[:8]

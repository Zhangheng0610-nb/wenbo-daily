"""Read dates and titles within the same official news card, never a neighbour."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

class CardParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {'tag':'root','attrs':{},'children':[]}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node={'tag':tag,'attrs':dict(attrs),'children':[]}
        self.stack[-1]['children'].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i]['tag']==tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1]['children'].append(data)


def nodes(node):
    yield node
    for child in node['children']:
        if isinstance(child,dict):
            yield from nodes(child)


def text(node):
    if node['tag'] in ('script','style'):
        return ''
    return ' '.join(' '.join(text(c) if isinstance(c,dict) else c for c in node['children']).split())


def news_cards(page, spec):
    parser=CardParser(); parser.feed(page)
    icom=spec['sourceId']=='icom-news'
    result=[]
    for card in nodes(parser.root):
        classes=(card['attrs'].get('class') or '').split()
        if not ((icom and card['tag']=='a' and 'news-abstract' in classes) or
                (not icom and card['tag']=='article' and 'node--type-news' in classes)):
            continue
        descendants=list(nodes(card))
        heading=next((n for n in descendants if n['tag']==('h2' if icom else 'h3')),None)
        date_node=next((n for n in descendants if (icom and n['tag']=='p') or
                       (not icom and 'date' in (n['attrs'].get('class') or '').split())),None)
        anchor=card if icom else next((n for n in descendants if n['tag']=='a' and '/news/' in (n['attrs'].get('href') or '')),None)
        if heading is None or anchor is None:
            continue
        url=urljoin(spec['url'],anchor['attrs'].get('href') or '')
        host=(urlsplit(url).hostname or '').lower()
        if host not in (spec['domain'],'www.'+spec['domain']):
            continue
        result.append((text(heading),url,text(date_node) if date_node is not None else ''))
    return result

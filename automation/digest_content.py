"""Shared NCHA digest parsing; paragraph boundaries prevent cross-item bleed."""
from html.parser import HTMLParser

class DigestHTMLParser(HTMLParser):
    """Read the real NCHA digest paragraph structure without cross-item bleed."""

    VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.in_content = False
        self.current = None
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.in_content and tag == 'div' and attrs.get('id') == 'zw':
            self.in_content = True
            self.depth = 1
            return
        if not self.in_content:
            return
        if tag == 'p':
            self.current = {'text': [], 'strong_text': [], 'strong_depth': 0}
        elif tag == 'strong' and self.current is not None:
            self.current['strong_depth'] += 1
        if tag not in self.VOID_TAGS:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        # Images and other self-closing nodes do not create paragraph text.
        if self.in_content and tag == 'p':
            self.current = {'text': [], 'strong_text': [], 'strong_depth': 0}
            self.finish_paragraph()

    def handle_endtag(self, tag):
        if not self.in_content:
            return
        if tag == 'p':
            self.finish_paragraph()
        elif tag == 'strong' and self.current is not None:
            self.current['strong_depth'] = max(0, self.current['strong_depth'] - 1)
        if tag not in self.VOID_TAGS:
            self.depth = max(0, self.depth - 1)
            if self.depth == 0:
                self.in_content = False

    def handle_data(self, data):
        if self.current is None or not self.in_content:
            return
        self.current['text'].append(data)
        if self.current['strong_depth']:
            self.current['strong_text'].append(data)

    def finish_paragraph(self):
        if self.current is None:
            return
        text = ' '.join(''.join(self.current['text']).split())
        strong = ' '.join(''.join(self.current['strong_text']).split())
        if text:
            self.paragraphs.append({'text': text, 'strong': strong})
        self.current = None


REGIONS = set("北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆".split())

def digest_blocks(page):
    parser = DigestHTMLParser()
    parser.feed(page or '')
    blocks, current, region = [], None, ''
    for paragraph in parser.paragraphs:
        text, strong = paragraph['text'], paragraph['strong']
        if text in REGIONS:
            if current:
                blocks.append(current)
            current, region = None, text
            continue
        if strong and strong == text and 4 <= len(text) <= 100:
            if current:
                blocks.append(current)
            current = {'title':text, 'body':[], 'region':region}
        elif current:
            current['body'].append(text)
    if current:
        blocks.append(current)
    return blocks

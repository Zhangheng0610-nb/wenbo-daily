"""Recruitment-specific source scans and bounded nationwide query planning.

Directory links are leads, not verified positions. Missing publication dates
are retained here: a long-running vacancy must not disappear like old news.
"""
from datetime import date,timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,urldefrag
import re
from html import unescape
from concurrent.futures import ThreadPoolExecutor

REGIONS = tuple('北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆'.split())
INTERNSHIP_QUERIES = (
 '博物馆 实习生 招募', '博物院 实习 招聘', '考古 实习 招募',
 '博物馆 学生助理 招募', '博物馆 见习 岗位', '文物修复 实习',
 '美术馆 策展 实习', '博物馆 公共教育 实习', '博物馆 数字化 实习',
 'site:edu.cn 博物馆 实习生', 'site:mp.weixin.qq.com 博物馆 实习 招募',
 '博物馆 长期招聘 实习', '香港 博物館 實習 招聘', '澳门 博物馆 招聘', '台湾 博物館 實習 招募',
)


def query_plan(run_date, families, registry, *, full_sweep=False):
    tasks=[]
    # Every week visits all 31 regions, with a 30-day overlap rather than a
    # one-day shard window. Full sweep is used for initial catch-up/recovery.
    regions=list(REGIONS) if full_sweep else [r for i,r in enumerate(REGIONS) if i%7==run_date.toordinal()%7]
    for family,queries in families.items():
        tasks.extend({'family':family,'query':q} for q in queries)
    tasks.extend({'family':'internship','query':q} for q in INTERNSHIP_QUERIES)
    for region in regions:
        for q in (f'{region} 博物馆 考古 招聘',f'{region} 人力资源 事业单位 文物 招聘',f'{region} 博物馆 实习'):
            tasks.append({'family':'national_rotation','query':q,'region':region})
    for source in registry.get('sources',[]):
        if not source.get('active'):continue
        host=urlsplit(source.get('url','')).hostname
        if host and host!='mp.weixin.qq.com':
            tasks.append({'family':'registered_radar','query':f'site:{host} 博物馆 招聘 实习','sourceUrl':source['url']})
    # Catch-up search includes a whole year, to find still-open rolling roles;
    # no result is labelled open until its application window is checked.
    for q in ('博物馆 长期招聘','博物馆 实习 长期 招募','考古 博士后 招聘'):
        tasks.append({'family':'open_ended','query':q,'lookbackDays':365})
    unique={}
    for task in tasks:
        key=(task['family'],task['query'])
        if key not in unique:unique[key]=task
        if task.get('sourceUrl'):
            unique[key].setdefault('sourceUrls',[]).append(task['sourceUrl'])
    tasks=list(unique.values())
    for task in tasks:task.setdefault('lookbackDays',90 if full_sweep else 30)
    return tasks


def navigational_url(url):
    parsed=urlsplit(url)
    return parsed.hostname in ('www.gaoxiaojob.com','gaoxiaojob.com') and (
        parsed.path.startswith(('/hotword/','/column/')) or parsed.path.rstrip('/') in ('/job','/announcement',''))


def inline_digest_records(html,source,checked_at):
    # Explicit regional subheadings delimit separate notices on a shared URL.
    clean=re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', html, flags=re.S|re.I)
    text=re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',clean)))
    matches=list(re.finditer(r'【([^】]{1,10})】\s*([^【]{2,80}?)(?=\s*一[、．.])',text))
    records=[]
    for i,m in enumerate(matches):
        institution=m[2].strip();body=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        if not any(term in institution for term in ('博物','考古','文物','历史馆','紀念館','纪念馆','美术馆')):continue
        title=institution+' — '+('实习招募' if '实习' in body else '招聘公告')
        records.append({'title':title,'institution':institution,'position':'公告岗位待展开','url':source['url'],
         'sourceSectionKey':source['url']+'#notice-'+str(i+1),'publishedDate':'','discoveredAt':checked_at,
         'discoverySource':source['name'],'discoverySourceType':'recruitment_inline_digest','region':m[1],
         'applicationHints':sorted(set(re.findall(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',body))),
         'deadlineHints':re.findall(r'报名(?:截止)?时间[：:]?[^。]{0,160}',body)[:2],
         'verificationStatus':'pending','decisionReason':'inline_digest_requires_original_notice_and_position_table'})
    return records


class DirectoryLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.current=None;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.current=dict(attrs).get('href');self.text=[]
    def handle_data(self,text):
        if self.current is not None:self.text.append(text)
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.links.append((self.current,' '.join(' '.join(self.text).split())))
            self.current=None;self.text=[]


def scan_directory(source, fetcher, *, checked_at):
    from automation.recruitment_discovery import is_recruitment_candidate
    url=source['url'];audit={'sourceUrl':url,'sourceName':source['name'],'checkedAt':checked_at,'method':'direct_directory','status':'failed','candidateLinks':0}
    try:
        html=fetcher(url)
        if any(marker in html[:15000] for marker in ('环境异常','访问验证','访问过于频繁','验证码','Access Denied')):
            raise ValueError('access_challenge')
        parser=DirectoryLinks();parser.feed(html)
        records=[];seen=set()
        for href,title in parser.links:
            link=urldefrag(urljoin(url,href))[0]
            if urlsplit(link).scheme not in ('https','http') or link==url or link in seen or navigational_url(link):continue
            if not is_recruitment_candidate(title):continue
            seen.add(link)
            records.append({'title':title,'url':link,'publishedDate':'','discoveredAt':checked_at,'discoverySource':source['name'],'discoverySourceType':'recruitment_directory','directoryUrl':url,'verificationStatus':'pending','decisionReason':'directory_lead_requires_detail_and_application_check'})
            if len(records)>=100:break
        if source.get('inlineDigest'):
            inline=inline_digest_records(html,source,checked_at);records.extend(inline);audit['inlineNotices']=len(inline)
        audit.update(status='success' if records else 'partial',candidateLinks=len(records),parsedLinks=len(parser.links),result='candidate_links' if records else 'no_candidate_links_structure_or_content_requires_review')
        return records,audit
    except Exception as exc:
        audit['error']=f'{type(exc).__name__}: {str(exc)[:240]}'
        return [],audit


def scan_directories(registry,fetcher,*,checked_at):
    sources=[s for s in registry.get('sources',[]) if s.get('active') and s.get('directScan')]
    if not sources:return [],[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda s:scan_directory(s,fetcher,checked_at=checked_at),sources))
    return [r for rows,_ in results for r in rows],[a for _,a in results]

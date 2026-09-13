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
    from automation.recruitment_discovery import is_recruitment_candidate, RECRUITMENT_TERMS
    url=source['url'];audit={'sourceUrl':url,'sourceName':source['name'],'checkedAt':checked_at,'method':'direct_directory','status':'failed','candidateLinks':0}
    try:
        html=fetcher(url)
        if any(marker in html[:15000] for marker in ('环境异常','访问验证','访问过于频繁','验证码','Access Denied')):
            raise ValueError('access_challenge')
        parser=DirectoryLinks();parser.feed(html)
        records=[];seen=set();updates=[]
        # Follow only explicit next-page links within the registered directory.
        pages=[url]; failures=[]
        for _ in range(min(int(source.get('followPages', 0)), 2)):
            next_url=next((urljoin(pages[-1],h) for h,t in parser.links if t.strip() in ('下一页','下页','Next','Next page') and urlsplit(urljoin(pages[-1],h)).scheme in ('http','https') and urlsplit(urljoin(pages[-1],h)).hostname==urlsplit(url).hostname and urlsplit(urljoin(pages[-1],h)).path.startswith(urlsplit(url).path.rsplit('/',1)[0]+'/') and urljoin(pages[-1],h) not in pages),None)
            if not next_url:break
            try:
                following=fetcher(next_url)
                if any(marker in following[:15000] for marker in ('环境异常','访问验证','验证码','Access Denied')):raise ValueError('access_challenge')
                pages.append(next_url);extra=DirectoryLinks();extra.feed(following)
                parser.links.extend((urljoin(next_url,h),t) for h,t in extra.links)
            except Exception as exc:failures.append(str(exc)[:200]);break
        audit.update(pagesChecked=pages,paginationFailures=failures)
        for href,title in parser.links:
            link=urldefrag(urljoin(url,href))[0]
            if urlsplit(link).scheme not in ('https','http') or link==url or link in seen or navigational_url(link):continue
            # Registered institutional context rescues headlines such as “实习生招募”.
            # External links inherit it only for an explicitly registered application path.
            if title.strip() in ('招聘','招聘信息','人才招聘','招聘公告','实习','Internships','Careers'):continue
            application=bool(source.get('applicationUrlPrefix') and link.startswith(source['applicationUrlPrefix']))
            umbrella=bool(source.get('umbrellaNotices') and urlsplit(link).hostname==urlsplit(url).hostname and re.search(r'事业单位.*(?:招聘|招考)|(?:招聘|招考).*事业单位',title))
            contextual=bool(source.get('institution') and source.get('type')=='official_institution' and urlsplit(link).hostname==urlsplit(url).hostname and any(term in title for term in RECRUITMENT_TERMS))
            if not is_recruitment_candidate(title) and not contextual and not application and not umbrella:continue
            seen.add(link)
            headline=re.split(r'\s+20\d{2}\s*[/.]\s*\d{1,2}\s*[/.]\s*\d{1,2}',title,maxsplit=1)[0].strip().removesuffix('查看详情').strip()
            if re.search(r'(?:拟(?:录|聘)用|入围(?:考察|面试)|进入面试|资格(?:复审|审查)|(?:笔试|面试)(?:成绩|名单)|体检)[^。]{0,24}(?:公告|公示|通知|名单|人员信息)$',headline):
                updates.append({'title':title,'url':link});continue
            if application:
                title=source['institution']+' — '+source.get('programName','招聘')+'：'+title
            elif contextual and not is_recruitment_candidate(title):
                title=source['institution']+' — '+title
            records.append({'title':title,'url':link,'publishedDate':'','discoveredAt':checked_at,'discoverySource':source['name'],'discoverySourceType':'recruitment_directory','directoryUrl':url,'verificationStatus':'pending','decisionReason':'directory_lead_requires_detail_and_application_check'})
            if contextual or application:records[-1]['institution']=source['institution']
            if umbrella:records[-1]['decisionReason']='umbrella_notice_needs_attachment_inspection'
            if len(records)>=100:break
        if source.get('inlineDigest'):
            inline=inline_digest_records(html,source,checked_at);records.extend(inline);audit['inlineNotices']=len(inline)
        audit.update(status='partial' if failures else 'success' if records or updates else 'partial',candidateLinks=len(records),parsedLinks=len(parser.links),lifecycleUpdates=updates,result='candidate_links' if records else 'workflow_updates_only' if updates else 'no_candidate_links_structure_or_content_requires_review')
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

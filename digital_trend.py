#!/usr/bin/env python3
"""
digital_trend.py — 国家文物局「数字化」新闻趋势数据抓取与页面生成

数据源: 国家文物局官网「文物新闻」栏目分页接口
  GET /module/jslib/jquery/jpage/dataproxy.jsp?page=N&appid=1&webid=1&path=/&columnid=722&unitid=8000&webname=国家文物局&permissiontype=0
  返回 XML,每页 300 条,全栏目约 12778 条;page=46 覆盖至 2020-12 月,满足 2021-01 至今的 5 年窗口。

流程:
  1) 抓全量标题+日期+链接 → 关键词筛选「数字化」相关
  2) 补充口径:抓「一周文物动态摘编」正文,提取正文内数字化小标题(标题未命中但正文命中的情况)
  3) 聚合生成 月/周/天 三套粒度数据 → digital-data.json
  4) 生成 ECharts 交互趋势页 → digital-trends.html

缓存:digital-data.json 当日已生成则跳过抓取(避免 build.py 每次构建都发 46 次请求)。
用法: python digital_trend.py          # 完整抓取+生成
      python digital_trend.py --force  # 强制重新抓取
      python digital_trend.py --build-only  # 只用已有数据重新生成页面
      python digital_trend.py --relabel-only  # 只为已有记录补充行业方向分类
"""
import os, re, json, sys, time
import urllib.request
from collections import defaultdict
from datetime import datetime, date

if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SITE_DIR, 'digital-data.json')
HTML_PATH = os.path.join(SITE_DIR, 'digital-trends.html')

BASE = 'http://www.ncha.gov.cn'
PROXY_TMPL = (BASE + '/module/jslib/jquery/jpage/dataproxy.jsp'
              '?page={p}&appid=1&webid=1&path=/&columnid=722&unitid=8000'
              '&webname=%E5%9B%BD%E5%AE%B6%E6%96%87%E7%89%A9%E5%B1%80&permissiontype=0')
START_DATE = date(2021, 1, 1)
END_DATE = date.today()

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'

# ───────────────── 关键词三层(已发用户审核通过,含扩充) ─────────────────
# 核心词:数字化直接表达(标题命中即强信号)
KEYWORDS_CORE = [
    '数字化', '数字化保护', '数字化采集', '数字化展示', '数字化管理', '数字化技术',
    '数字化应用', '数字化建设', '数字化成果', '数字化讲解', '数字化服务', '数字化传播',
    '数字文物', '数字博物馆', '数字敦煌', '数字故宫', '数字藏品', '数字孪生', '数字档案',
    '数字资源', '数字资产', '数字平台', '数字科技', '数字技术', '数字体验', '数字服务',
    '数字管理', '数字出版', '数字影像', '数字展示', '数字保护', '数字文化', '数字创意',
    '数字赋能', '数字讲解', '数字回归', '文化遗产数字化', '文物数字化',
]
# 技术词:数字化背后的技术
KEYWORDS_TECH = [
    '人工智能', 'AI', '大数据', '数据平台', '数据资源', '云计算', '区块链', '元宇宙',
    '虚拟现实', 'VR', '增强现实', 'AR', '混合现实', '全息', '三维扫描', '3D扫描',
    '5G', '物联网', '数字人', '虚拟漫游', '数字孪生',
]
# 扩展主题词:数字化应用场景
KEYWORDS_EXT = [
    '智慧博物馆', '智慧文博', '智慧服务', '智慧导览', '云展览', '云游', '云上看展',
    '云直播', '云端', '云上', '线上展览', '线上展播', '虚拟展厅', '掌上博物馆',
    '沉浸式', '交互体验', '信息化', '科技赋能', '线上直播', '智能导览',
]

LEVEL_NAME = {'core': '核心', 'tech': '技术', 'ext': '扩展'}

# 关键词仍然只负责“是否纳入趋势库”；页面展示改用行业方向。
# 一条记录可以命中多个方向，便于表达数字保护、技术、展陈等交叉实践。
TOPIC_INFO = [
    ('数字保护与数字采集', '记录、保存、修复和数字化采集文物与遗址'),
    ('AI、三维扫描与科技考古', '人工智能、三维建模、遥感和数据分析等技术'),
    ('数字展览与沉浸式体验', '数字展示、虚拟现实、沉浸式空间和数字复原'),
    ('数字博物馆与公共服务', '智慧博物馆、数字导览、云展览和线上公共服务'),
    ('数字档案、数据库与知识平台', '数字档案、数据库、知识库和数字资源管理'),
    ('数字传播与国际交流', '数字内容传播、线上推广和文化遗产数字出海'),
]

TOPIC_RULES = {
    # 以下是页面展示分类，不是新的纳入关键词；使用标题中的行业语义词，
    # 让“数字化”总括性标题也能在有足够语境时进入合适方向。
    '数字保护与数字采集': ('数字化保护', '文物数字化', '数字保护', '数字化采集',
                           '数字采集', '数字回归', '数字化记录', '数字化存档', '数字化建档',
                           '数字化测绘', '数字孪生', '保护修复', '保护与数字化', '预防性保护'),
    'AI、三维扫描与科技考古': ('人工智能', 'AI', '大数据', '机器学习', '算法', '遥感',
                              '三维扫描', '3D扫描', '三维建模', '三维数据', '三维数字化',
                              '数字人', '数字孪生', '科技考古', '空间信息', '数据集', '科技赋能',
                              '科技创新', '技术装备'),
    '数字展览与沉浸式体验': ('数字化展示', '数字展示', '数字体验', '沉浸式', '虚拟现实',
                            'VR', '增强现实', 'AR', '混合现实', '全息', '虚拟展厅',
                            '数字复原', '云展览', '线上展览', '线上展播', '展览', '展馆',
                            '展厅', '展出', '亮相', '巡展', '体验'),
    '数字博物馆与公共服务': ('数字博物馆', '智慧博物馆', '智慧文博', '数字服务', '智慧服务',
                            '智慧导览', '掌上博物馆', '云游', '云端', '云上', '线上服务',
                            '博物馆', '博物院', '平台上线', '上线', '公众', '开放'),
    '数字档案、数据库与知识平台': ('数字档案', '数字资源', '数字资产', '数字平台', '数据平台',
                                  '数据库', '知识库', '数据资源', '数字出版', '数字化管理', '信息化',
                                  '数据', '档案', '资源', '文献', '图像', '知识', '素材库', '数据集'),
    '数字传播与国际交流': ('数字传播', '数字文化', '数字出海', '国际交流', '国际传播',
                          '线上直播', '线上展播', '网络', '宣传', '传播', '全球', '海外',
                          '国际', '交流互鉴', '文明交流', '论坛', '大会'),
}

# 摘编类标题(正文含多条目聚合,需要正文补充提取)
DIGEST_PATTERN = re.compile(r'一周.{0,2}(文物|各地文物)动态摘编|一周文物动态')


def fetch(url, retries=3, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    last_err = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8', errors='replace')
        except Exception as e:
            last_err = e
            time.sleep(1.2 * (i + 1))
    print(f'  [warn] fetch failed x{retries}: {url} ({last_err})')
    return None


def fetch_all_titles():
    """抓取分页接口全部标题+日期+链接,过滤 START_DATE 之后。"""
    items = []
    page = 1
    while True:
        html = fetch(PROXY_TMPL.format(p=page))
        if not html:
            raise RuntimeError(f'国家文物局分页第 {page} 页抓取失败，已停止保存，避免用不完整数据覆盖旧趋势。')
        records = re.findall(r"<record><!\[CDATA\[(.*?)\]\]></record>", html, re.S)
        if not records:
            print(f'  [info] page {page} 无记录,停止')
            break
        page_items = []
        for r in records:
            m_title = re.search(r"href='(/art/\d{4}/\d+/\d+/art_\d+_\d+\.html)'\s+title='([^']*)'", r)
            m_date = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', r)
            if not m_title or not m_date:
                continue
            url, title = m_title.group(1), m_title.group(2)
            try:
                d = datetime.strptime(m_date.group(1), '%Y-%m-%d').date()
            except ValueError:
                continue
            if d < START_DATE:
                # 已越过起点；不要把同页中起点以前的记录写入窗口。
                items.extend(page_items)
                print(f'  [info] 第{page}页出现 {d} 早于起点,抓取结束')
                return items
            if d <= END_DATE:
                page_items.append({'date': d, 'title': title, 'url': url})
        items.extend(page_items)
        print(f'  page {page}: {len(page_items)} 条, 最新 {page_items[0]["date"] if page_items else "?"} ~ 最老 {page_items[-1]["date"] if page_items else "?"} | 累计 {len(items)}')
        page += 1
        if page > 60:
            print('  [warn] 超过60页,强制停止(异常情况)')
            break
    return items


def match_keywords(title):
    """返回 (level, word) 或 None。标题命中任一层即算。"""
    for w in KEYWORDS_CORE:
        if w in title:
            return ('core', w)
    for w in KEYWORDS_TECH:
        if w in title:
            return ('tech', w)
    for w in KEYWORDS_EXT:
        if w in title:
            return ('ext', w)
    return None


def classify_topics(title, level=''):
    """把已纳入趋势库的记录映射到行业方向，不改变关键词准入口径。"""
    text = title or ''
    topics = [name for name, _ in TOPIC_INFO
              if any(word in text for word in TOPIC_RULES.get(name, ()))]
    # 仅命中“数字化”等总括词的文章无法安全细分，不强行归入具体方向。
    return topics


def topics_for_record(record):
    """读取记录上的方向标签；兼容旧数据并在缺失时即时分类。"""
    topics = record.get('topics')
    if topics is not None:
        return topics
    return classify_topics(record.get('title', record.get('t', '')),
                           record.get('level', record.get('l', '')))


def topic_counts_for_records(records):
    """按原文 URL 统计各行业方向，方向是多标签，合计可能超过总原文数。"""
    urls_by_topic = defaultdict(set)
    for record in records:
        url = record.get('url', record.get('u', ''))
        if not url:
            continue
        for topic in topics_for_record(record):
            urls_by_topic[topic].add(url)
    return {name: len(urls_by_topic[name]) for name, _ in TOPIC_INFO}


def article_entities(records):
    """Merge trend records into canonical article entities by original URL.

    ``items`` keeps every keyword/digest hit for auditability.  Consumers that
    display trends, topics, or evidence should use ``articles`` so one source
    article can never be counted twice in the same direction.  A single
    article may still carry several direction labels.
    """
    by_url = {}
    for record in records:
        url = record.get('url', record.get('u', ''))
        title = record.get('title', record.get('t', ''))
        item_date = record.get('date', record.get('d', ''))
        if hasattr(item_date, 'isoformat'):
            item_date = item_date.isoformat()
        key = url or f'{title}|{item_date}'
        if not key:
            continue
        if key not in by_url:
            by_url[key] = {
                'u': url,
                't': title,
                'd': item_date,
                'l': record.get('level', record.get('l', '')),
                'topics': [],
                'matched_keywords': [],
                'digest_snippets': [],
                'matched_titles': [],
                'record_count': 0,
            }
        article = by_url[key]
        article['record_count'] += 1
        if item_date and (not article['d'] or item_date < article['d']):
            article['d'] = item_date
            article['t'] = title or article['t']
            article['l'] = record.get('level', record.get('l', '')) or article['l']
        for topic in topics_for_record(record):
            if topic not in article['topics']:
                article['topics'].append(topic)
        keyword = record.get('word', record.get('w', ''))
        if keyword and keyword not in article['matched_keywords']:
            article['matched_keywords'].append(keyword)
        if title and title not in article['matched_titles']:
            article['matched_titles'].append(title)
        if record.get('from_digest') and title and title not in article['digest_snippets']:
            article['digest_snippets'].append(title)

    for article in by_url.values():
        # Primary title is already displayed separately.  Keep every merged
        # hit title for evidence drill-down; the UI must disclose any paging
        # rather than silently trimming evidence.
        article['matched_titles'] = [title for title in article['matched_titles']
                                     if title != article['t']]
    return sorted(by_url.values(), key=lambda item: (item.get('d', ''), item.get('u', '')), reverse=True)


def extract_digest_items(body, url, pub_date):
    """从摘编正文提取数字化相关条目。

    摘编正文格式:每条目 = 「标题行 + 正文段落(可含换行)」,地区行(如'北京')穿插其间。
    策略:逐行扫描,短行(≤60字且不含句末标点)视为"条目标题"候选;
    任一行命中关键词时,若该行本身是标题行则直接用,否则向上回溯最近的标题行作为条目标题。
    """
    region_names = set(['北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江',
                        '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
                        '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州',
                        '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆'])
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    found = []
    title_candidates = []
    title_re = re.compile(r'^[^\n。！？，,；;]{4,60}$')

    for line in lines:
        is_title_like = bool(title_re.match(line)) and not DIGEST_PATTERN.search(line)
        if is_title_like and line not in region_names:
            title_candidates.append(line)
        m = match_keywords(line)
        if not m:
            continue
        # 命中关键词:确定条目标题
        if is_title_like:
            item_title = line
        elif title_candidates:
            item_title = title_candidates[-1]
        else:
            continue  # 正文命中但无标题上下文,跳过
        if len(item_title) > 60:
            continue
        if item_title not in (f['title'] for f in found):
            found.append({'title': item_title, 'date': pub_date, 'url': url,
                          'level': m[0], 'word': m[1], 'from_digest': True})
    return found


def fetch_digest_bodies(items):
    """对标题含摘编特征的文章抓正文,提取数字化小标题作为补充口径。"""
    digests = [it for it in items if DIGEST_PATTERN.search(it['title'])]
    extra = []
    failed = 0
    print(f'  摘编类文章 {len(digests)} 篇,开始抓正文提取数字化条目...')
    for i, dg in enumerate(digests):
        body = fetch(BASE + dg['url'])
        if not body:
            failed += 1
            continue
        # 提取正文纯文本(粗略:去 script/style/标签)
        text = re.sub(r'<script[\s\S]*?</script>', ' ', body)
        text = re.sub(r'<style[\s\S]*?</style>', ' ', text)
        text = re.sub(r'<[^>]+>', '\n', text)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'\n+', '\n', text)
        for item in extract_digest_items(text, dg['url'], dg['date']):
            extra.append(item)
        if (i + 1) % 25 == 0:
            print(f'    进度 {i+1}/{len(digests)}, 已提取 {len(extra)} 条')
        time.sleep(0.15)
    return extra, failed


def dedup_and_filter(items):
    """质量门禁:
    1) 标题完全一致的条目去重(跨摘编转载),保留最早日期。
    2) 两级过滤: 标题含数字化词 → 保留; 标题无词但正文命中"核心词" → 保留;
       正文仅命中扩展/技术词 → 剔除(弱关联噪声,如"某馆开馆"(正文顺带提科技赋能))。
    """
    seen = {}
    for it in items:
        if it['title'] not in seen or it['date'] < seen[it['title']]['date']:
            seen[it['title']] = it
    keep = []
    for v in seen.values():
        if match_keywords(v['title']):
            keep.append(v)
        elif v['level'] == 'core':
            keep.append(v)
        else:
            continue
    keep.sort(key=lambda x: x['date'])
    return keep


def aggregate(items, source_items):
    """生成趋势聚合数据。

    count 是关键词命中的记录数，unique_count 是去重后的原文 URL 数；
    source_count/source_unique_count 用于计算数字化报道在国家文物局全部文物
    新闻中的占比，避免把整体发稿量变化误当成数字化趋势变化。
    """
    by_month = defaultdict(list)
    by_week = defaultdict(list)
    by_day = defaultdict(list)
    by_year = defaultdict(list)
    source_by_month = defaultdict(list)
    source_by_week = defaultdict(list)
    source_by_day = defaultdict(list)
    source_by_year = defaultdict(list)
    for it in items:
        ym = it['date'].strftime('%Y-%m')
        iso = it['date'].isocalendar()
        wk = f"{it['date'].strftime('%Y')}-W{iso[1]:02d}"
        year = str(it['date'].year)
        by_month[ym].append(it)
        by_week[wk].append(it)
        by_day[it['date'].isoformat()].append(it)
        by_year[year].append(it)
    for it in source_items:
        ym = it['date'].strftime('%Y-%m')
        iso = it['date'].isocalendar()
        wk = f"{it['date'].strftime('%Y')}-W{iso[1]:02d}"
        year = str(it['date'].year)
        source_by_month[ym].append(it)
        source_by_week[wk].append(it)
        source_by_day[it['date'].isoformat()].append(it)
        source_by_year[year].append(it)

    def to_series(group, source_group, include_items=True):
        keys = sorted(set(group) | set(source_group))
        out = []
        for k in keys:
            v = group.get(k, [])
            source_v = source_group.get(k, [])
            unique_count = len({x['url'] for x in v})
            source_unique_count = len({x['url'] for x in source_v})
            share = round(unique_count / source_unique_count * 100, 2) if source_unique_count else 0
            row = {'key': k, 'count': len(v), 'unique_count': unique_count,
                   'source_count': len(source_v),
                   'source_unique_count': source_unique_count,
                   'share': share}
            if include_items:
                row['items'] = [
                    {'t': x['title'], 'd': x['date'].isoformat(), 'u': x['url'], 'l': x['level']} for x in v
                ]
            out.append(row)
        return out

    return {
        'by_month': to_series(by_month, source_by_month),
        'by_week': to_series(by_week, source_by_week),
        'by_day': to_series(by_day, source_by_day),
        'by_year': to_series(by_year, source_by_year, include_items=False),
    }


def save_data(items, extra, digest_count, digest_failed, levels, source_items):
    items = dedup_and_filter(items)
    for it in items:
        it['topics'] = classify_topics(it['title'], it.get('level', ''))
    levels = defaultdict(int)
    for it in items:
        levels[it['level']] += 1
    agg = aggregate(items, source_items)
    extra_n = len(extra) if isinstance(extra, (list, tuple)) else extra
    articles = article_entities(items)
    unique_urls = len(articles)
    source_unique_urls = len({x['url'] for x in source_items})
    data = {
        'generated': date.today().isoformat(),
        'source': '国家文物局官网「文物新闻」栏目',
        'range': {'start': START_DATE.isoformat(), 'end': END_DATE.isoformat()},
        'stats': {
            'total': len(items),
            'title_hit': sum(1 for x in items if match_keywords(x['title'])),
            'digest_extra': extra_n,
            'levels': {k: v for k, v in sorted(levels.items())},
            'digest_articles': digest_count,
            'unique_source_pages': unique_urls,
            'source_article_total': len(source_items),
            'source_unique_pages': source_unique_urls,
            'overall_share': round(unique_urls / source_unique_urls * 100, 2) if source_unique_urls else 0,
            'topic_unique_counts': topic_counts_for_records(articles),
            'classified_article_count': sum(1 for article in articles if article['topics']),
            'unclassified_article_count': sum(1 for article in articles if not article['topics']),
        },
        'quality': {
            'source_fetch_complete': True,
            'digest_fetch_failed': digest_failed,
            'note': '关键词只负责纳入趋势库；页面按六类行业方向展示。主数据 articles 按原文URL聚合，保留关键词、方向与摘编命中片段；unique_count按原文URL去重，share按国家文物局全部文物新闻原文URL计算。',
        },
        'topic_info': [{'name': name, 'description': description} for name, description in TOPIC_INFO],
        'items': [
            {'t': x['title'], 'd': x['date'].isoformat(), 'u': x['url'], 'l': x['level'],
             'w': x.get('word', ''), 'topics': x.get('topics', []),
             'from_digest': bool(x.get('from_digest'))} for x in items
        ],
        'articles': articles,
        **agg,
    }
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def relabel_existing_data():
    """给旧版 digital-data.json 补方向分类，不重新请求国家文物局。"""
    if not os.path.exists(DATA_PATH):
        raise RuntimeError('找不到已有 digital-data.json，无法执行 --relabel-only。')
    with open(DATA_PATH, encoding='utf-8') as f:
        data = json.load(f)

    items = data.get('items', [])
    for item in items:
        item['topics'] = classify_topics(item.get('t', ''), item.get('l', ''))

    for granularity in ('by_month', 'by_week', 'by_day'):
        for group in data.get(granularity, []):
            group_items = group.get('items', [])
            group.pop('topic_counts', None)
            for item in group_items:
                item.pop('topics', None)

    annual = {}
    for group in data.get('by_month', []):
        year = group.get('key', '')[:4]
        if not year:
            continue
        row = annual.setdefault(year, {'key': year, 'count': 0, 'unique_count': 0,
                                       'source_count': 0, 'source_unique_count': 0})
        for field in ('count', 'unique_count', 'source_count', 'source_unique_count'):
            row[field] += group.get(field, 0) or 0
    for row in annual.values():
        row['share'] = round(row['unique_count'] / row['source_unique_count'] * 100, 2) if row['source_unique_count'] else 0
    data['by_year'] = [annual[key] for key in sorted(annual)]

    stats = data.setdefault('stats', {})
    articles = article_entities(items)
    data['articles'] = articles
    stats['unique_source_pages'] = len(articles)
    stats['topic_unique_counts'] = topic_counts_for_records(articles)
    stats['classified_article_count'] = sum(1 for article in articles if article['topics'])
    stats['unclassified_article_count'] = sum(1 for article in articles if not article['topics'])
    data['topic_info'] = [{'name': name, 'description': description}
                          for name, description in TOPIC_INFO]
    quality = data.setdefault('quality', {})
    quality['topic_taxonomy'] = '六类行业方向为页面展示分类；关键词口径未改变；同一原文可归入多个方向。articles按原文URL聚合，用于方向和趋势主统计。'

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def main(args=None):
    """Refresh source data only when explicitly requested.

    ``build.py`` runs every day and should never trigger the five-year source
    crawl merely because the calendar date changed.  Call ``main(['--force'])``
    from a separately scheduled maintenance job when the corpus itself needs a
    refresh; daily builds call ``main(['--build-only'])``.
    """
    args = set(sys.argv[1:] if args is None else args)
    force = '--force' in args
    build_only = '--build-only' in args
    relabel_only = '--relabel-only' in args
    if relabel_only:
        print('=== 为现有趋势记录补充六类行业方向分类 ===')
        relabel_existing_data()
        print(f'分类已补充: {DATA_PATH}')
        print('=== 生成趋势页面 ===')
        import build_digital_page
        build_digital_page.build_page(HTML_PATH, DATA_PATH)
        print(f'页面已生成: {HTML_PATH}')
        return
    cache_valid = build_only  # --build-only: 只用现有数据重建页面
    if not force and not build_only and os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, encoding='utf-8') as f:
                old = json.load(f)
            if old.get('generated') == date.today().isoformat():
                cache_valid = True
                print(f'[缓存] digital-data.json 今日已生成,跳过抓取(--force 可强制重抓)')
        except Exception:
            pass

    if not cache_valid:
        print('=== 步骤1: 抓取国家文物局全量标题 ===')
        all_items = fetch_all_titles()
        print(f'获取到 {len(all_items)} 条新闻(含历史,{all_items[-1]["date"]} ~ {all_items[0]["date"]})')

        print('=== 步骤2: 标题关键词筛选 ===')
        hit = []
        levels = defaultdict(int)
        for it in all_items:
            m = match_keywords(it['title'])
            if m:
                it['level'], it['word'] = m
                it['from_digest'] = False
                hit.append(it)
                levels[m[0]] += 1
        print(f'标题命中数字化相关: {len(hit)} 条 (核心 {levels["core"]} / 技术 {levels["tech"]} / 扩展 {levels["ext"]})')

        print('=== 步骤3: 摘编正文补充提取 ===')
        extra, digest_failed = fetch_digest_bodies(all_items)
        # 按标题去重(与标题命中项及摘编内部)
        seen_titles = set(it['title'] for it in hit)
        digest_count = sum(1 for it in all_items if DIGEST_PATTERN.search(it['title']))
        added = 0
        for x in extra:
            if x['title'] not in seen_titles:
                seen_titles.add(x['title'])
                hit.append(x)
                added += 1
        # 重新统计去重后各层计数
        levels = defaultdict(int)
        for it in hit:
            levels[it['level']] += 1
        hit.sort(key=lambda x: x['date'])
        print(f'正文补充命中: {len(extra)} 条,去重后新增 {added} 条')
        print(f'最终命中列表: {len(hit)} 条 (核心 {levels["core"]} / 技术 {levels["tech"]} / 扩展 {levels["ext"]})')

        print('=== 步骤4: 聚合与保存 ===')
        save_data(hit, extra, digest_count, digest_failed, levels, all_items)
        print(f'数据已保存: {DATA_PATH}')

    print('=== 步骤5: 生成趋势页面 ===')
    import build_digital_page
    build_digital_page.build_page(HTML_PATH, DATA_PATH)
    print(f'页面已生成: {HTML_PATH}')


if __name__ == '__main__':
    main()

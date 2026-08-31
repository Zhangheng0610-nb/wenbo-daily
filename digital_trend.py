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

缓存:digital-data.json 由维护模式全量生成；每日模式只扫描近期分页并增量合并。
用法: python digital_trend.py          # 完整抓取+生成
      python digital_trend.py --force  # 强制重新抓取
      python digital_trend.py --incremental  # 每日近期增量扫描
      python digital_trend.py --incremental --date YYYY-MM-DD  # 回放指定日期
      python digital_trend.py --build-only  # 只用已有数据重新生成页面
      python digital_trend.py --relabel-only  # 只为已有记录补充行业方向分类
"""
import copy, os, re, json, sys, time, hashlib
from html.parser import HTMLParser
import urllib.request
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone

if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SITE_DIR, 'digital-data.json')
HTML_PATH = os.path.join(SITE_DIR, 'digital-trends.html')
DIGITAL_MONITOR_DIR = os.path.join(SITE_DIR, 'content', '数字趋势监测')

BASE = 'http://www.ncha.gov.cn'
PROXY_TMPL = (BASE + '/module/jslib/jquery/jpage/dataproxy.jsp'
              '?page={p}&appid=1&webid=1&path=/&columnid=722&unitid=8000'
              '&webname=%E5%9B%BD%E5%AE%B6%E6%96%87%E7%89%A9%E5%B1%80&permissiontype=0')
START_DATE = date(2021, 1, 1)
END_DATE = date.today()
CN_TZ = timezone(timedelta(hours=8))
INCREMENTAL_WINDOW_DAYS = 7
INCREMENTAL_MAX_PAGES = 5

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

# 弱/语境型词不能单独把文章纳入数字化趋势。它们需要在同一篇普通文章，
# 或同一个摘编小条目中，同时出现一个明确的数字技术/数字系统信号。
WEAK_KEYWORDS = (
    '大数据', '云端', '云上', '云直播', '线上直播', '线上展播',
    '沉浸式', '交互体验', '信息化', '科技赋能', '数据资源',
)

# 强词允许单独准入；其余现有关键词保持为明确的数字技术、数字系统或数字
# 应用表达。用集合派生可以避免维护第二份容易漂移的长清单。
STRONG_KEYWORDS = tuple(dict.fromkeys(
    KEYWORDS_CORE + [word for word in KEYWORDS_TECH + KEYWORDS_EXT
                     if word not in WEAK_KEYWORDS]
))

LATIN_KEYWORDS = {'AI', 'VR', 'AR', '5G', '3D', '3D扫描'}

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

# 以下是页面展示分类，不是新的纳入关键词。每个方向分为：
# direct：足够具体，可以单独生成方向标签；
# context：语境型词，必须与明确的数字载体/系统/技术同时出现。
# 泛化的“博物馆、展览、体验、国际、论坛、数据”等不再单独生成标签。
TOPIC_RULES = {
    '数字保护与数字采集': {
        'direct': ('数字化保护', '文物数字化', '数字保护', '数字化采集', '数字采集',
                   '数字回归', '数字化记录', '数字化存档', '数字化建档', '数字化测绘',
                   '数字化测量', '数字化复原', '数字化修复', '数字化保存', '保护与数字化'),
        'context': (
            ('保护修复', ('数字化', '数字保护', '数字采集', '数字测绘', '数字复原',
                         '三维', '影像', '扫描', '数据')),
            ('预防性保护', ('数字化', '数字保护', '数字采集', '数字测绘', '数字复原',
                           '三维', '影像', '扫描', '数据')),
            ('数字孪生', ('保护', '遗址', '遗产', '文物', '古建筑', '病害', '修缮')),
        ),
    },
    'AI、三维扫描与科技考古': {
        'direct': ('人工智能', 'AI', '机器学习', '算法', '遥感', '三维扫描', '3D扫描',
                   '三维建模', '三维数据', '三维数字化', '数字化建模', '数字人', '数字孪生', '科技考古',
                   '空间信息', '数据集', '数据分析', '数据模型', '数据中台', '计算机视觉'),
        'context': (
            ('大数据', ('数据分析', '数据平台', '数据库', '数据模型', '数据中台', '算法',
                       '人工智能', '数字技术', '数字化')),
            ('科技赋能', ('人工智能', 'AI', '三维', '数据', '算法', '虚拟现实', '增强现实')),
            ('科技创新', ('人工智能', 'AI', '三维', '数据', '算法', '虚拟现实', '增强现实')),
            ('技术装备', ('三维', '扫描', '监测', '智能', '数据', '遥感')),
        ),
    },
    '数字展览与沉浸式体验': {
        'direct': ('数字化展示', '数字化展陈', '数字展示', '数字展陈', '数字体验', '数字展览',
                   '数字展馆', '数字展厅', '虚拟展览', '虚拟现实', 'VR', '增强现实', 'AR',
                   '混合现实', '全息', '虚拟展厅', '数字复原展', '云展览', '线上展览',
                   '线上展播', '数字光影'),
        'context': (
            ('沉浸式', ('数字体验', '数字展示', '数字化展示', '虚拟', 'VR', 'AR', '全息', '投影', '影像',
                       '多媒体', '交互')),
            ('交互体验', ('数字体验', '数字展示', '数字化展示', '虚拟', 'VR', 'AR', '全息', '投影', '影像',
                         '多媒体', '交互')),
            ('体验', ('数字体验', '沉浸式数字', '虚拟现实', 'VR', 'AR', '全息', '交互装置',
                      '数字技术', '多媒体', '投影')),
             ('展览', ('虚拟', '线上', '云展览', 'VR', 'AR', '全息', '投影',
                      '影像', '多媒体', '交互')),
             ('展馆', ('虚拟', '线上', '云展览', 'VR', 'AR', '全息', '投影',
                      '影像', '多媒体', '交互')),
             ('展厅', ('虚拟', '线上', '云展览', 'VR', 'AR', '全息', '投影',
                      '影像', '多媒体', '交互')),
        ),
    },
    '数字博物馆与公共服务': {
        'direct': ('数字博物馆', '智慧博物馆', '智慧文博', '数字服务', '数字化服务', '智慧服务',
                   '数字导览', '智慧导览', '掌上博物馆', '云游', '线上服务', '智能导览'),
        'context': (
            ('数字敦煌', ('开放', '上线', '云游', '在线', '公众')),
            ('数字故宫', ('开放', '上线', '云游', '在线', '公众')),
            ('云端', ('博物馆', '博物院', '文博', '文物', '展览', '展馆', '展厅', '导览',
                    '线上', '服务')),
            ('云上', ('博物馆', '博物院', '文博', '文物', '展览', '展馆', '展厅', '导览',
                    '线上', '服务')),
            ('平台上线', ('博物馆', '博物院', '文博', '导览', '展览', '服务', '数字', '智慧')),
            ('信息化', ('博物馆', '博物院', '文博', '服务', '系统', '平台', '建设', '管理',
                      '数字', '数据')),
        ),
    },
    '数字档案、数据库与知识平台': {
        'direct': ('数字档案', '数字资源', '数字资产', '数字平台', '数据平台', '数据库', '知识库',
                   '数字出版', '数字化管理', '素材库', '数据集', '电子档案', '资源库', '数字图谱',
                   '知识图谱'),
        'context': (
            ('信息化', ('系统', '平台', '数据库', '数据', '资源', '档案', '数字化', '管理')),
            ('数据', ('数据库', '数据平台', '数据资源', '数据集', '数据分析', '数据模型',
                     '数据中台', '数据系统', '数据管理', '资源库', '知识库')),
            ('档案', ('数字', '电子', '数据', '数据库', '平台', '信息化')),
            ('资源', ('数字资源', '数据资源', '资源库', '数据库', '数字平台', '在线资源')),
            ('文献', ('数据库', '数字资源', '数字平台', '知识库', '电子')),
            ('图像', ('数字化', '三维', '影像', '图像库', '数据库', '采集')),
            ('知识', ('知识库', '知识图谱', '数据', '平台', '数据库')),
        ),
    },
    '数字传播与国际交流': {
        'direct': ('数字传播', '数字出海', '国际传播', '线上直播', '线上展播',
                   '网络传播', '线上传播', '数字推广'),
        'context': (
            ('数字文化', ('传播', '网络', '线上', '推广', '内容', '产品', 'IP', '平台')),
            ('网络', ('传播', '平台', '展览', '直播', '展播', '发布', '内容')),
            ('国际交流', ('数字', '线上', '网络', '平台', '云', '传播')),
            ('传播', ('线上', '网络', '平台', '展播', '直播')),
        ),
    },
}

# 普通文章的 evidence_snippet 可能只保留正文中的局部片段；仅补充这些
# 已明确指向技术、系统或数字应用的命中词，避免把“数字化”“科技创新”等
# 泛词重新带入方向组合判断。
CLASSIFICATION_HINT_KEYWORDS = {
    '人工智能', 'AI', '机器学习', '算法', '遥感', '三维扫描', '3D扫描', '三维建模',
    '三维数据', '三维数字化', '数字化建模', '数字人', '数字孪生', '科技考古', '空间信息', '数据集',
    '数据分析', '数据模型', '数据中台', '计算机视觉', '虚拟现实', 'VR', '增强现实', 'AR',
    '混合现实', '全息', '数字化展示', '数字化展陈', '数字展陈', '数字展馆', '数字展厅',
    '数字展览', '数字体验', '数字影像', '数字光影', '数字博物馆', '智慧博物馆', '智慧文博',
    '数字服务', '数字化服务', '智慧服务', '数字导览', '智慧导览', '云游', '线上服务',
    '数字档案', '数字资源', '数字资产', '数字平台', '数据平台', '数据库', '知识库',
    '数据资源', '数字出版', '数字化管理', '素材库', '电子档案', '资源库', '数字图谱',
    '知识图谱', '数字传播', '数字出海', '国际传播', '线上直播', '线上展播', '网络传播',
    '线上传播', '数字推广', '数字化保护', '文物数字化', '数字保护', '数字化采集',
    '数字采集', '数字回归', '数字化记录', '数字化存档', '数字化建档', '数字化测绘',
    '数字化测量', '数字化复原', '数字化修复', '数字化保存', '保护与数字化',
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


def contains_keyword(text, word):
    """Match Chinese phrases directly and Latin abbreviations by token boundary."""
    text = text or ''
    if word in LATIN_KEYWORDS:
        if word == '3D扫描':
            return bool(re.search(r'(?<![A-Za-z0-9])3D扫描', text, re.I))
        text = text.replace('３', '3').replace('Ｄ', 'D')
        return bool(re.search(r'(?<![A-Za-z0-9])' + re.escape(word) + r'(?![A-Za-z0-9])', text))
    return word in text


def keyword_matches(text):
    """Return all distinct configured keyword matches with strength metadata."""
    found = []
    for level, words in (('core', KEYWORDS_CORE), ('tech', KEYWORDS_TECH),
                         ('ext', KEYWORDS_EXT)):
        for word in words:
            if contains_keyword(text, word) and word not in [item['word'] for item in found]:
                found.append({'level': level, 'word': word,
                              'strength': 'weak' if word in WEAK_KEYWORDS else 'strong'})
    return found


def admission_for_record(title, body='', allow_body_only=False):
    """Apply the admission gate without letting topic rules admit records.

    Strong title signals admit directly. A weak title signal needs a strong
    signal in the same article body (or in the same digest item body).
    """
    title = title or ''
    body = body or ''
    title_matches = keyword_matches(title)
    body_matches = keyword_matches(body)
    strong_title = [item for item in title_matches if item['strength'] == 'strong']
    strong_body = [item for item in body_matches if item['strength'] == 'strong']
    weak_title = [item for item in title_matches if item['strength'] == 'weak']
    if strong_title:
        chosen = strong_title[0]
        reason = 'strong-title'
    elif (weak_title and strong_body) or (allow_body_only and strong_body):
        chosen = strong_body[0]
        reason = 'weak-title-plus-strong-body' if weak_title else 'strong-body'
    else:
        return None
    matches = []
    for item in title_matches + body_matches:
        if item['word'] not in [match['word'] for match in matches]:
            matches.append(item)
    return {
        'level': chosen['level'],
        'word': chosen['word'],
        'matched_keywords': [item['word'] for item in matches],
        'weak_keywords': [item['word'] for item in matches if item['strength'] == 'weak'],
        'strong_keywords': [item['word'] for item in matches if item['strength'] == 'strong'],
        'reason': reason,
        'evidence_snippet': evidence_snippet(body, [item['word'] for item in strong_body]),
    }


def match_keywords(title, body=''):
    """Backward-compatible (level, word) result using the new admission gate."""
    admission = admission_for_record(title, body)
    return (admission['level'], admission['word']) if admission else None


def classify_topics(title, level=''):
    """把已纳入趋势库的记录映射到行业方向，不改变关键词准入口径。"""
    text = title or ''
    return [name for name, _ in TOPIC_INFO if topic_match_details(text, TOPIC_RULES.get(name, {}))]


def topic_match_details(text, rule):
    """Return classification evidence without turning generic words into labels."""
    text = text or ''
    for word in rule.get('direct', ()):
        if contains_keyword(text, word):
            return True
    for word, contexts in rule.get('context', ()):
        if contains_keyword(text, word) and any(keyword_near(text, word, context) for context in contexts):
            return True
    return False


def keyword_positions(text, word):
    """Return match offsets using the same boundary rules as contains_keyword."""
    text = text or ''
    if word in LATIN_KEYWORDS:
        if word == '3D扫描':
            return [match.start() for match in re.finditer(r'(?<![A-Za-z0-9])3D扫描', text, re.I)]
        text = text.replace('３', '3').replace('Ｄ', 'D')
        pattern = r'(?<![A-Za-z0-9])' + re.escape(word) + r'(?![A-Za-z0-9])'
        return [match.start() for match in re.finditer(pattern, text, re.I)]
    positions = []
    start = 0
    while True:
        index = text.find(word, start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + max(1, len(word))


def keyword_near(text, first, second, max_gap=24):
    """Match a contextual pair only when the evidence is locally connected."""
    first_positions = keyword_positions(text, first)
    second_positions = keyword_positions(text, second)
    if not first_positions or not second_positions:
        return False
    return any(abs(left - right) <= max_gap for left in first_positions for right in second_positions)


def topics_for_record(record):
    """读取记录上的方向标签；兼容旧数据并在缺失时即时分类。"""
    topics = record.get('topics')
    if topics is not None:
        return topics
    return classify_topics(record.get('title', record.get('t', '')),
                           record.get('level', record.get('l', '')))


def topic_counts_for_records(records):
    """按内容条目统计各行业方向；同一条目同一方向只计一次。"""
    counts = defaultdict(int)
    for record in records:
        for topic in topics_for_record(record):
            counts[topic] += 1
    return {name: counts[name] for name, _ in TOPIC_INFO}


def record_match_text(record):
    """Return only the text belonging to this trend record.

    Digest records carry a source-page title plus one separately parsed item
    block.  Classification and filtering must use that item's own title/body,
    never the neighbouring digest items.
    """
    hints = [word for word in record.get('matched_keywords', [])
             if word in CLASSIFICATION_HINT_KEYWORDS]
    if record.get('from_digest'):
        return ' '.join(filter(None, [
            record.get('digest_title', record.get('item_title', '')),
            record.get('digest_body', ''),
            record.get('evidence_snippet', ''),
            ' '.join(hints),
        ]))
    return ' '.join(filter(None, [
        record.get('title', record.get('t', '')),
        record.get('evidence_snippet', ''),
        ' '.join(hints),
    ]))


def all_keyword_matches(text):
    """Return every distinct configured keyword found in *text*."""
    return keyword_matches(text)


def evidence_snippet(body, keywords, limit=180):
    """Keep a short body-only excerpt containing an actual matched keyword."""
    text = ' '.join((body or '').split())
    if not text:
        return ''
    def match_index(word):
        if word in LATIN_KEYWORDS:
            if word == '3D扫描':
                found = re.search(r'(?<![A-Za-z0-9])3D扫描', text, re.I)
            else:
                found = re.search(r'(?<![A-Za-z0-9])' + re.escape(word) + r'(?![A-Za-z0-9])', text)
            return found.start() if found else -1
        return text.find(word)
    index = next((match_index(word) for word in keywords if match_index(word) >= 0), -1)
    if index < 0:
        return ''
    if len(text) <= limit:
        return text
    start = max(0, index - limit // 3)
    end = min(len(text), start + limit)
    start = max(0, end - limit)
    prefix = '…' if start else ''
    suffix = '…' if end < len(text) else ''
    return prefix + text[start:end] + suffix


def html_to_text(html):
    """Small, dependency-free body extractor for weak title candidates."""
    text = re.sub(r'<script[\s\S]*?</script>', ' ', html or '', flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', ' ', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'&(?:nbsp|amp|lt|gt|quot|#39);', ' ', text, flags=re.I)
    return ' '.join(text.split())


def enrich_weak_title_candidate(item):
    """Fetch one ordinary article body only when its title is weak-only."""
    title_matches = keyword_matches(item.get('title', ''))
    if not any(match['strength'] == 'weak' for match in title_matches):
        return admission_for_record(item.get('title', ''))
    body_html = fetch(BASE + item['url'])
    body = html_to_text(body_html) if body_html else ''
    admission = admission_for_record(item.get('title', ''), body)
    if admission:
        admission['body'] = body
    return admission


def _digest_identity(title):
    normalized = re.sub(r'\s+', '', title or '')
    normalized = re.sub(r'[「」“”"‘’‘’、，。；：！？（）()【】\[\]《》〈〉—_\-]', '', normalized)
    return hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:12]


def content_item_entities(records):
    """Build the canonical content-item layer from matched records.

    A standalone article uses its source URL as identity.  A digest item uses
    the source URL plus a normalized digest-title hash; repeated same-title
    items receive a deterministic occurrence suffix.  Keyword hits therefore
    enrich one item instead of creating extra items.
    """
    counts = defaultdict(int)
    entities = []
    for record in records:
        url = record.get('url', record.get('u', ''))
        is_digest = bool(record.get('from_digest'))
        digest_title = record.get('digest_title', '') if is_digest else ''
        title = digest_title or record.get('title', record.get('t', ''))
        item_date = record.get('date', record.get('d', ''))
        if hasattr(item_date, 'isoformat'):
            item_date = item_date.isoformat()
        base_key = (url, _digest_identity(digest_title)) if is_digest else (url, '')
        counts[base_key] += 1
        suffix = f'-{counts[base_key]}' if counts[base_key] > 1 else ''
        item_id = (f'{url}#digest-{base_key[1]}{suffix}' if is_digest
                   else url or f'article-{_digest_identity(title)}')
        entities.append({
            'content_item_id': item_id,
            'display_title': title,
            'source_url': url,
            'source_page_title': record.get('source_page_title') or record.get('title', record.get('t', '')),
            'digest_title': digest_title,
            'date': item_date,
            'level': record.get('level', record.get('l', '')),
            'matched_keywords': list(record.get('matched_keywords') or []),
            'evidence_snippet': record.get('evidence_snippet', ''),
            'topics': list(topics_for_record(record)),
            'is_digest_item': is_digest,
        })
    return entities


def source_page_entities(content_items):
    """Build source-page entities without inheriting child-item topics."""
    by_url = {}
    for item in content_items:
        url = item.get('source_url', '')
        key = url or f"{item.get('source_page_title', '')}|{item.get('date', '')}"
        if not key:
            continue
        if key not in by_url:
            by_url[key] = {
                'source_page_id': url or key,
                'source_url': url,
                'source_page_title': item.get('source_page_title', ''),
                'date': item.get('date', ''),
                'is_digest_page': bool(item.get('is_digest_item')),
                'content_item_ids': [],
                'content_item_count': 0,
                'digest_content_item_count': 0,
                'standalone_content_item_count': 0,
            }
        page = by_url[key]
        page['content_item_ids'].append(item['content_item_id'])
        page['content_item_count'] += 1
        if item.get('is_digest_item'):
            page['is_digest_page'] = True
            page['digest_content_item_count'] += 1
        else:
            page['standalone_content_item_count'] += 1
    return sorted(by_url.values(), key=lambda item: (item.get('date', ''), item.get('source_url', '')), reverse=True)


def article_entities(records):
    """Backward-compatible alias returning source-page entities."""
    return source_page_entities(content_item_entities(records))


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


def extract_digest_items(html, url, pub_date, source_page_title=''):
    """Extract and match each NCHA digest item inside its own HTML block.

    A bold paragraph starts a new item; following paragraphs belong only to
    that item until the next bold heading or region label. This prevents a
    keyword in one item from being attributed to a neighbouring item.
    """
    region_names = set(['北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江',
                        '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
                        '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州',
                        '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆'])
    parser = DigestHTMLParser()
    parser.feed(html or '')
    blocks = []
    current = None
    for paragraph in parser.paragraphs:
        text = paragraph['text']
        strong = paragraph['strong']
        if text in region_names:
            if current:
                blocks.append(current)
            current = None
            continue
        is_heading = bool(strong) and strong == text and 4 <= len(text) <= 100
        if is_heading:
            if current:
                blocks.append(current)
            current = {'title': text, 'body': []}
        elif current:
            current['body'].append(text)
    if current:
        blocks.append(current)

    found = []
    for block in blocks:
        body = ' '.join(block['body']).strip()
        admission = admission_for_record(block['title'], body, allow_body_only=True)
        if not admission:
            continue
        found.append({
            'title': source_page_title or url.rsplit('/', 1)[-1],
            'source_page_title': source_page_title,
            'digest_title': block['title'],
            'digest_body': body,
            'date': pub_date,
            'url': url,
            'level': admission['level'],
            'word': admission['word'],
            'matched_keywords': admission['matched_keywords'],
            'admission_reason': admission['reason'],
            'evidence_snippet': admission['evidence_snippet'],
            'from_digest': True,
        })
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
        for item in extract_digest_items(body, dg['url'], dg['date'], dg['title']):
            extra.append(item)
        if (i + 1) % 25 == 0:
            print(f'    进度 {i+1}/{len(digests)}, 已提取 {len(extra)} 条')
        time.sleep(0.15)
    return extra, failed


def dedup_and_filter(items):
    """Deduplicate source records and apply the same admission gate again."""
    seen = {}
    for it in items:
        key = ((it.get('url', ''), it.get('digest_title', ''))
               if it.get('from_digest') else (it.get('url', ''), it.get('title', '')))
        if key not in seen or it['date'] < seen[key]['date']:
            seen[key] = it
    keep = []
    for v in seen.values():
        title = v.get('digest_title') if v.get('from_digest') else v.get('title', '')
        body = v.get('digest_body', '') if v.get('from_digest') else v.get('body', '')
        admission = admission_for_record(title, body, allow_body_only=v.get('from_digest', False))
        if admission:
            v['level'] = admission['level']
            v['word'] = admission['word']
            v['matched_keywords'] = admission['matched_keywords']
            v['admission_reason'] = admission['reason']
            if admission.get('evidence_snippet'):
                v['evidence_snippet'] = admission['evidence_snippet']
            keep.append(v)
    keep.sort(key=lambda x: x['date'])
    return keep


def aggregate(items, source_items):
    """生成趋势聚合数据。

    趋势数量以 content item 为单位；source_page_count 和 share 仍然是
    来源页面层指标，避免把两个统计单位相除。
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
        item_date = it['date'] if hasattr(it['date'], 'strftime') else datetime.fromisoformat(it['date']).date()
        ym = item_date.strftime('%Y-%m')
        iso = item_date.isocalendar()
        wk = f"{iso.year}-W{iso.week:02d}"
        year = str(item_date.year)
        by_month[ym].append(it)
        by_week[wk].append(it)
        by_day[item_date.isoformat()].append(it)
        by_year[year].append(it)
    for it in source_items:
        source_date = it['date'] if hasattr(it['date'], 'strftime') else datetime.fromisoformat(it['date']).date()
        ym = source_date.strftime('%Y-%m')
        iso = source_date.isocalendar()
        wk = f"{iso.year}-W{iso.week:02d}"
        year = str(source_date.year)
        source_by_month[ym].append(it)
        source_by_week[wk].append(it)
        source_by_day[source_date.isoformat()].append(it)
        source_by_year[year].append(it)

    def to_series(group, source_group, include_items=True):
        keys = sorted(set(group) | set(source_group))
        out = []
        for k in keys:
            v = group.get(k, [])
            source_v = source_group.get(k, [])
            source_page_count = len({x.get('source_url', x.get('url', '')) for x in v if x.get('source_url', x.get('url', ''))})
            source_unique_count = len({x['url'] for x in source_v})
            share = round(source_page_count / source_unique_count * 100, 2) if source_unique_count else 0
            row = {'key': k, 'count': len(v), 'content_item_count': len(v),
                   'source_page_count': source_page_count, 'unique_count': source_page_count,
                   'source_count': len(source_v),
                   'source_unique_count': source_unique_count,
                   'share': share}
            if include_items:
                row['items'] = [
                    {'content_item_id': x['content_item_id'],
                     'display_title': x['display_title'],
                     'source_url': x['source_url'],
                     'source_page_title': x['source_page_title'],
                     'digest_title': x['digest_title'],
                     'is_digest_item': x['is_digest_item'],
                     'evidence_snippet': x['evidence_snippet'],
                     'matched_keywords': x['matched_keywords'],
                     'topics': x['topics'],
                     'd': x['date'], 'u': x['source_url'], 't': x['display_title'], 'l': x['level']}
                    for x in v
                ]
            out.append(row)
        return out

    return {
        'by_month': to_series(by_month, source_by_month),
        'by_week': to_series(by_week, source_by_week),
        'by_day': to_series(by_day, source_by_day),
        'by_year': to_series(by_year, source_by_year, include_items=False),
    }


def aggregate_existing_source_maps(content_items, old_data):
    """Rebuild content-item series while preserving stored source-page denominators."""
    groups = {name: defaultdict(list) for name in ('by_month', 'by_week', 'by_day', 'by_year')}
    for item in content_items:
        item_date = item['date']
        groups['by_month'][item_date[:7]].append(item)
        parsed = datetime.fromisoformat(item_date).date()
        iso = parsed.isocalendar()
        groups['by_week'][f'{iso.year}-W{iso.week:02d}'].append(item)
        groups['by_day'][item_date].append(item)
        groups['by_year'][item_date[:4]].append(item)

    def row_items(values):
        return [
            {'content_item_id': x['content_item_id'], 'display_title': x['display_title'],
             'source_url': x['source_url'], 'source_page_title': x['source_page_title'],
             'digest_title': x['digest_title'], 'is_digest_item': x['is_digest_item'],
             'evidence_snippet': x['evidence_snippet'], 'matched_keywords': x['matched_keywords'],
             'topics': x['topics'], 'd': x['date'], 'u': x['source_url'],
             't': x['display_title'], 'l': x['level']}
            for x in values
        ]

    def rebuild(name, include_items=True):
        old_rows = {row.get('key'): row for row in old_data.get(name, [])}
        current = groups[name]
        out = []
        for key in sorted(set(current) | set(old_rows)):
            values = current.get(key, [])
            old = old_rows.get(key, {})
            source_page_count = len({x['source_url'] for x in values if x['source_url']})
            source_unique_count = old.get('source_unique_count', 0) or 0
            row = {
                'key': key,
                'count': len(values),
                'content_item_count': len(values),
                'source_page_count': source_page_count,
                'unique_count': source_page_count,
                'source_count': old.get('source_count', 0) or 0,
                'source_unique_count': source_unique_count,
                'share': round(source_page_count / source_unique_count * 100, 2) if source_unique_count else 0,
            }
            if include_items:
                row['items'] = row_items(values)
            out.append(row)
        return out

    return {
        'by_month': rebuild('by_month'),
        'by_week': rebuild('by_week'),
        'by_day': rebuild('by_day'),
        'by_year': rebuild('by_year', include_items=False),
    }


class IncrementalScanError(RuntimeError):
    """A typed failure so the daily coverage ledger never says no_update."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _parse_source_page_records(html, start_date, end_date):
    """Parse one recent NCHA pagination response without doing a full crawl."""
    records = re.findall(r"<record><!\[CDATA\[(.*?)\]\]></record>", html or '', re.S)
    if not records:
        raise IncrementalScanError('parse_failed', '国家文物局分页响应没有可解析记录')
    items = []
    older_than_window = False
    for record in records:
        m_title = re.search(r"href='(/art/\d{4}/\d+/\d+/art_\d+_\d+\.html)'\s+title='([^']*)'", record)
        m_date = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', record)
        if not m_title or not m_date:
            continue
        try:
            item_date = datetime.strptime(m_date.group(1), '%Y-%m-%d').date()
        except ValueError:
            continue
        if item_date < start_date:
            older_than_window = True
        if start_date <= item_date <= end_date:
            items.append({'date': item_date, 'title': m_title.group(2), 'url': m_title.group(1)})
    return items, older_than_window


def fetch_recent_titles(end_date, window_days=INCREMENTAL_WINDOW_DAYS,
                        max_pages=INCREMENTAL_MAX_PAGES):
    """Scan only the recent NCHA pages needed by the daily incremental mode."""
    start_date = end_date - timedelta(days=max(1, window_days) - 1)
    items = []
    pages_checked = 0
    for page in range(1, max_pages + 1):
        pages_checked += 1
        html = fetch(PROXY_TMPL.format(p=page))
        if not html:
            raise IncrementalScanError('fetch_failed', f'国家文物局近期分页第 {page} 页抓取失败')
        page_items, older_than_window = _parse_source_page_records(html, start_date, end_date)
        items.extend(page_items)
        if older_than_window:
            break
    unique = {}
    for item in items:
        unique[item['url']] = item
    return sorted(unique.values(), key=lambda item: (item['date'], item['url']), reverse=True), pages_checked


def _data_source_end(data):
    """Return the last source-feed date represented by the stored denominator."""
    candidates = []
    for row in data.get('by_day', []) or []:
        if row.get('key'):
            try:
                candidates.append(date.fromisoformat(row['key']))
            except ValueError:
                pass
    if candidates:
        return max(candidates)
    try:
        return date.fromisoformat(data.get('range', {}).get('end', ''))
    except ValueError:
        return START_DATE - timedelta(days=1)


def _source_bucket_key(item_date, granularity):
    if granularity == 'month':
        return item_date.strftime('%Y-%m')
    if granularity == 'week':
        iso = item_date.isocalendar()
        return f'{iso.year}-W{iso.week:02d}'
    if granularity == 'year':
        return str(item_date.year)
    return item_date.isoformat()


def _apply_source_denominator_updates(aggregates, new_source_items):
    """Extend existing page-level denominators with newly scanned source pages."""
    unique_items = {}
    for item in new_source_items:
        unique_items[item['url']] = item
    for granularity, field in (
        ('month', 'by_month'), ('week', 'by_week'),
        ('day', 'by_day'), ('year', 'by_year'),
    ):
        rows = {row.get('key'): row for row in aggregates.get(field, [])}
        for item in unique_items.values():
            item_date = item['date'] if hasattr(item['date'], 'strftime') else date.fromisoformat(item['date'])
            key = _source_bucket_key(item_date, granularity)
            row = rows.get(key)
            if row is None:
                row = {
                    'key': key, 'count': 0, 'content_item_count': 0,
                    'source_page_count': 0, 'unique_count': 0,
                    'source_count': 0, 'source_unique_count': 0, 'share': 0,
                }
                if granularity != 'year':
                    row['items'] = []
                rows[key] = row
            row['source_count'] = row.get('source_count', 0) + 1
            row['source_unique_count'] = row.get('source_unique_count', 0) + 1
        for row in rows.values():
            denominator = row.get('source_unique_count', 0)
            row['share'] = round(row.get('source_page_count', 0) / denominator * 100, 2) if denominator else 0
        aggregates[field] = [rows[key] for key in sorted(rows) if key]


def _compact_content_item(entity, record):
    """Keep the legacy items array compatible while content_items remains canonical."""
    return {
        'content_item_id': entity['content_item_id'],
        'display_title': entity['display_title'],
        'source_url': entity['source_url'],
        'source_page_title': entity['source_page_title'],
        'is_digest_item': entity['is_digest_item'],
        't': entity['display_title'],
        'd': entity['date'],
        'u': entity['source_url'],
        'l': entity['level'],
        'w': record.get('word', ''),
        'topics': entity['topics'],
        'matched_keywords': entity['matched_keywords'],
        'from_digest': entity['is_digest_item'],
        'digest_title': entity['digest_title'],
        'evidence_snippet': entity['evidence_snippet'],
        'admission_reason': record.get('admission_reason', ''),
    }


def merge_incremental_data(old_data, new_records, new_source_items, end_date,
                           checked_at, digest_extra_count=0,
                           digest_article_count=0, title_hit_count=0):
    """Merge newly discovered records while preserving source/content semantics."""
    old_content = list(old_data.get('content_items') or [])
    if not old_content:
        old_content = content_item_entities(old_data.get('items') or [])
    prepared = dedup_and_filter([dict(item) for item in new_records])
    for item in prepared:
        item['topics'] = classify_topics(record_match_text(item), item.get('level', ''))
    proposed = content_item_entities(prepared)
    existing_ids = {item.get('content_item_id') for item in old_content}
    fresh = []
    duplicate_items = 0
    for entity, record in zip(proposed, prepared):
        if entity['content_item_id'] in existing_ids:
            duplicate_items += 1
            continue
        existing_ids.add(entity['content_item_id'])
        fresh.append(entity)
    content_items = old_content + fresh
    source_pages = source_page_entities(content_items)
    aggregates = aggregate_existing_source_maps(content_items, old_data)
    _apply_source_denominator_updates(aggregates, new_source_items)

    data = copy.deepcopy(old_data)
    data['generated'] = checked_at[:10]
    data['range'] = dict(data.get('range') or {})
    data['range']['start'] = data['range'].get('start') or START_DATE.isoformat()
    old_end = data['range'].get('end', '')
    data['range']['end'] = max(old_end, end_date.isoformat())
    old_stats = dict(data.get('stats') or {})
    source_urls = {item['url'] for item in new_source_items if item.get('url')}
    source_total = old_stats.get('source_article_total', 0) + len(source_urls)
    source_unique = old_stats.get('source_unique_pages', 0) + len(source_urls)
    levels = defaultdict(int)
    for item in content_items:
        levels[item.get('level', '')] += 1
    stats = {
        **old_stats,
        'total': len(content_items),
        'matched_record_count': len(content_items),
        'content_item_count': len(content_items),
        'digest_content_item_count': sum(1 for item in content_items if item.get('is_digest_item')),
        'standalone_content_item_count': sum(1 for item in content_items if not item.get('is_digest_item')),
        'title_hit': old_stats.get('title_hit', 0) + title_hit_count,
        'digest_extra': old_stats.get('digest_extra', 0) + digest_extra_count,
        'levels': {key: value for key, value in sorted(levels.items()) if key},
        'digest_articles': old_stats.get('digest_articles', 0) + digest_article_count,
        'digital_source_pages': len(source_pages),
        'digest_source_pages': sum(1 for item in source_pages if item.get('is_digest_page')),
        'standalone_source_pages': sum(1 for item in source_pages if not item.get('is_digest_page')),
        'unique_source_pages': len(source_pages),
        'source_article_total': source_total,
        'source_unique_pages': source_unique,
        'overall_share': round(len(source_pages) / source_unique * 100, 2) if source_unique else 0,
        'topic_content_item_counts': topic_counts_for_records(content_items),
        'topic_unique_counts': topic_counts_for_records(content_items),
        'classified_content_item_count': sum(1 for item in content_items if item.get('topics')),
        'unclassified_content_item_count': sum(1 for item in content_items if not item.get('topics')),
    }
    stats['classified_article_count'] = stats['classified_content_item_count']
    stats['unclassified_article_count'] = stats['unclassified_content_item_count']
    data['stats'] = stats
    data['content_items'] = content_items
    data['source_pages'] = source_pages
    old_legacy = {}
    old_legacy_items = data.get('items') or []
    if len(old_legacy_items) == len(old_content):
        # Older snapshots did not carry content_item_id in their compatibility
        # array; its order still matches the canonical content_items array.
        old_legacy.update({entity['content_item_id']: legacy
                           for entity, legacy in zip(old_content, old_legacy_items)})
    else:
        old_legacy.update({item.get('content_item_id'): item for item in old_legacy_items
                           if item.get('content_item_id')})
    for entity in old_content:
        old_legacy.setdefault(entity['content_item_id'], _compact_content_item(entity, {}))
    for entity, record in zip(proposed, prepared):
        old_legacy.setdefault(entity['content_item_id'], _compact_content_item(entity, record))
    data['items'] = [old_legacy[item['content_item_id']] for item in content_items]
    data.update(aggregates)
    quality = data.setdefault('quality', {})
    quality['incremental_update_mode'] = 'recent source-page scan'
    quality['last_incremental_scan_at'] = checked_at
    quality['last_incremental_scan_window'] = {
        'start': (end_date - timedelta(days=INCREMENTAL_WINDOW_DAYS - 1)).isoformat(),
        'end': end_date.isoformat(),
    }
    return data, len(fresh), duplicate_items


def _write_incremental_coverage(required_date, checked_at, *, window_start,
                                 source_pages_checked=0, source_pages_new=0,
                                 content_items_new=0, duplicates_skipped=0,
                                 fetch_failed=0, parse_failed=0, status='not_run',
                                 pages_checked=0, note=''):
    os.makedirs(DIGITAL_MONITOR_DIR, exist_ok=True)
    payload = {
        'version': 1,
        'date': required_date.isoformat(),
        'checkedAt': checked_at,
        'scanMode': 'incremental',
        'scanWindow': {'start': window_start.isoformat(), 'end': required_date.isoformat()},
        'sourceColumn': 722,
        'paginationPagesChecked': pages_checked,
        'sourcePagesChecked': source_pages_checked,
        'sourcePagesNew': source_pages_new,
        'contentItemsNew': content_items_new,
        'duplicatesSkipped': duplicates_skipped,
        'fetchFailed': fetch_failed,
        'parseFailed': parse_failed,
        'status': status,
        'note': note,
    }
    path = os.path.join(DIGITAL_MONITOR_DIR, f'{required_date.isoformat()}.json')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    return payload


def run_incremental(end_date=None, window_days=INCREMENTAL_WINDOW_DAYS):
    """Scan recent NCHA source pages and merge only new digital content."""
    end_date = end_date or date.today()
    checked_at = datetime.now(CN_TZ).isoformat(timespec='seconds')
    window_days = max(1, int(window_days))
    window_start = end_date - timedelta(days=window_days - 1)
    try:
        recent_items, pages_checked = fetch_recent_titles(end_date, window_days)
    except IncrementalScanError as exc:
        payload = _write_incremental_coverage(
            end_date, checked_at, window_start=window_start,
            fetch_failed=int(exc.kind == 'fetch_failed'),
            parse_failed=int(exc.kind == 'parse_failed'),
            status=exc.kind, note=str(exc),
        )
        raise
    if not os.path.exists(DATA_PATH):
        payload = _write_incremental_coverage(
            end_date, checked_at, window_start=window_start,
            source_pages_checked=len(recent_items), pages_checked=pages_checked,
            status='parse_failed', note='缺少已有 digital-data.json，无法安全执行增量合并',
            parse_failed=1,
        )
        raise IncrementalScanError('parse_failed', '缺少已有 digital-data.json，无法安全执行增量合并')
    with open(DATA_PATH, encoding='utf-8') as handle:
        old_data = json.load(handle)
    old_source_pages = {
        item.get('source_url') or item.get('source_page_id')
        for item in old_data.get('source_pages', [])
    }
    old_source_end = _data_source_end(old_data)
    source_urls = {item['url'] for item in recent_items}
    new_page_candidates = [item for item in recent_items if item['url'] not in old_source_pages]
    new_source_items = []
    seen_source_urls = set()
    for item in recent_items:
        if item['date'] > old_source_end and item['url'] not in seen_source_urls:
            new_source_items.append(item)
            seen_source_urls.add(item['url'])

    matched_records = []
    digest_extra_count = 0
    digest_article_count = sum(1 for item in new_source_items if DIGEST_PATTERN.search(item['title']))
    title_hit_count = 0
    fetch_failed = 0
    parse_failed = 0
    for item in new_page_candidates:
        if DIGEST_PATTERN.search(item['title']):
            body_html = fetch(BASE + item['url'])
            if not body_html:
                fetch_failed += 1
                continue
            try:
                extracted = extract_digest_items(body_html, item['url'], item['date'], item['title'])
            except Exception:
                parse_failed += 1
                continue
            digest_extra_count += len(extracted)
            matched_records.extend(extracted)
            continue
        title_matches = keyword_matches(item['title'])
        if not title_matches:
            continue
        title_hit_count += 1
        if any(match['strength'] == 'weak' for match in title_matches) and not any(
                match['strength'] == 'strong' for match in title_matches):
            body_html = fetch(BASE + item['url'])
            if not body_html:
                fetch_failed += 1
                continue
            body = html_to_text(body_html)
            admission = admission_for_record(item['title'], body)
            if admission:
                admission['body'] = body
        else:
            admission = admission_for_record(item['title'])
        if admission:
            item = dict(item)
            item['level'] = admission['level']
            item['word'] = admission['word']
            item['matched_keywords'] = admission['matched_keywords']
            item['admission_reason'] = admission['reason']
            item['evidence_snippet'] = admission.get('evidence_snippet', '')
            item['from_digest'] = False
            matched_records.append(item)

    data, content_items_new, duplicate_items = merge_incremental_data(
        old_data, matched_records, new_source_items, end_date, checked_at,
        digest_extra_count=digest_extra_count,
        digest_article_count=digest_article_count,
        title_hit_count=title_hit_count,
    )
    source_pages_new = len({item['source_url'] for item in data['content_items'][-content_items_new:]}) if content_items_new else 0
    known_recent_pages = len(source_urls & old_source_pages)
    duplicates_skipped = known_recent_pages + duplicate_items
    if fetch_failed:
        status = 'fetch_failed'
    elif parse_failed:
        status = 'parse_failed'
    elif source_pages_new or content_items_new:
        status = 'scan_success_with_update'
    else:
        status = 'scan_success_no_update'
    note = '近期分页扫描完成；未发现新的数字化来源页或内容条目。' if status == 'scan_success_no_update' else ''
    payload = _write_incremental_coverage(
        end_date, checked_at, window_start=window_start,
        source_pages_checked=len(recent_items), source_pages_new=source_pages_new,
        content_items_new=content_items_new, duplicates_skipped=duplicates_skipped,
        fetch_failed=fetch_failed, parse_failed=parse_failed, status=status,
        pages_checked=pages_checked, note=note,
    )
    with open(DATA_PATH, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    return data, payload


def save_data(items, extra, digest_count, digest_failed, levels, source_items):
    items = dedup_and_filter(items)
    for it in items:
        it['topics'] = classify_topics(record_match_text(it), it.get('level', ''))
    levels = defaultdict(int)
    for it in items:
        levels[it['level']] += 1
    content_items = content_item_entities(items)
    source_pages = source_page_entities(content_items)
    agg = aggregate(content_items, source_items)
    extra_n = len(extra) if isinstance(extra, (list, tuple)) else extra
    source_page_n = len(source_pages)
    source_unique_urls = len({x['url'] for x in source_items})
    data = {
        'generated': date.today().isoformat(),
        'source': '国家文物局官网「文物新闻」栏目',
        'range': {'start': START_DATE.isoformat(), 'end': END_DATE.isoformat()},
        'stats': {
            'total': len(items),
            'matched_record_count': len(items),
            'content_item_count': len(content_items),
            'digest_content_item_count': sum(1 for x in content_items if x['is_digest_item']),
            'standalone_content_item_count': sum(1 for x in content_items if not x['is_digest_item']),
            'title_hit': sum(1 for x in items if match_keywords(x['title'])),
            'digest_extra': extra_n,
            'levels': {k: v for k, v in sorted(levels.items())},
            'digest_articles': digest_count,
            'digital_source_pages': source_page_n,
            'digest_source_pages': sum(1 for x in source_pages if x['is_digest_page']),
            'standalone_source_pages': sum(1 for x in source_pages if not x['is_digest_page']),
            'unique_source_pages': source_page_n,
            'source_article_total': len(source_items),
            'source_unique_pages': source_unique_urls,
            'overall_share': round(source_page_n / source_unique_urls * 100, 2) if source_unique_urls else 0,
            'topic_content_item_counts': topic_counts_for_records(content_items),
            'topic_unique_counts': topic_counts_for_records(content_items),
            'classified_content_item_count': sum(1 for item in content_items if item['topics']),
            'unclassified_content_item_count': sum(1 for item in content_items if not item['topics']),
            'classified_article_count': sum(1 for item in content_items if item['topics']),
            'unclassified_article_count': sum(1 for item in content_items if not item['topics']),
        },
        'quality': {
            'source_fetch_complete': True,
            'digest_fetch_failed': digest_failed,
            'note': '关键词只负责纳入趋势库；content_items 是真正的数字化内容条目，按 source_url + digest_title（普通文章仅 source_url）建立身份；source_pages 是来源页层。六方向、趋势数量按 content_items，overall_share 按数字化 source_pages / 同期全部文物新闻 source_pages 计算。',
        },
        'topic_info': [{'name': name, 'description': description} for name, description in TOPIC_INFO],
        'items': [
            {'content_item_id': content_items[index]['content_item_id'],
             'display_title': content_items[index]['display_title'],
             'source_url': content_items[index]['source_url'],
             'source_page_title': content_items[index]['source_page_title'],
             'is_digest_item': content_items[index]['is_digest_item'],
             't': x['title'], 'd': x['date'].isoformat(), 'u': x['url'], 'l': x['level'],
             'w': x.get('word', ''), 'topics': x.get('topics', []),
             'matched_keywords': x.get('matched_keywords', []),
             'from_digest': bool(x.get('from_digest')),
             'digest_title': x.get('digest_title', ''),
             'evidence_snippet': x.get('evidence_snippet', ''),
             'admission_reason': x.get('admission_reason', '')} for index, x in enumerate(items)
        ],
        'content_items': content_items,
        'source_pages': source_pages,
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
        item_record = {
            'title': item.get('t', ''),
            'from_digest': item.get('from_digest', False),
            'digest_title': item.get('digest_title', ''),
            'evidence_snippet': item.get('evidence_snippet', ''),
            'matched_keywords': item.get('matched_keywords', []),
        }
        item['topics'] = classify_topics(record_match_text(item_record), item.get('l', ''))

    stats = data.setdefault('stats', {})
    content_items = content_item_entities(items)
    source_pages = source_page_entities(content_items)
    data.pop('articles', None)
    data['content_items'] = content_items
    data['source_pages'] = source_pages
    data.update(aggregate_existing_source_maps(content_items, data))
    source_page_n = len(source_pages)
    stats['matched_record_count'] = len(items)
    stats['content_item_count'] = len(content_items)
    stats['digest_content_item_count'] = sum(1 for x in content_items if x['is_digest_item'])
    stats['standalone_content_item_count'] = sum(1 for x in content_items if not x['is_digest_item'])
    stats['digital_source_pages'] = source_page_n
    stats['digest_source_pages'] = sum(1 for x in source_pages if x['is_digest_page'])
    stats['standalone_source_pages'] = sum(1 for x in source_pages if not x['is_digest_page'])
    stats['unique_source_pages'] = source_page_n
    stats['overall_share'] = round(source_page_n / stats.get('source_unique_pages', 0) * 100, 2) if stats.get('source_unique_pages') else 0
    stats['topic_content_item_counts'] = topic_counts_for_records(content_items)
    stats['topic_unique_counts'] = topic_counts_for_records(content_items)
    stats['classified_content_item_count'] = sum(1 for item in content_items if item['topics'])
    stats['unclassified_content_item_count'] = sum(1 for item in content_items if not item['topics'])
    stats['classified_article_count'] = stats['classified_content_item_count']
    stats['unclassified_article_count'] = stats['unclassified_content_item_count']
    data['topic_info'] = [{'name': name, 'description': description}
                          for name, description in TOPIC_INFO]
    quality = data.setdefault('quality', {})
    quality['topic_taxonomy'] = '六类行业方向和趋势按 content_items 统计；source_pages 仅用于来源页和 page-level 占比；同一摘编父页的不同条目不会继承彼此方向。'

    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def main(args=None):
    """Refresh source data in maintenance or daily incremental mode.

    ``--incremental`` scans only recent source pages and writes a daily coverage
    ledger.  ``--force`` remains the explicit full-crawl maintenance mode;
    ``--build-only`` only rebuilds the page from existing data.
    """
    raw_args = list(sys.argv[1:] if args is None else args)
    args = set(raw_args)
    force = '--force' in args
    build_only = '--build-only' in args
    incremental = '--incremental' in args
    relabel_only = '--relabel-only' in args
    target_date = date.today()
    if '--date' in args:
        try:
            target_date = date.fromisoformat(raw_args[raw_args.index('--date') + 1])
        except (ValueError, IndexError):
            raise ValueError('--date must be followed by YYYY-MM-DD')
    if incremental:
        print(f'=== 数字趋势每日增量扫描: {target_date.isoformat()} ===')
        data, coverage = run_incremental(target_date)
        print(
            f"扫描来源页 {coverage['sourcePagesChecked']} 个，新增来源页 "
            f"{coverage['sourcePagesNew']} 个，新增内容条目 {coverage['contentItemsNew']} 个，"
            f"重复跳过 {coverage['duplicatesSkipped']} 个，状态 {coverage['status']}"
        )
        print(f'数据已更新: {DATA_PATH}')
        print('=== 生成趋势页面 ===')
        import build_digital_page
        build_digital_page.build_page(HTML_PATH, DATA_PATH)
        print(f'页面已生成: {HTML_PATH}')
        return
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
        weak_title_candidates = 0
        weak_title_failed = 0
        for it in all_items:
            title_matches = keyword_matches(it['title'])
            if not title_matches:
                continue
            if any(match['strength'] == 'weak' for match in title_matches) and not any(
                    match['strength'] == 'strong' for match in title_matches):
                weak_title_candidates += 1
                admission = enrich_weak_title_candidate(it)
            else:
                admission = admission_for_record(it['title'])
            if admission:
                it['level'], it['word'] = admission['level'], admission['word']
                it['matched_keywords'] = admission['matched_keywords']
                it['admission_reason'] = admission['reason']
                if admission.get('body'):
                    # Keep the fetched body in memory for the final quality
                    # gate; it is intentionally not written into JSON.
                    it['body'] = admission['body']
                if admission.get('evidence_snippet'):
                    it['evidence_snippet'] = admission['evidence_snippet']
                it['from_digest'] = False
                hit.append(it)
                levels[admission['level']] += 1
            elif title_matches:
                weak_title_failed += 1
        print(f'标题候选: {len(hit) + weak_title_failed} 条,弱词单独候选 {weak_title_candidates} 条,'
              f'弱词无第二数字信号剔除 {weak_title_failed} 条')
        print(f'标题准入: {len(hit)} 条 (核心 {levels["core"]} / 技术 {levels["tech"]} / 扩展 {levels["ext"]})')

        print('=== 步骤3: 摘编正文补充提取 ===')
        extra, digest_failed = fetch_digest_bodies(all_items)
        # 普通文章按原文 URL 去重；摘编按 source page + 小条目去重，
        # 防止不同小条目因共享摘编 URL 被错误合并。
        seen_keys = set((it.get('url', ''), it.get('digest_title', ''))
                        if it.get('from_digest') else (it.get('url', ''), it.get('title', ''))
                        for it in hit)
        digest_count = sum(1 for it in all_items if DIGEST_PATTERN.search(it['title']))
        added = 0
        for x in extra:
            key = (x.get('url', ''), x.get('digest_title', ''))
            if key not in seen_keys:
                seen_keys.add(key)
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

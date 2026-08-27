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
            print(f'  [warn] page {page} 抓取失败,停止翻页')
            break
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
                # 已越过起点,收集完本页后停止
                page_items.append({'date': d, 'title': title, 'url': url})
                items.extend(page_items)
                print(f'  [info] 第{page}页出现 {d} 早于起点,抓取结束')
                return items
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
    print(f'  摘编类文章 {len(digests)} 篇,开始抓正文提取数字化条目...')
    for i, dg in enumerate(digests):
        body = fetch(BASE + dg['url'])
        if not body:
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
    return extra


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


def aggregate(items):
    """生成 月/周/天 三套粒度聚合数据。items 为已匹配命中列表(含 date)。"""
    by_month = defaultdict(list)
    by_week = defaultdict(list)
    by_day = defaultdict(list)
    for it in items:
        ym = it['date'].strftime('%Y-%m')
        iso = it['date'].isocalendar()
        wk = f"{it['date'].strftime('%Y')}-W{iso[1]:02d}"
        by_month[ym].append(it)
        by_week[wk].append(it)
        by_day[it['date'].isoformat()].append(it)

    def to_series(group):
        return [{'key': k, 'count': len(v), 'items': [
            {'t': x['title'], 'd': x['date'].isoformat(), 'u': x['url'], 'l': x['level']} for x in v
        ]} for k, v in sorted(group.items())]

    return {
        'by_month': to_series(by_month),
        'by_week': to_series(by_week),
        'by_day': to_series(by_day),
    }


def save_data(items, extra, digest_count, levels):
    items = dedup_and_filter(items)
    levels = defaultdict(int)
    for it in items:
        levels[it['level']] += 1
    agg = aggregate(items)
    extra_n = len(extra) if isinstance(extra, (list, tuple)) else extra
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
        },
        'items': [
            {'t': x['title'], 'd': x['date'].isoformat(), 'u': x['url'], 'l': x['level'],
             'w': x.get('word', '')} for x in items
        ],
        **agg,
    }
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
        extra = fetch_digest_bodies(all_items)
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
        save_data(hit, extra, digest_count, levels)
        print(f'数据已保存: {DATA_PATH}')

    print('=== 步骤5: 生成趋势页面 ===')
    import build_digital_page
    build_digital_page.build_page(HTML_PATH, DATA_PATH)
    print(f'页面已生成: {HTML_PATH}')


if __name__ == '__main__':
    main()

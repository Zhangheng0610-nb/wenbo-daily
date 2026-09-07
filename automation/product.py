"""Shared static product shell, freshness evidence and RSS. No network I/O."""
from pathlib import Path
from html import escape
from urllib.parse import urlsplit
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ORIGIN = 'https://zhangheng666.top'
NAV = [('index.html', '资讯'), ('command-center/', '行业观察'), ('jobs.html', '机会'), ('archive.html', '档案'), ('search.html', '搜索')]


def job_id(item):
    """Stable across reorder, status changes and editorial notes."""
    identity = '|'.join(str(item.get(k, '')).strip() for k in
                        ('institution', 'position', 'link_url', 'deadline'))
    return 'job-' + hashlib.sha256(identity.encode()).hexdigest()[:14]


def safe_url(value):
    value = str(value or '').strip()
    if any(ord(c) < 32 for c in value):
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ('http', 'https') and parsed.hostname:
            return value
        if parsed.scheme == 'mailto' and '@' in parsed.path:
            return value
    except ValueError:
        pass
    return ''


def decorate(html, path):
    if 'data-product-shell' in html:
        return html
    prefix = '../' * (len(Path(path).parts) - 1)
    active = 'archive.html' if path.startswith('reports/') else path
    if path == 'intern.html':
        active = 'jobs.html'
    if path in ('heatmap.html', 'digital-trends.html'):
        active = 'command-center/'
    if path == 'command-center/index.html':
        active = 'command-center/'
    links = ''.join(f'<a href="{prefix}{url}"' + (' aria-current="page"' if active == url else '') + f'>{label}</a>' for url, label in NAV)
    nav = f'<div class="product-bar" data-product-shell><a class="skip-link" href="#product-main">跳到正文</a><a class="product-brand" href="{prefix}index.html">文博<span>DAILY</span></a><nav aria-label="全站导航">{links}</nav></div>'
    head = f'<link rel="stylesheet" href="{prefix}assets/product.css"><script src="{prefix}assets/product.js" defer></script><script src="{prefix}assets/reader.js" defer></script><link rel="alternate" type="application/rss+xml" title="每日文博资讯" href="{prefix}feed.xml">'
    canonical = ORIGIN + ('/' if path == 'index.html' else '/' + path)
    if 'rel="canonical"' not in html:
        head += f'<link rel="canonical" href="{canonical}">'
    if 'name="description"' not in html:
        title = re.search(r'<title>(.*?)</title>', html, re.S)
        head += '<meta name="description" content="' + escape(re.sub('<[^>]+>', '', title[1]) if title else '文博资讯与行业机会', quote=True) + '">'
    html = html.replace('</head>', head + '\n</head>', 1)
    html = re.sub(r'<body([^>]*)>', lambda m: '<body' + m[1] + '>' + nav, html, count=1)
    # An existing main retains its layout and receives the skip target.
    if '<main' in html:
        html = re.sub(r'<main([^>]*)>', lambda m: '<main' + m[1] + ' tabindex="-1" id="product-main">', html, count=1)
    else:
        html = html.replace(nav, nav + '<main id="product-main" tabindex="-1">', 1)
        html = html.replace('<footer>', '</main><footer>', 1) if '<footer>' in html else html.replace('</body>', '</main></body>')
    html = html.replace('<body>', '<body class="product-page">', 1)
    return html


def finish_site(root, reports):
    root = Path(root)
    from automation.reader_product import write_reader_product
    write_reader_product(root, reports)
    latest = max((r['date'] for r in reports), default='')
    from automation.ingestion_health import write_health
    write_health(root, latest)
    monitoring = root / 'content' / '监测' / (latest + '.json')
    payload = json.loads(monitoring.read_text()) if monitoring.exists() else {}
    coverage = payload.get('coverage', [])
    live = payload.get('mode') == 'operational' and payload.get('runType') == 'live'
    complete = sum(c.get('status') in ('success', 'no_update') for c in coverage) if live else 0
    status = {'latestReport': latest, 'monitoringDate': payload.get('date'),
              'operational': live, 'completeSources': complete, 'expectedSources': 6,
              'coverage': [{'sourceId': c.get('sourceId'), 'status': c.get('status'), 'checkedAt': c.get('checkedAt')} for c in coverage]}
    (root / 'site-status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
    pages = list(root.glob('*.html')) + list((root / 'reports').glob('*.html')) + list((root / 'command-center').glob('*.html'))
    for page in pages:
        relative = page.relative_to(root).as_posix()
        html = page.read_text()
        if relative == 'index.html':
            evidence = f'<aside class="freshness" data-report-date="{latest}"><strong>最近发布：{latest}</strong><span data-freshness-message>固定信源 {latest} 巡检 {complete}/6 · ' + ('仅代表该日，不代表长期覆盖' if live else '暂无当日正式运行证据') + f'</span><a href="data-health.html">查看采集与更新记录</a><a href="feed.xml">RSS 订阅</a></aside>'
            html = html.replace('<section class="hero"', evidence + '<section class="hero"', 1)
            html = html.replace('今日精选 ·', '最新精选 ·').replace('阅读今日日报', '阅读最新日报')
        if relative == 'command-center/index.html':
            html = html.replace('</header>', '</header><p style="padding:0 24px"><a href="../data-health.html">查看实际采集时间、每日入库量与发现入口状态 →</a></p>', 1)
        page.write_text(decorate(html, relative))
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for k, v in [('title', '每日文博资讯'), ('link', ORIGIN), ('description', '文博、考古、博物馆与文化遗产精选。事实以链接原文为准。'), ('language', 'zh-CN')]:
        ET.SubElement(channel, k).text = v
    for report in sorted(reports, key=lambda r: r['date'], reverse=True)[:30]:
        item = ET.SubElement(channel, 'item')
        link = ORIGIN + '/reports/' + report['date'] + '.html'
        ET.SubElement(item, 'title').text = '文博日报 · ' + report['date']
        ET.SubElement(item, 'link').text = link
        ET.SubElement(item, 'guid', isPermaLink='true').text = link
        entries = report.get('ordered_items') or report['domestic'] + report['international']
        ET.SubElement(item, 'description').text = '\n'.join(row['title'] for row in entries)
        # No invented publication time: the date is part of the title; pubDate is omitted.
    ET.indent(rss)
    (root / 'feed.xml').write_bytes(ET.tostring(rss, encoding='utf-8', xml_declaration=True))
    print(f'Product shell: {len(pages)} pages; RSS and source coverage written.')

#!/usr/bin/env python3
"""
Build HTML reports from Markdown files and rebuild index.html.
Handles daily reports (日报), weekly digests (周报), and monthly digests (月报).
Usage: python build.py
"""
import os, re, glob, json
from urllib.parse import quote

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(SITE_DIR, 'reports')
MD_DIR = os.path.join(os.path.dirname(SITE_DIR), '日报')
JOBS_MD = os.path.join(os.path.dirname(SITE_DIR), '招聘', 'jobs.md')
INTERN_MD = os.path.join(os.path.dirname(SITE_DIR), '招聘', 'intern.md')

WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

CSS = """<style>
  :root {
    --bg: #f5f0eb; --card: #fff; --text: #2c2416; --muted: #8b7355;
    --accent: #8b4513; --tag-bg: #f0e6d3; --border: #e0d5c1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1815; --card: #252320; --text: #e8e0d0; --muted: #9b8b7a;
      --accent: #d4a76a; --tag-bg: #2a2520; --border: #3a3530;
    }
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.85;
    padding: 16px; max-width: 720px; margin: 0 auto; font-size: 16px;
  }
  header {
    text-align: center; padding: 20px 0 16px;
    border-bottom: 2px solid var(--accent); margin-bottom: 20px;
  }
  header h1 { font-size: 1.3em; }
  header .meta { color: var(--muted); font-size: .88em; margin-top: 6px; }
  header a { color: var(--accent); }
  h2.section {
    font-size: 1.1em; color: var(--accent); margin: 28px 0 14px;
    padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }
  h3 { font-size: 1.02em; margin: 20px 0 8px; }
  p { margin: 8px 0; }
  a { color: var(--accent); word-break: break-all; }
  a:visited { color: var(--muted); }
  blockquote {
    border-left: 3px solid var(--accent); padding: 6px 14px;
    margin: 10px 0; background: var(--tag-bg); border-radius: 0 6px 6px 0;
    color: var(--muted); font-size: .95em;
  }
  .news-img {
    max-width: 100%; border-radius: 8px; margin: 4px 0;
    border: 1px solid var(--border);
  }
  .tag {
    display: inline-block; font-size: .72em; padding: 2px 8px;
    border-radius: 10px; margin-right: 4px; margin-bottom: 6px;
    font-weight: 600; letter-spacing: .02em;
	    background: var(--tag-bg); color: var(--muted);
  }
  .tag-考古 { background: #fce4d6; color: #a0522d; }
  .tag-博物馆 { background: #dbe9f5; color: #2c5f8a; }
  .tag-展览 { background: #e8dbf0; color: #6b3a8b; }
  .tag-文物追索 { background: #fde0dc; color: #b03a2e; }
  .tag-科技 { background: #ccfbf1; color: #0d6b5e; }
  .tag-文化遗产 { background: #d9f0d1; color: #3d6b2e; }
  .tag-国际 { background: #fef3c7; color: #8b6914; }
	  .tag-世界遗产 { background: #fde8c8; color: #92400e; }
	  .tag-政策 { background: #e2e8f0; color: #475569; }
	  .tag-数字化 { background: #dbeafe; color: #1e40af; }
	  .tag-文物保护 { background: #ffe4d6; color: #9a3412; }
	  .tag-文物修复 { background: #fce7f3; color: #9d174d; }
  a.tag { text-decoration: none; }
  @media (prefers-color-scheme: dark) {
    .tag-考古 { background: #3d2010; color: #e8a87c; }
    .tag-博物馆 { background: #1a2d3d; color: #7ab8e0; }
    .tag-展览 { background: #2a1a3d; color: #b88ada; }
    .tag-文物追索 { background: #3d1a16; color: #e8786e; }
    .tag-科技 { background: #0d332e; color: #5eeadb; }
    .tag-文化遗产 { background: #1a3316; color: #7cc46e; }
    .tag-国际 { background: #3d3010; color: #e8c84a; }
	    .tag-世界遗产 { background: #3d2808; color: #fbbf24; }
	    .tag-政策 { background: #1e293b; color: #94a3b8; }
	    .tag-数字化 { background: #1e3a5f; color: #93c5fd; }
	    .tag-文物保护 { background: #3d2010; color: #f97316; }
	    .tag-文物修复 { background: #3d1028; color: #f472b6; }
  }
  .toc {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 18px; margin: 0 0 20px;
  }
  .toc summary {
    font-size: 1em; color: var(--accent); cursor: pointer;
    padding: 4px 0; user-select: none;
  }
  .toc ol {
    margin: 10px 0 0 20px; font-size: .92em; line-height: 2;
  }
  .toc ol a {
    color: var(--text); text-decoration: none;
    border-bottom: 1px dotted var(--border);
  }
  .toc ol a:hover { color: var(--accent); }
  hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: .85em; }
  td, th { border: 1px solid var(--border); padding: 7px 10px; }
  strong { color: var(--accent); }
  .top10-table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: .88em; }
  .top10-table thead th {
    background: var(--accent); color: #fff; padding: 10px 12px;
    text-align: left; font-weight: 600; border: none;
  }
  .top10-table tbody td {
    padding: 10px 12px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .top10-table tbody tr:hover { background: var(--tag-bg); }
  .top10-table .rank {
    font-weight: 700; font-size: 1.15em; color: var(--accent);
    text-align: center; width: 36px;
  }
  .top10-table .news-title { font-weight: 600; }
  .top10-table .date {
    color: var(--muted); font-size: .82em; white-space: nowrap;
    width: 60px;
  }
  .top10-table .sig { color: var(--muted); font-size: .85em; line-height: 1.5; }
  footer {
    text-align: center; padding: 28px 0 16px;
    color: var(--muted); font-size: .78em;
    border-top: 1px solid var(--border); margin-top: 24px;
  }
  footer a { color: var(--accent); }
  #back-to-top {
    position: fixed; bottom: 24px; right: 24px; z-index: 999;
    width: 44px; height: 44px; border-radius: 50%;
    background: var(--accent); color: #fff; border: none;
    font-size: 1.3em; cursor: pointer; opacity: 0;
    transition: opacity .25s; display: flex;
    align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
  }
  #back-to-top.show { opacity: .85; }
  #back-to-top:hover { opacity: 1; }
  #reading-progress {
    position: fixed; top: 0; left: 0; height: 3px; z-index: 999;
    background: var(--accent); width: 0%; transition: width .1s;
  }
  .nav-prev-next {
    display: flex; justify-content: space-between; gap: 12px;
    margin: 20px 0; flex-wrap: wrap;
  }
  .nav-prev-next a {
    flex: 1; min-width: 120px; padding: 10px 14px;
    border: 1px solid var(--border); border-radius: 8px;
    text-decoration: none; color: var(--text);
    background: var(--card); font-size: .88em;
    transition: border-color .15s;
  }
  .nav-prev-next a:hover { border-color: var(--accent); }
  .nav-prev-next a.next { text-align: right; }
  .nav-prev-next a .nav-label { color: var(--muted); font-size: .8em; }
  .share-row { text-align: center; margin: 20px 0 8px; }
  #share-btn {
    background: var(--card); color: var(--accent);
    border: 1px solid var(--border); border-radius: 20px;
    padding: 8px 24px; font-size: .88em; cursor: pointer;
    font-family: inherit;
  }
  #share-btn:hover { border-color: var(--accent); }
  .share-tip { display: block; color: var(--muted); font-size: .75em; margin-top: 6px; opacity: .7; }
</style>"""


def parse_md(filepath):
    """Parse a daily markdown report and return structured data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'title': '', 'date': '', 'weekday': '',
        'domestic': [], 'international': [], 'trends': [],
        'domestic_count': 0, 'international_count': 0,
        'toc_items': []
    }

    lines = content.split('\n')

    # Parse title line: # 🏛️ 每日文博资讯 | 2026年7月11日（周六）
    title_match = re.match(r'# .+?\|\s*(\d{4})年(\d{1,2})月(\d{1,2})日（(.+?)）', lines[0])
    if title_match:
        y, m, d, wd = title_match.groups()
        data['date'] = f'{y}-{int(m):02d}-{int(d):02d}'
        data['weekday'] = wd
        data['title'] = lines[0].lstrip('# ')

    current_section = None
    current_item = None
    item_idx = 0

    i = 1
    while i < len(lines):
        line = lines[i]

        # Section headers
        if line.startswith('## 🇨🇳 国内要闻'):
            current_section = 'domestic'
            i += 1
            continue
        elif line.startswith('## 🌍 国际要闻'):
            current_section = 'international'
            i += 1
            continue
        elif line.startswith('## 📊 今日趋势总结'):
            current_section = 'trends'
            i += 1
            continue
        elif line.startswith('## 📑 目录'):
            current_section = 'toc'
            i += 1
            continue
        elif line.startswith('## ') or line.startswith('# '):
            current_section = None
            i += 1
            continue

        # News item header: ### N. title
        item_match = re.match(r'### (\d+)\.\s*(.+)', line)
        if item_match and current_section in ('domestic', 'international'):
            num = int(item_match.group(1))
            title = item_match.group(2).strip()
            title = re.sub(r'\s*\{#[^}]*\}\s*$', '', title)  # strip {#anchor} from title
            item_idx += 1
            current_item = {
                'id': f'item{item_idx}',
                'number': item_idx,
                'title': title,
                'sources': [],
                'tags': [],
                'body': '',
                'commentary': ''
            }
            data[current_section].append(current_item)
            data['toc_items'].append({'id': f'item{item_idx}', 'title': title})
            i += 1
            continue

        # Tag line: 🏷️ tag1 · tag2 · tag3
        tag_match = re.match(r'🏷️\s*(.+)', line)
        if tag_match and current_item:
            tags = [t.strip() for t in re.split(r'[·,，、]\s*', tag_match.group(1))]
            current_item['tags'] = [t for t in tags if t]
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Source links line
        src_match = re.findall(r'📎\s*\[(.+?)\]\((.+?)\)', line)
        if src_match and current_item:
            current_item['sources'] = [{'name': s[0], 'url': s[1]} for s in src_match]
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Image line
        img_match = re.match(r'!\[.*?\]\((.+?)\)', line)
        if img_match and current_item:
            current_item['image'] = img_match.group(1)
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Blockquote commentary
        if line.startswith('> ') and current_item:
            commentary = line.lstrip('> ').strip()
            commentary = re.sub(r'\*\*点评[：:]\*\*\s*', '', commentary)
            current_item['commentary'] = commentary
            i += 1
            continue

        # Table rows (trends section)
        if line.startswith('|') and current_section == 'trends':
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and not all(c.startswith('-') for c in cells):
                data['trends'].append(cells)
            i += 1
            continue

        # Skip markdown footer metadata
        if line.strip().startswith('*本日报由'):
            i += 1
            continue

        # Body text
        if current_item and line.strip() and not line.startswith('---') and not line.startswith('>'):
            if current_item['body']:
                current_item['body'] += '\n' + line
            else:
                current_item['body'] = line

        i += 1

    data['domestic_count'] = len(data['domestic'])
    data['international_count'] = len(data['international'])

    return data


def build_report_html(data, prev_report=None, next_report=None):
    """Generate HTML for a daily report.

    prev_report/next_report: dict with 'date' and 'weekday' or None.
    """
    total = data['domestic_count'] + data['international_count']

    toc_html = '<div class="toc">\n  <details open>\n    <summary><strong>📑 目录</strong></summary>\n    <ol>\n'
    for item in data['toc_items']:
        toc_html += f'      <li><a href="#{item["id"]}">{item["title"]}</a></li>\n'
    toc_html += '    </ol>\n  </details>\n</div>'

    def render_items(items, section_label):
        html = f'<h2 class="section">{section_label}</h2>\n\n'
        for item in items:
            tags_html = ''
            if item.get('tags'):
                for tag in item['tags']:
                    cls = f'tag tag-{tag}'
                    tags_html += f' <a class="{cls}" href="../index.html?q={quote(tag)}">#{tag}</a>'

            html += f'<h3 id="{item["id"]}">{item["number"]}. {item["title"]}{tags_html}</h3>\n'

            if item['sources']:
                src_parts = []
                for s in item['sources']:
                    src_parts.append(f'<a href="{s["url"]}" target="_blank" rel="noopener">{s["name"]}</a>')
                html += '<p>📎 ' + ' | '.join(src_parts) + '</p>\n'

            if item.get('image'):
                html += f'<p><img src="{item["image"]}" class="news-img" loading="lazy" alt="配图" onerror="this.style.display=\'none\'"></p>\n'

            if item['body']:
                html += f'<p>{md_inline(item["body"])}</p>\n'

            if item['commentary']:
                html += f'<blockquote><strong>点评：</strong> {md_inline(item["commentary"])}</blockquote>\n'

            html += '<hr>\n\n'
        return html

    domestic_html = render_items(data['domestic'], '🇨🇳 国内要闻')
    international_html = render_items(data['international'], '🌍 国际要闻')

    trends_html = '<h2 class="section">📊 今日趋势总结</h2>\n\n<table>\n'
    for i, row in enumerate(data['trends']):
        tag = 'th' if i == 0 else 'td'
        trends_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
    trends_html += '</table>\n'

    # Pre-compute prev/next navigation
    if prev_report:
        prev_html = f'''<a class="prev" href="{prev_report['date']}.html">
    <div class="nav-label">← 上一篇</div>
    📅 {prev_report['date']} {prev_report['weekday']}
  </a>'''
    else:
        prev_html = '<a class="prev" style="visibility:hidden"></a>'

    if next_report:
        next_html = f'''<a class="next" href="{next_report['date']}.html">
    <div class="nav-label">下一篇 →</div>
    📅 {next_report['date']} {next_report['weekday']}
  </a>'''
    else:
        next_html = '<a class="next" style="visibility:hidden"></a>'

    nav_html = f'<div class="nav-prev-next">\n  {prev_html}\n  {next_html}\n</div>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日文博资讯 | {data['date']}</title>
<meta name="description" content="{data['date']} 每日文博资讯，共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）。{data['toc_items'][0]['title'][:60] if data['toc_items'] else ''}">
<meta name="keywords" content="文博,考古,博物馆,文化遗产,文物,每日文博资讯,{data['date']}">
<link rel="canonical" href="https://zhangheng666.top/reports/{data['date']}.html">
<link rel="alternate" type="application/rss+xml" title="每日文博资讯" href="https://zhangheng666.top/feed.xml">
<meta property="og:title" content="每日文博资讯 | {data['date']}">
<meta property="og:description" content="{data['date']} 每日文博资讯，共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/reports/{data['date']}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "NewsArticle",
  "headline": "每日文博资讯 | {data['date']}",
  "datePublished": "{data['date']}T08:13:00+08:00",
  "dateModified": "{data['date']}T08:13:00+08:00",
  "description": "{data['date']} 每日文博资讯，共 {total} 条",
  "url": "https://zhangheng666.top/reports/{data['date']}.html",
  "publisher": {{
    "@type": "Organization",
    "name": "每日文博资讯",
    "url": "https://zhangheng666.top/"
  }}
}}
</script>
{CSS}
</head>
<body>

<header>
  <h1>🏛️ 每日文博资讯</h1>
  <p class="meta">{data['date']} · {data['weekday']} ｜ 共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）</p>
  <p style="margin-top:4px;font-size:.85em"><a href="../index.html">← 返回目录</a></p>
</header>

<main>

{toc_html}

{domestic_html}
{international_html}
{trends_html}

<hr>

<p><em>本日报由 Claude 自动采集编撰 | {data['date']}</em></p>

{nav_html}

<div class="share-row">
  <button id="share-btn" aria-label="分享本文">🔗 分享 / 复制链接</button>
  <span class="share-tip">转发给文博同好</span>
</div>

</main>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 每日早 8:13 自动更新 ｜ <a href="../about.html">关于本站</a> ｜ <a href="../feed.xml">RSS 订阅</a></p>
</footer>

<div id="reading-progress"></div>
<button id="back-to-top" aria-label="回到顶部">↑</button>

<script>
window.addEventListener('scroll', function() {{
  var st = window.pageYOffset || document.documentElement.scrollTop;
  var sh = document.documentElement.scrollHeight - document.documentElement.clientHeight;
  var pct = sh > 0 ? (st / sh * 100) : 0;
  document.getElementById('reading-progress').style.width = pct + '%';
  var btn = document.getElementById('back-to-top');
  if (st > 300) btn.classList.add('show'); else btn.classList.remove('show');
}});
document.getElementById('back-to-top').addEventListener('click', function() {{
  window.scrollTo({{top: 0, behavior: 'smooth'}});
}});
document.getElementById('share-btn').addEventListener('click', function() {{
  const url = location.href;
  const title = document.title;
  if (navigator.share) {{
    navigator.share({{title: title, url: url}}).catch(function(){{}});
  }} else if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(title + ' ' + url).then(function() {{
      const b = document.getElementById('share-btn');
      b.textContent = '✅ 链接已复制';
      setTimeout(function() {{ b.textContent = '🔗 分享 / 复制链接'; }}, 2000);
    }});
  }} else {{
    prompt('复制链接：', url);
  }}
}});
</script>

</body>
</html>'''
    return html


# ───────────────── 周报 / 月报 解析器 ─────────────────

def parse_digest(filepath, dtype='weekly'):
    """Parse a weekly or monthly digest markdown file.

    dtype: 'weekly' | 'monthly'
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'type': dtype,
        'title': '',
        'label': '',
        'date_range': '',
        'ref_date': '',   # YYYY-MM-DD for sorting/URL
        'overview': '',
        'overview_table': [],
        'items': [],
        'upcoming_title': '',
        'upcoming_table': [],
        'trends': [],
        'rich_sections': [],  # monthly report: arbitrary rich-text sections
        'footer': ''
    }

    lines = content.split('\n')

    # Parse title line
    if dtype == 'weekly':
        # # 📰 文博资讯周报 | 2026年7月6日 — 7月12日
        # Second date may omit year
        title_match = re.match(
            r'# .+?\|\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*[—\-]\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日', lines[0])
        if title_match:
            y1, m1, d1, y2, m2, d2 = title_match.groups()
            if not y2:
                y2 = y1
            data['date_range'] = f'{y1}-{int(m1):02d}-{int(d1):02d} — {y2}-{int(m2):02d}-{int(d2):02d}'
            data['ref_date'] = f'{y2}-{int(m2):02d}-{int(d2):02d}'
            data['label'] = '周报'
    else:
        # # 📚 文博资讯月报 | 2026年7月
        title_match = re.match(r'# .+?\|\s*(\d{4})年(\d{1,2})月', lines[0])
        if title_match:
            y, m = title_match.groups()
            data['date_range'] = f'{y}年{int(m)}月'
            data['ref_date'] = f'{y}-{int(m):02d}-28'  # fallback for sorting
            data['label'] = '月报'

    data['title'] = lines[0].lstrip('# ')

    # Parse sections
    current_section = None
    current_item = None
    current_rich = None
    i = 1
    while i < len(lines):
        line = lines[i]

        # Section headers
        if line.startswith('## 📊') and '概览' in line:
            current_section = 'overview'
            current_item = None; current_rich = None
            i += 1
            continue
        elif line.startswith('## 🔟') or line.startswith('## 🔝') or ('要闻' in line and '##' in line and '趋势' not in line):
            current_section = 'items'
            current_item = None; current_rich = None
            i += 1
            continue
        elif line.startswith('## 🗓️') or line.startswith('## 📅'):
            current_section = 'upcoming'
            current_item = None; current_rich = None
            i += 1
            data['upcoming_title'] = line.lstrip('# ').strip()
            continue
        elif line.startswith('## 📊') and '趋势' in line:
            # Monthly report: trends are rich-text sections, not just tables
            if dtype == 'monthly':
                current_section = 'rich'
                title = line.lstrip('# ').strip()
                title = re.sub(r'\s*\{#.*?\}\s*$', '', title)
                current_rich = {'icon': '📊', 'title': title, 'raw_lines': []}
                data['rich_sections'].append(current_rich)
            else:
                current_section = 'trends'
            current_item = None
            i += 1
            continue

        # Rich sections: 🌍, 💡, 📈, 🏆, 📂, etc.
        # For monthly/weekly reports, every unhandled ## header starts a new rich section
        if dtype in ('monthly', 'weekly') and line.startswith('## ') and not line.startswith('## 📑'):
            # Skip TOC section
            if '目录' in line:
                current_section = 'skip'
                current_item = None; current_rich = None
                i += 1
                continue
            # Start a new rich section (handles section transitions)
            icon_match = re.match(r'##\s+(\S)\s', line)
            icon = icon_match.group(1) if icon_match else '📄'
            title = line.lstrip('# ').strip()
            title = re.sub(r'\s*\{#.*?\}\s*$', '', title)
            current_section = 'rich'
            current_rich = {'icon': icon, 'title': title, 'raw_lines': []}
            data['rich_sections'].append(current_rich)
            current_item = None
            i += 1
            continue
        elif line.startswith('## ') or line.startswith('# '):
            current_section = None
            current_item = None; current_rich = None
            i += 1
            continue

        # Handle rich section content (monthly report)
        if current_section == 'rich' and current_rich is not None:
            current_rich['raw_lines'].append(line)
            i += 1
            continue

        # Item header: ### N. title
        item_match = re.match(r'### (\d+)\.\s*(.+)', line)
        if item_match and current_section == 'items':
            title = item_match.group(2).strip()
            current_item = {
                'id': f'item{item_match.group(1)}',
                'title': title,
                'sources': [],
                'body': '',
                'progress': ''
            }
            data['items'].append(current_item)
            i += 1
            continue

        # Source links (at end of item, after blockquote or body)
        src_match = re.findall(r'📎\s*\[(.+?)\]\((.+?)\)', line)
        if src_match and current_item:
            current_item['sources'] = [{'name': s[0], 'url': s[1]} for s in src_match]
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Blockquote (本周新进展 / 本月新进展 for digest items)
        if line.startswith('> ') and current_item:
            progress = line.lstrip('> ').strip()
            progress = re.sub(r'\*\*本周新进展[：:]\*\*\s*', '', progress)
            progress = re.sub(r'\*\*本月新进展[：:]\*\*\s*', '', progress)
            current_item['progress'] = progress
            i += 1
            continue

        # Table rows
        if line.startswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and not all(c.startswith('-') for c in cells):
                if current_section == 'overview':
                    data['overview_table'].append(cells)
                elif current_section == 'upcoming':
                    data['upcoming_table'].append(cells)
                elif current_section == 'trends':
                    data['trends'].append(cells)
                elif current_section == 'items' and dtype == 'monthly':
                    # Monthly report top-10 table: | rank | title | date | significance |
                    if len(cells) >= 3 and cells[0].isdigit():
                        rank = cells[0]
                        title = cells[1] if len(cells) > 1 else ''
                        date_info = cells[2] if len(cells) > 2 else ''
                        significance = cells[3] if len(cells) > 3 else ''
                        current_item = {
                            'id': f'item{rank}',
                            'title': title,
                            'sources': [],
                            'body': f'📅 {date_info} ｜ {significance}' if significance else date_info,
                            'progress': ''
                        }
                        data['items'].append(current_item)
            i += 1
            continue

        # Footer
        if line.strip().startswith('*本周报由') or line.strip().startswith('*本月报由'):
            data['footer'] = line.strip().strip('*')
            i += 1
            continue

        # Body text for overview or current item
        if current_section == 'overview' and line.strip() and not line.startswith('---'):
            if data['overview']:
                data['overview'] += '\n' + line.strip()
            else:
                data['overview'] = line.strip()

        elif current_item and current_section == 'items' and line.strip() and not line.startswith('---') and not line.startswith('>'):
            if current_item['body']:
                current_item['body'] += '\n' + line.strip()
            else:
                current_item['body'] = line.strip()

        i += 1

    return data


def md_inline(text):
    """Convert markdown inline formatting to HTML."""
    if not text:
        return text
    # **bold**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *italic*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # `code`
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


# ───────────────── 招聘信息 解析器 ─────────────────

def parse_jobs(filepath):
    """Parse recruitment markdown file and return structured data.

    Returns dict with:
      - update_date: 'YYYY-MM-DD'
      - summary: str (intro paragraph)
      - sections: [{category, icon, items: [{number, institution, position,
          education, location, deadline, link_url, link_text, urgent, days_left}]}]
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'update_date': '',
        'summary': '',
        'sections': []
    }

    lines = content.split('\n')

    # Parse title line for update date
    if lines:
        title_match = re.match(
            r'# .+?\|\s*(\d{4})年(\d{1,2})月(\d{1,2})日', lines[0])
        if title_match:
            y, m, d = title_match.groups()
            data['update_date'] = f'{y}-{int(m):02d}-{int(d):02d}'

    today = data['update_date']

    current_section = None  # dict with category, icon, items
    current_item = None

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith('---'):
            continue

        # Summary line: > text
        if stripped.startswith('> '):
            prefix = stripped[2:].strip()
            if data['summary']:
                data['summary'] += ' ' + prefix
            else:
                data['summary'] = prefix
            continue

        # Section header: ## 🏛️ 博物馆 etc.
        sec_match = re.match(r'##\s+(.{1,2})\s+(.+)', stripped)
        if sec_match:
            icon = sec_match.group(1)
            category = sec_match.group(2)
            current_section = {'category': category, 'icon': icon, 'items': []}
            data['sections'].append(current_section)
            current_item = None
            continue

        # Item header: ### N. Institution — Position  (or ### N. ⏰ ...)
        item_match = re.match(r'###\s+(\d+)\.\s+(⏰\s*)?(.+?)\s*[—\-]\s*(.+)', stripped)
        if item_match:
            number = int(item_match.group(1))
            urgent = bool(item_match.group(2))
            institution = item_match.group(3).strip()
            position = item_match.group(4).strip()

            current_item = {
                'number': number,
                'urgent': urgent,
                'institution': institution,
                'position': position,
                'education': '',
                'location': '',
                'deadline': '',
                'link_url': '',
                'link_text': '招聘公告',
                'days_left': None,
                'note': ''
            }
            if current_section is None:
                # Default section
                current_section = {'category': '招聘', 'icon': '💼', 'items': []}
                data['sections'].append(current_section)
            current_section['items'].append(current_item)
            continue

        # Field lines: - 🎓 **学历要求**：value
        if current_item:
            field_match = re.match(r'-\s*.+?\*\*(.+?)\*\*\s*[：:]\s*(.+)', stripped)
            if field_match:
                field_name = field_match.group(1).strip()
                field_value = field_match.group(2).strip()

                if '学历' in field_name:
                    current_item['education'] = field_value
                elif '地点' in field_name:
                    current_item['location'] = field_value
                elif '截止' in field_name:
                    current_item['deadline'] = field_value
                elif '待遇' in field_name:
                    current_item['note'] = field_value
                continue

            # Link line: - 🔗 [text](url)
            link_match = re.match(r'-\s*🔗\s*\[(.+?)\]\((.+?)\)', stripped)
            if link_match:
                current_item['link_text'] = link_match.group(1)
                current_item['link_url'] = link_match.group(2)
                continue

            # Email line: - 📧 投递：email@addr  or  📧 email@addr
            email_match = re.match(r'-\s*📧\s*(?:投递[：:]\s*)?([a-zA-Z0-9._%+-]+@[^\s|]+)', stripped)
            if email_match:
                email = email_match.group(1).strip()
                current_item['link_url'] = f'mailto:{email}'
                current_item['link_text'] = email
                continue

    # Compute days_left and urgent flag for each item
    for section in data['sections']:
        for item in section['items']:
            dl = item['deadline']
            if dl and today:
                dl_match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', dl)
                if dl_match:
                    try:
                        from datetime import date
                        dl_date = date(
                            int(dl_match.group(1)),
                            int(dl_match.group(2)),
                            int(dl_match.group(3))
                        )
                        today_date = date.fromisoformat(today)
                        item['days_left'] = (dl_date - today_date).days
                        if 0 <= item['days_left'] <= 3:
                            item['urgent'] = True
                    except (ValueError, KeyError):
                        pass

    # Sort items within each section by deadline (earliest first, no-deadline last)
    for section in data['sections']:
        def sort_key(item):
            if item['days_left'] is not None:
                return (0, item['days_left'])
            return (1, 9999)
        section['items'].sort(key=sort_key)

    return data


def build_jobs_html(data, page_type='jobs'):
    """Generate HTML for the recruitment page (jobs.html) or internship page (intern.html)."""
    total = sum(len(s['items']) for s in data['sections'])
    urgent_count = sum(1 for s in data['sections'] for it in s['items'] if it['urgent'])
    is_intern = (page_type == 'intern')
    page_title = '🌱 文博实习招聘' if is_intern else '💼 文博招聘信息'
    page_url = 'intern.html' if is_intern else 'jobs.html'

    # Build sections
    sections_html = ''
    for sec in data['sections']:
        items_html = ''
        for item in sec['items']:
            # Urgency badge — use specific date, not relative ("今天"/"明天")
            urgent_badge = ''
            if item['urgent'] and item['days_left'] is not None:
                dl = item['deadline']
                dl_match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', dl) if dl else None
                if dl_match:
                    m, d = int(dl_match.group(2)), int(dl_match.group(3))
                    urgent_badge = f' <span class="closing-badge">{m}月{d}日截止</span>'
                else:
                    urgent_badge = ' <span class="closing-badge">即将截止</span>'

            row_class = ' urgent-row' if item['urgent'] else ''

            items_html += f'''
        <div class="job-item{row_class}">
          <div class="job-header">
            <span class="job-number">#{item['number']}</span>
            <span class="job-title">{item['institution']} — {item['position']}</span>
            {urgent_badge}
          </div>
          <div class="job-meta">
            <span>🎓 {item['education'] or '见公告'}</span>
            <span>📍 {item['location'] or '见公告'}</span>
            <span class="job-deadline">📅 {item['deadline'] or '见公告'}</span>
            {('<span>💰 ' + item['note'] + '</span>') if item.get('note') else ''}
          </div>
          <div class="job-link">
            {'<a href="' + item['link_url'] + '" target="_blank" rel="noopener">🔗 ' + item['link_text'] + '</a>' if item['link_url'] else '<span style="color:var(--muted);font-size:.85em">📧 ' + (item.get("link_text") or "见公告") + '</span>'}
          </div>
        </div>'''

        sections_html += f'''
    <div class="job-section">
      <h2 class="section">{sec['icon']} {sec['category']} <span class="count-badge">{len(sec['items'])} 岗</span></h2>
      {items_html}
    </div>'''

    # Summary
    summary_html = ''
    if data['summary']:
        summary_html = f'<p class="job-summary">{md_inline(data["summary"])}</p>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title} | {data['update_date']}</title>
<meta property="og:title" content="{page_title} | {data['update_date']}">
<meta property="og:description" content="{'文博实习岗位，面向在读学生，共 ' + str(total) + ' 个岗位' if is_intern else '省级以上博物馆、考古院所、高校文博专业招聘信息，共 ' + str(total) + ' 个岗位。即将截止 ' + str(urgent_count) + ' 个。'}">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/jobs.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
{CSS}
<style>
  .job-summary {{
    background: var(--card); border-left: 3px solid var(--accent);
    padding: 12px 16px; margin: 16px 0; border-radius: 0 8px 8px 0;
    font-size: .9em; color: var(--muted);
  }}
  .job-section {{
    margin: 24px 0;
  }}
  .job-item {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px; margin: 10px 0;
    transition: box-shadow .15s;
  }}
  .job-item:hover {{
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
  }}
  .job-item.urgent-row {{
    border-left: 4px solid #e74c3c;
  }}
  @media (prefers-color-scheme: dark) {{
    .job-item.urgent-row {{
      border-left-color: #ff6b5b;
    }}
  }}
  .job-header {{
    display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
    margin-bottom: 6px;
  }}
  .job-number {{
    color: var(--muted); font-size: .8em; min-width: 24px;
  }}
  .job-title {{
    font-weight: 700; font-size: 1.05em; color: var(--text);
  }}
  .closing-badge {{
    display: inline-block; font-size: .75em; padding: 2px 10px;
    border-radius: 10px; background: #e74c3c; color: #fff;
    font-weight: 600; white-space: nowrap;
  }}
  @media (prefers-color-scheme: dark) {{
    .closing-badge {{
      background: #c0392b;
    }}
  }}
  .job-meta {{
    display: flex; gap: 16px; flex-wrap: wrap; font-size: .85em;
    color: var(--muted); margin: 6px 0;
  }}
  .job-deadline {{
    font-weight: 600;
  }}
  .job-link {{
    margin-top: 4px;
  }}
  .job-link a {{
    font-size: .9em; color: var(--accent); font-weight: 600;
    text-decoration: none;
  }}
  .job-link a:hover {{
    text-decoration: underline;
  }}
  .stats-bar {{
    display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0;
  }}
  .stat-item {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 16px; font-size: .85em;
  }}
  .stat-item strong {{ color: var(--accent); }}
</style>
</head>
<body>

<header>
  <h1>{page_title}</h1>
  <p class="meta">{data['update_date']} 更新 ｜ 共 {total} 个{'实习岗位' if is_intern else '岗位'}{' ｜ ⏰ 即将截止 ' + str(urgent_count) + ' 个' if not is_intern and urgent_count else ''}</p>
  <p style="margin-top:4px;font-size:.85em"><a href="index.html">← 返回首页</a></p>
</header>

{summary_html}

<div class="stats-bar">
  <div class="stat-item">📋 总岗位数：<strong>{total}</strong></div>
  <div class="stat-item">⏰ 即将截止：<strong>{urgent_count}</strong></div>
  <div class="stat-item">🔄 每两天更新一次</div>
</div>

{sections_html}

<hr>
<p style="font-size:.82em; color: var(--muted);">⚠️ 申请前请务必核对官方原文，本页面仅做信息聚合。收录范围：省级及以上博物馆、考古院所、设有考古/文博专业的高校。</p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 招聘栏目 · 每两日更新 ｜ <a href="about.html">关于本站</a></p>
</footer>

</body>
</html>'''
    return html


def _render_md_block(lines):
    """Convert a list of raw markdown lines to HTML.
    Handles: paragraphs, ### headers, bullet lists, tables, blockquotes.
    """
    html = ''
    i = 0
    while i < len(lines):
        line = lines[i]

        # Blank line or horizontal rule
        if not line.strip() or line.strip() == '---':
            i += 1
            continue

        # Sub-header: ### Title
        sub_match = re.match(r'###\s+(.+)', line)
        if sub_match:
            title = md_inline(sub_match.group(1).strip())
            # Remove {#anchor}
            title = re.sub(r'\s*\{#.*?\}\s*$', '', title)
            html += f'<h3>{title}</h3>\n'
            i += 1
            continue

        # Table
        if line.startswith('|'):
            table_rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].split('|')[1:-1]]
                if not all(c.startswith('-') for c in cells):
                    table_rows.append(cells)
                elif table_rows:
                    # separator row — skip but it marks header
                    pass
                i += 1
            if table_rows:
                html += '<table>\n'
                for ri, row in enumerate(table_rows):
                    tag = 'th' if ri == 0 else 'td'
                    html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
                html += '</table>\n'
            continue

        # Blockquote
        if line.startswith('> '):
            content = line[2:].strip()
            content = re.sub(r'\*\*点评[：:]\*\*\s*', '', content)
            html += f'<blockquote>{md_inline(content)}</blockquote>\n'
            i += 1
            continue

        # Unordered list
        if re.match(r'^-\s+', line):
            html += '<ul>\n'
            while i < len(lines) and re.match(r'^-\s+', lines[i]):
                item_text = md_inline(re.sub(r'^-\s+', '', lines[i]))
                html += f'<li>{item_text}</li>\n'
                i += 1
            html += '</ul>\n'
            continue

        # Ordered list
        if re.match(r'^\d+\.\s+', line):
            html += '<ol>\n'
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                item_text = md_inline(re.sub(r'^\d+\.\s+', '', lines[i]))
                html += f'<li>{item_text}</li>\n'
                i += 1
            html += '</ol>\n'
            continue

        # Regular paragraph — collect consecutive text lines
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|', '>', '-')) and not re.match(r'^\d+\.\s+', lines[i]):
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            text = ' '.join(para_lines)
            html += f'<p>{md_inline(text)}</p>\n'
            continue

        # Fallback: skip unrecognized lines
        i += 1

    return html


def build_digest_html(data):
    """Generate HTML for a weekly or monthly digest."""
    dtype = data['type']
    emoji = '📰' if dtype == 'weekly' else '📊'

    # Overview
    overview_html = f'<h2 class="section">📊 本期概览</h2>\n'
    if data['overview']:
        overview_html += f'<p>{md_inline(data["overview"])}</p>\n'
    if data['overview_table']:
        overview_html += '<table>\n'
        for i, row in enumerate(data['overview_table']):
            tag = 'th' if i == 0 else 'td'
            overview_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
        overview_html += '</table>\n'

    # Items
    if dtype == 'monthly' and data['items']:
        # Monthly report: render top 10 as a styled ranking table
        items_html = '<h2 class="section">🔟 七月十大文博新闻</h2>\n\n'
        items_html += '<p>本月文博领域重大事件精选，按重要性和影响力综合排序。</p>\n'
        items_html += '<table class="top10-table">\n'
        items_html += '<thead><tr><th>#</th><th>新闻</th><th>日期</th><th>为什么重要</th></tr></thead>\n<tbody>\n'
        for item in data['items']:
            rank = item['id'].replace('item', '')
            # body format: "📅 date | significance"
            body = item.get('body', '')
            date_str = ''
            sig_str = ''
            if '｜' in body:
                parts = body.split('｜', 1)
                date_str = parts[0].replace('📅', '').strip()
                sig_str = parts[1].strip()
            elif '|' in body:
                parts = body.split('|', 1)
                date_str = parts[0].replace('📅', '').strip()
                sig_str = parts[1].strip()
            items_html += f'<tr><td class="rank">{rank}</td><td class="news-title">{md_inline(item["title"])}</td><td class="date">{date_str}</td><td class="sig">{md_inline(sig_str)}</td></tr>\n'
        items_html += '</tbody>\n</table>\n'
    else:
        # Weekly report: flat item list (only if there are items)
        items_html = ''
        if data['items']:
            items_html = '<h2 class="section">🔟 本期要闻</h2>\n\n'
            for item in data['items']:
                items_html += f'<h3 id="{item["id"]}">{md_inline(item["title"])}</h3>\n'

                if item['body']:
                    items_html += f'<p>{md_inline(item["body"])}</p>\n'

                if item['progress']:
                    items_html += f'<blockquote><strong>{data["label"]}新进展：</strong> {md_inline(item["progress"])}</blockquote>\n'

                if item['sources']:
                    src_parts = []
                    for s in item['sources']:
                        src_parts.append(f'<a href="{s["url"]}" target="_blank" rel="noopener">{s["name"]}</a>')
                    items_html += '<p>📎 ' + ' | '.join(src_parts) + '</p>\n'

                items_html += '<hr>\n\n'

    # Upcoming / forecast
    upcoming_html = ''
    if data['upcoming_table']:
        upcoming_title = data.get('upcoming_title', '🗓️ 下期预告' if dtype == 'weekly' else '🗓️ 下月预告')
        upcoming_html = f'<h2 class="section">{upcoming_title}</h2>\n\n<table>\n'
        for i, row in enumerate(data['upcoming_table']):
            tag = 'th' if i == 0 else 'td'
            upcoming_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
        upcoming_html += '</table>\n'

    # Trends
    trends_html = ''
    if data['trends']:
        trends_html = '<h2 class="section">📊 趋势总结</h2>\n\n<table>\n'
        for i, row in enumerate(data['trends']):
            tag = 'th' if i == 0 else 'td'
            trends_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
        trends_html += '</table>\n'

    # Rich sections (monthly report)
    rich_html = ''
    if data.get('rich_sections'):
        for sec in data['rich_sections']:
            # Title already includes emoji, don't duplicate
            rich_html += f'<h2 class="section">{sec["title"]}</h2>\n\n'
            rich_html += _render_md_block(sec['raw_lines'])
            rich_html += '\n'

    og_label = '文博资讯周报' if dtype == 'weekly' else '文博资讯月报'
    url_slug = f'{dtype}-{data["ref_date"]}'

    # Count display: use items count, or fall back to overview-based text
    item_count = len(data['items'])
    if item_count == 0 and data.get('rich_sections'):
        count_text = '综合周报'
    elif item_count > 0:
        count_text = f'共 {item_count} 条要闻'
    else:
        count_text = ''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{og_label} | {data['date_range']}</title>
<meta property="og:title" content="{og_label} | {data['date_range']}">
<meta property="og:description" content="{data['date_range']} {og_label}{'，' + count_text if count_text else ''}">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/reports/{url_slug}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
{CSS}
</head>
<body>

<header>
  <h1>{emoji} {og_label}</h1>
  <p class="meta">{data['date_range']} ｜ {count_text}</p>
  <p style="margin-top:4px;font-size:.85em"><a href="../index.html">← 返回目录</a></p>
</header>

{overview_html}

{items_html}

{upcoming_html}

{trends_html}

{rich_html}

<hr>

<p><em>{data['footer']}</em></p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 每日早 8:13 自动更新</p>
</footer>

</body>
</html>'''
    return html


# ───────────────── 首页构建 ─────────────────

def build_index(daily_reports, weekly_reports=None, monthly_reports=None, recruitment_data=None, intern_data=None):
    """Rebuild index.html with daily, weekly, monthly, and recruitment sections."""
    if weekly_reports is None:
        weekly_reports = []
    if monthly_reports is None:
        monthly_reports = []

    daily_reports = sorted(daily_reports, key=lambda r: r['date'], reverse=True)

    # Daily cards — build list, limit to latest 3 by default
    DAILY_LIMIT = 2
    card_items = []
    for i, r in enumerate(daily_reports):
        total = r['domestic_count'] + r['international_count']
        badge = '<span class="badge">最新</span>' if i == 0 else ''
        card_items.append(f'''
<a class="day-card" href="reports/{r['date']}.html">
  <span class="date">📅 {r['date']}</span>
  <span class="weekday">{r['weekday']}</span>
  {badge}
  <div class="count">📰 共 {total} 条 ｜ 国内 {r['domestic_count']} + 国际 {r['international_count']}</div>
</a>''')

    latest_cards = '\n'.join(card_items[:DAILY_LIMIT])
    older_cards_html = ''
    if len(card_items) > DAILY_LIMIT:
        older_count = len(card_items) - DAILY_LIMIT
        older_cards_joined = '\n'.join(card_items[DAILY_LIMIT:])
        older_cards_html = f'''
<div class="older-cards" style="display:none;">
{older_cards_joined}
</div>
<button class="show-more-btn" onclick="toggleOlder(this)" data-expand-text="📅 展开更早的日报（{older_count} 天）" data-collapse-text="📅 收起">📅 展开更早的日报（{older_count} 天）</button>'''

    # Weekly cards — build list, limit to latest 1 by default
    weekly_card_items = []
    WEEKLY_LIMIT = 1
    weekly_reports = sorted(weekly_reports, key=lambda r: r['ref_date'], reverse=True)
    for r in weekly_reports:
        w_count = len(r['items'])
        if w_count == 0 and r.get('rich_sections'):
            w_count_text = '综合周报'
        elif w_count > 0:
            w_count_text = f'共 {w_count} 条要闻'
        else:
            w_count_text = ''
        weekly_card_items.append(f'''
<a class="day-card weekly-card" href="reports/weekly-{r['ref_date']}.html">
  <span class="date">📰 {r['date_range']}</span>
  <div class="count">📋 {w_count_text}</div>
</a>''')
    weekly_latest = '\n'.join(weekly_card_items[:WEEKLY_LIMIT])
    weekly_older_html = ''
    if len(weekly_card_items) > WEEKLY_LIMIT:
        w_older_count = len(weekly_card_items) - WEEKLY_LIMIT
        weekly_older_html = f'''
<div class="older-cards" style="display:none;">
{'\n'.join(weekly_card_items[WEEKLY_LIMIT:])}
</div>
<button class="show-more-btn" onclick="toggleOlder(this)" data-expand-text="📰 展开更早的周报（{w_older_count} 期）" data-collapse-text="📰 收起">📰 展开更早的周报（{w_older_count} 期）</button>'''

    # Monthly cards — build list, limit to latest 1 by default
    monthly_card_items = []
    MONTHLY_LIMIT = 1
    monthly_reports = sorted(monthly_reports, key=lambda r: r['ref_date'], reverse=True)
    for r in monthly_reports:
        monthly_card_items.append(f'''
<a class="day-card monthly-card" href="reports/monthly-{r['ref_date']}.html">
  <span class="date">📊 {r['date_range']}</span>
  <div class="count">📋 共 {len(r['items'])} 条要闻</div>
</a>''')
    monthly_latest = '\n'.join(monthly_card_items[:MONTHLY_LIMIT])
    monthly_older_html = ''
    if len(monthly_card_items) > MONTHLY_LIMIT:
        m_older_count = len(monthly_card_items) - MONTHLY_LIMIT
        monthly_older_html = f'''
<div class="older-cards" style="display:none;">
{'\n'.join(monthly_card_items[MONTHLY_LIMIT:])}
</div>
<button class="show-more-btn" onclick="toggleOlder(this)" data-expand-text="📊 展开更早的月报（{m_older_count} 期）" data-collapse-text="📊 收起">📊 展开更早的月报（{m_older_count} 期）</button>'''

    index_css = """<style>
  :root {
    --bg: #f5f0eb; --card: #fff; --text: #2c2416; --muted: #8b7355;
    --accent: #8b4513; --tag-bg: #f0e6d3; --border: #e0d5c1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1815; --card: #252320; --text: #e8e0d0; --muted: #9b8b7a;
      --accent: #d4a76a; --tag-bg: #2a2520; --border: #3a3530;
    }
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.7;
    padding: 16px; max-width: 720px; margin: 0 auto;
  }
  header {
    text-align: center; padding: 32px 0 20px;
    border-bottom: 2px solid var(--accent); margin-bottom: 24px;
  }
  header h1 { font-size: 1.6em; letter-spacing: .05em; }
  header p.sub { color: var(--muted); font-size: .9em; margin-top: 4px; }
  header p.tip { color: var(--muted); font-size: .78em; margin-top: 10px; opacity: .7; }
  /* Search */
  .search-wrap {
    position: relative; margin-bottom: 20px;
  }
  .search-wrap input {
    width: 100%; padding: 12px 40px 12px 16px;
    font-size: .95em; border: 1px solid var(--border);
    border-radius: 24px; background: var(--card); color: var(--text);
    outline: none; transition: border-color .2s;
    -webkit-appearance: none;
  }
  .search-wrap input:focus { border-color: var(--accent); }
  .search-wrap input::placeholder { color: var(--muted); opacity: .7; }
  .search-wrap .clear {
    position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
    background: none; border: none; color: var(--muted); font-size: 1.2em;
    cursor: pointer; display: none; line-height: 1; padding: 4px;
  }
  .highlight { background: #f0c040; border-radius: 2px; padding: 0 1px; }
  .no-results { text-align: center; color: var(--muted); padding: 36px 0; display: none; }
  .result-count { font-size: .8em; color: var(--muted); text-align: center; margin-bottom: 12px; display: none; }
  /* Tag cloud */
  .tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; align-items: center; }
  .tag-cloud-label { color: var(--muted); font-size: .85em; }
  .tag-cloud-chip {
    background: var(--tag-bg); color: var(--muted); border: none;
    border-radius: 14px; padding: 4px 12px; font-size: .82em;
    cursor: pointer; font-family: inherit;
  }
  .tag-cloud-chip:hover { color: var(--accent); }
  .chip-count { opacity: .6; font-size: .85em; }
  /* Section headers */
  .section-header {
    font-size: 1.05em; color: var(--accent); margin: 28px 0 12px;
    padding-bottom: 8px; border-bottom: 2px solid var(--border);
    display: flex; align-items: center; gap: 8px;
  }
  .section-header .count-badge {
    font-size: .75em; background: var(--tag-bg); color: var(--muted);
    padding: 2px 10px; border-radius: 10px; font-weight: normal;
  }
  a.day-card {
    background: var(--card); border-radius: 10px; padding: 18px 20px;
    margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06);
    border: 1px solid var(--border);
    display: block; text-decoration: none; color: var(--text);
    transition: transform .15s;
  }
  a.day-card:active { transform: scale(.98); }
  a.day-card.hidden { display: none; }
  a.day-card .date { font-weight: 700; font-size: 1.1em; color: var(--accent); }
  a.day-card .weekday { color: var(--muted); font-size: .85em; margin-left: 8px; }
  a.day-card .badge {
    display: inline-block; background: var(--accent); color: #fff;
    font-size: .72em; padding: 2px 8px; border-radius: 10px;
    margin-left: 6px; vertical-align: middle;
  }
  a.day-card .count { font-size: .82em; color: var(--muted); margin-top: 4px; }
  a.day-card .match-preview {
    font-size: .8em; color: var(--muted); margin-top: 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  footer {
    text-align: center; padding: 32px 0 20px;
    color: var(--muted); font-size: .8em;
    border-top: 1px solid var(--border); margin-top: 24px;
  }
  footer a { color: var(--accent); }
  .empty { text-align: center; color: var(--muted); padding: 36px 0; font-size: .9em; }
  /* Headline teaser */
  .headlines {
    background: var(--card); border: 1px solid var(--border);
    border-left: 3px solid var(--accent); border-radius: 10px;
    padding: 14px 18px; margin-bottom: 14px;
  }
  .headlines-title { font-size: .85em; color: var(--muted); margin-bottom: 6px; }
  .headlines-title a { color: var(--accent); text-decoration: none; }
  .headlines-list { margin: 0 0 0 18px; font-size: .92em; line-height: 1.9; }
  .headlines-list a { color: var(--text); text-decoration: none; border-bottom: 1px dotted var(--border); }
  .headlines-list a:hover { color: var(--accent); }
  /* Collapsible sections */
  .section-header.collapsible {
    cursor: pointer; user-select: none;
    position: relative; padding-right: 28px;
  }
  .section-header.collapsible:hover { color: var(--text); }
  .section-header.collapsible::after {
    content: '▾'; position: absolute; right: 4px; top: 50%;
    transform: translateY(-50%); font-size: .85em;
    transition: transform .2s; color: var(--muted);
  }
  .section-header.collapsible.collapsed::after {
    transform: translateY(-50%) rotate(-90deg);
  }
  .section-body { transition: opacity .15s; }
  .section-body.hidden { display: none; }
  /* Show more button */
  .show-more-btn {
    display: block; width: 100%; padding: 10px;
    background: var(--card); border: 1px dashed var(--border);
    border-radius: 10px; color: var(--accent); font-size: .88em;
    cursor: pointer; margin-bottom: 14px; text-align: center;
    transition: background .15s;
  }
  .show-more-btn:hover { background: var(--tag-bg); }
  .older-cards { }
</style>"""

    # Build section blocks
    weekly_block = ''
    if weekly_card_items:
        weekly_block = f'<div class="section-header collapsible" onclick="toggleSection(this)">📰 周报 <span class="count-badge">{len(weekly_reports)} 期</span></div>\n<div class="section-body"><div id="weekly-list">{weekly_latest}\n{weekly_older_html}</div></div>\n'
    else:
        weekly_block = '<div class="section-header collapsible collapsed" onclick="toggleSection(this)">📰 周报 <span class="count-badge">0 期</span></div>\n<div class="section-body hidden"><div class="empty">周报每周日发布，敬请期待</div></div>\n'

    monthly_block = ''
    if monthly_card_items:
        monthly_block = f'<div class="section-header collapsible" onclick="toggleSection(this)">📊 月报 <span class="count-badge">{len(monthly_reports)} 期</span></div>\n<div class="section-body"><div id="monthly-list">{monthly_latest}\n{monthly_older_html}</div></div>\n'
    else:
        monthly_block = '<div class="section-header collapsible collapsed" onclick="toggleSection(this)">📊 月报 <span class="count-badge">0 期</span></div>\n<div class="section-body hidden"><div class="empty">月报每月 1 日发布，敬请期待</div></div>\n'

    # Recruitment section (正职 + 实习 as sub-sections)
    recruitment_block = ''
    has_jobs = recruitment_data and recruitment_data.get('sections')
    has_intern = intern_data and intern_data.get('sections')

    total_jobs = sum(len(s['items']) for s in recruitment_data['sections']) if has_jobs else 0
    total_intern = sum(len(s['items']) for s in intern_data['sections']) if has_intern else 0
    total_all = total_jobs + total_intern

    if has_jobs or has_intern:
        # Job sub-card
        jobs_card = ''
        if has_jobs:
            section_labels = [f'{s["icon"]} {s["category"]} {len(s["items"])} 条' for s in recruitment_data['sections']]
            section_summary = ' · '.join(section_labels)
            jobs_card = f'''<a class="day-card" href="jobs.html">
  <span class="date">💼 正职招聘</span>
  <div class="count">{section_summary} ｜ {total_jobs} 个岗位 · 更新于 {recruitment_data['update_date']}</div>
</a>
'''
        # Intern sub-card
        intern_card = ''
        if has_intern:
            intern_labels = [f'{s["icon"]} {s["category"]} {len(s["items"])} 条' for s in intern_data['sections']]
            intern_summary = ' · '.join(intern_labels)
            intern_card = f'''<a class="day-card" href="intern.html">
  <span class="date">🌱 实习招聘</span>
  <div class="count">{intern_summary} ｜ {total_intern} 个岗位 · 更新于 {intern_data['update_date']}</div>
</a>
'''
        recruitment_block = f'''<div class="section-header collapsible" onclick="toggleSection(this)">💼 招聘信息 <span class="count-badge">{total_all} 个岗位</span></div>
<div class="section-body">
{intern_card}{jobs_card}
</div>
'''
    else:
        recruitment_block = '<div class="section-header collapsible collapsed" onclick="toggleSection(this)">💼 招聘信息 <span class="count-badge">0 岗位</span></div>\n<div class="section-body hidden"><div class="empty">招聘信息每两日更新，敬请期待</div></div>\n'

    # Headline teaser: top 3 items of the latest daily report
    headline_html = ''
    if daily_reports:
        latest = daily_reports[0]
        if latest['toc_items']:
            links = ''.join(
                f'<li><a href="reports/{latest["date"]}.html">{t["title"]}</a></li>'
                for t in latest['toc_items'][:3])
            headline_html = f'''<div class="headlines">
  <div class="headlines-title">📌 最新一期头条 · <a href="reports/{latest["date"]}.html">{latest["date"]} {latest["weekday"]}</a></div>
  <ol class="headlines-list">{links}</ol>
</div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日文博资讯 | 文博·考古·博物馆行业日报</title>
<meta name="description" content="每日文博资讯 — 国内外文物博物馆、考古、文化遗产领域每日推送。AI 自动采集编撰，每天早 8:13 更新，已有 {len(daily_reports)} 天日报">
<meta name="keywords" content="文博,考古,博物馆,文化遗产,文物,文博资讯,文博日报,每日文博">
<link rel="canonical" href="https://zhangheng666.top/">
<link rel="alternate" type="application/rss+xml" title="每日文博资讯" href="https://zhangheng666.top/feed.xml">
<meta property="og:title" content="每日文博资讯">
<meta property="og:description" content="国内外文物博物馆 · 考古 · 文化遗产 · 每日推送">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="文博日报">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "每日文博资讯",
  "url": "https://zhangheng666.top/",
  "description": "国内外文物博物馆、考古、文化遗产领域每日推送",
  "potentialAction": {{
    "@type": "SearchAction",
    "target": "https://zhangheng666.top/?q={{search_term_string}}",
    "query-input": "required name=search_term_string"
  }}
}}
</script>
{index_css}
</head>
<body>

<header>
  <h1>🏛️ 每日文博资讯</h1>
  <p class="sub">国内外文物博物馆 · 考古 · 文化遗产 ｜ 每日推送</p>
  <p class="tip">📱 浏览器菜单 → 「添加到主屏幕」→ 体验接近小程序</p>
</header>

<main>

<div class="search-wrap">
  <input type="search" id="search" placeholder="🔍 搜索新闻…" autocomplete="off" aria-label="搜索新闻">
  <button class="clear" id="clear" aria-label="清除">✕</button>
</div>
<div class="result-count" id="result-count"></div>
<div class="no-results" id="no-results">😕 没有找到匹配的结果</div>
<div class="tag-cloud" id="tag-cloud"></div>

<div class="section-header collapsible" onclick="toggleSection(this)">📅 日报 <span class="count-badge">{len(daily_reports)} 天</span></div>
<div class="section-body">
{headline_html}
<div id="daily-list">
{latest_cards}
{older_cards_html}
</div>
</div>

{weekly_block}

{monthly_block}

{recruitment_block}

</main>

<footer>
  <p>由 <a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> 自动生成 ｜ 每日早 8:13 更新 ｜ <a href="about.html">关于本站</a> ｜ <a href="feed.xml">RSS 订阅</a></p>
</footer>

</body>
</html>'''
    # Inject JS (toggles + search)
    html = html.replace('</body>', '''<script>
function toggleSection(header) {
  header.classList.toggle('collapsed');
  const body = header.nextElementSibling;
  if (body && body.classList.contains('section-body')) {
    body.classList.toggle('hidden');
  }
}
function toggleOlder(btn) {
  const olderDiv = btn.previousElementSibling;
  if (olderDiv && olderDiv.classList.contains('older-cards')) {
    const isHidden = olderDiv.style.display === 'none';
    olderDiv.style.display = isHidden ? '' : 'none';
    if (isHidden) {
      btn.textContent = btn.getAttribute('data-collapse-text') || '收起 ▲';
    } else {
      btn.textContent = btn.getAttribute('data-expand-text') || btn.textContent;
    }
  }
}
(async function(){
  const searchInput = document.getElementById('search');
  const clearBtn = document.getElementById('clear');
  const noResults = document.getElementById('no-results');
  const resultCount = document.getElementById('result-count');
  const cards = document.querySelectorAll('.day-card');

  let searchData = null;
  try {
    const resp = await fetch('search-index.json');
    if (resp.ok) searchData = await resp.json();
  } catch(e) {}

  function doSearch(q) {
    q = q.trim().toLowerCase();
    let visible = 0;

    if (!q) {
      cards.forEach(c => c.classList.remove('hidden'));
      noResults.style.display = 'none';
      resultCount.style.display = 'none';
      clearBtn.style.display = 'none';
      cards.forEach(c => {
        const prev = c.querySelector('.match-preview');
        if (prev) prev.remove();
      });
      return;
    }

    clearBtn.style.display = 'block';
    const queryWords = q.split(/\\s+/).filter(Boolean);

    cards.forEach((card) => {
      const href = card.getAttribute('href');
      const cardText = card.textContent.toLowerCase();
      let matched = false;
      let previewText = '';

      for (const w of queryWords) {
        if (cardText.includes(w)) { matched = true; break; }
      }

      if (!matched && searchData) {
        const report = searchData.find(r => href && href.includes(r.date));
        if (report) {
          for (const item of report.items) {
            const itemText = (item.title + ' ' + item.body + ' ' + (item.commentary||'') + ' ' + (item.tags||[]).join(' ')).toLowerCase();
            for (const w of queryWords) {
              if (itemText.includes(w)) {
                matched = true;
                const idx = itemText.indexOf(w);
                const start = Math.max(0, idx - 30);
                const end = Math.min(itemText.length, idx + w.length + 40);
                let snippet = itemText.substring(start, end);
                if (start > 0) snippet = '…' + snippet;
                if (end < itemText.length) snippet = snippet + '…';
                const re = new RegExp('(' + w.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');
                snippet = snippet.replace(re, '<mark class="highlight">$1</mark>');
                previewText = snippet;
                break;
              }
            }
            if (matched) break;
          }
        }
      }

      if (matched) {
        card.classList.remove('hidden');
        visible++;
        let prev = card.querySelector('.match-preview');
        if (previewText) {
          if (!prev) {
            prev = document.createElement('div');
            prev.className = 'match-preview';
            card.appendChild(prev);
          }
          prev.innerHTML = previewText;
        } else {
          if (prev) prev.remove();
        }
      } else {
        card.classList.add('hidden');
        const prev = card.querySelector('.match-preview');
        if (prev) prev.remove();
      }
    });

    noResults.style.display = visible === 0 ? 'block' : 'none';
    resultCount.style.display = 'block';
    resultCount.textContent = `找到 ${visible} 天的相关报道`;
  }

  function buildTagCloud() {
    const cloud = document.getElementById('tag-cloud');
    if (!cloud) return;
    if (!searchData) { cloud.style.display = 'none'; return; }
    const counts = {};
    searchData.forEach(r => r.items.forEach(it => (it.tags||[]).forEach(t => { counts[t] = (counts[t]||0)+1; })));
    const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,14);
    if (!top.length) { cloud.style.display = 'none'; return; }
    cloud.innerHTML = '<span class="tag-cloud-label">🏷️ 按标签浏览</span>' +
      top.map(([t,n]) => `<button class="tag-cloud-chip" data-tag="${t}">#${t} <span class="chip-count">${n}</span></button>`).join('');
    cloud.querySelectorAll('.tag-cloud-chip').forEach(chip => {
      chip.addEventListener('click', function(){
        const t = this.getAttribute('data-tag');
        searchInput.value = t;
        doSearch(t);
        window.scrollTo({top: 0, behavior: 'smooth'});
      });
    });
  }
  buildTagCloud();

  searchInput.addEventListener('input', function(){
    doSearch(this.value);
  });

  clearBtn.addEventListener('click', function(){
    searchInput.value = '';
    doSearch('');
    searchInput.focus();
  });

  const params = new URLSearchParams(location.search);
  const q = params.get('q');
  if (q) {
    searchInput.value = q;
    doSearch(q);
  }
})();
</script>
</body>''')
    return html


# ───────────────── sitemap.xml ─────────────────

def build_sitemap(daily_reports, weekly_reports=None, monthly_reports=None):
    """Generate sitemap.xml listing all pages."""
    from datetime import datetime

    base = 'https://zhangheng666.top'
    urls = []

    # Homepage
    urls.append(f'''  <url>
    <loc>{base}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>''')

    # Jobs & intern pages
    urls.append(f'''  <url>
    <loc>{base}/jobs.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/about.html</loc>
    <changefreq>yearly</changefreq>
    <priority>0.3</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/intern.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>''')

    # Daily reports
    for r in sorted(daily_reports, key=lambda r: r['date'], reverse=True):
        urls.append(f'''  <url>
    <loc>{base}/reports/{r['date']}.html</loc>
    <lastmod>{r['date']}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>''')

    # Weekly reports
    if weekly_reports:
        for r in sorted(weekly_reports, key=lambda r: r['ref_date'], reverse=True):
            urls.append(f'''  <url>
    <loc>{base}/reports/weekly-{r['ref_date']}.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>''')

    # Monthly reports
    if monthly_reports:
        for r in sorted(monthly_reports, key=lambda r: r['ref_date'], reverse=True):
            urls.append(f'''  <url>
    <loc>{base}/reports/monthly-{r['ref_date']}.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>''')

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>'''
    return xml


# ───────────────── RSS feed ─────────────────

def build_rss_feed(daily_reports, limit=20):
    """Generate RSS 2.0 feed XML for the latest daily reports."""
    from datetime import datetime
    import xml.sax.saxutils as saxutils

    base = 'https://zhangheng666.top'
    sorted_reports = sorted(daily_reports, key=lambda r: r['date'], reverse=True)[:limit]

    items_xml = ''
    for r in sorted_reports:
        total = r['domestic_count'] + r['international_count']
        title = f'每日文博资讯 | {r["date"]} {r["weekday"]}'
        link = f'{base}/reports/{r["date"]}.html'
        desc = f'{r["date"]} 每日文博资讯，共 {total} 条（国内 {r["domestic_count"]} + 国际 {r["international_count"]}）'

        # Build description with item titles
        item_titles = []
        for item in r['toc_items']:
            item_titles.append(f'  <li>{saxutils.escape(item["title"])}</li>')
        desc_html = f'{saxutils.escape(desc)}<br/><br/>今日目录：<ul>{"".join(item_titles)}</ul>'

        # Parse date to RFC 822 format
        try:
            dt = datetime.strptime(r['date'], '%Y-%m-%d')
            pub_date = dt.strftime('%a, %d %b %Y 08:13:00 +0800')
        except (ValueError, TypeError):
            pub_date = ''

        items_xml += f'''    <item>
      <title>{saxutils.escape(title)}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <description>{saxutils.escape(desc_html)}</description>
      <pubDate>{pub_date}</pubDate>
    </item>
'''

    # Build channel pubDate from latest report
    latest_date = sorted_reports[0]['date'] if sorted_reports else '2026-07-11'
    try:
        dt = datetime.strptime(latest_date, '%Y-%m-%d')
        channel_pub = dt.strftime('%a, %d %b %Y 08:13:00 +0800')
    except (ValueError, TypeError):
        channel_pub = ''

    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>每日文博资讯</title>
    <link>{base}/</link>
    <description>国内外文物博物馆 · 考古 · 文化遗产 · 每日推送</description>
    <language>zh-CN</language>
    <lastBuildDate>{channel_pub}</lastBuildDate>
    <ttl>1440</ttl>
{items_xml}  </channel>
</rss>'''
    return rss


# ───────────────── 关于页面 ─────────────────

def build_about_html():
    """Generate the about page."""
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>关于本站 | 每日文博资讯</title>
<meta name="description" content="每日文博资讯 — 网站介绍、内容来源、编撰流程与免责声明">
<link rel="canonical" href="https://zhangheng666.top/about.html">
<meta property="og:title" content="关于本站 | 每日文博资讯">
<meta property="og:description" content="每日文博资讯 — 国内外文物博物馆、考古、文化遗产领域每日推送">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:url" content="https://zhangheng666.top/about.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
{CSS}
</head>
<body>
<main>
<header>
  <h1>🏛️ 关于本站</h1>
  <p class="meta">每日文博资讯 · 网站说明</p>
  <p style="margin-top:4px;font-size:.85em"><a href="index.html">← 返回首页</a></p>
</header>

<h2 class="section">📖 这是什么</h2>
<p>「每日文博资讯」是一个聚焦<strong>文物、博物馆、考古、文化遗产</strong>领域的每日资讯站点，每天推送 4–7 条国内外要闻，附带专业点评与趋势总结。内容由 AI（Claude）自动采集、筛选并编撰。</p>

<h2 class="section">🕐 更新节奏</h2>
<table>
<tr><th>栏目</th><th>更新频率</th></tr>
<tr><td>📅 日报</td><td>每天早 8:13</td></tr>
<tr><td>📰 周报</td><td>每周日</td></tr>
<tr><td>📊 月报</td><td>每月 1 日</td></tr>
<tr><td>💼 招聘 / 🌱 实习</td><td>每两天（偶数日期）</td></tr>
</table>

<h2 class="section">🗞️ 信源说明</h2>
<p>国内新闻优先采用<strong>官方机构和权威媒体</strong>：国家文物局、新华社、光明日报、中国文物报、央视及各博物馆官方发布。国际新闻采用 UNESCO、AP、BBC、The Art Newspaper、Archaeology.org 及各国博物馆官方渠道。每篇报道均附来源链接，方便核对原文。</p>

<h2 class="section">🤖 AI 编撰流程与声明</h2>
<blockquote><strong>重要声明：</strong>本站内容由 AI 自动生成，未经人工逐条核实。AI 可能出错——请务必以文末附带的原始来源链接为准，重要信息请查证官方原文后再引用。</blockquote>
<p>流程：定时抓取候选新闻 → 按信源权威性筛选 → 与近 5 天内容去重 → 生成条目与点评 → 构建页面并部署。若发现错误，欢迎在 GitHub 仓库提 issue 反馈。</p>

<h2 class="section">🔒 隐私</h2>
<p>本站为纯静态网站：<strong>不收集任何个人信息、不使用 Cookie、不接入任何统计或广告脚本</strong>。你只是阅读，我们只是展示。</p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ <a href="index.html">返回首页</a> ｜ <a href="feed.xml">RSS 订阅</a></p>
</footer>
</main>
</body>
</html>'''
    return html


# ───────────────── 主流程 ─────────────────

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)

    md_files = glob.glob(os.path.join(MD_DIR, '*.md'))
    if not md_files:
        print('No markdown files found in', MD_DIR)
        return

    daily_reports = []
    weekly_reports = []
    monthly_reports = []

    for md_path in sorted(md_files):
        fname = os.path.basename(md_path)
        print(f'Building: {fname}')

        # Read first line to detect type (avoids filename encoding issues on Windows)
        with open(md_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()

        # Determine type by title content
        if '周报' in first_line:
            data = parse_digest(md_path, 'weekly')
            if not data['ref_date']:
                print('  SKIP: could not parse weekly date')
                continue
            html = build_digest_html(data)
            html_path = os.path.join(REPORTS_DIR, f'weekly-{data["ref_date"]}.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f'  -> weekly-{data["ref_date"]}.html')
            weekly_reports.append(data)

        elif '月报' in first_line:
            data = parse_digest(md_path, 'monthly')
            if not data['ref_date']:
                print('  SKIP: could not parse monthly date')
                continue
            html = build_digest_html(data)
            html_path = os.path.join(REPORTS_DIR, f'monthly-{data["ref_date"]}.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f'  -> monthly-{data["ref_date"]}.html')
            monthly_reports.append(data)

        else:
            # Daily report - parse first, build HTML later (need prev/next)
            data = parse_md(md_path)
            if not data['date']:
                print(f'  SKIP: could not parse date')
                continue
            print(f'  -> parsed {data["date"]}')
            daily_reports.append(data)

    # Build search index JSON (daily reports only for now)
    search_data = []
    for r in daily_reports:
        items = []
        for item in r['domestic'] + r['international']:
            items.append({
                'title': item['title'],
                'body': item['body'][:200] if item['body'] else '',
                'commentary': item['commentary'],
                'tags': item.get('tags', [])
            })
        search_data.append({
            'date': r['date'],
            'weekday': r['weekday'],
            'domestic_count': r['domestic_count'],
            'international_count': r['international_count'],
            'items': items
        })
    idx_path = os.path.join(SITE_DIR, 'search-index.json')
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(search_data, f, ensure_ascii=False, indent=2)
    print(f'Search index: {idx_path} ({len(search_data)} daily reports)')

    # Build daily report HTML with prev/next navigation
    sorted_daily = sorted(daily_reports, key=lambda r: r['date'])
    for i, r in enumerate(sorted_daily):
        prev_r = sorted_daily[i - 1] if i > 0 else None
        next_r = sorted_daily[i + 1] if i < len(sorted_daily) - 1 else None
        html = build_report_html(r, prev_report=prev_r, next_report=next_r)
        html_path = os.path.join(REPORTS_DIR, f"{r['date']}.html")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
    print(f'Daily reports: {len(sorted_daily)} pages built')

    # Parse recruitment data
    recruitment_data = None
    if os.path.exists(JOBS_MD):
        recruitment_data = parse_jobs(JOBS_MD)
        if recruitment_data and recruitment_data.get('sections'):
            rec_html = build_jobs_html(recruitment_data)
            rec_path = os.path.join(SITE_DIR, 'jobs.html')
            with open(rec_path, 'w', encoding='utf-8') as f:
                f.write(rec_html)
            total = sum(len(s['items']) for s in recruitment_data['sections'])
            print(f'Jobs: {rec_path} ({total} jobs)')
        else:
            print('Jobs: no listings found in', JOBS_MD)
    else:
        print('Jobs: no source file at', JOBS_MD)

    # Parse internship data
    intern_data = None
    if os.path.exists(INTERN_MD):
        intern_data = parse_jobs(INTERN_MD)
        if intern_data and intern_data.get('sections'):
            intern_html = build_jobs_html(intern_data, page_type='intern')
            intern_path = os.path.join(SITE_DIR, 'intern.html')
            with open(intern_path, 'w', encoding='utf-8') as f:
                f.write(intern_html)
            total_intern = sum(len(s['items']) for s in intern_data['sections'])
            print(f'Intern: {intern_path} ({total_intern} internships)')
        else:
            print('Intern: no listings found in', INTERN_MD)
    else:
        print('Intern: no source file at', INTERN_MD)

    # Build index with all sections
    index_html = build_index(daily_reports, weekly_reports, monthly_reports, recruitment_data, intern_data)
    index_path = os.path.join(SITE_DIR, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_html)
    print(f'Index: {index_path} ({len(daily_reports)} 日报 + {len(weekly_reports)} 周报 + {len(monthly_reports)} 月报 + {"招聘" if recruitment_data else "无招聘"} + {"实习" if intern_data else "无实习"})')

    # Build about page
    about_html = build_about_html()
    about_path = os.path.join(SITE_DIR, 'about.html')
    with open(about_path, 'w', encoding='utf-8') as f:
        f.write(about_html)
    print(f'About: {about_path}')

    # Build robots.txt
    robots_txt = 'User-agent: *\nAllow: /\n\nSitemap: https://zhangheng666.top/sitemap.xml\n'
    with open(os.path.join(SITE_DIR, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(robots_txt)
    print('robots.txt: written')

    # Build sitemap.xml
    sitemap_xml = build_sitemap(daily_reports, weekly_reports, monthly_reports)
    sitemap_path = os.path.join(SITE_DIR, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write(sitemap_xml)
    print(f'Sitemap: {sitemap_path} ({len(daily_reports)} daily + {len(weekly_reports)} weekly + {len(monthly_reports)} monthly)')

    # Build RSS feed
    rss_xml = build_rss_feed(daily_reports)
    rss_path = os.path.join(SITE_DIR, 'feed.xml')
    with open(rss_path, 'w', encoding='utf-8') as f:
        f.write(rss_xml)
    print(f'RSS feed: {rss_path} ({min(len(daily_reports), 20)} items)')

    print('\nDone! Run push to deploy.')


if __name__ == '__main__':
    main()

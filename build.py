#!/usr/bin/env python3
"""
Build HTML reports from Markdown files and rebuild index.html.
Usage: python build.py
"""
import os, re, glob

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(SITE_DIR, 'reports')
MD_DIR = os.path.join(os.path.dirname(SITE_DIR), '日报')

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
  footer {
    text-align: center; padding: 28px 0 16px;
    color: var(--muted); font-size: .78em;
    border-top: 1px solid var(--border); margin-top: 24px;
  }
  footer a { color: var(--accent); }
</style>"""


def parse_md(filepath):
    """Parse a markdown report and return structured data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'title': '', 'date': '', 'weekday': '',
        'domestic': [], 'international': [], 'trends': [],
        'domestic_count': 0, 'international_count': 0,
        'toc_items': []
    }

    lines = content.split('\n')

    # Parse title line: # 🏛️ 文博资讯日报 | 2026年7月11日（周六）
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
            # Skip TOC section in MD - we generate our own
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
            item_idx += 1
            current_item = {
                'id': f'item{item_idx}',
                'number': item_idx,
                'title': title,
                'sources': [],
                'body': '',
                'commentary': ''
            }
            data[current_section].append(current_item)
            data['toc_items'].append({'id': f'item{item_idx}', 'title': title})
            i += 1
            continue

        # Source links line
        src_match = re.findall(r'📎\s*\[(.+?)\]\((.+?)\)', line)
        if src_match and current_item:
            current_item['sources'] = [{'name': s[0], 'url': s[1]} for s in src_match]
            i += 1
            # Skip blank line after sources
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Blockquote commentary
        if line.startswith('> ') and current_item:
            commentary = line.lstrip('> ').strip()
            # Remove **点评：** prefix
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

        # Body text - accumulate non-empty, non-separator lines
        if current_item and line.strip() and not line.startswith('---') and not line.startswith('>'):
            if current_item['body']:
                current_item['body'] += '\n' + line
            else:
                current_item['body'] = line

        i += 1

    data['domestic_count'] = len(data['domestic'])
    data['international_count'] = len(data['international'])

    return data


def build_report_html(data):
    """Generate HTML for a single report."""
    total = data['domestic_count'] + data['international_count']

    # TOC HTML
    toc_html = '<div class="toc">\n  <details open>\n    <summary><strong>📑 目录</strong></summary>\n    <ol>\n'
    for item in data['toc_items']:
        toc_html += f'      <li><a href="#{item["id"]}">{item["title"]}</a></li>\n'
    toc_html += '    </ol>\n  </details>\n</div>'

    # News items HTML
    def render_items(items, section_label):
        html = f'<h2 class="section">{section_label}</h2>\n\n'
        for item in items:
            html += f'<h3 id="{item["id"]}">{item["number"]}. {item["title"]}</h3>\n'

            # Source links
            if item['sources']:
                src_parts = []
                for s in item['sources']:
                    src_parts.append(f'<a href="{s["url"]}" target="_blank" rel="noopener">{s["name"]}</a>')
                html += '<p>📎 ' + ' | '.join(src_parts) + '</p>\n\n'

            # Body
            if item['body']:
                html += f'<p>{item["body"]}</p>\n\n'

            # Commentary
            if item['commentary']:
                html += f'<blockquote><strong>点评：</strong> {item["commentary"]}</blockquote>\n\n'

            html += '<hr>\n\n'
        return html

    domestic_html = render_items(data['domestic'], '🇨🇳 国内要闻')
    international_html = render_items(data['international'], '🌍 国际要闻')

    # Trends table
    trends_html = '<h2 class="section">📊 今日趋势总结</h2>\n\n<table>\n'
    for i, row in enumerate(data['trends']):
        tag = 'th' if i == 0 else 'td'
        trends_html += '<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in row) + '</tr>\n'
    trends_html += '</table>\n'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>文博资讯日报 | {data['date']}</title>
<meta property="og:title" content="文博资讯日报 | {data['date']}">
<meta property="og:description" content="{data['date']} 文博资讯日报，共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）">
<meta property="og:image" content="https://zhangheng0610-nb.github.io/wenbo-daily/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng0610-nb.github.io/wenbo-daily/reports/{data['date']}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="文博资讯日报">
<meta name="twitter:card" content="summary_large_image">
{CSS}
</head>
<body>

<header>
  <h1>🏛️ 文博资讯日报</h1>
  <p class="meta">{data['date']} · {data['weekday']} ｜ 共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）</p>
  <p style="margin-top:4px;font-size:.85em"><a href="../index.html">← 返回目录</a></p>
</header>

{toc_html}

{domestic_html}
{international_html}
{trends_html}

<hr>

<p><em>本日报由 Claude 自动采集编撰 | {data['date']}</em></p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">文博资讯日报</a> ｜ 每日早 8:13 自动更新</p>
</footer>

</body>
</html>'''
    return html


def build_index(reports):
    """Rebuild index.html from list of report data dicts."""
    # Sort by date descending
    reports = sorted(reports, key=lambda r: r['date'], reverse=True)

    cards = ''
    for i, r in enumerate(reports):
        total = r['domestic_count'] + r['international_count']
        badge = '<span class="badge">最新</span>' if i == 0 else ''
        cards += f'''
<a class="day-card" href="reports/{r['date']}.html">
  <span class="date">📅 {r['date']}</span>
  <span class="weekday">{r['weekday']}</span>
  {badge}
  <div class="count">📰 共 {total} 条 ｜ 国内 {r['domestic_count']} + 国际 {r['international_count']}</div>
</a>'''

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
  .empty { text-align: center; color: var(--muted); padding: 48px 0; }
</style>"""

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>文博资讯日报</title>
<meta property="og:title" content="文博资讯日报">
<meta property="og:description" content="国内外文物博物馆 · 考古 · 文化遗产 · 每日推送">
<meta property="og:image" content="https://zhangheng0610-nb.github.io/wenbo-daily/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng0610-nb.github.io/wenbo-daily/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="文博资讯日报">
<meta name="twitter:card" content="summary_large_image">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="文博日报">
{index_css}
</head>
<body>

<header>
  <h1>🏛️ 文博资讯日报</h1>
  <p class="sub">国内外文物博物馆 · 考古 · 文化遗产 ｜ 每日推送</p>
  <p class="tip">📱 浏览器菜单 → 「添加到主屏幕」→ 体验接近小程序</p>
</header>

<div class="search-wrap">
  <input type="search" id="search" placeholder="🔍 搜索新闻…" autocomplete="off">
  <button class="clear" id="clear" aria-label="清除">✕</button>
</div>
<div class="result-count" id="result-count"></div>
<div class="no-results" id="no-results">😕 没有找到匹配的结果</div>

<div id="card-list">
{cards}
</div>
<footer>
  <p>由 <a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">文博资讯日报</a> 自动生成 ｜ 每日早 8:13 更新</p>
</footer>

</body>
</html>'''
    # Inject search JS
    html = html.replace('</body>', '''<script>
(async function(){
  const searchInput = document.getElementById('search');
  const clearBtn = document.getElementById('clear');
  const cardList = document.getElementById('card-list');
  const noResults = document.getElementById('no-results');
  const resultCount = document.getElementById('result-count');
  const cards = cardList.querySelectorAll('.day-card');

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
            const itemText = (item.title + ' ' + item.body + ' ' + (item.commentary||'')).toLowerCase();
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


def main():
    # Ensure reports directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # Find all markdown files
    md_files = glob.glob(os.path.join(MD_DIR, '*.md'))
    if not md_files:
        print('No markdown files found in', MD_DIR)
        return

    all_reports = []
    for md_path in sorted(md_files):
        print(f'Building: {os.path.basename(md_path)}')
        data = parse_md(md_path)
        if not data['date']:
            print(f'  SKIP: could not parse date')
            continue

        html = build_report_html(data)
        html_path = os.path.join(REPORTS_DIR, f"{data['date']}.html")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'  -> {html_path}')

        all_reports.append(data)

    # Build search index JSON
    search_data = []
    for r in all_reports:
        items = []
        for item in r['domestic'] + r['international']:
            items.append({
                'title': item['title'],
                'body': item['body'][:200] if item['body'] else '',
                'commentary': item['commentary']
            })
        search_data.append({
            'date': r['date'],
            'weekday': r['weekday'],
            'domestic_count': r['domestic_count'],
            'international_count': r['international_count'],
            'items': items
        })
    import json
    idx_path = os.path.join(SITE_DIR, 'search-index.json')
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(search_data, f, ensure_ascii=False, indent=2)
    print(f'Search index: {idx_path}')

    # Build index
    if all_reports:
        index_html = build_index(all_reports)
        index_path = os.path.join(SITE_DIR, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_html)
        print(f'Index: {index_path} ({len(all_reports)} reports)')

    print('\nDone! Run push to deploy.')


if __name__ == '__main__':
    main()

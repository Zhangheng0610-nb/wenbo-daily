"""Project published digital reporting into a recent feed, separate from NCHA statistics."""
import json
from html import escape
from pathlib import Path
from automation.reader_product import reader_events
from automation.daily_scope import daily_scope_rejection
from automation.product import safe_url
from digital_trend import admission_for_record, classify_topics


def digital_news(root, reports):
    items = []
    for event in reader_events(root, reports):
        if daily_scope_rejection(event):
            continue
        admission = admission_for_record(event['title'], event['summary'], allow_body_only=True)
        if not admission:
            continue
        update = event['updates'][0]
        items.append({
            'eventId': event['id'], 'title': event['title'], 'summary': event['summary'],
            'reportDate': update['reportDate'], 'publishedDate': update['publishedDate'],
            'reportUrl': update['url'], 'sources': update['documents'],
            'topics': classify_topics(event['title'] + ' ' + event['summary']),
            'matchedKeywords': admission['matched_keywords'],
        })
    return {'schemaVersion': 1, 'asOf': max((r['date'] for r in reports), default=''),
            'scope': 'published_reporting_latest_issue_minus_13_days',
            'countUnit': 'editorial_event', 'items': items}


def render_digital_news(data, prefix='../'):
    rows = []
    for item in data['items']:
        sources = ' · '.join(dict.fromkeys(s['title'].split('：')[0] for s in item['sources']))
        original_links = ' · '.join('<a href="' + escape(s['url'], quote=True) + '" target="_blank" rel="noopener noreferrer">' + escape(s['title']) + '</a>' for s in item['sources'] if safe_url(s.get('url')))
        rows.append('<article class="digital-news-item"><p class="digital-news-meta">' + escape(item['reportDate']) + ' 收录 · ' + escape(sources) + '</p><h3><a href="' + prefix + escape(item['reportUrl'], quote=True) + '">' + escape(item['title']) + '</a></h3><p class="digital-news-excerpt">' + escape(item['summary'][:110]) + '</p><details><summary>原文链接</summary>' + original_links + '</details></article>')
    older = '<details class="digital-news-more"><summary>其余 ' + str(len(rows)-4) + ' 条</summary>' + ''.join(rows[4:]) + '</details>' if len(rows)>4 else ''
    content = ''.join(rows[:4]) + older if rows else '<p>近两周已刊报道中暂无匹配内容。<a href="../index.html">查看最新日报</a></p>'
    return '<section class="digital-news" aria-labelledby="digital-news-title"><div class="reader-heading"><h2 id="digital-news-title">近期数字化动向</h2><span class="digital-news-meta">近两周 · ' + str(len(rows)) + ' 条</span></div><p class="digital-news-meta">汇集本站已刊报道 · 截至 ' + escape(data['asOf']) + '</p>' + content + '</section>'


def write_digital_news(root, reports):
    root = Path(root)
    data = digital_news(root, reports)
    (root/'digital-news.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return render_digital_news(data)

"""Reader-facing projections: explicit editorial event identity, dates, and source documents.

Never infer event identity solely from a shared source URL: a digest can contain
several events. Never use the report's issue date as a source publication date.
"""
import json
from pathlib import Path
from datetime import date,timedelta
from html import escape
from automation.evidence_audit import audit_for
from automation.product import safe_url

def reader_events(root,reports):
    root=Path(root)
    if not reports:return []
    cutoff=date.fromisoformat(max(r['date'] for r in reports))-timedelta(days=13)
    groups={}
    for report in sorted(reports,key=lambda r:r['date'],reverse=True):
        if date.fromisoformat(report['date'])<cutoff:continue
        path=root/'content/候选'/f'{report["date"]}.json'
        candidates=json.loads(path.read_text(encoding='utf-8')).get('candidates',[]) if path.exists() else []
        for item in report.get('ordered_items') or report['domestic']+report['international']:
            audit=audit_for(report['date'],item)
            if audit and audit['status']!='supported':continue
            matching=[c for c in candidates if c.get('selectedForDaily') and
                      c.get('dailyItemTitle',c.get('title'))==item['title'] and
                      c.get('dailyItemNumber')==item['number']]
            candidate=matching[0] if len(matching)==1 else {}
            key=candidate.get('eventId') or f'entry-{report["date"]}-{item["id"]}'
            occurrence={'reportDate':report['date'],'url':f'reports/{report["date"]}.html#{item["id"]}',
                        'title':item['title'],'publishedDate':candidate.get('publishedDate'),
                        'newDevelopment':bool(candidate.get('newDevelopment')),
                        'documents':[{'title':s['name'],'url':s['url']} for s in item['sources'] if safe_url(s.get('url'))]}
            if key not in groups:
                groups[key]={'id':key,'title':item['title'],'tags':item.get('tags',[]),
                             'summary':item['body'],'updates':[]}
            groups[key]['updates'].append(occurrence)
    return list(groups.values())

def write_reader_product(root,reports):
    root=Path(root); events=reader_events(root,reports)
    (root/'reader-events.json').write_text(json.dumps({'schemaVersion':1,'window':'latest-report-minus-13-days','events':events},ensure_ascii=False,separators=(',',':'))+'\n', encoding='utf-8')
    rows=[]
    for event in events:
        update=event['updates'][0]
        tags=' · '.join(event['tags'][:3])
        source_date=update['publishedDate'] or '原文日期待核'
        history = '<details class="event-history"><summary>查看收录记录与原文</summary>' + ''.join('<p><a href="' + u['url'] + '">' + u['reportDate'] + (' · 新进展' if u['newDevelopment'] else ' · 日报记录') + '</a></p>' + ''.join('<p><a href="' + escape(d['url'], quote=True) + '" target="_blank" rel="noopener noreferrer">' + escape(d['title']) + '</a></p>' for d in u['documents']) for u in event['updates']) + '</details>'
        rows.append(f'<article class="reader-entry" data-report-date="{update['reportDate']}" data-topics="{escape(" ".join(event["tags"]),quote=True)}"><p class="reader-meta">收录 {update["reportDate"]} · 原文 {escape(source_date)}</p><h3><a href="{update["url"]}">{escape(event["title"])}</a></h3><p>{escape(event["summary"][:140])}</p><p class="reader-meta">{escape(tags)} · {len(event["updates"])} 次日报收录</p><button class="save-entry" data-save-id="{escape(event["id"],quote=True)}" data-save-url="{update["url"]}" data-save-title="{escape(event["title"],quote=True)}" aria-pressed="false">收藏</button>{history}</article>')
    section='<section class="reader-feed" data-latest="' + max((r['date'] for r in reports), default='') + '" aria-labelledby="followup-heading"><div class="reader-heading"><h2 id="followup-heading">近期新闻</h2><a href="reading.html">我的收藏</a></div><p class="reader-meta">近两周新闻，按最近收录排序。</p><div class="reader-controls"><label class="reader-period">范围<select id="reader-period"><option value="earlier">此前新闻</option><option value="all">近两周全部</option></select></label><label class="reader-keyword">关键词<input id="reader-query" type="search" placeholder="机构、地点或事件" aria-label="筛选近两周新闻"></label><label class="reader-filter">主题 <select id="reader-topic"><option value="">全部</option><option value="考古">考古</option><option value="博物馆">博物馆</option><option value="文物保护">文物保护</option><option value="政策">政策</option><option value="数字">数字化</option></select></label><button id="reader-reset" type="button">清除筛选</button></div><p id="reader-result" role="status" aria-live="polite"></p>'+''.join(rows)+'<button id="reader-more" type="button" hidden>查看更多</button><p><a href="search.html">检索更多主题与历史进展 →</a></p></section>'
    page=root/'index.html';html=page.read_text(encoding='utf-8');html=html.replace('<section aria-labelledby="recent-heading">',section+'<section aria-labelledby="recent-heading">',1)
    if section not in html:
        html=html.replace('<footer>',section+'<footer>',1)
    page.write_text(html, encoding='utf-8')
    (root/'reading.html').write_text('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>我的收藏 | 文博</title></head><body><header><h1>我的收藏</h1><p>保存报道和岗位，方便继续阅读或申请。收藏仅保存在当前浏览器；清除网站数据后会丢失，不会跨设备同步。</p></header><section id="reading-list" aria-label="收藏条目"><p>启用 JavaScript 后可读取此浏览器的收藏。</p></section><p id="save-message" role="status" aria-live="polite"></p><footer><a href="index.html">返回资讯</a> · <a href="jobs.html">查看招聘机会</a></footer></body></html>''', encoding='utf-8')

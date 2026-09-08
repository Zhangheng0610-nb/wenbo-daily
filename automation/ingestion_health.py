"""Expose source observation evidence, never use a page build as a collection time."""
import json
from datetime import date, timedelta
from html import escape
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def collection_observations(root):
    """Latest actual attempts, independently of the latest published daily."""
    panel = {}
    for path in sorted((root / 'content/监测').glob('????-??-??.json')):
        for entry in load(path).get('coverage', []):
            if entry.get('runType') != 'live' or entry.get('mode') != 'operational':
                continue
            stamp = entry.get('checkedAt') or ''
            source = entry.get('sourceId')
            if source and stamp and stamp > (panel.get(source, {}).get('checkedAt') or ''):
                panel[source] = {key: entry.get(key) for key in
                                 ('sourceId', 'checkedAt', 'status', 'scanStatus', 'rawCount', 'note')}
    digital = {}
    for path in sorted((root / 'content/数字趋势监测').glob('????-??-??.json')):
        entry = load(path)
        stamp = entry.get('checkedAt') or ''
        # Historical scans cannot establish today's collection health.
        if stamp[:10] != entry.get('date') or entry.get('runType') == 'replay':
            continue
        if stamp > (digital.get('checkedAt') or ''):
            digital = {key: entry.get(key) for key in
                       ('checkedAt', 'status', 'contentItemsNew', 'fetchFailed', 'parseFailed', 'note')}
    return {'panel': list(panel.values()), 'digital': digital}


def write_health(root, latest):
    root = Path(root)
    rows = []
    if latest:
        for offset in range(7):
            day = (date.fromisoformat(latest) - timedelta(days=offset)).isoformat()
            panel = load(root / 'content/监测' / (day + '.json'))
            discovery = load(root / 'content/发现' / (day + '.json'))
            editorial = load(root / 'content/候选' / (day + '.json'))
            digital = load(root / 'content/数字趋势监测' / (day + '.json'))
            scans = discovery.get('sourceScans', [])
            # Historical files sometimes called a zero-date parser successful.
            usable = sum(s.get('status') == 'checked' and s.get('datedLinks', 0) > 0 for s in scans)
            coverage = [c for c in panel.get('coverage', []) if c.get('runType') == 'live']
            rows.append({'date': day, 'checkedAt': max((c.get('checkedAt') or '' for c in coverage), default='') or None,
                         'panelItems': len(panel.get('items', [])),
                         'panelChecks': len(coverage), 'usableDiscoverySources': usable,
                         'discoverySources': len(scans),
                         'queriesAttempted': discovery.get('summary', {}).get('queriesAttempted'),
                         'queriesSucceeded': discovery.get('summary', {}).get('queriesSucceeded'),
                         'selected': editorial.get('summary', {}).get('selected'),
                         'digitalCheckedAt': digital.get('checkedAt'),
                         'digitalStatus': digital.get('status'),
                         'digitalNewItems': digital.get('contentItemsNew'),
                         'publicationWindow': panel.get('scanAudit', {}).get('publicationWindow'),
                         'lateArrivalCount': panel.get('scanAudit', {}).get('lateArrivalCount')})
    result = {'schemaVersion': 2, 'latestReport': latest, 'days': rows,
              'observations': collection_observations(root),
              'meaning': 'Fixed-panel counts are source articles by publication date; they are not unique events or proof of full coverage. Build time is not collection time.'}
    (root / 'ingestion-health.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def show(value):
        if isinstance(value, str) and 'T' in value and value.endswith('+08:00'):
            value = value[5:19].replace('T', ' ')
        return escape(str(value)) if value is not None else '未记录'
    body = ''.join('<tr>' + ''.join('<td>' + show(v) + '</td>' for v in (
        r['date'], r['checkedAt'], r['panelItems'],
        f"{r['usableDiscoverySources']}/{r['discoverySources']}",
        f"{show(r['queriesSucceeded'])}/{show(r['queriesAttempted'])}", r['selected'],
        r['digitalCheckedAt'], r['digitalNewItems'])) + '</tr>' for r in rows)
    names = {row['id']: row['name'] for row in load(root / 'heatmap-data.json').get('coverage', {}).get('panel', [])}
    states = {'success': '检查完成，有收录', 'no_update': '检查完成，本期无新增',
              'partial': '部分覆盖', 'failed': '检查失败', 'parse_failed': '解析失败'}
    observation_rows = ''.join('<tr><td>' + show(names.get(row['sourceId'], row['sourceId'])) +
        '</td><td>' + show(row.get('checkedAt')) + '</td><td>' +
        show(states.get(row.get('status'), '状态未知')) + '</td><td>' +
        show(row.get('rawCount')) + '</td><td>' + show(row.get('note') or '—') + '</td></tr>'
        for row in result['observations']['panel'])
    latest_row = rows[0] if rows else {}
    panel_entries = result['observations']['panel']
    panel_complete = sum(row.get('status') in ('success', 'no_update') for row in panel_entries)
    trend = result['observations']['digital']
    trend_labels = {'scan_success_no_update': '已检查，暂无新增', 'scan_success_with_update': '已检查，有新增',
                    'fetch_failed': '抓取失败', 'parse_failed': '解析失败'}
    overview = ('<section class="health-overview" aria-label="更新概览">'
                '<a class="health-card" href="index.html"><span>最近一期日报</span><strong>' +
                show(latest_row.get('selected')) + ' 条</strong><small>' + show(latest) + ' · 阅读精选 →</small></a>'
                '<a class="health-card" href="#source-checks"><span>固定信源最近检查</span><strong>' +
                str(panel_complete) + '/' + str(len(names)) + ' 完整</strong><small>查看逐源时间与缺口 ↓</small></a>'
                '<a class="health-card" href="digital-trends.html"><span>数字趋势最近检查</span><strong>' +
                show(trend_labels.get(trend.get('status'), '尚无检查记录')) + '</strong><small>' +
                show(trend.get('checkedAt')) + ' · 查看趋势 →</small></a></section>')
    observations_html = ('<h2 id="source-checks">各信源最近一次实际检查</h2><p>以下保留最近一次尝试，失败不会被先前成功记录遮盖。'
                         '历史回放不计入实际检查；是否延迟请结合检查时间判断。</p>'
                         '<div class="table-scroll" role="region" aria-label="各信源检查记录，可横向滚动" tabindex="0">'
                         '<table><thead><tr><th>信源</th><th>检查时间</th><th>当次结果</th><th>原始发现</th><th>说明</th>'
                         '</tr></thead><tbody>' + observation_rows + '</tbody></table></div>')
    (root / 'data-health.html').write_text('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>采集与更新记录 | 文博</title><style>main{max-width:1120px;margin:auto;padding:24px}th,td{padding:12px;text-align:left;border-bottom:1px solid #8997ac55}table{border-collapse:collapse;min-width:940px}p{line-height:1.8}.table-scroll{overflow:auto}td{font-variant-numeric:tabular-nums;white-space:nowrap}td:last-child{white-space:normal;min-width:160px;max-width:440px}@media(max-width:600px){main{padding:16px 0}main h1{font-size:26px;line-height:1.4}}details{margin:16px 0}.health-overview{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:14px;margin:24px 0}.health-card{display:flex;flex-direction:column;gap:12px;padding:20px;border:1px solid #8997ac55;border-radius:14px;text-decoration:none;color:inherit}.health-card:hover,.health-card:focus-visible{border-color:#497d8b;box-shadow:0 4px 16px #34506415}.health-card strong{font-size:24px;line-height:1.4}.health-card small{line-height:1.6;opacity:.8}</style></head><body><main><h1>采集与更新记录</h1><p>页面重新构建不等于抓到了新新闻。时间均为北京时间。这里分别列出原站检查、可解析的发现入口、搜索执行和日报入选结果，帮助判断内容少在哪一步。</p>''' + overview + '''<details><summary>如何理解这些数字</summary><p>固定源文章量按原文发布日期统计，包含补收与历史记录，不等于独立事件量。发现入口只有解析到带日期链接才计入可用；零条解析结果不能证明原站没有新闻。数字新增为 0 表示该次没有新增，未记录表示缺少运行证据。</p></details><div class="table-scroll" role="region" aria-label="最近七期采集记录，可横向滚动" tabindex="0"><table><thead><tr><th>日期</th><th>固定源实际检查时间</th><th>固定源文章</th><th>发现入口可解析/总数</th><th>搜索成功/尝试</th><th>日报入选</th><th>数字趋势检查时间</th><th>数字新增</th></tr></thead><tbody>''' + body + '''</tbody></table></div><p>日报采用近 7 天发现窗口；正式固定源巡检也回看近 7 天，补收保留原文日期，实际发现时间另行记录。早间日报涵盖截至检查时可核实的信息，不代表当天尚未发生的全部新闻。</p>''' + observations_html + '''<p><a href="index.html">阅读日报</a> · <a href="command-center/">行业观察</a> · <a href="ingestion-health.json">下载运行记录</a></p></main></body></html>''', encoding='utf-8')
    return result

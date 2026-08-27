#!/usr/bin/env python3
"""
build_digital_page.py — 生成「文博数字化趋势」交互页面 digital-trends.html

数据来自 digital-data.json(ECharts 5 + dataZoom 缩放联动粒度切换:月→周→天)。
"""
import os, json, sys

if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def build_page(html_path, data_path):
    with open(data_path, encoding='utf-8') as f:
        data = json.load(f)

    stats = data['stats']
    total = stats['total']
    core_n = stats['levels'].get('core', 0)
    tech_n = stats['levels'].get('tech', 0)
    ext_n = stats['levels'].get('ext', 0)
    rng = data['range']

    # 年度分布(用于统计卡片)
    year_cnt = {}
    for it in data['items']:
        y = it['d'][:4]
        year_cnt[y] = year_cnt.get(y, 0) + 1
    year_html = ' · '.join(f'{y}年 <b>{c}</b>' for y, c in sorted(year_cnt.items()))

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>文博数字化趋势 | 每日文博资讯</title>
<meta name="description" content="国家文物局「数字化」相关新闻趋势 — {rng['start']} 至 {rng['end']}，共 {total} 条。按年月周天粒度自由缩放查看。">
<meta name="keywords" content="文博数字化,智慧博物馆,数字藏品,数字化趋势,文博趋势,数据可视化">
<link rel="canonical" href="https://zhangheng666.top/digital-trends.html">
<meta property="og:title" content="文博数字化趋势 | 每日文博资讯">
<meta property="og:description" content="国家文物局数字化相关新闻 {total} 条 · {rng['start']} 至 {rng['end']}">
<meta property="og:url" content="https://zhangheng666.top/digital-trends.html">
<meta property="og:type" content="website">
<style>
  :root {{
    --bg: #f7f5f2; --card: #fff; --ink: #222; --muted: #777;
    --accent: #2563eb; --accent2: #0d9488; --accent3: #d97706;
    --line: #e5e0d8; --shadow: 0 2px 12px rgba(0,0,0,.06);
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--ink); font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.6; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 18px 60px; }}
  header {{ text-align: center; padding: 18px 0 6px; }}
  h1 {{ font-size: 1.7em; letter-spacing: .5px; }}
  .sub {{ color: var(--muted); font-size: .92em; margin-top: 8px; }}
  .sub a {{ color: var(--accent); text-decoration: none; }}

  .stats {{ display: flex; gap: 14px; flex-wrap: wrap; justify-content: center; margin: 22px 0 6px; }}
  .stat {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 22px; box-shadow: var(--shadow); text-align: center; min-width: 130px; }}
  .stat b {{ display: block; font-size: 1.7em; color: var(--accent); }}
  .stat span {{ font-size: .82em; color: var(--muted); }}
  .stat.core b {{ color: var(--accent); }}
  .stat.tech b {{ color: var(--accent2); }}
  .stat.ext b {{ color: var(--accent3); }}
  .years {{ text-align: center; color: var(--muted); font-size: .88em; margin: 8px 0 4px; }}
  .years b {{ color: var(--ink); }}

  .chart-card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 16px 14px 10px; margin-top: 16px; box-shadow: var(--shadow); }}
  #chart {{ width: 100%; height: 420px; }}
  .hint {{ color: var(--muted); font-size: .8em; text-align: center; padding: 4px 0 8px; }}
  .hint kbd {{ background: #eee; border: 1px solid #ccc; border-radius: 4px; padding: 0 6px; font-size: .9em; }}

  .list-card {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; margin-top: 18px; box-shadow: var(--shadow); overflow: hidden; }}
  .list-head {{ display: flex; justify-content: space-between; align-items: center; padding: 13px 18px; border-bottom: 1px solid var(--line); background: #faf8f5; }}
  .list-head h2 {{ font-size: 1.05em; }}
  .list-head .tag {{ color: var(--muted); font-size: .82em; }}
  #period-list {{ padding: 6px 0; }}
  .p-item {{ display: flex; gap: 12px; align-items: baseline; padding: 10px 18px; border-bottom: 1px dashed var(--line); }}
  .p-item:last-child {{ border-bottom: none; }}
  .p-date {{ color: var(--muted); font-size: .8em; white-space: nowrap; }}
  .p-title {{ flex: 1; }}
  .p-title a {{ color: var(--ink); text-decoration: none; }}
  .p-title a:hover {{ color: var(--accent); text-decoration: underline; }}
  .p-level {{ font-size: .72em; border-radius: 4px; padding: 1px 7px; color: #fff; white-space: nowrap; }}
  .p-level.core {{ background: var(--accent); }}
  .p-level.tech {{ background: var(--accent2); }}
  .p-level.ext {{ background: var(--accent3); }}
  .empty {{ color: var(--muted); text-align: center; padding: 26px 0; font-size: .92em; }}

  .method {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 16px 20px; margin-top: 18px; box-shadow: var(--shadow); font-size: .88em; color: #444; }}
  .method h3 {{ font-size: 1em; margin-bottom: 8px; }}
  .method ul {{ padding-left: 20px; }}
  .method li {{ margin: 4px 0; }}

  footer {{ text-align: center; color: var(--muted); font-size: .84em; margin-top: 26px; }}
  footer a {{ color: var(--accent); text-decoration: none; }}
</style>
<script src="echarts.min.js"></script>
</head>
<body>
<div class="wrap">
  <header>
    <h1>📈 文博数字化趋势</h1>
    <div class="sub">数据源：<a href="http://www.ncha.gov.cn/col/col722/index.html" target="_blank">国家文物局 · 文物新闻</a> ｜ {rng['start']} 至 {rng['end']} ｜ 每日本站更新时增量刷新</div>
  </header>

  <div class="stats">
    <div class="stat"><b>{total}</b><span>数字化相关新闻</span></div>
    <div class="stat core"><b>{core_n}</b><span>核心词命中</span></div>
    <div class="stat tech"><b>{tech_n}</b><span>技术词命中</span></div>
    <div class="stat ext"><b>{ext_n}</b><span>场景词命中</span></div>
  </div>
  <div class="years">年度分布：{year_html}</div>

  <div class="chart-card">
    <div id="chart"></div>
    <div class="hint">🖱️ 滚轮缩放 · 拖拽平移 · 双击回到全部 ｜ 缩放跨度会自动切换 <kbd>月</kbd> / <kbd>周</kbd> / <kbd>天</kbd> 粒度 ｜ 点击数据点查看该周期新闻明细</div>
  </div>

  <div class="list-card">
    <div class="list-head"><h2 id="period-title">📋 点击图表数据点查看明细</h2><span class="tag" id="period-count"></span></div>
    <div id="period-list"><div class="empty">上方图表中点击任意数据点，这里会列出该周期内所有数字化相关新闻。</div></div>
  </div>

  <div class="method">
    <h3>📌 统计口径说明</h3>
    <ul>
      <li><b>信源</b>：国家文物局官网「文物新闻」栏目全部文章（2021-01 至今，约 1.2 万条），非抽样。</li>
      <li><b>判定</b>：标题命中「核心词（数字化/数字藏品/智慧博物馆等）」「技术词（AI/大数据/元宇宙/VR 等）」「场景词（云展览/沉浸式/信息化等）」任一即计入；另对每周「文物动态摘编」正文做补充提取（条目需标题含数字化词，或正文命中数字化核心表达），标题完全相同的跨周转载已去重。</li>
      <li><b>口径</b>：计的是「新闻条数」，同一新闻可能因系列报道在列表中多次出现，趋势反映的是行业报道热度。</li>
      <li><b>局限</b>：关键词法存在少量漏判/误判；2021 年前部分数据未纳入；标注来源的条目可点击跳转原文核验。</li>
    </ul>
  </div>

  <footer><a href="/">← 返回首页</a> ｜ <a href="/about.html">关于本站</a></footer>
</div>

<script>
var DATA_URL = 'digital-data.json';
var LEVEL_NAMES = {{ 'core': '核心', 'tech': '技术', 'ext': '场景' }};
var LEVEL_COLORS = {{ 'core': '#2563eb', 'tech': '#0d9488', 'ext': '#d97706' }};

fetch(DATA_URL).then(function(r){{ return r.json(); }}).then(function(data){{
  init(data);
}}).catch(function(e){{
  document.getElementById('chart').innerHTML = '<div class="empty">⚠️ 数据加载失败：' + e + '</div>';
}});

function init(data) {{
  // 构建各粒度索引: key -> {{count, items[]}}
  var byMonth = {{}}, byWeek = {{}}, byDay = {{}};
  data.by_month.forEach(function(s){{ byMonth[s.key] = s; }});
  data.by_week.forEach(function(s){{ byWeek[s.key] = s; }});
  data.by_day.forEach(function(s){{ byDay[s.key] = s; }});

  var rangeStart = data.range.start, rangeEnd = data.range.end;

  // ---- 时间轴工具 ----
  function pad(n) {{ return n < 10 ? '0' + n : '' + n; }}
  function fmtYMD(d) {{ return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }}
  function addDays(d, n) {{ var x = new Date(d); x.setDate(x.getDate() + n); return x; }}

  // 月粒度完整轴
  function monthKeys() {{
    var out = [], d = new Date(rangeStart.slice(0, 7) + '-01');
    var end = new Date(rangeEnd.slice(0, 7) + '-01');
    while (d <= end) {{
      out.push(d.getFullYear() + '-' + pad(d.getMonth() + 1));
      d.setMonth(d.getMonth() + 1);
    }}
    return out;
  }}
  // 周粒度完整轴(yyyy-Wnn)
  function weekKeys() {{
    var out = [];
    var d = new Date(rangeStart + 'T00:00:00');
    // 对齐到 ISO 周一
    var day = (d.getDay() + 6) % 7;
    d = addDays(d, -day);
    var end = new Date(rangeEnd + 'T00:00:00');
    while (d <= end) {{
      var iso = getISOWeek(d);
      var key = d.getFullYear() + '-W' + pad(iso.week);
      if (out.indexOf(key) === -1) out.push(key);
      d = addDays(d, 7);
    }}
    return out;
  }}
  function getISOWeek(d) {{
    var t = new Date(d.getTime());
    var day = (t.getDay() + 6) % 7;
    t.setDate(t.getDate() - day + 3);
    var firstThu = new Date(t.getFullYear(), 0, 4);
    var diff = ((t - firstThu) / 86400000);
    return {{ week: 1 + Math.ceil(diff / 7), year: t.getFullYear() }};
  }}
  // 天粒度完整轴
  function dayKeys() {{
    var out = [], d = new Date(rangeStart + 'T00:00:00');
    var end = new Date(rangeEnd + 'T00:00:00');
    while (d <= end) {{
      out.push(fmtYMD(d));
      d = addDays(d, 1);
    }}
    return out;
  }}

  // 生成某粒度 series: xAxis 全轴, 空数据用 0(连续折线)
  function buildSeries(keys, map, displayFmt) {{
    var cats = [], vals = [];
    keys.forEach(function(k) {{
      cats.push(displayFmt(k));
      var s = map[k];
      vals.push(s ? s.count : 0);
    }});
    return {{ cats: cats, vals: vals, keys: keys }};
  }}

  function monthFmt(k) {{ return k.slice(0, 4) + '-' + k.slice(5); }}
  function weekFmt(k) {{ return k; }}
  function dayFmt(k) {{ return k.slice(5); }}

  var seriesCache = {{
    month: buildSeries(monthKeys(), byMonth, monthFmt),
    week: buildSeries(weekKeys(), byWeek, weekFmt),
    day: buildSeries(dayKeys(), byDay, dayFmt)
  }};
  var GRAN = {{ month: '月', week: '周', day: '天' }};

  var chart = echarts.init(document.getElementById('chart'));
  var currentGran = 'month';

  function granForRange(days) {{
    if (days > 180) return 'month';
    if (days > 35) return 'week';
    return 'day';
  }}

  function optionFor(gran) {{
    var s = seriesCache[gran];
    return {{
      backgroundColor: '#fff',
      tooltip: {{
        trigger: 'axis',
        confine: true,
        formatter: function(params) {{
          var p = params[0];
          return p.axisValue + '<br/>数字化相关新闻：<b>' + (p.value || 0) + '</b> 条';
        }}
      }},
      grid: {{ left: 46, right: 20, top: 30, bottom: 60 }},
      xAxis: {{
        type: 'category', data: s.cats, boundaryGap: false,
        axisLabel: {{ fontSize: 11 }},
        axisLine: {{ lineStyle: {{ color: '#999' }} }},
        axisTick: {{ show: false }}
      }},
      yAxis: {{
        type: 'value', minInterval: 1, name: '新闻条数',
        axisLabel: {{ fontSize: 11 }},
        splitLine: {{ lineStyle: {{ color: '#f0ece6' }} }}
      }},
      dataZoom: [
        {{ type: 'inside', startValue: 0, endValue: 100, filterMode: 'none' }},
        {{ type: 'slider', height: 22, bottom: 10, filterMode: 'none' }}
      ],
      series: [{{
        name: '数字化新闻', type: 'line', data: s.vals,
        connectNulls: false, smooth: gran === 'month',
        symbolSize: 7,
        lineStyle: {{ width: 2.4, color: '#2563eb' }},
        itemStyle: {{ color: '#2563eb' }},
        areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {{ offset: 0, color: 'rgba(37,99,235,.28)' }}, {{ offset: 1, color: 'rgba(37,99,235,0)' }}
        ]) }},
        markLine: {{
          silent: true, symbol: 'none',
          data: [{{ yAxis: Math.round(data.stats.total / ((rangeEnd.slice(0,4)-rangeStart.slice(0,4))*12 + (rangeEnd.slice(5,7)-rangeStart.slice(5,7)) + 1)), name: '月均' }}],
          lineStyle: {{ color: '#d97706', type: 'dashed' }},
          label: {{ formatter: '月均 {{c}}', fontSize: 10, color: '#d97706' }}
        }}
      }}]
    }};
  }}

  chart.setOption(optionFor('month'));

  // 粒度切换:根据缩放跨度
  var switching = false;
  function maybeSwitch(startIndex, endIndex) {{
    var s = seriesCache[currentGran];
    if (!s.keys[startIndex] || !s.keys[endIndex]) return;
    var startDate = keyToDate(s.keys[startIndex], currentGran);
    var endDate = keyToDate(s.keys[endIndex], currentGran);
    var days = (endDate - startDate) / 86400000;
    var target = granForRange(days);
    if (target !== currentGran) {{
      applyGran(target, startDate, endDate);
    }}
  }}

  function keyToDate(key, gran) {{
    if (gran === 'month') return new Date(key + '-01T00:00:00');
    if (gran === 'day') return new Date(key + 'T00:00:00');
    // week: yyyy-Wnn → 周一
    var parts = key.split('-W');
    var y = +parts[0], w = +parts[1];
    var jan1 = new Date(y, 0, 1);
    var day = (jan1.getDay() + 6) % 7;
    var start = addDays(jan1, -day);
    return addDays(start, (w - 1) * 7);
  }}

  function applyGran(gran, startDate, endDate) {{
    var s = seriesCache[gran];
    var si = -1, ei = -1;
    s.keys.forEach(function(k, i) {{
      var d = keyToDate(k, gran);
      if (si === -1 && d >= startDate) si = i;
      if (d <= endDate) ei = i;
    }});
    if (si === -1) si = 0;
    if (ei === -1) ei = s.keys.length - 1;
    currentGran = gran;
    switching = true;
    chart.setOption({{
      xAxis: {{ data: s.cats }},
      series: [{{ data: s.vals, smooth: gran === 'month' }}],
      dataZoom: [
        {{ startValue: si, endValue: ei, filterMode: 'none' }},
        {{ startValue: si, endValue: ei, filterMode: 'none' }}
      ]
    }});
    setTimeout(function() {{ switching = false; }}, 50);
  }}

  chart.on('datazoom', function(evt) {{
    if (switching) return;
    var dz = evt.batch ? evt.batch[0] : evt;
    var s = seriesCache[currentGran];
    if (!s || dz.startValue === undefined) return;
    var si = Math.floor(dz.startValue), ei = Math.ceil(dz.endValue);
    maybeSwitch(si, ei);
  }});

  // 点击数据点 → 展示该周期新闻明细
  function periodItems(gran, key) {{
    var map = {{ month: byMonth, week: byWeek, day: byDay }}[gran];
    return (map[key] || {{ items: [] }}).items;
  }}

  chart.on('click', function(params) {{
    var gran = currentGran;
    var s = seriesCache[gran];
    if (params.dataIndex == null || !s) return;
    var key = s.keys[params.dataIndex];
    var label = s.cats[params.dataIndex];
    var items = periodItems(gran, key);
    document.getElementById('period-title').textContent = '📋 ' + label + ' · 数字化相关新闻 ' + items.length + ' 条';
    document.getElementById('period-count').textContent = '粒度：' + GRAN[gran];
    var box = document.getElementById('period-list');
    if (!items.length) {{
      box.innerHTML = '<div class="empty">该周期暂无数字化相关新闻。</div>';
      return;
    }}
    box.innerHTML = items.map(function(it) {{
      return '<div class="p-item">' +
        '<span class="p-date">' + it.d + '</span>' +
        '<span class="p-title"><a href="https://www.ncha.gov.cn' + it.u + '" target="_blank" rel="noopener">' + it.t + '</a></span>' +
        '<span class="p-level ' + it.l + '">' + (LEVEL_NAMES[it.l] || it.l) + '</span>' +
        '</div>';
    }}).join('');
  }});

  window.addEventListener('resize', function() {{ chart.resize(); }});
}}
</script>
</body>
</html>'''
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)


if __name__ == '__main__':
    build_page(HTML_PATH if False else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'digital-trends.html'),
               os.path.join(os.path.dirname(os.path.abspath(__file__)), 'digital-data.json'))

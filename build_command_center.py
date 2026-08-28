#!/usr/bin/env python3
"""Build the independent visual command-center page.

The page reads the site's existing JSON outputs at runtime. It has its own
HTML/CSS/JS surface and can later move to a separate repo or subdomain.
"""
from pathlib import Path


SITE_DIR = Path(__file__).resolve().parent
OUT_DIR = SITE_DIR / "command-center"
OUT_FILE = OUT_DIR / "index.html"


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#050b16">
  <meta name="description" content="每日文博资讯文博行业数字驾驶舱：数字化趋势与行业关注地图。">
  <title>文博行业数字驾驶舱｜每日文博资讯</title>
  <style>
    :root { --bg:#050b16; --panel:#0b1525; --line:#1b3953; --cyan:#54d7ff; --blue:#3b8dff; --gold:#ffc857; --mint:#45e0b1; --text:#eaf5ff; --muted:#86a0b7; --danger:#ff7f79; }
    * { box-sizing:border-box; }
    html,body { margin:0; min-height:100%; background:radial-gradient(circle at 50% -20%,#17304e 0,#081120 35%,#050b16 72%); color:var(--text); font-family:Inter,"Microsoft YaHei","PingFang SC",sans-serif; }
    body { padding:20px; }
    a { color:inherit; }
    .shell { width:min(1700px,100%); margin:auto; }
    .topbar { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; padding:10px 2px 18px; border-bottom:1px solid rgba(84,215,255,.28); }
    .eyebrow { color:var(--cyan); font-size:11px; letter-spacing:.24em; text-transform:uppercase; }
    h1 { margin:6px 0 0; font-size:clamp(25px,3vw,44px); letter-spacing:.08em; font-weight:700; text-shadow:0 0 18px rgba(84,215,255,.42); }
    .top-actions { display:flex; align-items:center; gap:12px; color:var(--muted); font-size:13px; text-align:right; }
    .top-actions a,.top-actions button { border:1px solid var(--line); border-radius:5px; background:#0d1b2c; color:var(--text); padding:8px 12px; text-decoration:none; cursor:pointer; }
    .top-actions a:hover,.top-actions button:hover { border-color:var(--cyan); color:var(--cyan); }
    .status { color:var(--mint); white-space:nowrap; }
    .kpis { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:16px 0; }
    .kpi,.panel { position:relative; overflow:hidden; border:1px solid var(--line); background:linear-gradient(145deg,rgba(16,34,56,.94),rgba(7,16,29,.94)); box-shadow:inset 0 0 28px rgba(40,115,165,.08),0 10px 35px rgba(0,0,0,.16); }
    .kpi { min-height:96px; padding:14px 16px; }
    .kpi:before,.panel:before { position:absolute; content:""; top:0; left:0; width:58px; height:2px; background:var(--cyan); box-shadow:0 0 12px var(--cyan); }
    .kpi-label { color:var(--muted); font-size:12px; }
    .kpi-value { margin-top:8px; font:700 clamp(25px,3vw,37px)/1 "Arial Narrow",Inter,sans-serif; letter-spacing:.04em; color:#f6fbff; }
    .kpi-unit { margin-left:4px; color:var(--cyan); font-size:12px; }
    .grid-main { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(340px,.65fr); gap:14px; }
    .panel { padding:16px; }
    .panel-title { display:flex; justify-content:space-between; gap:10px; align-items:baseline; margin-bottom:12px; color:#e8f5ff; font-weight:700; letter-spacing:.08em; }
    .panel-title small { color:var(--muted); font-size:11px; font-weight:400; letter-spacing:0; }
    #map { height:520px; width:100%; }
    .map-note { color:var(--muted); font-size:11px; line-height:1.7; margin:0; }
    .event-list { height:520px; overflow:auto; padding-right:4px; }
    .event { padding:12px 0; border-bottom:1px solid rgba(134,160,183,.16); }
    .event:last-child { border-bottom:0; }
    .event-title { display:block; color:#f0f8ff; text-decoration:none; font-size:14px; line-height:1.55; }
    .event-title:hover { color:var(--cyan); }
    .event-meta { display:flex; flex-wrap:wrap; gap:6px 10px; margin-top:7px; color:var(--muted); font-size:11px; }
    .tag { color:var(--gold); }
    .charts { display:grid; grid-template-columns:1.25fr .75fr; gap:14px; margin-top:14px; }
    .chart { height:310px; }
    .topic-list { display:grid; gap:10px; margin-top:15px; }
    .topic-row { display:grid; grid-template-columns:1fr 44px; gap:10px; align-items:center; color:#d9e9f5; font-size:12px; }
    .topic-bar { height:7px; margin-top:5px; border-radius:99px; background:#14263a; overflow:hidden; }
    .topic-bar i { display:block; height:100%; border-radius:99px; background:linear-gradient(90deg,var(--blue),var(--cyan)); box-shadow:0 0 9px rgba(84,215,255,.6); }
    .topic-count { color:var(--cyan); text-align:right; }
    .detail { margin-top:14px; display:none; }
    .detail.show { display:block; }
    .detail-body { max-height:300px; overflow:auto; }
    .empty { color:var(--muted); padding:34px 0; text-align:center; }
    .footnote { margin:15px 2px 0; color:var(--muted); font-size:11px; line-height:1.8; }
    .footnote strong { color:#c6d9e8; }
    .error { color:var(--danger); padding:40px; text-align:center; }
    @media (max-width:980px) { body{padding:12px}.kpis{grid-template-columns:repeat(3,1fr)}.grid-main,.charts{grid-template-columns:1fr}#map,.event-list{height:430px} }
    @media (max-width:600px) { .topbar{align-items:flex-start;flex-direction:column}.top-actions{width:100%;justify-content:space-between;text-align:left}.kpis{grid-template-columns:repeat(2,1fr);gap:8px}.kpi{padding:12px;min-height:86px}.kpi-value{font-size:25px}.panel{padding:12px}.chart{height:280px}h1{letter-spacing:.04em} }
  </style>
</head>
<body>
<div class="shell">
  <header class="topbar">
    <div>
      <div class="eyebrow">WENBO DAILY · DATA COMMAND CENTER</div>
      <h1>文博行业数字驾驶舱</h1>
    </div>
    <div class="top-actions">
      <span class="status">● 数据链路正常</span>
      <span id="updated">读取数据中</span>
      <a href="../index.html">返回每日文博资讯</a>
      <button type="button" id="fullscreen">全屏</button>
    </div>
  </header>

  <section class="kpis" aria-label="核心指标">
    <div class="kpi"><div class="kpi-label">数字化独立原文</div><div class="kpi-value" id="k-unique">—</div></div>
    <div class="kpi"><div class="kpi-label">数字化报道占比</div><div class="kpi-value" id="k-share">—<span class="kpi-unit">%</span></div></div>
    <div class="kpi"><div class="kpi-label">近90天地区事件</div><div class="kpi-value" id="k-events">—</div></div>
    <div class="kpi"><div class="kpi-label">固定权威信源</div><div class="kpi-value" id="k-sources">—<span class="kpi-unit">个</span></div></div>
    <div class="kpi"><div class="kpi-label">数据覆盖范围</div><div class="kpi-value" id="k-range" style="font-size:21px">—</div></div>
  </section>

  <main>
    <div class="grid-main">
      <section class="panel">
        <div class="panel-title"><span>全国行业关注分布</span><small>固定权威信源 · 近30天样本</small></div>
        <div id="map"></div>
        <p class="map-note">颜色深浅表示固定信源近期报道关注的相对集中度，不代表各地区真实活动总量。点击省份查看对应事项；地图数据与日报精选相互独立。</p>
      </section>
      <section class="panel">
        <div class="panel-title"><span>近期重点事项</span><small id="event-summary">—</small></div>
        <div class="event-list" id="events"><div class="empty">正在读取监测记录…</div></div>
      </section>
    </div>

    <div class="charts">
      <section class="panel">
        <div class="panel-title"><span>数字化年度趋势</span><small>独立原文数 + 占比</small></div>
        <div id="year-chart" class="chart"></div>
      </section>
      <section class="panel">
        <div class="panel-title"><span>数字化行业方向</span><small>按独立原文统计</small></div>
        <div id="topics" class="topic-list"></div>
      </section>
    </div>

    <section class="panel detail" id="detail">
      <div class="panel-title"><span id="detail-title">地区事项</span><small>点击标题打开原文</small></div>
      <div class="detail-body" id="detail-body"></div>
    </section>
  </main>

  <p class="footnote"><strong>口径提示：</strong>数字化趋势来自国家文物局“文物新闻”栏目中的关键词筛选，并按原文 URL 去重；行业关注地图来自固定权威信源的独立事件监测。驾驶舱用于发现线索，不替代原文核验，也不把样本量解释为行业真实总量。</p>
</div>
<script src="../echarts.min.js"></script>
<script>
  const articleUrl = (url) => url && url.startsWith('/') ? 'https://www.ncha.gov.cn' + url : (url || '#');
  const $ = (id) => document.getElementById(id);
  const dateValue = (s) => Date.parse((s || '') + 'T00:00:00+08:00');
  const escapeHtml = (s) => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ageDays = (s, asOf) => Math.max(0, (dateValue(asOf) - dateValue(s)) / 86400000);
  let heat = null, digital = null, mapChart = null;
  const shortToGeo = {'北京':'北京市','天津':'天津市','河北':'河北省','山西':'山西省','内蒙古':'内蒙古自治区','辽宁':'辽宁省','吉林':'吉林省','黑龙江':'黑龙江省','上海':'上海市','江苏':'江苏省','浙江':'浙江省','安徽':'安徽省','福建':'福建省','江西':'江西省','山东':'山东省','河南':'河南省','湖北':'湖北省','湖南':'湖南省','广东':'广东省','广西':'广西壮族自治区','海南':'海南省','重庆':'重庆市','四川':'四川省','贵州':'贵州省','云南':'云南省','西藏':'西藏自治区','陕西':'陕西省','甘肃':'甘肃省','青海':'青海省','宁夏':'宁夏回族自治区','新疆':'新疆维吾尔自治区','台湾':'台湾省','香港':'香港特别行政区','澳门':'澳门特别行政区'};

  function eventScore(event, asOf) {
    const recency = 100 * Math.pow((heat && heat.decay) || .93, ageDays(event.lastDate, asOf));
    return (+event.impact || 0) * .35 + (+event.evidence || 0) * .30 + (+event.breadth || 0) * .20 + recency * .15;
  }
  function inLast30(event) { return ageDays(event.lastDate, heat.asOf) < 30; }
  function provinceRows() {
    const rows = {};
    (heat.events || []).filter(inLast30).forEach(event => {
      if (!event.primaryProvince) return;
      const p = event.primaryProvince;
      if (!rows[p]) rows[p] = {name:p, raw:0, events:[], count:0};
      rows[p].raw += eventScore(event, heat.asOf); rows[p].events.push(event); rows[p].count++;
    });
    const max = Math.max(0, ...Object.values(rows).map(x => x.raw));
    return Object.values(rows).map(x => ({...x, index:max ? x.raw / max * 100 : 0})).sort((a,b) => b.raw-a.raw);
  }
  function renderKpis(rows) {
    const s = digital.stats || {}, hs = heat.stats || {};
    $('k-unique').textContent = s.unique_source_pages ?? '—';
    $('k-share').firstChild.textContent = s.overall_share ?? '—';
    $('k-events').textContent = hs.provincialEvents ?? rows.reduce((n,x)=>n+x.count,0);
    $('k-sources').firstChild.textContent = hs.panelSourceCount ?? (heat.coverage && heat.coverage.panel || []).length;
    $('k-range').textContent = (digital.range && digital.range.start || '—') + '—' + (digital.range && digital.range.end || '—');
    $('updated').textContent = '更新于 ' + (digital.generated || heat.generated || '—');
    $('event-summary').textContent = rows.length + ' 个地区 · ' + rows.reduce((n,x)=>n+x.count,0) + ' 件事项';
  }
  function renderEvents(events, target) {
    const list = (events || []).slice().sort((a,b)=>eventScore(b,heat.asOf)-eventScore(a,heat.asOf)).slice(0,14);
    if (!list.length) { target.innerHTML = '<div class="empty">当前监测窗口暂无合格事项。</div>'; return; }
    target.innerHTML = list.map(e => {
      const r = e.reports && e.reports[0] || {};
      return '<article class="event"><a class="event-title" href="'+escapeHtml(r.url || '#')+'" target="_blank" rel="noopener">'+escapeHtml(e.title)+'</a><div class="event-meta"><span>'+escapeHtml(e.lastDate)+'</span><span class="tag">'+escapeHtml(e.primaryProvince || '全国性')+'</span><span>'+escapeHtml(e.primaryTheme || (e.themes||[])[0] || '行业动态')+'</span><span>指数 '+eventScore(e,heat.asOf).toFixed(0)+'</span></div></article>';
    }).join('');
  }
  function renderDetail(row) {
    const box = $('detail');
    if (!row) { box.classList.remove('show'); return; }
    $('detail-title').textContent = row.name + ' · ' + row.count + ' 件事项';
    $('detail-body').innerHTML = row.events.sort((a,b)=>eventScore(b,heat.asOf)-eventScore(a,heat.asOf)).map(e => {
      const r = e.reports && e.reports[0] || {};
      return '<article class="event"><a class="event-title" href="'+escapeHtml(r.url || '#')+'" target="_blank" rel="noopener">'+escapeHtml(e.title)+'</a><div class="event-meta"><span>'+escapeHtml(e.lastDate)+'</span><span>'+escapeHtml(e.primaryTheme || (e.themes||[])[0] || '行业动态')+'</span><span>'+escapeHtml((e.sources||[]).map(s=>s.name).join('、'))+'</span></div></article>';
    }).join('');
    box.classList.add('show'); box.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  function renderMap(rows, geo) {
    if (!window.echarts) { $('map').innerHTML='<div class="error">图表组件不可用，请打开网络或使用桌面浏览器。</div>'; return; }
    const geoFeatures = (geo.features || []).filter(f => f.properties && f.properties.name);
    echarts.registerMap('wenbo-china', {...geo, features:geoFeatures});
    mapChart = echarts.init($('map'));
    const values = rows.map(r => ({name:shortToGeo[r.name] || r.name, value:+r.index.toFixed(1), count:r.count}));
    mapChart.setOption({backgroundColor:'transparent',tooltip:{trigger:'item',backgroundColor:'#0b1525',borderColor:'#2a6484',textStyle:{color:'#eaf5ff'},formatter:p=>{const row=rows.find(r=>(shortToGeo[r.name]||r.name)===p.name);return '<b>'+p.name+'</b><br/>关注指数：'+(row?row.index.toFixed(0):'—')+'<br/>近30天事项：'+(row?row.count:0);}},visualMap:{min:0,max:100,left:12,bottom:4,text:['高','低'],textStyle:{color:'#86a0b7'},inRange:{color:['#102238','#155174','#2f9fc8','#8bdcff']},calculable:false},series:[{type:'map',map:'wenbo-china',roam:true,zoom:1.08,data:values,label:{show:false},itemStyle:{areaColor:'#0d1c2d',borderColor:'#315872',borderWidth:1},emphasis:{label:{show:true,color:'#fff'},itemStyle:{areaColor:'#38bce9'}}}]});
    mapChart.on('click', p => { const row=rows.find(r=>(shortToGeo[r.name]||r.name)===p.name); renderDetail(row); });
    window.addEventListener('resize',()=>mapChart && mapChart.resize());
  }
  function renderYearChart() {
    const years = digital.by_year || [];
    const labels = years.map(x=>x.key + (x.key === String(new Date().getFullYear()) ? ' YTD' : ''));
    const count = years.map(x=>x.unique_count ?? x.count ?? 0), share = years.map(x=>x.share ?? 0);
    const chart=echarts.init($('year-chart'));
    chart.setOption({grid:{left:45,right:48,top:24,bottom:28},tooltip:{trigger:'axis',backgroundColor:'#0b1525',borderColor:'#2a6484',textStyle:{color:'#eaf5ff'}},legend:{top:0,textStyle:{color:'#a9c0d2'},data:['独立原文数','占比']},xAxis:{type:'category',data:labels,axisLabel:{color:'#86a0b7'},axisLine:{lineStyle:{color:'#29475d'}}},yAxis:[{type:'value',name:'篇',nameTextStyle:{color:'#86a0b7'},axisLabel:{color:'#86a0b7'},splitLine:{lineStyle:{color:'rgba(134,160,183,.12)'}}},{type:'value',name:'%',max:Math.max(10,Math.ceil(Math.max(...share)/5)*5),axisLabel:{color:'#86a0b7'},splitLine:{show:false}}],series:[{name:'独立原文数',type:'line',smooth:true,symbol:'circle',symbolSize:7,data:count,lineStyle:{width:3,color:'#54d7ff'},itemStyle:{color:'#54d7ff'},areaStyle:{color:'rgba(84,215,255,.1)'}},{name:'占比',type:'line',smooth:true,yAxisIndex:1,symbol:'circle',symbolSize:6,data:share,lineStyle:{width:2,color:'#ffc857'},itemStyle:{color:'#ffc857'}}]});
    window.addEventListener('resize',()=>chart.resize());
  }
  function renderTopics() {
    const entries=Object.entries((digital.stats && digital.stats.topic_unique_counts)||{}).sort((a,b)=>b[1]-a[1]);
    const max=Math.max(1,...entries.map(x=>x[1]));
    $('topics').innerHTML=entries.map(([name,count])=>'<div class="topic-row"><div>'+escapeHtml(name)+'<div class="topic-bar"><i style="width:'+Math.round(count/max*100)+'%"></i></div></div><div class="topic-count">'+count+'</div></div>').join('');
  }
  async function init() {
    try {
      [digital,heat] = await Promise.all([fetch('../digital-data.json').then(r=>r.json()),fetch('../heatmap-data.json').then(r=>r.json())]);
      const rows=provinceRows(); renderKpis(rows); renderEvents((heat.events||[]).filter(inLast30),$('events')); renderTopics(); renderYearChart();
      const geo=await fetch('../lib/china.json').then(r=>r.json()); renderMap(rows,geo);
    } catch (err) { console.error(err); document.querySelector('main').innerHTML='<div class="panel error">驾驶舱数据加载失败。请返回每日文博资讯，确认数据文件可访问后重试。</div>'; }
  }
  $('fullscreen').addEventListener('click',()=>document.documentElement.requestFullscreen && document.documentElement.requestFullscreen());
  init();
</script>
</body>
</html>'''


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(HTML, encoding="utf-8")
    print(f"Command center: {OUT_FILE}")


if __name__ == "__main__":
    main()

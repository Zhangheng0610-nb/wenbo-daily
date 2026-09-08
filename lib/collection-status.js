/* Collection status uses actual attempts; a static rebuild cannot refresh it. */
(function(root) {
  'use strict';
  function attempt(entry, now, good) {
    const stamp = entry && entry.checkedAt;
    const time = stamp && /(?:Z|[+-]\d\d:\d\d)$/.test(stamp) ? Date.parse(stamp) : NaN;
    if (!Number.isFinite(time) || time > now.getTime() + 300000) return {level:'failed', label:'缺少有效检查记录'};
    const age = (now.getTime() - time) / 3600000;
    if (age > 72) return {level:'failed', label:'超过三天未检查'};
    if (!good.includes(entry.status)) return {level:entry.status==='partial'?'partial':'failed', label:entry.status==='partial'?'部分覆盖':'采集异常'};
    if (age > 36) return {level:'delayed', label:'检查延迟'};
    return {level:'ready', label:'已检查'};
  }
  function assess(health, expected, now) {
    const observations=(health||{}).observations||{}, panel=observations.panel||[];
    const rows=expected.map(id=>attempt(panel.find(row=>row.sourceId===id),now,['success','no_update']));
    if (!rows.length) rows.push({level:'failed',label:'缺少固定信源配置'});
    const digital=attempt(observations.digital,now,['scan_success_with_update','scan_success_no_update']);
    const rank={ready:0,partial:1,delayed:2,failed:3};
    const worst=rows.concat(digital).sort((a,b)=>rank[b.level]-rank[a.level])[0];
    const count=rows.filter(row=>row.level==='ready').length;
    const labels={ready:'采集检查正常',partial:'采集部分覆盖',delayed:'采集检查延迟',failed:'采集异常或记录缺失'};
    return {level:worst.level,label:labels[worst.level],detail:'固定信源 '+count+'/'+expected.length+' 检查正常 · 数字趋势：'+digital.label+''};
  }
  const api={attempt,assess};
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.WenboCollectionStatus=api;
})(typeof globalThis!=='undefined'?globalThis:this);

'use strict';
(() => {
  const freshness = document.querySelector('[data-report-date]');
  if (freshness) {
    const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    if (freshness.dataset.reportDate < today) {
      freshness.classList.add('is-stale');
      freshness.querySelector('strong').textContent = `最新日报截至 ${freshness.dataset.reportDate}，尚非今日内容`;
    }
  }
  const rows = [...document.querySelectorAll('.job-item')];
  if (!rows.length) return;
  const panel = document.createElement('form');
  panel.className = 'job-filters';
  panel.setAttribute('role','search');
  panel.setAttribute('aria-label','筛选岗位');
  panel.innerHTML = '<label>岗位、机构、地点<input type="search" name="jobq" placeholder="例如：修复、宁波、数字化"></label><label>申请状态<select name="status"><option value="active">未截止及待核验</option><option value="open">可申请</option><option value="upcoming">尚未开始</option><option value="check">状态待核验</option><option value="closed">已截止</option><option value="all">全部档案</option></select></label><button type="reset">清除筛选</button><p class="job-filter-result" role="status" aria-live="polite"></p>';
  document.querySelector('.job-section').before(panel);
  const input = panel.elements.jobq, select = panel.elements.status;
  const params = new URLSearchParams(location.search);
  input.value = params.get('jobq') || '';
  if ([...select.options].some(o=>o.value===params.get('status'))) select.value=params.get('status');
  function refresh() {
    const now = Date.now(), counts = {open:0,closed:0,upcoming:0,check:0};
    let visible=0, urgent=0;
    const tokens = input.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    rows.forEach(row=>{
      const end = Date.parse(row.dataset.deadlineAt), start=Date.parse(row.dataset.opensAt);
      let state = Number.isFinite(end) ? now>=end ? 'closed' : Number.isFinite(start)&&now<start ? 'upcoming' : 'open' : 'check';
      counts[state]++;
      const closing=state==='open'&&end-now<=3*86400000;
      if(closing)urgent++;
      row.classList.toggle('closed-row',state==='closed');row.classList.toggle('urgent-row',closing);
      const badge=row.querySelector('.job-status');
      badge.textContent={open:'可申请',closed:'已截止',upcoming:'尚未开始',check:'状态待核验'}[state];
      badge.className='status-badge job-status status-'+(state==='upcoming'?'check':state);
      const closingBadge=row.querySelector('.closing-badge');if(closingBadge)closingBadge.hidden=!closing;
      const stateMatch=select.value==='all'||(select.value==='active'?state!=='closed':state===select.value);
      row.hidden=!(stateMatch&&tokens.every(t=>row.textContent.toLocaleLowerCase().includes(t)));
      if(!row.hidden)visible++;
    });
    document.querySelectorAll('.job-section').forEach(section=>section.hidden=![...section.querySelectorAll('.job-item')].some(row=>!row.hidden));
    for(const [id,value] of Object.entries({'job-open-count':counts.open,'job-open-stat':counts.open,'job-closed-count':counts.closed,'job-closed-stat':counts.closed,'job-urgent-stat':urgent})){
      const node=document.getElementById(id);if(node)node.textContent=value;
    }
    panel.querySelector('[role=status]').textContent=visible?`显示 ${visible} / ${rows.length} 条 · 待核验不代表仍在招，申请前请核对公告。`:'没有匹配岗位。可清除关键词或选择“全部档案”。';
  }
  function sync(){const url=new URL(location.href);for(const [k,v] of [['jobq',input.value],['status',select.value]]){if(v&&(k!=='status'||v!=='active'))url.searchParams.set(k,v);else url.searchParams.delete(k);}history.replaceState(null,'',url);refresh();}
  panel.addEventListener('submit',e=>{e.preventDefault();sync();});
  input.addEventListener('input',sync);select.addEventListener('change',sync);
  panel.addEventListener('reset',()=>setTimeout(sync,0));
  refresh();setInterval(refresh,60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();

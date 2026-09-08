'use strict';
(() => {
 const key='wenbo-reading-v1';
 let saved=[]; let available=true;
 const safePath=value=>{try{const u=new URL(value,location.href);return u.origin===location.origin&&/^https?:$/.test(u.protocol)?u.pathname+u.search+u.hash:null;}catch{return null;}};
 try{const raw=JSON.parse(localStorage.getItem(key)||'[]');if(Array.isArray(raw))saved=raw.filter(x=>x&&typeof x.id==='string'&&typeof x.title==='string'&&safePath(x.url)).slice(0,500);}catch{available=false;}
 let message=document.getElementById('save-message');
 if(!message){message=document.createElement('p');message.id='save-message';message.setAttribute('role','status');message.setAttribute('aria-live','polite');document.querySelector('main')?.append(message);}
 function persist(){try{localStorage.setItem(key,JSON.stringify(saved));return true;}catch{if(message)message.textContent='此浏览器暂时无法保存收藏，请使用浏览器书签。';return false;}}
 function controls(){document.querySelectorAll('[data-save-id]').forEach(b=>{const yes=saved.some(x=>x.id===b.dataset.saveId||safePath(x.url)===safePath(b.dataset.saveUrl));b.textContent=yes?'已收藏 · 取消':'收藏';b.setAttribute('aria-pressed',String(yes));});}
 function render(){const list=document.getElementById('reading-list');if(!list)return;list.replaceChildren();if(!saved.length){const p=document.createElement('p');p.textContent=available?'尚无收藏。可从资讯、日报或岗位条目旁点击“收藏”。':'此浏览器无法读取收藏，请检查网站存储权限。';list.append(p);return;}
  saved.forEach(item=>{const article=document.createElement('article');article.className='reader-entry';const a=document.createElement('a');a.href=safePath(item.url);a.textContent=item.title;const button=document.createElement('button');button.textContent='移除';button.addEventListener('click',()=>{const previous=saved;saved=saved.filter(x=>x.id!==item.id);if(!persist()){saved=previous;return;}render();controls();});article.append(a,button);list.append(article);});
 }
 document.querySelectorAll('.job-item').forEach(row=>{const b=document.createElement('button');b.className='save-entry';b.dataset.saveId=row.id;b.dataset.saveUrl=location.pathname+'?status=all#'+row.id;b.dataset.saveTitle=row.querySelector('.job-title').textContent;row.querySelector('.job-link').append(b);});
 document.querySelectorAll('h3[id^="item"]').forEach(h=>{const b=document.createElement('button');b.className='save-entry';b.dataset.saveId=location.pathname+'#'+h.id;b.dataset.saveUrl=location.pathname+'#'+h.id;b.dataset.saveTitle=h.textContent;b.setAttribute('aria-label','收藏：'+h.textContent);h.after(b);});
 document.querySelectorAll('[data-save-id]').forEach(b=>b.addEventListener('click',()=>{const old=saved;const exists=saved.some(x=>x.id===b.dataset.saveId||safePath(x.url)===safePath(b.dataset.saveUrl));if(exists)saved=saved.filter(x=>x.id!==b.dataset.saveId&&safePath(x.url)!==safePath(b.dataset.saveUrl));else {if(saved.length>=500){if(message)message.textContent='已达到500条收藏，请先移除部分条目。';return;}const path=safePath(b.dataset.saveUrl);if(!path)return;saved=[{id:b.dataset.saveId,title:b.dataset.saveTitle,url:path},...saved];}if(!persist()){saved=old;return;}controls();if(message)message.textContent=exists?'已取消收藏。':'已收藏，可在首页“我的收藏”中查看。';}));
 controls();render();
 const filter=document.getElementById('reader-topic');
 if(filter){
  const query=document.getElementById('reader-query'), more=document.getElementById('reader-more'), period=document.getElementById('reader-period');
  const latest=document.querySelector('.reader-feed').dataset.latest;
  const entries=[...document.querySelectorAll('.reader-feed .reader-entry')];
  let limit=6;
  function restore(){const p=new URLSearchParams(location.search);filter.value=[...filter.options].some(o=>o.value===p.get('topic'))?p.get('topic'):'';query.value=p.get('readerq')||'';period.value=p.get('period')==='all'?'all':'earlier';limit=6;apply();}
  function apply(){
   const words=query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
   const matched=entries.filter(row=>(period.value==='all'||row.dataset.reportDate!==latest)&&(!filter.value||row.dataset.topics.includes(filter.value))&&words.every(w=>row.textContent.toLocaleLowerCase().includes(w)));
   const visible=new Set(matched.slice(0,limit));entries.forEach(row=>row.hidden=!visible.has(row));
   document.getElementById('reader-result').textContent=matched.length?`${period.value==='all'?'近两周':'此前新闻'}共 ${matched.length} 条 · 已显示 ${Math.min(limit,matched.length)} 条`:'没有匹配新闻，试试其他关键词或全站搜索。';
   more.hidden=matched.length<=limit;more.textContent=`再看 ${Math.min(6,Math.max(0,matched.length-limit))} 条`;
  }
  function sync(){limit=6;const url=new URL(location.href);for(const [key,value] of [['topic',filter.value],['readerq',query.value],['period',period.value==='all'?'all':'']]){if(value)url.searchParams.set(key,value);else url.searchParams.delete(key);}history.replaceState(null,'',url);apply();}
  period.addEventListener('change',sync);filter.addEventListener('change',sync);query.addEventListener('input',sync);
  document.getElementById('reader-reset').addEventListener('click',()=>{query.value='';filter.value='';period.value='earlier';sync();query.focus();});
  more.addEventListener('click',()=>{const previous=limit;limit+=6;apply();const shown=entries.filter(row=>!row.hidden);shown[previous]?.querySelector('h3 a')?.focus();});
  window.addEventListener('popstate',restore);restore();
 }
})();

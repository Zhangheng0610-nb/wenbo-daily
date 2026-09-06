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
 if(filter){const params=new URLSearchParams(location.search);if([...filter.options].some(o=>o.value===params.get('topic')))filter.value=params.get('topic');const apply=()=>{let shown=0;document.querySelectorAll('.reader-entry').forEach(row=>{row.hidden=!!filter.value&&!row.dataset.topics.includes(filter.value);if(!row.hidden)shown++;});document.getElementById('reader-result').textContent=shown?`显示 ${shown} 条`:'当前展示范围内暂无匹配；可用全站搜索查询历史内容。';};filter.addEventListener('change',()=>{const url=new URL(location.href);if(filter.value)url.searchParams.set('topic',filter.value);else url.searchParams.delete('topic');history.replaceState(null,'',url);apply();});apply();}
})();

'use strict';
(() => {
 const select=document.getElementById('archive-month');
 if(!select)return;
 const groups=[...document.querySelectorAll('.archive-group')];
 const initialOpen=new Map([...document.querySelectorAll('.older-group')].map(group=>[group,group.open]));
 function apply(){
  document.getElementById('collapse-floating').hidden=Boolean(select.value);
  let total=0;
  groups.forEach(group=>{
   let count=0;
   group.querySelectorAll('.archive-card').forEach(card=>{card.hidden=Boolean(select.value&&!card.dataset.issueDate.startsWith(select.value));if(!card.hidden)count++;});
   group.hidden=count===0;total+=count;
   const badge=group.querySelector('h2 span');if(badge)badge.textContent=count+' 条';
   group.querySelectorAll('.older-group').forEach(older=>{
    older.hidden=Boolean(select.value&&![...older.querySelectorAll('.archive-card')].some(card=>!card.hidden));
    older.open=select.value?true:initialOpen.get(older);
   });
  });
  document.getElementById('archive-result').textContent=(select.value||'全部月份')+' · '+total+' 期';
 }
 function restore(){const month=new URLSearchParams(location.search).get('month')||'';select.value=[...select.options].some(option=>option.value===month)?month:'';apply();}
 select.addEventListener('change',()=>{const url=new URL(location.href);if(select.value)url.searchParams.set('month',select.value);else url.searchParams.delete('month');history.replaceState(null,'',url);apply();});
 window.addEventListener('popstate',restore);restore();
})();

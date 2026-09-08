import shutil
import subprocess
import unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'),'Node needed for reader interaction checks')
class ReaderInteractionTests(unittest.TestCase):
 def test_filter_reaches_beyond_old_twelve_row_limit(self):
  script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
function element(value=''){return {value,hidden:false,textContent:'',dataset:{},events:{},options:[],addEventListener(name,fn){this.events[name]=fn},setAttribute(){},append(){},focus(){this.focused=true}}}
const ids=Object.fromEntries(['save-message','reader-topic','reader-query','reader-period','reader-more','reader-reset','reader-result'].map(id=>[id,element()]));
ids['reader-topic'].options=[{value:''},{value:'数字'}];ids['reader-period'].value='earlier';
const rows=Array.from({length:20},(_,i)=>({...element(),dataset:{reportDate:i<7?'2026-09-08':'2026-09-07',topics:i===18?'数字':'考古'},textContent:i===18?'远处的数字藏品平台':'考古发现 '+i,querySelector(){return element()}}));
const location=new URL('https://example.test/index.html');
const document={getElementById:id=>ids[id]||null,querySelectorAll:s=>s==='.reader-feed .reader-entry'?rows:[],querySelector:s=>s==='.reader-feed'?{dataset:{latest:'2026-09-08'}}:null};
const context={document,location,URL,URLSearchParams,localStorage:{getItem(){return '[]'},setItem(){}},history:{replaceState(a,b,u){location.href=u.href}},window:{addEventListener(){}},console};
vm.runInNewContext(fs.readFileSync('assets/reader.js','utf8'),context);
assert.equal(rows.filter(r=>!r.hidden).length,6);
assert.equal(rows[0].hidden,true);
ids['reader-more'].events.click();assert.equal(rows.filter(r=>!r.hidden).length,12);
ids['reader-query'].value='数字藏品';ids['reader-query'].events.input();
assert.equal(rows.filter(r=>!r.hidden).length,1);assert.equal(rows[18].hidden,false);
assert.equal(ids['reader-more'].hidden,true);
ids['reader-reset'].events.click();assert.equal(rows.filter(r=>!r.hidden).length,6);
ids['reader-period'].value='all';ids['reader-period'].events.change();assert.equal(rows[0].hidden,false);
assert.equal(location.search,'?period=all');
"""
  subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True,text=True)

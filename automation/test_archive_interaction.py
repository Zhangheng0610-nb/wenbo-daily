"""The month filter must reach issues inside collapsed history groups."""
import subprocess
import unittest
from pathlib import Path

class ArchiveInteractionTests(unittest.TestCase):
    def test_month_reveals_old_issues_and_restores_unfiltered_groups(self):
        code = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const select={value:'',options:[{value:''},{value:'2026-08'},{value:'2026-09'}],addEventListener(name,fn){this[name]=fn}};
const result={},floating={};
const recent={dataset:{issueDate:'2026-09-08'},hidden:false};
const old={dataset:{issueDate:'2026-08-01'},hidden:false};
const older={open:false,hidden:false,querySelectorAll(){return [old]}};
const group={hidden:false,querySelector(){return {}},querySelectorAll(s){return s==='.archive-card'?[recent,old]:[older]}};
const location=new URL('https://example.test/archive.html?month=2026-08');
let popstate;
const context={URL,URLSearchParams,location,history:{replaceState(a,b,url){location.href=url.href}},window:{addEventListener(name,fn){popstate=fn}},document:{getElementById(id){return {'archive-month':select,'archive-result':result,'collapse-floating':floating}[id]},querySelectorAll(s){return s==='.archive-group'?[group]:[older]}}};
vm.runInNewContext(fs.readFileSync('assets/archive.js','utf8'),context);
assert.equal(old.hidden,false);assert.equal(recent.hidden,true);assert.equal(older.open,true);assert.equal(floating.hidden,true);
select.value='2026-09';select.change();assert.equal(old.hidden,true);assert.equal(older.hidden,true);assert.equal(recent.hidden,false);assert.equal(location.search,'?month=2026-09');
select.value='';select.change();assert.equal(old.hidden,false);assert.equal(recent.hidden,false);assert.equal(older.open,false);assert.equal(floating.hidden,false);
location.search='?month=invalid';popstate();assert.equal(select.value,'');assert.equal(group.hidden,false);
'''
        subprocess.run(['node','-e',code],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True)

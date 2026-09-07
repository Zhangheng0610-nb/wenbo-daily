"""Check built-page navigation, local assets, metadata, and executable JS syntax."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.links=[];self.main=0;self.canonical=0;self.scripts=[];self.script=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='main':self.main+=1
        if tag=='link' and a.get('rel')=='canonical':self.canonical+=1
        if tag in ('a','link','script','img'):
            ref=a.get('href') or a.get('src')
            if ref:self.links.append(ref)
        if tag=='script' and not a.get('src') and a.get('type','') not in ('application/ld+json','application/json'):self.script=''
    def handle_data(self,data):
        if self.script is not None:self.script+=data
    def handle_endtag(self,tag):
        if tag=='script' and self.script is not None:self.scripts.append(self.script);self.script=None

def main():
    errors=[];pages=list(ROOT.glob('*.html'))+list((ROOT/'reports').glob('*.html'))+list((ROOT/'command-center').glob('*.html'))
    for path in pages:
        p=Page();p.feed(path.read_text())
        if p.main!=1:errors.append(f'{path.name}: expected one main, got {p.main}')
        if len(set(p.ids))!=len(p.ids):errors.append(f'{path.name}: duplicate IDs')
        if p.canonical!=1:errors.append(f'{path.name}: expected canonical URL')
        for link in p.links:
            u=urlsplit(link)
            if u.scheme or u.netloc or not u.path:continue
            target=(ROOT/u.path.lstrip('/')) if u.path.startswith('/') else path.parent/unquote(u.path)
            if not target.exists():errors.append(f'{path.name}: missing {link}')
        for script in p.scripts:
            with tempfile.NamedTemporaryFile(suffix='.js',mode='w') as f:
                f.write(script);f.flush()
                result=subprocess.run(['node','--check',f.name],capture_output=True,text=True)
                if result.returncode:errors.append(f'{path.name}: JS syntax: {result.stderr[:200]}')
    ET.parse(ROOT/'feed.xml')
    for script in (ROOT/'assets').glob('*.js'):
        if subprocess.run(['node','--check',str(script)],capture_output=True).returncode:errors.append(f'{script.name}: JS syntax')
    if errors:raise SystemExit('\n'.join(errors))
    print(f'PRODUCT VALIDATION OK: {len(pages)} pages, local assets, unique IDs, main landmarks, canonical URLs, RSS, JS syntax')
if __name__=='__main__':main()

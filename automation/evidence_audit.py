"""Item-level correction overlay. Preserve original editorial records and provenance."""
import json
from pathlib import Path
from html import escape
from functools import lru_cache
from automation.product import safe_url
ROOT=Path(__file__).resolve().parents[1]
LABELS={'supported':'核心事实有原文支持','partial':'部分表述待核','source_mismatch':'引用对应错误','older_source':'旧闻日期更正','unresolved':'原文待核'}
@lru_cache(maxsize=1)
def audits():
    path=ROOT/'content/复核/history-source-audit.json'
    return {(r['reportDate'],r['itemId']):r for r in json.loads(path.read_text(encoding='utf-8'))['items']} if path.exists() else {}
def audit_for(report_date,item):
    record=audits().get((report_date,item.get('id')))
    if record and record['title'] != item['title']:
        raise ValueError(f'Historical audit title changed: {report_date}/{item["id"]}; review its evidence mapping')
    return record

def audit_html(record):
    if not record:return ''
    links=' '.join(f'<a href="{escape(safe_url(e["url"]),quote=True)}" target="_blank" rel="noopener noreferrer">{escape(e["title"])}</a>' for e in record['evidence'])
    return f'<aside class="evidence-audit" aria-label="条目原文复核"><strong>{LABELS[record["status"]]}</strong> · 复核 {record["checkedAt"]}<p>{escape(record["note"])}</p><p>核查依据：{links}</p></aside>'

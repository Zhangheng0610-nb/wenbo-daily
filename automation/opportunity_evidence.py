"""Field-scoped, expiring application evidence; never infer verification from a date."""
import hashlib,json
from datetime import datetime,timedelta
from pathlib import Path
from html import escape
from automation.product import job_id,safe_url
ROOT=Path(__file__).resolve().parents[1]
FIELDS=('institution','position','deadline','application')

def signature(item):
    return hashlib.sha256(json.dumps({k:item.get(k,'') for k in FIELDS},ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def load_records():
    p=ROOT/'content/招聘/evidence.json'
    return json.loads(p.read_text())['records'] if p.exists() else []

def evidence_for(item,now,records=None):
    matches=[r for r in (load_records() if records is None else records) if r['jobId']==job_id(item)]
    if not matches:return {'state':'missing','label':'报名信息尚无逐项核验记录'}
    r=max(matches,key=lambda r:r['checkedAt'])
    result=dict(r)
    if r.get('outcome')!='supported':result.update(state='unavailable',label='本次原文未能读取')
    elif r.get('signature')!=signature(item):result.update(state='changed',label='报名信息已变更，需重新核验')
    elif not {'deadline','application'}.issubset(r.get('fields',[])) or not safe_url(r.get('sourceUrl')):
        result.update(state='incomplete',label='报名核验依据不完整')
    else:
        checked=datetime.fromisoformat(r['checkedAt'])
        until=datetime.fromisoformat(r['reviewAfter'])
        if checked.tzinfo is None or until.tzinfo is None:raise ValueError('Evidence dates must have timezone')
        fresh=checked<=now<until
        result.update(state='recent' if fresh else 'stale',label='报名窗口与入口已核对' if fresh else '核验记录已过复核期')
    return result

def evidence_html(record):
    if record['state']=='missing':
        return '<aside class="opportunity-evidence"><span class="evidence-state">报名依据待核对</span></aside>'
    detail=escape(record.get('note','尚未保存本条报名窗口与投递方式的原文核验依据；日期状态不代表公告仍有效。'))
    link=safe_url(record.get('sourceUrl'))
    return '<aside class="opportunity-evidence"><strong class="evidence-state">'+escape(record['label'])+'</strong><p>'+detail+'</p>'+ ('<p>核查日期 '+escape(record['checkedAt'][:10])+' · <a href="'+escape(link,quote=True)+'" target="_blank" rel="noopener noreferrer">核查原文</a></p>' if link else '')+'</aside>'

def write_projection(root,boards,now):
    rows=[]
    for kind,data in boards:
        for section in (data or {}).get('sections',[]):
            for item in section['items']:
                evidence=evidence_for(item,now)
                rows.append({'id':job_id(item),'kind':kind,'institution':item['institution'],'position':item['position'],
                 'deadline':item['deadline'],'deadlineAt':item.get('deadline_at'),'opensAt':item.get('opens_at'),
                 'timeStatus':item['status'],'evidence':evidence,'url':kind+'.html?status=all#'+job_id(item)})
    queue=[r for r in rows if r['timeStatus']!='closed' and r['evidence']['state']!='recent']
    queue.sort(key=lambda r:(0 if r['timeStatus']=='open' else 1 if r['timeStatus']=='upcoming' else 2,r['deadlineAt'] or '9999'))
    payload={'schemaVersion':1,'generatedAt':now.isoformat(),'items':rows,'reviewQueue':[r['id'] for r in queue],
       'counts':{'total':len(rows),'recentEvidence':sum(r['evidence']['state']=='recent' for r in rows),'reviewNeeded':len(queue)}}
    (Path(root)/'opportunities.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    return payload

"""Offline saved-input supply replay; does not fetch, publish, or change ledgers."""
import argparse
import json
from datetime import date
from pathlib import Path
from automation.daily_discovery import build_audit
from automation.digest_discovery import digest_records
from automation.recall_benchmark import evaluate, matches
from automation.supply_recovery import supply_assessment


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',required=True)
    parser.add_argument('--references',required=True)
    parser.add_argument('--extra-records',action='append',default=[])
    parser.add_argument('--digest-html')
    parser.add_argument('--digest-url')
    parser.add_argument('--digest-published')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.digest_html and not (args.digest_url and args.digest_published):
        parser.error('digest input requires --digest-url and --digest-published')
    original=read(args.audit)
    rows=original['records']
    for path in args.extra_records:
        rows+=read(path)['records']
    if args.digest_html:
        rows+=digest_records({'title':'一周文物动态摘编','url':args.digest_url,
                             'publishedDate':args.digest_published,'scope':'domestic','sourceDomain':'ncha.gov.cn'},
                             Path(args.digest_html).read_text(encoding='utf-8'))
    # Derived annotations are outputs, not evidence to feed into a new replay.
    for row in rows:
        for key in list(row):
            if key.startswith('duplicate') or key in ('canonicalEventId','eventId','newDevelopment'):
                row.pop(key,None)
    audit=build_audit(date.fromisoformat(original['date']),rows,[],[],perform_evidence_upgrade=False)
    result=evaluate(read(args.references),audit)
    result['mode']='offline saved inputs; no new network, no evidence upgrade, no publication'
    result['inputs']={'audit':args.audit,'extras':args.extra_records,'digestUrl':args.digest_url}
    result['supply']=supply_assessment(audit['candidateEvaluation']['finalEditorialPool']['events'])
    result['duplicateStatuses']=[{'id':ref['id'],'statuses':[
        {k:r.get(k) for k in ('title','duplicateStatus','duplicateOf','duplicateOfTitle')}
        for r in audit['records'] if matches(ref,r)
    ]} for ref in read(args.references)['events']]
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for row in result['events']:
        print(row['stage'],row['title'])


if __name__=='__main__': main()

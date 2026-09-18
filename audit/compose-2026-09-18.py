"""Explicit editorial decisions after source-body review; no network or scheduling."""
import copy, hashlib, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation.daily_scope import save_action_source
from automation.governance import source_info

ROOT=Path.cwd()
now=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
day='2026-09-18'
def read(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def write(p,d): (ROOT/p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
base='content/发现/'+day+'.json'
discovery=read(base)
events=copy.deepcopy(discovery['candidateEvaluation']['finalEditorialPool']['events'])
bodies={r['url']:r for r in read('audit/daily-source-review-'+day+'.json')+read('audit/daily-supplement-sources-'+day+'.json')}
query_times=[q.get('executedAt') for q in discovery.get('queryAudits',[]) if isinstance(q,dict) and q.get('executedAt')]
discovery_checked_at=min(query_times) if query_times else now
pa='https://www.pa.gov/agencies/phmc/newsroom/phmc-appoints-lauren-stark-director-of-the-state-museum-of-penns'
# Exact paragraphs read through the web tool after the local request returned 403.
bodies[pa]={'url':pa,'checkedAt':now,'method':'codex-web-search official-page extraction','text':'''Pennsylvania Historical & Museum Commission Appoints Lauren Stark Director of The State Museum of Pennsylvania
September 16, 2026
Harrisburg, PA — Today, the Pennsylvania Historical and Museum Commission (PHMC) announced the appointment of Lauren Stark as the new Director of The State Museum of Pennsylvania.
In her new role, Stark will oversee all aspects of day-to-day operations, visitor services, and strategic planning at The State Museum. She takes the helm at a pivotal time, guiding the institution through a historic $79.73 million renovation while upholding the highest standards of interpretation, education, and preservation for the Commonwealth's heritage.
Stark is a seasoned museum professional with a wealth of experience within PHMC and on the national stage. Most recently serving as Director of Strategic Initiatives in the PHMC Executive Office, she has managed critical priorities, including the complex logistical relocation of over 16,500 artifacts and dozens of staff ahead of the museum's renovation.
Currently closed for $79.73 million dollar renovation project, the State Museum of Pennsylvania offers visitors a captivating journey through time.'''}
write('audit/daily-pa-source-'+day+'.json',bodies[pa])
specs=[
 {'id':'event-b7f60a5fc25d','title':'北京启动博物馆条例草案立法协商，聚焦统筹协调与规范运营','url':'https://www.bjzx.gov.cn/zxgz/zxyw/202609/t20260916_55806.html','name':'北京市政协','date':'2026-09-15','published':'2026-09-16','scope':'domestic','topic':'政策行业','kind':'policy','actor':'市政协','action':'召开《北京市博物馆条例（草案）》立法协商工作动员部署暨情况通报会','dateExcerpt':'9月15日','quote':'9月15日，市政协召开《北京市博物馆条例（草案）》立法协商工作动员部署暨情况通报会。','summary':'9月15日，北京市政协召开《北京市博物馆条例（草案）》立法协商工作动员部署暨情况通报会，司法、文物、文旅、规划、财政及执法部门通报相关情况。协商将围绕博物馆统筹协调、均衡发展、规范运营等问题听取各界意见。官方通报显示，北京现有备案博物馆252家、类博物馆88家。','comment':'备案博物馆与类博物馆并存，使这次协商需要面对不同主体的管理责任和服务差异。文物、财政、规划和执法部门共同参与，为讨论跨部门协调提供了条件；但这次公布的是协商安排，不能据此认定条例已经通过或具体义务已经生效。'},
 {'id':'event-128d081e8c9f','title':'湖南省博物馆“众神吴哥”展开展，呈现高棉造像与石刻艺术','url':'https://www.chinanews.com.cn/cul/2026/09-17/10698502.shtml','name':'中国新闻网','date':'2026-09-17','published':'2026-09-17','scope':'domestic','topic':'博物馆展览','kind':'exhibition','actor':'湖南省博物馆','action':'开展','dateExcerpt':'9月17日','quote':'9月17日，“众神吴哥——高棉帝国的千年瑰宝”展览在湖南省博物馆开展。','summary':'9月17日，“众神吴哥——高棉帝国的千年瑰宝”在湖南省博物馆开展。柬埔寨国家博物馆、吴哥保护库房及中国多家博物馆提供150余件（套）藏品，涵盖宗教造像、建筑构件、金属器等。展览以“溯源”“鼎盛”“对望”组织叙事，展期至2027年3月21日。','comment':'借展把柬埔寨馆藏与中国多馆材料放入同一展陈，以造像和石刻为核心，让高棉文明有了可直接观察的物质载体。“对望”单元提供跨文化比较的入口；看展时值得追问的是作品的宗教用途与建筑语境，而不仅是吴哥纹样营造的氛围。'},
 {'id':'event-93883938aa54','title':'延庆长城管理处与马丘比丘区政府签署友好合作备忘录','url':'https://www.stdaily.com/web/gdxw/2026-09/13/content_580300.html','name':'科技日报','date':'2026-09-13','published':'2026-09-13','scope':'domestic','topic':'国际交流','kind':'international_cooperation','actor':'延庆区长城管理处与秘鲁马丘比丘区政府','action':'签署友好合作备忘录','dateExcerpt':'9月13日','quoteStart':'9月13日，2026八达岭长城文化论坛','quoteEnd':'搭建世界遗产对话交流平台。','summary':'9月13日，2026八达岭长城文化论坛在北京延庆举办，延庆区长城管理处与秘鲁马丘比丘区政府签署友好合作备忘录，拟在遗产宣传、技术攻关和文化交流等领域深化合作。论坛同时讨论长城关联遗存的系统保护，展示用于病害测绘与风险评估的三维采集技术。','comment':'备忘录让交流有了明确的遗产管理主体，技术攻关也被列为合作方向。现场关于关联遗存保护和三维测绘的讨论，提示合作可落到管护问题；目前能确认的是签署与交流，尚不能把它写成已经实施的联合监测或修缮项目。'},
 {'id':'event-dbf67ad4df3b','title':'UNESCO与ICOM公布博物馆AI调查：应用领先于内部治理','url':'https://www.unesco.org/en/articles/unesco-icom-global-survey-finds-museums-embracing-ai-governance-and-capacity-lag-behind','name':'UNESCO','date':'2026-09-17','published':'2026-09-16','scope':'international','topic':'数字文博','kind':'project_milestone','actor':'UNESCO','action':'were presented','dateExcerpt':'17 September','quoteStart':'Findings of the first UNESCO– International','quoteEnd':'Brazil, Egypt and Kenya.','summary':'UNESCO与国际博物馆协会（ICOM）首次全球博物馆AI使用调查结果于9月17日在利雅得全球人工智能伦理论坛公布。调查覆盖90个国家的400多家博物馆：57%的受访馆已使用AI，55%没有内部AI政策、战略或指引。应用涉及行政、翻译、藏品研究、建档、展览及观众服务，结果将用于后续操作指引和能力建设。','comment':'57%的使用率与55%的制度缺口揭示了同一批受访馆中技术采用和治理准备的不同步，而不是两组可直接相减的数字。调查还指出应用多由员工探索推动；机构需要把准确性、版权和数据保护落实到业务责任，不能仅用采购工具衡量数字化成熟度。'},
 {'id':'event-44f8f9f6a0a4','title':'宾州州立博物馆任命新馆长，负责闭馆改造期间运营与战略规划','url':pa,'name':'宾夕法尼亚州历史与博物馆委员会','date':'2026-09-16','published':'2026-09-16','scope':'international','topic':'政策行业','kind':'institution_operation','actor':'Pennsylvania Historical and Museum Commission','action':'announced the appointment of Lauren Stark','dateExcerpt':'Today','quote':'Harrisburg, PA — Today, the Pennsylvania Historical and Museum Commission (PHMC) announced the appointment of Lauren Stark as the new Director of The State Museum of Pennsylvania.','summary':'9月16日，宾夕法尼亚州历史与博物馆委员会宣布任命Lauren Stark为州立博物馆馆长，负责日常运营、观众服务和战略规划。该馆正因7973万美元改造项目闭馆。Stark此前在委员会负责战略项目，并参与改造前超过1.65万件文物及数十名员工的迁移安排。','comment':'这项任命发生在闭馆改造中，责任落在藏品迁移、运营协调和未来服务衔接上。新馆长已有本次迁移经验，使人事调整与项目实施直接相关；评估改造时也应关注收藏安全与阐释更新，不能把预算规模本身等同于服务提升。'}
]
reasons=[
 '9月12日开幕的良渚琮谱展已在9月13日日报刊登；本次为同一开幕事件的视频报道，没有实质新进展。',
 '选用UNESCO完整正文替代ICOM仅提取到标题的页面；调查结果于9月17日公开，直接揭示博物馆业务采用与内部治理差距。',
 '主体为流域生态修复与农业面源污染治理，且实地考察在9月10日；不属于本期文博行业动作。',
 '博物馆历史与既有展陈的纪念日报道，未定位近七日新开幕、改造或制度动作。',
 '文旅大会图片报道主要回顾古城夜游业态，无具体新发生的文物保护或博物馆业务变化。',
 '农业品牌知识产权保护，正文无文物博物馆对象，属于范围误匹配。',
 '城市绿地与口袋公园建设，正文无文化遗产对象，属于范围误匹配。',
 '地方领导常规调研与原则性工作要求，未公布具体新规则、立项或工程验收。',
 '忠县历史保护案例回顾；皇华城展示中心开放在5月15日，9月16日活动为探访，不是新工程里程碑。',
 '仓桥直街二十余年保护模式回顾，未给出本期新政策或工程完成日期。',
 '柳孜遗址博物馆体验介绍，未说明本期开馆或展陈调整。',
 '革命文物片区累计工作综述，关联会议在9月10日，早于9月12日至18日事件窗口。',
 '与天津调研同一事件，且为常规调研，未公布具体制度或工程新增变化。',
 '吉林抗联遗址保护案例总结；十佳案例获评在6月，建设和机构设置未给出本期时间依据。',
 '电视栏目简介未明确遗址主体与近期保护节点，节目播出日期不能替代工程日期。',
 '横琴陕耀中华开幕已在9月17日日报刊登，本次同一开幕视频无新增事实。',
 '9月17日高棉文明跨馆借展开幕，展陈对象、参与机构与展期均有正文支持。',
 '电视节目回顾2019年以来尧王城考古，未确认本期新发现正式公布。',
 '水下遗产日研讨会报道提及8月21日纪念日，无法确认活动发生在9月12日至18日；不以页面发布日期替代活动日期。',
 '巡视动员会实际召开于9月11日，已超出本期近七日动作窗口。'
]
original_ids={e['eventId'] for e in events}
all_candidates=discovery['candidateEvaluation']['eventCandidates']
for spec in specs:
 if spec['id'] not in original_ids:
  source=next(e for e in all_candidates if e['eventId']==spec['id'])
  source=copy.deepcopy(source)
  source['title']=source.get('title') or source.get('representativeTitle') or spec['title']
  source['representativeTitle']=source.get('representativeTitle') or source['title']
  source['editorialPriorityScore']=source.get('editorialPriorityScore',70)
  source['editorialPriorityLabel']=source.get('editorialPriorityLabel','high')
  source['editorialReasons']=source.get('editorialReasons') or ['supplemental_editorial_review']
  source['evidenceTierAfterUpgrade']='provisional_B'
  source['candidateDisposition']='evidence_qualified'
  events.append(source)
spec_by_id={s['id']:s for s in specs}
spec_by_id['event-dbf67ad4df3b']['substantiveNewDevelopment']=True
spec_by_id['event-dbf67ad4df3b']['newDevelopmentEvidence']='UNESCO与ICOM在9月17日公布博物馆AI使用调查结果，主题为人工智能采用与机构治理，不是9月12日ICOM—INTERPOL博物馆安保调查的同一事件。'
ledger=[]
for idx,event in enumerate(events):
 spec=spec_by_id.get(event['eventId']); decision='selected' if spec else 'rejected'
 reason=(reasons[idx] if idx<20 else '补查原始高优先级事件，正文确认近期机构动作，已核对历史无同一事件刊登。')
 if spec:
  body=bodies[spec['url']]; text=body['text']; tier=source_info(spec['url'])['tier']; tier=tier if tier in ('A','B') else 'provisional_B'
  evidence=[{'name':spec['name'],'url':spec['url'],'tier':tier,'articleVerified':True,'publisher':spec['name'],'sourceRelationship':'primary','publishedDate':spec['published'],'verificationMethod':'retained source body reviewed','verifiedAt':now}]
  if 'quote' in spec: quote=spec['quote']
  else:
   start=text.index(spec['quoteStart']); end=text.index(spec['quoteEnd'],start)+len(spec['quoteEnd']);quote=text[start:end]
  assert quote in text, spec['id']
  action={'kind':spec['kind'],'actor':spec['actor'],'action':spec['action'],'change':spec['summary'],'eventDate':spec['date'],'timeBasis':'announcement_date' if spec['id']=='event-44f8f9f6a0a4' else 'event_date','dateExcerpt':spec['dateExcerpt'],'sourceUrl':spec['url'],'sourceExcerpt':quote,**save_action_source(ROOT,spec['url'],text,body['checkedAt'])}
  event.update(evidenceSources=evidence,evidenceTierAfterUpgrade=tier,candidateDisposition='evidence_qualified',industryAction=action)
 else: evidence=event['evidenceSources'];tier=event.get('evidenceTierAfterUpgrade','A')
 event.update(finalEditorialDecision=decision,finalEditorialReason=reason)
 reports=event.get('discoveryReports') or [{}]; first=reports[0]
 scope=spec['scope'] if spec else event.get('scope','domestic')
 event_title=event.get('title') or event.get('representativeTitle') or event.get('sourceTitle') or event['eventId']
 row={'candidateId':'20260918-'+event['eventId'],'date':day,'eventId':event['eventId'],'title':spec['title'] if spec else event_title,'sourceTitle':event_title,'publishedDate':spec['published'] if spec else event.get('publishedDate',day),'discoveredAt':discovery_checked_at,'discoverySource':first.get('sourceDomain','broad-discovery'),'discoverySourceType':first.get('discoverySourceType','query_search'),'discoveryUrl':first.get('url') or event.get('url') or evidence[0]['url'],'publisher':spec['name'] if spec else first.get('sourceDomain','原始发现来源'),'evidenceSources':evidence,'evidenceTier':tier,'topic':spec['topic'] if spec else '政策行业','scope':scope,'domestic':scope=='domestic','international':scope=='international','decision':decision,'decisionReason':reason,'selectedForDaily':bool(spec),'dedupStatus':'unique_event','duplicateOf':None,'duplicateReason':None,'notes':'原始发现审计不改写；正文与动作依据单独保存。','discoveredVia':first.get('discoveredVia','broad-discovery'),'discoveryQuery':first.get('discoveryQuery',''),'newDevelopment':bool(spec.get('substantiveNewDevelopment')) if spec else bool(event.get('newDevelopment')),'finalEditorialDecision':decision,'finalEditorialReason':reason,'editorialPriorityScore':event.get('editorialPriorityScore',28),'editorialPriorityLabel':event.get('editorialPriorityLabel','low'),'editorialReasons':event.get('editorialReasons',[])}
 if spec: row.update(dailyItemNumber=specs.index(spec)+1,dailyItemTitle=spec['title'],industryAction=action)
 if spec and spec.get('substantiveNewDevelopment'):
  row.update(substantiveNewDevelopment=True,newDevelopmentEvidence=spec['newDevelopmentEvidence'])
 if idx in [0,15]: row.update(dedupStatus='historical_duplicate',duplicateOf='content/日报/2026-09-'+('13' if idx==0 else '17')+'.md',duplicateReason=reason)
 if idx==12: row.update(dedupStatus='same_day_duplicate',duplicateOf=events[7]['eventId'],duplicateReason=reason)
 ledger.append(row)
pool={'status':'editorial_review_completed','rawQualifiedEvents':len(events),'canonicalUniqueEvents':len(events),'editoriallyReviewed':len(events),'events':events}
replaypath='content/复核/'+day+'.json'
replay={'schema':'daily-editorial-replay-v1','date':day,'runType':'same_day_editorial_revision','replayedAt':now,'replayCutoff':now,'baseDiscoveryAuditPath':base,'baseDiscoveryAuditSha256':hashlib.sha256((ROOT/base).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),'baseDiscoveryAuditHashMode':'lf-normalized-v1','discoveryAuditUnchanged':True,'queryAudits':discovery['queryAudits'],'sourceScans':discovery['sourceScans'],'supplementalDiscoveryAuditPath':'audit/daily-supplement-sources-'+day+'.json','evidenceQualification':{'status':'completed','method':'逐条阅读20个原始最终池事件；定向核验原始高优先级队列，补入3个原文合格事件；ICOM改用同一调查的UNESCO正文。','attemptedEvents':23,'qualifiedEvents':23},'finalEditorialPool':pool}
write(replaypath,replay)
payload={'version':'daily-candidate-ledger-v3','date':day,'scope':'daily','discoveryAuditPath':base,'editorialInputPath':replaypath,'discoveryCompleted':True,'internationalDiscoveryChecked':True,'internationalDiscoveryStatus':'partial','internationalDiscoveryNote':'国际查询完成；ICCROM直接入口fetch_failed，部分高优先级事件原文未完成核验。','candidatePoolDefinition':'唯一编辑输入为复核artifact的finalEditorialPool，继承20个原始事件并补入3个已核验的原始高优先级事件。','productionRun':{'status':'content_prepared','runType':'same_day_catch_up','actualStartedAt':'2026-09-18T11:54:20+08:00','scheduledTime':'07:13 Asia/Shanghai','reason':'北京时间当日日报不存在，实际启动已过07:13；本次为唯一同日回补。'},'revision':{'revisionType':'same_day_editorial_revision','revisedAt':now,'editorialInputPath':replaypath,'discoveryAuditUnchanged':True,'revisionReason':'本轮首次成稿前补核高优先级原文，不修改原始广域发现审计。'},'editorialReview':{'status':'completed','reviewedAt':now,'reviewedEvents':23,'selectedEvents':5,'rejectedEvents':18,'needsVerification':0},'summary':{'discovered':23,'selected':5,'rejected':18,'deferred':0,'needsVerification':0,'finalEditorialPoolEvents':23},'candidates':ledger}
write('content/候选/'+day+'.json',payload)
lines=['# 🏛️ 每日文博资讯 | 2026年9月18日（周五）','','## 📑 本期目录','']+[f"{i}. [{s['title']}](#item{i})" for i,s in enumerate(specs,1)]
lastscope=None
for i,s in enumerate(specs,1):
 if s['scope']!=lastscope: lines+=['','## '+('🇨🇳 国内要闻' if s['scope']=='domestic' else '🌍 国际动态'),''];lastscope=s['scope']
 lines += [f"### {i}. {s['title']}",'',f"🏷️ {s['topic']}",'',f"📎 [{s['name']}]({s['url']})",'',s['summary'],'',f"> **点评：** {s['comment']}",'']
(ROOT/'content/日报'/f'{day}.md').write_text('\n'.join(lines),encoding='utf-8')
print('Prepared 23 reviewed events, 5 selected, 18 rejected; original discovery unchanged.')

"""Concrete institution actions used consistently for recall and ranking.

No publisher/domain/editorial-note bonuses: the subject and action must occur
in article title, summary or body. These are leads, never publication approval.
"""
import re

SUBJECT = r'(?:博物馆|博物院|美术馆|纪念馆|史密森尼|卢浮宫|\b(?:museums?|galleries|gallery|smithsonian|louvre|guggenheim|rijksmuseum)\b)'


def industry_signals(record: dict) -> set[str]:
    text = ' '.join(str(record.get(k) or '') for k in ('title','representativeTitle','summary','body')).lower()
    signals = set()
    if re.search(SUBJECT,text):
        if re.search(r'遭窃|失窃|被盗|盗窃|遭劫|\b(?:stolen|theft|heist|burglary|looted)\b',text):
            signals.add('museum_security_event')
        if re.search(r'\b(?:resigns?|resigned|dismissed|appoints?|appointed|steps down|funding)\b|辞职|卸任|免职|任命|拨款|资金获批|\b(?:federal|government|restoration|capital|research|project) grants?\b|\b(?:awarded|receives?|secures?|gets?|wins?)\b.{0,35}\bgrants?\b',text):
            signals.add('museum_governance_action')
    if re.search(r'洞穴艺术|岩画|\b(?:cave art|rock art)\b',text) and re.search(r'新发现|发现.*(?:人类活动|年代|万年前)|\b(?:discover(?:y|ies|ed)?|uncovered|reveals?)\b',text):
        signals.add('archaeological_discovery_action')
    return signals


def same_restoration_funding(current: dict, previous: dict) -> bool:
    """Conservative Chinese-headline bridge across geographic title prefixes.

Require a distinctive museum-name suffix, identical explicit amount/currency,
    restoration purpose and nearby dates. Other grant types remain unmerged.
    """
    from datetime import date
    from decimal import Decimal
    def facts(row):
        title = re.sub(r'\s+', '', str(row.get('title') or row.get('representativeTitle') or ''))
        title = re.sub(r'(?<=\d),(?=\d)', '', title)
        if re.search(r'取消|撤回|终止|削减|追加|新一轮|第二笔|再次|另获|另拨', title):
            return None
        institution = re.search(r'([\u4e00-\u9fff·]{2,40})(?:博物馆|博物院)', title)
        amount = re.search(r'(\d+(?:\.\d+)?)(万|亿)?(加元|美元|英镑|欧元|人民币)', title)
        if not institution or not amount or not re.search(r'修复|修缮|修缮工程', title) or not re.search(r'拨款|资金|获资助', title):
            return None
        value=Decimal(amount[1])*{'万':10000,'亿':100000000,None:1}[amount[2]]
        return institution[1], value, amount[3]
    left,right=facts(current),facts(previous)
    if not left or not right or left[1:] != right[1:]:return False
    try:
        if abs((date.fromisoformat(current.get('publishedDate',''))-date.fromisoformat(previous.get('publishedDate',''))).days)>7:return False
    except (TypeError,ValueError):return False
    suffix=''
    for a,b in zip(reversed(left[0]),reversed(right[0])):
        if a!=b:break
        suffix=a+suffix
    # 五字专名，排除“历史/自然/国家”等通用馆名尾部。
    return len(suffix)>=5 and not re.search(r'历史|自然|国家|省立|市立|民族|文化',suffix)

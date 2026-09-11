"""Product scope gate: industry developments, not a bibliography feed.

Use the news headline, not source reputation, publication date or an editor's
impact commentary. This conservative lexical guard complements editorial review.
"""
import re

ACADEMIC_PATTERNS = (
    r'名称.{0,8}功用', r'探析|考释|辨析|刍议|试论|浅谈|学术探讨',
    r'发掘(?:简报|报告)', r'分子考古学.*(?:解码|同行史)',
    r'石质文物保护.*(?:检测|建模|材料试验|一域磨剑|全国攻坚)',
    r'(?:研究|考古学).{0,12}(?:解码|演化史|起源问题)',
    r'(?:保护|修复).{0,16}(?:方法介绍|技术综述|实验研究|材料试验)',
    r'新书|书讯|书评|论文解读|研究综述',
    r'\b(?:excavation report|book review|literature review|methodological review)\b',
)
# A concrete action must be in the headline itself. Generic "发布/研究/发现"
# cannot rescue a routine paper/report; a source name or notes cannot rescue it.
ACTION_PATTERNS = (
    r'(?:博物馆|博物院|遗址公园|新馆).{0,18}(?:正式开放|正式开馆|获批建设)',
    r'(?:保护工程|修复工程|考古项目|数字平台|数字化平台).{0,12}(?:启动|获批|验收|上线|启用)',
    r'(?:启动|获批|验收|上线|启用).{0,12}(?:保护工程|修复工程|考古项目|数字平台|数字化平台)',
)


def daily_scope_rejection(record: dict) -> str | None:
    title = str(record.get('representativeTitle') or record.get('title') or '')
    urls = [str(record.get(k) or '') for k in ('url', 'discoveryUrl')]
    urls.extend(str(source.get('url') or '') for source in record.get('evidenceSources', []) if isinstance(source, dict))
    academic_section = any('/kycg/xslw/' in url or '/kycg/jbbg/' in url for url in urls)
    if not academic_section and not any(re.search(pattern, title, re.I) for pattern in ACADEMIC_PATTERNS):
        return None
    if any(re.search(pattern, title, re.I) for pattern in ACTION_PATTERNS):
        return None
    return 'academic_discussion_without_industry_action'

"""Shared, conservative topic classification for daily and map records.

The topic labels are editorial facets, not a bag-of-words dump.  In
particular, a historical subject such as 古文字 is not automatically
archaeology, and words such as 科技/数据/还原 are not, by themselves, proof
of digitisation.
"""

from __future__ import annotations

import re
from typing import Iterable


THEME_ORDER = (
    "考古", "博物馆", "展览", "文物保护", "文化遗产", "数字化",
    "文物追索", "国际交流", "政策行业",
)

# These are intentionally explicit.  Do not add generic words such as
# “科技”“数据”“平台”“还原” here: they create systematic false positives.
DIGITAL_TERMS = (
    "数字化", "数字文博", "数字文物", "数字博物馆", "数字敦煌", "数字故宫",
    "数字孪生", "数字档案", "数字资源", "数字资产", "数字平台", "数字科技",
    "数字技术", "数字体验", "数字服务", "数字展示", "数字保护", "数字回归",
    "数字人文", "数字复原", "数字重建", "数字采集", "数字扫描", "数据平台",
    "数据资源", "知识图谱", "人工智能", "机器学习", "计算机视觉", "大模型",
    "虚拟现实", "增强现实", "混合现实", "虚拟展览", "虚拟展厅",
    "云展览", "线上展览", "线上展播", "智能导览", "智慧博物馆", "智慧文博",
    "数字化展示", "数字化保护", "数字化采集", "数字化管理", "三维扫描",
    "三维重建", "三维建模", "高精度采集", "数字孪生", "元宇宙", "全息",
    "VR", "AR", "XR", "3D扫描",
)

EXHIBITION_TERMS = (
    "展览", "成果展", "特展", "临展", "巡展", "文物展", "艺术展", "国际展览",
    "大展", "展出", "开展", "展陈", "开幕", "亮相", "公众开放", "展厅",
)

ARCHAEOLOGY_TERMS = (
    "考古", "考古发现", "考古学", "田野考古", "公共考古", "科技考古",
    "考古遗址", "旧石器时代", "水下考古", "考古新发现", "发掘", "遗址",
    "墓葬", "古墓", "石窟", "出土", "探方", "地层", "考古调查", "考古发掘",
)

# Scientific study of an excavated object belongs with archaeology when the
# title makes that research intent clear.  “古文字” alone is deliberately
# absent; an ancient-script exhibition belongs with exhibition/museum.
ARCHAEOLOGY_RESEARCH_TERMS = (
    "矿料溯源", "产地溯源", "成分分析", "年代测定", "器物研究", "青铜器研究",
    "祭祀场景", "考释出土", "文物出土", "遗存研究", "考古研究",
)

MUSEUM_TERMS = (
    "博物馆", "博物院", "纪念馆", "展馆", "国博", "馆藏", "开馆", "闭馆",
    "策展", "馆员", "博物馆日",
)

PROTECTION_TERMS = (
    "文物保护", "文物安全", "文物修复", "修复", "保护技术", "科技保护",
    "古建修缮", "壁画保护", "预防性保护", "保护工程", "预防性",
)

HERITAGE_TERMS = (
    "文化遗产", "世界遗产", "世遗", "非遗", "非物质文化遗产", "工业遗产",
    "海洋文化遗产", "农业遗产", "历史街区", "文明探源", "中华文明探源",
    "探源工程", "遗产大会", "传统村落",
)

RECOVERY_TERMS = (
    "文物追索", "文物归还", "文物返还", "文物回归", "流失文物", "追缴", "返还",
)

INTERNATIONAL_TERMS = (
    "国际", "国际合作", "国际交流", "文化外交", "对外交流", "文明互鉴",
    "文明桥梁", "海外", "出国", "UNESCO", "联合国",
)

POLICY_TERMS = (
    "政策", "行业动态", "国家文物局", "立法", "规划", "标准", "指南", "通知",
    "办法", "条例", "规章", "部令", "规范", "规定", "规程", "施行", "修订",
    "文化和旅游部", "文化部", "国务院", "人才", "教育", "出版", "文创", "产业", "文旅",
    "报告", "会议", "论坛",
)


def _has(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _is_exhibition(text: str) -> bool:
    if _has(text, EXHIBITION_TERMS):
        return True
    # Covers common titles such as “图像展对公众开放” without treating
    # unrelated words like “发展”“展示” as exhibitions.
    return bool(re.search(r"(?<!发)[\u4e00-\u9fff]{1,12}展(?=(?:览|出|厅|对公众|开幕|启幕|亮相|在|于|开放))", text))


def classify_themes(
    title: str = "",
    tags: Iterable[str] | None = None,
    body: str = "",
) -> list[str]:
    """Return up to three reliable topic facets in display priority order.

    Title semantics carry more weight than legacy tags.  Legacy generic tags
    such as “科技”“数据”“古文字” are ignored unless the title provides an
    explicit digital/archaeological signal.
    """
    title_text = str(title or "")
    tag_values = [str(tag or "").strip() for tag in (tags or []) if str(tag or "").strip()]
    tag_text = " ".join(tag_values)
    text = f"{title_text} {' '.join(tag_values)} {body or ''}"

    exhibition = _is_exhibition(title_text) or any(
        tag in {"展览", "特展", "临展", "巡展", "文物展", "艺术展", "大展"}
        for tag in tag_values
    )
    explicit_digital = _has(title_text, DIGITAL_TERMS) or any(
        _has(tag, DIGITAL_TERMS) for tag in tag_values
    )
    archaeology = _has(title_text, ARCHAEOLOGY_TERMS)
    research_archaeology = _has(title_text, ARCHAEOLOGY_RESEARCH_TERMS)

    # 古文字/简牍/甲骨等是内容对象，不是自动的事件类型。  They only
    # become archaeology when the title also states excavation/archaeological
    # research, and an exhibition title is kept as exhibition first.
    ancient_script_only = _has(title_text, ("古文字", "甲骨文", "金文", "简牍", "简帛", "铭文"))
    if exhibition and not _has(title_text, ARCHAEOLOGY_TERMS):
        archaeology = False
        research_archaeology = False
    elif not archaeology and ancient_script_only:
        research_archaeology = False

    themes: list[str] = []

    def add(theme: str, enabled: bool = True) -> None:
        if enabled and theme not in themes:
            themes.append(theme)

    # Clear format and institution signals are more useful to readers than
    # generic subject words.  This makes “古文字成果展” read as exhibition.
    add("展览", exhibition)
    add("博物馆", _has(title_text, MUSEUM_TERMS) or (not title_text and _has(tag_text, MUSEUM_TERMS)))
    add("考古", archaeology or research_archaeology)
    add("文物保护", _has(text, PROTECTION_TERMS))
    add("文化遗产", _has(text, HERITAGE_TERMS))
    add("数字化", explicit_digital)
    add("文物追索", _has(text, RECOVERY_TERMS))
    add("国际交流", _has(text, INTERNATIONAL_TERMS))

    # “研究” alone is not a digital or archaeology signal, but it is useful
    # as a broad secondary facet for research/policy records.
    add("政策行业", _has(text, POLICY_TERMS))

    # If a short legacy record contains only a clean explicit tag, retain it;
    # never revive the generic false-positive tags listed above.
    if not themes:
        for tag in tag_values:
            if tag in THEME_ORDER and tag not in {"数字化", "考古"}:
                themes.append(tag)
        if not themes and any(tag in {"数字化", "数字文博"} for tag in tag_values):
            themes.append("数字化")
    return themes[:3] or ["政策行业"]

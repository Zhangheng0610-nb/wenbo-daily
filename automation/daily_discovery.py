"""Auditable broad discovery helpers for the daily editorial report.

The map's fixed six-source monitoring remains separate.  This module records
the wider discovery pass used by the daily editor: source-driven scans,
real query-driven RSS searches, and lightweight event-level deduplication.  It
deliberately does not decide what should be published.
"""
from __future__ import annotations

import argparse
import email.utils
import hashlib
from html import unescape
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener
from xml.etree import ElementTree

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[1]

from automation.backfill_monitoring import fetch, links
from automation.governance import canonical_url, host_matches, source_info

TZ = timezone(timedelta(hours=8))
DISCOVERY_DIR = ROOT / "content" / "发现"
# Search endpoints are public web services and may require the host's normal
# HTTP route.  Fixed-source monitoring keeps its proxy-free opener separately;
# broad discovery must not silently use that network policy.
SEARCH_OPENER = build_opener()
SEARCH_USER_AGENT = "WenboDailyDiscovery/1.1 (+https://zhangheng666.top/)"

# These are repeatable source-driven entry points, not additions to the map
# panel.  A scan can fail independently and must never be recorded as
# ``no_update``.
SOURCE_SCANS = (
    {
        "sourceId": "ncha-wenwu-news",
        "name": "国家文物局文物新闻栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "http://www.ncha.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp?appid=1&webid=1&path=/&columnid=722&unitid=8000&webname=" + quote("国家文物局") + "&permissiontype=0&page=1",
        "domain": "ncha.gov.cn",
    },
    {
        "sourceId": "ncha-policy-news",
        "name": "国家文物局政策/工作动态栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "http://www.ncha.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp?appid=1&webid=1&path=/&columnid=1879&unitid=8000&webname=" + quote("国家文物局") + "&permissiontype=0&page=1",
        "domain": "ncha.gov.cn",
    },
    {
        "sourceId": "xinhua-cultural",
        "name": "新华网文化/文博栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "https://www.news.cn/ci/wb.html",
        "domain": "news.cn",
    },
    {
        "sourceId": "chinanews-cultural",
        "name": "中国新闻网文化栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "https://www.chinanews.com.cn/cul/",
        "domain": "chinanews.com.cn",
    },
    {
        "sourceId": "mct-national-museum",
        "name": "文化和旅游部直属中国国家博物馆栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "https://www.mct.gov.cn/whzx/zsdw/zggjbwg/",
        "domain": "mct.gov.cn",
    },
    {
        "sourceId": "shanxi-museum",
        "name": "山西博物院官网新闻/公告入口",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "https://shanximuseum.com.cn/sx/index/index.html",
        "domain": "shanximuseum.com.cn",
    },
    {
        "sourceId": "unesco-news",
        "name": "UNESCO新闻",
        "kind": "source_scan",
        "scope": "international",
        "url": "https://www.unesco.org/en/newsroom/news",
        "domain": "unesco.org",
    },
    {
        "sourceId": "archaeology-magazine",
        "name": "Archaeology Magazine新闻",
        "kind": "source_scan",
        "scope": "international",
        "url": "https://archaeology.org/news/",
        "domain": "archaeology.org",
    },
)

QUERY_FAMILIES = (
    {"id": "policy-governance", "scope": "domestic", "queries": ("文物 政策 管理办法 通知 施行", "博物馆 管理 政策 文物局", "site:gov.cn 文物 博物馆 政策", "文博 考古 专家 政府特殊津贴", "博物馆 入馆 预约 证件 规则", "博物馆 陈列展览 内容审核 通知")},
    {"id": "archaeology-heritage", "scope": "domestic", "queries": ("考古 新发现 遗址 保护 研究成果", "文物保护 工程 遗产 条例", "site:chinanews.com.cn 考古 遗址 文明", "site:henandaily.cn 考古 文物", "古建筑 修缮 保护工程 文物", "革命文物 烈士墓葬 考古发现", "革命文物 烈士墓 文物保护")},
    {"id": "museum-public-culture", "scope": "domestic", "queries": ("博物馆 开馆 展览 重要馆藏 官方", "博物馆 安全 声明 重大事件", "site:thepaper.cn 博物馆 文物 安全", "site:gov.cn 博物馆 开馆 展览", "博物馆 展览 闭幕 参观人次", "博物馆 国际合作 文物展 数字展示", "site:chinanews.com.cn 博物馆 展览", "博物馆 馆际借展 国际借展 文物", "博物馆 藏品 出境 借展 联展")},
    {"id": "digital-heritage", "scope": "domestic", "queries": ("数字文博 AI 三维 虚拟现实 博物馆", "文物 数字化 数据平台 保护")},
    # Keep Chinese query clauses short.  Search backends commonly treat a
    # long whitespace-separated clause as an AND query; several focused
    # queries preserve recall while the downstream scope/editorial filters
    # remove ordinary awards, routine notices and other noise.
    {"id": "heritage-professionals", "scope": "domestic", "queries": ("文博 特殊津贴", "文博 人才 入选", "考古 专家 名单", "文物专家 公示", "博物馆 人才 任命", "专家 政府 特殊津贴")},
    {"id": "museum-operations", "scope": "domestic", "queries": ("博物馆 入馆", "博物馆 证件 二维码", "博物馆 预约 规则", "博物馆 开放 调整", "博物馆 证件 入馆")},
    {"id": "modern-heritage", "scope": "domestic", "queries": ("烈士墓葬 发现", "革命文物 保护 修缮", "革命遗址 调查", "近现代遗产 保护")},
    {"id": "international-loans", "scope": "international", "queries": ("museum loan exhibition", "museum collection loan", "touring exhibition museum", "museum objects on loan", "major museum loan exhibition", "site:theartnewspaper.com museum loan", "site:smithsonianmag.com museum exhibition")},
    {"id": "local-heritage-governance", "scope": "domestic", "queries": ("文物局 陈列展览 审核", "博物馆 内容审核", "文物局 藏品管理", "地方 博物馆 监管 通知", "site:thepaper.cn 博物馆 陈列展览 审核")},
    {"id": "international-heritage", "scope": "international", "queries": ("museum archaeology cultural heritage", "archaeological discovery heritage site", "heritage protection museum theft", "repatriation museum policy", "digital heritage museum technology", "museum loan exhibition Islamic art", "natural history museum fossil palaeontology exhibition", "museum dinosaur fossil exhibition", "site:polizei.gv.at museum theft", "site:aa.com.tr archaeology heritage", "site:reuters.com museum archaeology heritage", "site:apnews.com museum archaeology heritage")},
)

QUERY_BACKENDS = (
    {"id": "bing-news-rss", "name": "Bing News RSS", "base": "https://www.bing.com/news/search", "locale": "zh"},
    {"id": "google-news-rss", "name": "Google News RSS", "base": "https://news.google.com/rss/search", "locale": "en"},
)

GENERIC_TITLE_WORDS = {
    "文物", "博物馆", "考古", "文化", "遗址", "发布", "举行", "召开", "相关", "我国", "中国", "国际",
    "正式", "工作", "活动", "项目", "新闻", "报道", "最新", "举行", "开展", "推出", "举办",
}
GENERIC_EVENT_WORDS = {
    "museum", "museums", "archaeology", "archaeological", "heritage", "cultural", "culture", "art",
    "news", "report", "official", "china", "chinese", "international", "new", "found", "finds",
    "discovered", "discovery", "research", "study", "event", "theft", "stolen", "steal", "thieves",
    "from", "with", "before", "in", "the", "of", "and", "to", "a", "an", "on", "for", "buy", "tickets",
    "plundering", "brazen", "daytime", "heist",
}
EVIDENCE_CONTEXT_TERMS = {
    "发布", "公布", "举行", "召开", "开展", "推出", "举办", "正式", "相关", "活动", "工作", "成果", "研究",
    "落幕", "闭幕", "开幕", "开馆", "开放", "展期", "接待访客逾", "万人次", "个半月逾", "万访客",
    "文创商品收入逾", "万元", "official", "source", "news", "report",
}
EVIDENCE_CONTEXT_PATTERNS = re.compile(r"(?:接待|访客|人次|收入|万元|带来|逾|超|展期|文创|落幕|闭幕|开幕|开馆|正式)")
DEVELOPMENT_WORDS = ("正式施行", "正式开幕", "正式开放", "揭牌", "签约", "完成交接", "追回", "落网", "发布结论", "新发现", "新增", "启动发掘", "落地")
EVENT_KIND_TERMS = {
    "policy": ("办法", "条例", "规章", "规划", "施行", "规范", "制度"),
    "archaeology": ("考古", "遗址", "墓", "发掘", "出土", "发现", "研究"),
    "museum": ("博物馆", "展览", "大展", "特展", "开馆", "开幕", "闭幕", "展期", "访客"),
    "security": ("盗窃", "失窃", "抢劫", "安全", "追回", "受损"),
    "heritage": ("世界遗产", "历史文化名城", "文化遗产", "古城", "古村"),
    "cooperation": ("合作", "联合", "签约", "备忘录", "交流"),
}
EVENT_ENTITY_SUFFIXES = (
    "展示馆", "博物馆", "博物院", "纪念馆", "研究所", "考古所", "遗址群", "遗址", "大展", "展览",
    "文物展", "墓地", "古墓", "岩画", "古城", "保护工程", "数据平台", "数据库", "资源库", "项目",
)
EVENT_ACTION_PATTERNS = (
    ("policy", ("管理办法", "实施办法", "保护条例", "条例", "规章", "规划", "规范", "制度", "部令", "内容审核", "内容审查", "核查")),
    ("security", ("盗窃", "失窃", "抢劫", "被盗", "追回", "落网", "安全事件", "安全事故")),
    ("archaeology", ("考古发掘", "发掘成果", "遗址调查", "考古发现", "新发现", "出土", "研究揭示", "成果公布")),
    ("opening", ("开馆", "开幕", "正式开放", "启用", "落成", "揭牌")),
    ("exhibition", ("展览", "大展", "特展", "展期", "落幕", "闭幕")),
    ("digital_resource", ("数据库", "数据平台", "资源库", "数字资源", "数字化项目")),
    ("cooperation", ("联合考古", "签约", "合作", "备忘录", "交接")),
)
MATCH_GENERIC_PHRASES = {
    "文物", "博物馆", "博物院", "考古", "遗址", "遗产", "文化", "保护", "研究", "成果", "发现",
    "考古发现", "新发现", "研究成果", "成果公布", "举办展览", "普通活动", "政策", "办法", "条例", "规划",
    "会议", "召开", "活动", "展览", "大展", "特展", "开馆", "开幕", "闭幕", "展期", "正式施行", "正式开放",
    "古墓", "墓地", "遗址发现古墓", "发现古墓", "遗址发掘", "发掘成果", "发掘成果公布", "考古新发现", "重要遗迹",
    "研究揭示", "研究新认识", "工作动态", "一般活动", "内容审核工作", "政策解读", "会议召开", "工作会议", "看展览", "活动通知", "新闻发布", "情况通报", "通知公告",
    "museum", "museums", "archaeology", "archaeological", "heritage", "cultural", "culture", "research",
    "discovery", "discoveries", "found", "finds", "news", "report", "official", "source",
}
PUBLISHER_SUFFIX_TERMS = (
    "新华社", "新华网", "中新网", "中国新闻网", "央视网", "人民网", "中国一带一路网", "文博资讯", "部门动态",
    "新浪财经", "搜狐", "Sohu", "WestK", "香港01", "星島頭條", "即时新闻", "新闻网", "日报", "新闻", "资讯", "门户网站",
)
HIGH_VALUE_TERMS = (
    "政策", "办法", "条例", "施行", "规范", "改革", "考古", "发掘", "新发现", "遗址", "遗产保护", "保护工程",
    "保护研究", "研究成果", "研究揭示", "成果公布", "揭牌", "合作", "签约", "联合考古", "藏品", "安全", "盗窃", "追回", "调查结论", "总结会", "国家历史文化名城", "历史文化名城",
    "museum policy", "museum theft", "stolen", "repatriation", "archaeological discovery", "archaeologists",
    "heritage protection", "conservation", "excavation", "unearthed", "new discovery", "research findings",
    "标本受损", "展品受损", "藏品损坏", "化石受损", "人为破坏", "游客破坏", "擅自触摸",
)
ROUTINE_TERMS = ("报名", "招募", "研学", "常规讲座", "讲座预告", "市集", "音乐季", "周末活动", "打卡", "优惠", "routine", "workshop", "weekend events")
RELEVANCE_TERMS = (
    "文物", "博物馆", "考古", "遗址", "文化遗产", "世界遗产", "国家历史文化名城", "历史文化名城", "石窟", "古建筑", "古墓", "古迹", "发掘", "出土",
    "展览", "大展", "特展", "临展", "联展", "展期", "藏品", "标本", "保护", "修复", "博物馆", "museum", "archaeology", "heritage", "conservation", "excavation",
)
QUERY_FAMILY_RELEVANCE_TERMS = {
    # Query-family terms are a discovery-scope signal only.  They prevent a
    # headline such as a national talent-list announcement from being
    # discarded before editorial review when the headline omits its wenbo
    # discipline; they do not promote the item or bypass evidence checks.
    "heritage-professionals": ("特殊津贴", "文博人才", "文物专家", "考古专家", "博物馆人才", "文博", "文物", "考古"),
    "museum-operations": ("入馆", "博物馆", "博物院", "预约", "二维码", "证件", "开放", "闭馆", "参观"),
    "modern-heritage": ("革命文物", "革命遗址", "烈士墓", "抗战遗址", "近现代遗产", "红色文物", "红色遗产"),
    "international-loans": ("loan", "lending", "on loan", "touring exhibition", "museum", "louvre", "smithsonian", "collection"),
    "local-heritage-governance": ("文物局", "博物馆", "文物", "考古", "遗产", "展览审核", "内容审核", "藏品管理"),
}

# Editorial importance is deliberately independent from source tier.  These
# rules only prioritize the order in which a human/Codex editor should try to
# upgrade evidence; they do not publish a record or replace the evidence gate.
POLICY_PRIORITY_TERMS = ("办法", "条例", "规章", "规划", "规范", "正式施行", "部令", "制度")
NATIONAL_POLICY_TERMS = ("国家文物局", "文化和旅游部", "全国范围", "全国博物馆", "国家级")
ARCHAEOLOGY_DISCOVERY_TERMS = ("考古发现", "考古发掘", "发掘成果", "成果公布", "研究揭示", "研究成果", "新发现", "新认识", "出土", "墓地发现", "遗址发现")
MAJOR_DISCOVERY_TERMS = ("重大考古", "重大新发现", "填补", "重要发现", "重大发现")
SECURITY_PRIORITY_TERMS = ("盗窃", "失窃", "抢劫", "文物安全事件", "追回", "落网", "藏品受损")
MUSEUM_INSTITUTION_TERMS = (
    "博物馆", "博物院", "纪念馆", "美术馆", "自然博物馆", "动物博物馆", "科技馆", "收藏展示机构",
)
COLLECTION_OBJECT_TERMS = (
    "藏品", "馆藏", "展品", "标本", "化石", "遗骸", "文物", "艺术品", "科研标本", "展陈实物",
)
PUBLIC_INCIDENT_TERMS = (
    "受损", "损坏", "破坏", "毁损", "打砸", "踢打", "手抓", "抓取", "拿起", "攀爬", "涂写", "泼洒",
    "擅自触摸", "人为破坏", "游客破坏", "盗窃", "失窃", "抢劫",
)
PUBLIC_SALIENCE_LEVELS = {"normal", "cross_media_attention", "sustained_public_attention"}
PUBLIC_SALIENCE_CENTRAL_DOMAINS = (
    "news.cn", "xinhuanet.com", "people.com.cn", "cctv.com", "cnr.cn", "chinanews.com.cn", "gmw.cn",
)
REPATRIATION_TERMS = ("文物返还", "文物追索", "归还", "交接完成")
HERITAGE_RECOGNITION_TERMS = ("世界遗产", "国家历史文化名城", "历史文化名城")
MUSEUM_PROJECT_TERMS = ("重要展览", "大型展览", "大展", "特展", "正式开幕", "正式开放", "闭幕", "开馆")
MUSEUM_SCALE_TERMS = ("访客", "人次", "观众", "参观人数", "展期")
DIGITAL_PRIORITY_TERMS = ("数字化", "人工智能", "三维扫描", "三维建模", "数字孪生", "数据库", "数据平台", "智慧博物馆", "虚拟现实", "增强现实")
COOPERATION_TERMS = ("联合考古", "国际合作", "合作签约", "签约", "合作备忘录", "国际交流")
ROUTINE_PRIORITY_TERMS = ROUTINE_TERMS + ("培训", "开班", "常规会议", "一般会议", "普通活动", "探馆", "参观", "消费体验")
HIGH_LEVEL_REPRESENTATIVE_TERMS = (
    "国家主席", "主席夫人", "国家元首", "政府首脑", "国家领导人", "第一夫人",
    "总统", "总理", "首相", "总统夫人", "首相夫人", "总理夫人", "外国总统", "外国元首", "国王", "王后",
)
FOREIGN_NATIONAL_REPRESENTATIVE_TERMS = ("总统", "总理", "首相", "国王", "王后", "国家元首", "第一夫人")
DIPLOMATIC_CONTEXT_TERMS = (
    "国事访问", "正式访问", "外事访问", "访问期间", "双边", "两国", "人文交流", "文化交流",
    "文物合作", "联合展览", "联合办展", "联展",
)
CULTURAL_DIPLOMACY_OBJECT_TERMS = ("国家历史博物馆", "国家博物馆", "国家级博物馆", "国家博物院", "世界遗产", "国家级文化机构")
CULTURAL_DIPLOMACY_SUBSTANCE_TERMS = (
    "展览", "文物", "传统文化", "文明", "文化遗产", "人文交流", "文化交流", "联合展", "联展", "文物合作", "保护", "传承",
)
HIGH_RISK_EVIDENCE_TERMS = (
    "盗窃", "失窃", "抢劫", "被盗", "追回", "落网", "犯罪", "指控", "责任", "非法交易",
    "文物损毁", "重大损毁", "法规", "条例", "办法", "规章", "正式施行", "政策发布",
)


def now_cn() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def parse_date(value: str) -> date | None:
    text = value or ""
    patterns = (
        r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)",
        r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)",
        r"(?<!\d)(20\d{2})年(\d{1,2})月(\d{1,2})日",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            continue
    return None


def parse_feed_date(value: str) -> date | None:
    """Parse RSS publication dates without treating an unparseable result as current."""
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is not None:
        return parsed.astimezone(TZ).date() if parsed.tzinfo else parsed.date()
    return parse_date(value)


def actual_query(query: str, start: date, end: date) -> str:
    """Make the requested date window explicit in every real search."""
    return f'{query} after:{start.isoformat()} before:{(end + timedelta(days=1)).isoformat()}'


def search_url(backend: dict, query: str, scope: str = "international") -> str:
    if backend["id"] == "bing-news-rss":
        return backend["base"] + "?" + urlencode({"q": query, "format": "rss"})
    if scope == "domestic":
        params = {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return backend["base"] + "?" + urlencode(params)


def parse_rss(xml_text: str, *, family: dict, backend: dict, query: str, start: date, end: date) -> tuple[list[dict], int, int]:
    root = ElementTree.fromstring(xml_text)
    records = []
    returned = 0
    undated = 0
    for item in root.findall(".//item"):
        returned += 1
        def value(tag: str) -> str:
            node = item.find(tag)
            return (node.text or "").strip() if node is not None else ""
        title = value("title")
        url = value("link")
        published = parse_feed_date(value("pubDate"))
        if not published:
            undated += 1
            continue
        if not (start <= published <= end):
            continue
        source = item.find("source")
        source_name = (source.text or "").strip() if source is not None else backend["name"]
        source_publisher_url = (source.get("url") or "").strip() if source is not None else ""
        record = {
            "title": title,
            "publishedDate": published.isoformat(),
            "url": url,
            "discoveredVia": backend["id"],
            "discoverySourceType": "query_search",
            "discoveryQuery": query,
            "queryFamily": family["id"],
            "queryBackend": backend["id"],
            "scope": family["scope"],
            "sourceDomain": source_name,
        }
        if source_publisher_url:
            record["sourcePublisherUrl"] = source_publisher_url
        records.append(record)
    return records, returned, undated


def _execute_one_query(family: dict, backend: dict, base_query: str, start: date, end: date, *, date_filter: bool = True) -> tuple[list[dict], dict]:
    query = actual_query(base_query, start, end) if date_filter else base_query
    audit = {
        "queryFamily": family["id"],
        "scope": family["scope"],
        "backend": backend["id"],
        "actualQuery": query,
        "executedAt": now_cn(),
        "success": False,
        "failure": None,
        "returnedResultCount": 0,
        "acceptedRawCount": 0,
        "undatedResultCount": 0,
        "dateFilterApplied": date_filter,
    }
    try:
        request = Request(search_url(backend, query, family["scope"]), headers={
            "User-Agent": SEARCH_USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        with SEARCH_OPENER.open(request, timeout=8) as response:
            payload = response.read()
        found, returned, undated = parse_rss(
            payload.decode("utf-8", errors="replace"), family=family, backend=backend,
            query=query, start=start, end=end
        )
        audit["success"] = True
        audit["returnedResultCount"] = returned
        audit["acceptedRawCount"] = len(found)
        audit["undatedResultCount"] = undated
        return found, audit
    except Exception as exc:  # each query is independently auditable
        audit["failure"] = f"{type(exc).__name__}: {exc}"
        return [], audit


def execute_queries(required_date: date, start: date, end: date) -> tuple[list[dict], list[dict]]:
    """Execute every configured query concurrently, retaining one audit row per query."""
    tasks = [
        (family, backend, base_query)
        for family in QUERY_FAMILIES
        for backend in QUERY_BACKENDS
        for base_query in family["queries"]
    ]
    results = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
        futures = {
            pool.submit(_execute_one_query, family, backend, base_query, start, end): index
            for index, (family, backend, base_query) in enumerate(tasks)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    records = []
    audits = []
    for found, audit in results:
        records.extend(found)
        audits.append(audit)
    return records, audits


def compact(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def meaningful_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", (text or "").lower()))
    return {term for term in terms if term not in GENERIC_TITLE_WORDS and len(term) >= 2}


def clean_discovery_title(title: str) -> str:
    """Remove transport/source suffixes before comparing syndicated reports."""
    value = unescape(title or "").replace("\u00a0", " ").strip()
    suffix = "|".join(re.escape(term) for term in PUBLISHER_SUFFIX_TERMS)
    domain = r"(?:[a-z0-9][a-z0-9.-]*\.[a-z]{2,})"
    publisher_label = r"(?:[\u4e00-\u9fff]{2,16}(?:新闻|日报|新闻网|资讯|网|报|网站|部门动态|文博资讯))"
    suffix_pattern = re.compile(
        rf"\s*(?:-|_|[|｜])\s*(?:{suffix}|{domain}|{publisher_label})\s*$",
        re.I,
    )
    previous = None
    while value and value != previous:
        previous = value
        value = suffix_pattern.sub("", value).strip()
    return re.sub(r"^[\s【\[]*(?:新华社|中新网|央视网|媒体报道)[：:）)、 ]*", "", value).strip()


def _match_fragment_is_weak(fragment: str) -> bool:
    """Reject topic-only fragments while retaining named entities and places."""
    value = compact(fragment)
    if len(value) < 3:
        return True
    if value in {compact(term) for term in MATCH_GENERIC_PHRASES}:
        return True
    if re.fullmatch(r"[a-z0-9]+", value):
        return value in GENERIC_EVENT_WORDS or len(value) < 4
    generic_chars = set("".join(MATCH_GENERIC_PHRASES))
    # “考古新发现” and “一般展览” are made entirely of generic vocabulary;
    # “元谋人遗址”“塞赫迈特神庙” retain a named/location signal.
    return len(value) <= 8 and all(char in generic_chars for char in value)


def event_match_terms(text: str) -> set[str]:
    """Create bounded Chinese/Latin anchors for article-level event matching."""
    value = clean_discovery_title(text)
    terms = set()
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if not _match_fragment_is_weak(token):
            terms.add(token)
    for run in re.findall(r"[\u4e00-\u9fff]+", value):
        if not _match_fragment_is_weak(run) and len(run) <= 48:
            terms.add(run)
        upper = min(8, len(run))
        for size in range(3, upper + 1):
            for start in range(0, len(run) - size + 1):
                fragment = run[start:start + size]
                if not _match_fragment_is_weak(fragment):
                    terms.add(fragment)
    return terms


def event_actions(text: str) -> set[str]:
    value = clean_discovery_title(text)
    return {
        action for action, patterns in EVENT_ACTION_PATTERNS
        if any(pattern in value for pattern in patterns)
    }


def publisher_domains(record: dict) -> list[str]:
    """Return publisher hosts separately from RSS/search transport hosts."""
    domains = set()
    publisher_url = str(record.get("sourcePublisherUrl") or "")
    host = (urlsplit(publisher_url).hostname or "").lower()
    if host and not is_search_wrapper_url(publisher_url):
        domains.add(host)
    source_domain = str(record.get("sourceDomain") or "").lower().strip()
    if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", source_domain) and source_domain not in {"news.google.com", "bing.com"}:
        domains.add(source_domain)
    return sorted(domains)


def event_match_details(event: dict, result: dict, body: str = "") -> dict:
    """Explain whether an article is about the event, independent of its tier."""
    event_title = clean_discovery_title(event.get("representativeTitle") or event.get("title", ""))
    result_title = clean_discovery_title(result.get("title", ""))
    body_text = visible_article_text(body)[:12000]
    event_terms = event_match_terms(event_title)
    result_title_terms = event_match_terms(result_title)
    result_body_terms = event_match_terms(body_text)
    shared_title = event_terms & result_title_terms
    shared_body = event_terms & result_body_terms
    strong_title = sorted(shared_title, key=lambda term: (-len(term), term))
    strong_body = sorted(shared_body, key=lambda term: (-len(term), term))
    event_text = " ".join((event_title, str(event.get("summary") or ""), str(event.get("body") or "")))
    result_text = " ".join((result_title, body_text))
    event_action_set = event_actions(event_text)
    result_action_set = event_actions(result_text)
    action_overlap = event_action_set & result_action_set
    action_conflict = bool(event_action_set and result_action_set and not action_overlap)
    kind_overlap = event_kind(event_title) & event_kind(result_text)
    normalized_equal = bool(
        normalized_event_title(event_title)
        and normalized_event_title(event_title) == normalized_event_title(result_title)
    )
    score = 0
    reasons = []
    if normalized_equal:
        score = 100
        reasons.append("normalized_title_equal")
    else:
        if strong_title:
            score += min(60, 28 + len(strong_title) * 7 + min(20, len(strong_title[0]) * 2))
            reasons.append("shared_named_title_anchor")
        if strong_body:
            score += min(24, 12 + len(strong_body) * 3)
            reasons.append("shared_named_body_anchor")
        if action_overlap:
            score += 20
            reasons.append("compatible_event_action")
        elif kind_overlap:
            score += 10
            reasons.append("compatible_event_kind")
    matched = (normalized_equal and not action_conflict) or bool(strong_title and action_overlap) or bool(
        len(strong_title) >= 2 and strong_body
    )
    return {
        "matched": matched,
        "score": min(100, score),
        "reasons": reasons,
        "eventAnchors": strong_title[:8],
        "bodyAnchors": strong_body[:8],
        "actionOverlap": sorted(action_overlap),
        "actionConflict": action_conflict,
        "eventKindOverlap": sorted(kind_overlap),
    }


def normalized_event_title(title: str) -> str:
    """Normalize a headline for cross-source historical identity checks."""
    value = clean_discovery_title(title)
    value = re.sub(r"(?:\s+|[：:，。、“”‘’「」『』《》（）()【】\[\]—–·•,.;!?！？])", "", value)
    return compact(value)


def event_kind(title: str) -> set[str]:
    text = clean_discovery_title(title)
    return {kind for kind, terms in EVENT_KIND_TERMS.items() if any(term in text for term in terms)}


def event_action(text: str) -> str:
    """Return a coarse event action so one entity's different events stay separate."""
    value = text or ""
    for action, patterns in EVENT_ACTION_PATTERNS:
        if any(pattern in value for pattern in patterns):
            return action
    return ""


def event_named_entity(text: str) -> str:
    """Extract a named institution/project/instrument, not a generic topic word."""
    value = clean_discovery_title(text)
    quoted = re.findall(r"《([^》]{2,48})》", value)
    for phrase in quoted:
        if any(phrase.endswith(suffix) for suffix in EVENT_ENTITY_SUFFIXES) or any(
            phrase.endswith(suffix) for suffix in ("办法", "条例", "规章", "规划", "规范")
        ):
            return compact(phrase)
    candidates = []
    for suffix in EVENT_ENTITY_SUFFIXES:
        for candidate in re.findall(rf"[\u4e00-\u9fff]{{4,40}}{re.escape(suffix)}", value):
            # A body sentence can continue with the host institution, e.g.
            # “成果展示馆在湖南省博物馆开馆”.  Keep the named object before
            # the relation rather than accidentally choosing the host venue.
            candidate = re.split(r"(?:在|于|与|和|并|发布|推出|位于)", candidate, maxsplit=1)[0]
            if len(candidate) >= 4:
                candidates.append(candidate)
    if not candidates:
        return ""
    # Prefer the longest named phrase; this keeps a specific project ahead of
    # a hosting institution such as 湖南省博物馆.
    return compact(max(candidates, key=len))


def has_specific_event_anchor(record: dict) -> bool:
    """Keep generic exact headlines from becoming cross-event identities."""
    title = clean_discovery_title(record.get("representativeTitle") or record.get("title", ""))
    context = " ".join(str(record.get(key) or "") for key in ("summary", "body", "entity", "institution", "location"))
    normalized_title = compact(title)
    generic_titles = {compact(phrase) for phrase in MATCH_GENERIC_PHRASES}
    if normalized_title and normalized_title in generic_titles:
        return False
    if event_named_entity(title) or event_named_entity(context):
        return True
    if re.search(r"[\u4e00-\u9fff]{2,16}(?:管理办法|实施办法|保护条例|条例|办法|规定|规程|规划)", title):
        return True
    return any(not _match_fragment_is_weak(term) for term in event_match_terms(title))


def event_match_relation(current: dict, previous: dict) -> tuple[str, str] | None:
    """Bridge article-level semantic matching into current-window clustering."""
    if not (has_specific_event_anchor(current) and has_specific_event_anchor(previous)):
        return None
    details = event_match_details(current, previous, "")
    if not details.get("matched"):
        return None
    try:
        distance = abs(date.fromisoformat(current.get("publishedDate", "")) - date.fromisoformat(previous.get("publishedDate", ""))).days
    except (TypeError, ValueError):
        distance = 99
    if distance > 14:
        return None
    if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
        return ("new_development", "specific event match with a current development marker")
    return (
        "same_day_duplicate" if distance == 0 else "historical_duplicate",
        "specific event match across title/action variants",
    )


def canonical_event_identity(record: dict) -> str:
    """Build a stable cross-report identity from entity + action + structure.

    Published daily Markdown is the historical authority.  Its body is used
    here so a shortened later headline can still match the same event without
    treating a same-institution, different-action event as a duplicate.
    """
    identity_hint = record.get("canonicalIdentity")
    if identity_hint:
        return str(identity_hint)
    explicit = record.get("canonicalEventId")
    if explicit:
        return str(explicit)
    title = str(record.get("title") or "")
    context = " ".join(
        str(record.get(key) or "")
        for key in ("summary", "body", "notes", "institution", "publisher", "entity", "eventType", "location")
    )
    # Headline entities are preferred over descriptive phrases in the body
    # (for example “首座以语言资源为主题的展示馆”).
    named = event_named_entity(title) or event_named_entity(context)
    text = " ".join((title, context))
    action = event_action(text)
    if named and action:
        location = compact(str(record.get("location") or ""))
        return "named|" + named + "|" + action + ("|" + location if location else "")
    structured = [record.get("entity", ""), record.get("eventType", ""), record.get("location", "")]
    if any(structured):
        return "structured|" + "|".join(compact(str(bit)) for bit in structured)
    if named:
        return "named|" + named
    return ""


def event_report_relation(current: dict, previous: dict) -> tuple[str, str] | None:
    """Find same-event reports without treating similar subjects as one event."""
    current_url = canonical_url(current.get("url") or "")
    previous_url = canonical_url(previous.get("url") or "")
    if current_url and previous_url and current_url == previous_url:
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical discovery URL")
    current_identity = canonical_event_identity(current)
    previous_identity = canonical_event_identity(previous)
    if current_identity and current_identity == previous_identity:
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "same canonical event identity with a substantive development marker")
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical event identity")
    matched_relation = event_match_relation(current, previous)
    if matched_relation:
        return matched_relation
    left = meaningful_terms(clean_discovery_title(current.get("title", "")))
    right = meaningful_terms(clean_discovery_title(previous.get("title", "")))
    shared = left & right
    generic_cjk = set(GENERIC_TITLE_WORDS) | {
        "大展", "展览", "展", "开展", "展在", "政策", "政策解读", "政策措施", "办法", "管理办法", "实施办法", "规划", "十五五", "征求意见", "意见", "公告",
        "会议", "活动", "研究成果", "新发现", "考古发现", "博物馆", "美术馆", "文物", "考古", "遗址", "发现", "成果", "研究", "文化", "遗产", "国际", "中国", "国家",
    }
    anchors = {
        term for term in shared
        if len(term) >= 4
        and term not in GENERIC_EVENT_WORDS
        and not re.fullmatch(r"[a-z0-9.]+", term)
        and not any(generic in term for generic in generic_cjk)
    }
    # A title may shorten a named event, such as "古埃及文明大展" versus
    # "古埃及展". Accept a shared non-generic CJK name fragment while keeping
    # broad words such as 博物馆/政策 out of event identity matching.
    left_cjk = [term for term in left if re.search(r"[\u4e00-\u9fff]", term)]
    right_cjk = [term for term in right if re.search(r"[\u4e00-\u9fff]", term)]
    for lterm in left_cjk:
        for rterm in right_cjk:
            fragment = lterm if len(lterm) <= len(rterm) and lterm in rterm else rterm if rterm in lterm else ""
            if len(fragment) >= 3 and not any(generic in fragment for generic in generic_cjk):
                anchors.add(fragment)
    # Continuous Chinese titles are often not segmented around a shortened
    # exhibition name. A three-character fragment is accepted only when both
    # titles visibly describe an exhibition, avoiding generic policy or
    # archaeology fragments such as 管理办法/址考古.
    left_text = "".join(left_cjk)
    right_text = "".join(right_cjk)
    for size in (3,):
        for start in range(0, len(left_text) - size + 1):
            fragment = left_text[start:start + size]
            if fragment in right_text and not any(generic in fragment for generic in generic_cjk):
                left_pos = left_text.find("展", start, min(len(left_text), start + size + 7))
                right_pos = right_text.find("展")
                if left_pos < 0 or right_pos < 0 or abs(left_pos - start) > 6 or abs(right_pos - right_text.find(fragment)) > 6:
                    continue
                anchors.add(fragment)
                break
    if not anchors or not (event_kind(current.get("title", "")) & event_kind(previous.get("title", ""))):
        return None
    try:
        distance = abs(date.fromisoformat(current.get("publishedDate", "")) - date.fromisoformat(previous.get("publishedDate", ""))).days
    except (TypeError, ValueError):
        distance = 99
    if distance > 2 and len(shared) < 2:
        return None
    if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
        return ("new_development", "shared named event anchor with a current development marker")
    return ("same_day_duplicate" if distance == 0 else "historical_duplicate", "shared named event anchor and event type")


def event_id_for(group: list[dict]) -> str:
    identities = {canonical_event_identity(row) for row in group if canonical_event_identity(row)}
    if len(identities) == 1:
        identity = next(iter(identities))
        return "event-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    common = None
    for row in group[1:]:
        terms = meaningful_terms(clean_discovery_title(row.get("title", "")))
        common = terms if common is None else common & terms
    if not common:
        common = meaningful_terms(clean_discovery_title(group[0].get("title", "")))
    identity = "|".join(sorted(term for term in common if len(term) >= 4)) or event_key(group[0])
    return "event-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]


def compact_discovery_report(row: dict) -> dict:
    compacted = {
        key: row.get(key)
        for key in ("title", "url", "publishedDate", "discoveredVia", "discoverySourceType", "discoveryQuery", "queryFamily", "sourceDomain", "sourcePublisherUrl", "duplicateStatus", "duplicateOrigin")
        if row.get(key) is not None
    }
    domains = publisher_domains(row)
    if domains:
        compacted["publisherDomain"] = domains[0] if len(domains) == 1 else domains
    if is_search_wrapper_url(str(row.get("url") or "")):
        compacted["transportUrl"] = row.get("url")
    return compacted


def aggregate_event_candidates(records: list[dict]) -> list[dict]:
    """Collapse current-window reports into event candidates before scoring."""
    groups: list[list[dict]] = []
    for row in records:
        if row.get("duplicateStatus") == "historical_duplicate":
            continue
        for group in groups:
            relation = event_report_relation(row, group[0])
            if relation:
                group.append(row)
                break
        else:
            groups.append([row])
    # A report may have been marked historical because it matched an older
    # daily item, while another report for the same event is also present in
    # this replay window. Keep that report only when it matches a current
    # event group; history-only repeats stay out of the candidate pool.
    for row in records:
        if row.get("duplicateStatus") != "historical_duplicate":
            continue
        for group in groups:
            if event_report_relation(row, group[0]):
                group.append(row)
                break
    events = []
    used_event_ids = set()
    for group in groups:
        # Prefer a directly classified A/B URL as representative; otherwise use
        # the most informative title while preserving all discovery reports.
        ranked = sorted(
            group,
            key=lambda row: (
                1 if source_info(row.get("url", "")).get("tier") in {"A", "B"} else 0,
                len(clean_discovery_title(row.get("title", ""))),
            ),
            reverse=True,
        )
        representative = ranked[0]
        title = clean_discovery_title(representative.get("title", ""))
        dates = [row.get("publishedDate") for row in group if row.get("publishedDate")]
        scopes = [row.get("scope", "domestic") for row in group]
        source_domains = sorted({row.get("sourceDomain") for row in group if row.get("sourceDomain")})
        query_families = sorted({row.get("queryFamily") for row in group if row.get("queryFamily")})
        publisher_domain_set = set()
        for row in group:
            publisher_domain_set.update(publisher_domains(row))
        event_id = event_id_for(group)
        if event_id in used_event_ids:
            # Identity terms can legitimately collide for separate reports
            # such as generic "政策解读" pages. Keep the semantic base ID,
            # but make the collision deterministic from this group's URLs.
            signature = "|".join(sorted(canonical_url(row.get("url") or "") for row in group))
            suffix = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8]
            event_id = f"{event_id}-{suffix}"
            counter = 2
            while event_id in used_event_ids:
                event_id = f"{event_id_for(group)}-{suffix}-{counter}"
                counter += 1
        used_event_ids.add(event_id)
        event = {
            "eventId": event_id,
            "title": title,
            "representativeTitle": title,
            "url": representative.get("url", ""),
            "publishedDate": max(dates) if dates else representative.get("publishedDate", ""),
            "scope": "international" if scopes.count("international") > len(scopes) / 2 else "domestic",
            "newDevelopment": any(row.get("newDevelopment") is True for row in group),
            "discoveryReports": [compact_discovery_report(row) for row in group],
            "reportCount": len(group),
            "sourceDomains": source_domains,
            "publisherDomains": sorted(publisher_domain_set),
            "queryFamilies": query_families,
        }
        events.append(event)
        for row in group:
            row["eventId"] = event["eventId"]
    return events


def evidence_upgrade_queries(event: dict) -> list[str]:
    """Build bounded, event-specific searches without using source tier as rank."""
    title = clean_discovery_title(event.get("representativeTitle") or event.get("title", ""))
    terms = [
        term for term in meaningful_terms(title)
        if len(term) >= 3
        and term not in EVIDENCE_CONTEXT_TERMS
        and term not in GENERIC_EVENT_WORDS
        and not EVIDENCE_CONTEXT_PATTERNS.search(term)
        and not re.fullmatch(r"\d+", term)
        and not re.search(r"\d", term)
    ]
    # Prefer named Chinese phrases and keep the anchor small.  Metrics and
    # event verbs make source searches noisy without improving identity
    # matching; parse_rss still applies the requested date window.
    cjk_terms = sorted((term for term in terms if re.search(r"[\u4e00-\u9fff]", term)), key=lambda term: (-len(term), term))
    latin_terms = sorted((term for term in terms if re.fullmatch(r"[a-z][a-z0-9-]{3,}", term)), key=lambda term: (-len(term), term))
    anchor_terms = cjk_terms[:1] if cjk_terms else latin_terms[:3]
    anchor_query = " ".join(anchor_terms)
    suffix = " 官方原文" if event.get("scope") != "international" else " official source"
    queries = [title + suffix]
    if anchor_query and anchor_query not in title:
        queries.append(anchor_query + suffix)
    elif anchor_query:
        queries.append(anchor_query)
    domains = set(event.get("publisherDomains", []))
    for report in event.get("discoveryReports", []):
        domains.update(publisher_domains(report))
    for domain in domains | {
        value for value in event.get("sourceDomains", [])
        if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", str(value or "").lower())
    }:
        if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", str(domain or "").lower()) and domain not in {"news.google.com", "bing.com"}:
            queries.append(f"site:{domain} {anchor_query or title}")
            # A named event plus one concrete fact is often indexed more
            # reliably than the title alone.  Keep this generic: derive the
            # qualifier from the event title instead of baking in a headline.
            qualifiers = re.findall(r"\d+(?:\.\d+)?(?:万|亿|人次|件|种|个月|亿元|万元)", title)
            if anchor_query and qualifiers:
                queries.append(f"site:{domain} {anchor_query} {qualifiers[0]}")
    return list(dict.fromkeys(query for query in queries if query.strip()))


def publisher_search_endpoint(report: dict) -> tuple[str, str] | None:
    """Return a publisher's own search endpoint when it is publicly known.

    Search-engine RSS is useful for recall but often exposes only an opaque
    redirect.  A small, explicit adapter for a publisher's public search
    endpoint lets the resolver retrieve the publisher URL without promoting
    that publisher's whole domain or treating the RSS wrapper as evidence.
    The adapter is keyed by publisher host, never by a headline.
    """
    publisher_url = report.get("sourcePublisherUrl") or ""
    host = (urlsplit(publisher_url).hostname or "").lower()
    if not host and re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", str(report.get("sourceDomain") or "").lower()):
        host = str(report["sourceDomain"]).lower()
    if host_matches(host, "chinanews.com.cn") or host_matches(host, "chinanews.com"):
        return "https://sou.chinanews.com.cn/search.do", host
    return None


def publisher_search_results(event: dict, report: dict, start: date, end: date) -> tuple[list[dict], dict | None]:
    """Query a known publisher search page and return direct article URLs."""
    endpoint = publisher_search_endpoint(report)
    if not endpoint:
        return [], None
    search_url_base, host = endpoint
    title = clean_discovery_title(event.get("representativeTitle") or event.get("title", ""))
    query_terms = [
        term for term in meaningful_terms(title)
        if term not in EVIDENCE_CONTEXT_TERMS
        and term not in GENERIC_EVENT_WORDS
        and len(term) <= 24
    ]
    named_terms = [
        term for term in query_terms
        if any(term.endswith(suffix) for suffix in EVENT_ENTITY_SUFFIXES)
    ]
    remaining_terms = [term for term in query_terms if term not in named_terms]
    # Prefer two stable named anchors.  Adding every long headline fragment
    # makes publisher search brittle, especially for Chinese pages whose
    # search endpoint already performs its own tokenization.
    anchors = named_terms[:2] or remaining_terms[:2]
    query = " ".join(anchors) or title
    url = search_url_base + "?" + urlencode({"q": query})
    audit = {
        "queryFamily": "evidence-upgrade",
        "scope": event.get("scope", "domestic"),
        "backend": "publisher-search",
        "actualQuery": f"site:{host} {query}",
        "executedAt": now_cn(),
        "success": False,
        "failure": None,
        "returnedResultCount": 0,
        "acceptedRawCount": 0,
        "dateFilterApplied": True,
    }
    try:
        request = Request(url, headers={
            "User-Agent": SEARCH_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        with SEARCH_OPENER.open(request, timeout=8) as response:
            payload = response.read(320_000).decode("utf-8", errors="replace")
        # China News exposes its public search result list as JSON assigned to
        # docArr.  This is a publisher-level result API, not a title-specific
        # exception, and the returned URLs are fetched and matched below.
        match = re.search(r"var\s+docArr\s*=\s*(\[.*?\]);", payload, flags=re.S)
        docs = json.loads(match.group(1)) if match else []
        if not isinstance(docs, list):
            docs = []
        found = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            article_url = unescape(str(doc.get("url") or "")).replace("\\/", "/")
            published = parse_date(str(doc.get("createtime") or ""))
            if not article_url or not published or not (start <= published <= end):
                continue
            snippet = visible_article_text(str(doc.get("content_without_tag") or ""))
            found.append({
                "title": snippet or title,
                "publishedDate": published.isoformat(),
                "url": article_url,
                "discoveredVia": "publisher-search",
                "discoverySourceType": "evidence_upgrade",
                "discoveryQuery": query,
                "queryFamily": "evidence-upgrade",
                "queryBackend": "publisher-search",
                "scope": event.get("scope", "domestic"),
                "sourceDomain": host,
            })
        audit["success"] = True
        audit["returnedResultCount"] = len(docs)
        audit["acceptedRawCount"] = len(found)
        return found, audit
    except Exception as exc:
        audit["failure"] = f"{type(exc).__name__}: {exc}"
        return [], audit


class _EvidenceMetaParser(HTMLParser):
    """Collect publisher URLs exposed by ordinary article metadata."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): value for key, value in attrs}
        if tag.lower() == "link" and str(values.get("rel", "")).lower() == "canonical":
            value = values.get("href")
        elif tag.lower() == "meta" and str(values.get("property", "")).lower() in {"og:url", "og:see_also"}:
            value = values.get("content")
        elif tag.lower() == "meta" and str(values.get("name", "")).lower() in {"original-source", "source_url", "source-url"}:
            value = values.get("content")
        else:
            value = None
        if value:
            self.urls.append(value.strip())


class _ArticleMetaParser(HTMLParser):
    """Collect the small amount of page metadata needed for article checks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.dates = []
        self.publisher = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): value for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
            return
        if tag.lower() != "meta":
            return
        key = str(values.get("property") or values.get("name") or "").lower()
        value = str(values.get("content") or "").strip()
        if not value:
            return
        if key in {"article:published_time", "datepublished", "pubdate", "publishdate", "datecreated"}:
            self.dates.append(value)
        elif key in {"og:site_name", "application-name", "publisher", "author"} and not self.publisher:
            self.publisher = value

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and data.strip():
            self.title_parts.append(data.strip())


def article_metadata(body: str) -> dict:
    parser = _ArticleMetaParser()
    try:
        parser.feed(body or "")
    except Exception:
        return {"title": "", "dates": [], "publisher": ""}
    return {
        "title": unescape(" ".join(parser.title_parts)).strip(),
        "dates": parser.dates,
        "publisher": parser.publisher,
    }


def visible_article_text(body: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", body or "", flags=re.I | re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def is_search_wrapper_url(url: str) -> bool:
    host = (urlsplit(url or "").hostname or "").lower()
    return host in {"news.google.com", "www.google.com", "bing.com", "www.bing.com"}


def article_level_provisional_b(event: dict, result: dict, resolved_url: str, body: str) -> tuple[bool, dict]:
    """Verify an unregistered direct article without promoting its whole domain."""
    info = source_info(resolved_url)
    metadata = article_metadata(body)
    host = (urlsplit(resolved_url or "").hostname or "").lower()
    visible = visible_article_text(body)
    article_result = dict(result)
    article_result["title"] = metadata.get("title") or result.get("title", "")
    matched = bool(host) and not is_search_wrapper_url(resolved_url) and evidence_matches_event(event, article_result, body)
    has_date = bool(result.get("publishedDate")) or any(parse_date(value) for value in metadata.get("dates", [])) or bool(parse_date(resolved_url))
    publisher = metadata.get("publisher") or result.get("sourceDomain") or host
    checks = {
        "articleMatched": matched,
        "hasPublisher": bool(publisher),
        "hasPublishedDate": has_date,
        "bodyCharacters": len(visible),
        "directArticle": bool(host) and not is_search_wrapper_url(resolved_url),
        "blocked": bool(info.get("blocked")),
        "publisher": publisher,
    }
    return bool(
        info.get("tier") == "C"
        and not info.get("blocked")
        and checks["directArticle"]
        and checks["articleMatched"]
        and checks["hasPublisher"]
        and checks["hasPublishedDate"]
        and checks["bodyCharacters"] >= 80
    ), checks


def unwrap_redirect_url(url: str) -> tuple[str, bool]:
    """Extract an embedded publisher URL from common news redirect links."""
    original = url or ""
    parts = urlsplit(original)
    host = (parts.hostname or "").lower()
    if host.endswith("bing.com") and parts.path.lower().endswith("/apiclick.aspx"):
        embedded = parse_qs(parts.query).get("url", [""])[0]
        if embedded:
            return unquote(embedded), True
    # Some providers use a generic redirect endpoint with a url/u/target
    # parameter. Only accept an absolute HTTP(S) target; arbitrary query text
    # must never become an evidence URL.
    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
        for key in ("url", "u", "target", "dest", "destination"):
            embedded = parse_qs(parts.query).get(key, [""])[0]
            if urlsplit(embedded).scheme in {"http", "https"}:
                return unquote(embedded), True
    return original, False


def metadata_urls(base_url: str, body: str) -> list[str]:
    parser = _EvidenceMetaParser()
    try:
        parser.feed(body or "")
    except Exception:
        return []
    candidates = []
    for value in parser.urls:
        candidate = urljoin(base_url, value)
        if urlsplit(candidate).scheme in {"http", "https"} and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def resolve_evidence_url(url: str) -> tuple[str, str, str | None]:
    """Follow redirects/canonical metadata and retrieve a bounded source sample."""
    url, _ = unwrap_redirect_url(url)
    request = Request(url, headers={"User-Agent": SEARCH_USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
    try:
        with SEARCH_OPENER.open(request, timeout=8) as response:
            resolved = response.geturl() or url
            body = response.read(256_000).decode("utf-8", errors="replace")
        # A publisher page may explicitly expose the canonical/original URL.
        # Follow only a non-aggregator HTTP(S) metadata target, and keep the
        # first page as a fallback if the metadata target is unavailable.
        for candidate in metadata_urls(resolved, body):
            candidate_host = (urlsplit(candidate).hostname or "").lower()
            if candidate_host.endswith(("news.google.com", "bing.com")) or canonical_url(candidate) == canonical_url(resolved):
                continue
            actual = source_info(candidate)
            if actual.get("blocked"):
                continue
            try:
                follow_request = Request(candidate, headers={"User-Agent": SEARCH_USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
                with SEARCH_OPENER.open(follow_request, timeout=8) as follow_response:
                    followed = follow_response.geturl() or candidate
                    followed_body = follow_response.read(256_000).decode("utf-8", errors="replace")
                return followed, followed_body, None
            except Exception:
                continue
        return resolved, body, None
    except Exception as exc:
        return url, "", f"{type(exc).__name__}: {exc}"


def evidence_matches_event(event: dict, result: dict, body: str) -> bool:
    return bool(event_match_details(event, result, body).get("matched"))


def resolve_evidence_attempt(event: dict, result: dict, method: str) -> tuple[dict, dict | None]:
    """Resolve one report and return an auditable attempt plus publishable source."""
    input_url = result.get("url", "")
    publisher_domain = (publisher_domains(result) or [(urlsplit(input_url).hostname or "").lower()])[0]
    unwrapped_url, unwrapped = unwrap_redirect_url(input_url)
    attempts = []
    if unwrapped:
        unwrapped_actual = source_info(unwrapped_url)
        attempts.append({
            "method": "redirect_unwrap",
            "inputUrl": input_url,
            "resolvedUrl": unwrapped_url,
            "domain": (urlsplit(unwrapped_url).hostname or "").lower(),
            "publisherDomain": publisher_domain,
            "fetchStatus": "resolved",
            "articleMatched": False,
            "evidenceTier": unwrapped_actual.get("tier", "C"),
        })
    resolved_url, body, resolve_error = resolve_evidence_url(unwrapped_url)
    actual = source_info(resolved_url)
    matched = False
    match_details = {}
    evidence_tier = actual.get("tier", "C")
    verification = {}
    wrapper_page = is_search_wrapper_url(resolved_url)
    if not resolve_error and not actual.get("blocked") and not wrapper_page:
        metadata = article_metadata(body)
        article_result = dict(result)
        article_result["title"] = metadata.get("title") or result.get("title", "")
        match_details = event_match_details(event, article_result, body)
        matched = bool(match_details.get("matched"))
        if actual.get("tier") not in {"A", "B"}:
            provisional, verification = article_level_provisional_b(event, result, resolved_url, body)
            matched = provisional
            if provisional:
                evidence_tier = "provisional_B"
    attempts.append({
        "method": method,
        "inputUrl": input_url,
        "resolvedUrl": resolved_url,
        "domain": (urlsplit(resolved_url).hostname or "").lower(),
        "publisherDomain": publisher_domain,
        "fetchStatus": "wrapper" if wrapper_page and not resolve_error else "ok" if not resolve_error else "failed",
            "articleMatched": matched,
            "matchScore": match_details.get("score", 0),
            "matchReasons": match_details.get("reasons", []),
            "evidenceTier": evidence_tier if matched else actual.get("tier", "C"),
    })
    checked = {
        "discoveryUrl": input_url,
        "url": resolved_url,
        "publisherDomain": publisher_domain,
        "title": result.get("title", ""),
        "tier": actual.get("tier", "C"),
        "retrieved": not bool(resolve_error) and not wrapper_page,
        "matched": matched,
        "error": ("search_wrapper" if wrapper_page and not resolve_error else resolve_error),
        "method": method,
    }
    checked["articleVerified"] = bool(matched and evidence_tier in {"A", "B", "provisional_B"})
    checked["articleVerification"] = verification
    checked["eventMatch"] = match_details
    if matched and evidence_tier == "provisional_B":
        checked["tier"] = "provisional_B"
    publishable = None
    if matched:
        publishable = {
            "name": result.get("title", ""),
            "url": resolved_url,
            "tier": evidence_tier,
            "role": "evidence-upgrade",
            "articleVerified": True,
            "publisher": verification.get("publisher") or result.get("sourceDomain") or (urlsplit(resolved_url).hostname or "").lower(),
            "publisherDomain": (urlsplit(resolved_url).hostname or "").lower(),
            "publishedDate": result.get("publishedDate") or "",
        }
    return {"attempts": attempts, "checked": checked}, publishable


def run_evidence_upgrade(required_date: date, events: list[dict]) -> dict:
    """Actually search, retrieve and assess evidence for queued event candidates."""
    queued = [
        event for event in events
        if event.get("candidateDisposition") == "needs_verification"
        and (event.get("editorialPriorityLabel") == "high" or event.get("editorialPriorityScore", 0) >= 55)
    ]
    attempted = qualified = failed = ambiguous = 0
    upgrade_rows = []
    resolver_discovered = []
    resolver_discovered_urls = set()
    query_jobs = []
    for event in queued:
        family = {"id": "evidence-upgrade", "scope": event.get("scope", "domestic")}
        for base_query in evidence_upgrade_queries(event):
            for backend in QUERY_BACKENDS:
                # Exact source-domain queries get a fallback without date
                # operators. The RSS item dates are still filtered by
                # parse_rss, while this helps engines that ignore or mishandle
                # after:/before: for older indexed source pages.
                query_jobs.append((event["eventId"], family, backend, base_query, not base_query.startswith("site:")))
    query_results = {event_id: [] for event_id in {event["eventId"] for event in queued}}
    with ThreadPoolExecutor(max_workers=min(8, len(query_jobs) or 1)) as pool:
        futures = {
            pool.submit(_execute_one_query, family, backend, base_query, required_date - timedelta(days=6), required_date, date_filter=date_filter): event_id
            for event_id, family, backend, base_query, date_filter in query_jobs
        }
        for future in as_completed(futures):
            event_id = futures[future]
            try:
                found, audit = future.result()
            except Exception as exc:
                found, audit = [], {
                    "queryFamily": "evidence-upgrade",
                    "actualQuery": "",
                    "executedAt": now_cn(),
                    "success": False,
                    "failure": f"{type(exc).__name__}: {exc}",
                    "returnedResultCount": 0,
                    "acceptedRawCount": 0,
                }
            query_results[event_id].append((found, audit))
    for event in queued:
        attempted += 1
        query_audits = []
        checked_sources = []
        resolution_attempts = []
        publishable = []
        had_query_failure = False
        had_resolution_failure = False
        seen_result_urls = set()
        publisher_search_visited = set()

        def collect_resolver_candidate(result: dict, audit: dict) -> None:
            """Return one relevant, unmatched result for a single reflow pass."""
            result_url = canonical_url(result.get("url") or "")
            if not result_url or result_url in resolver_discovered_urls:
                return
            if not is_relevant_record(result):
                return
            resolver_discovered_urls.add(result_url)
            candidate = dict(result)
            candidate.update({
                "discoveredVia": "evidence-resolver",
                "discoverySourceType": "resolver_discovered",
                "resolverParentEventId": event.get("eventId"),
                "resolverDepth": 1,
                "resolverQuery": audit.get("actualQuery", ""),
                "duplicateStatus": "unresolved",
                "newDevelopment": False,
            })
            resolver_discovered.append(candidate)

        def collect_unmatched_direct_result(result: dict, audit: dict, outcome: dict) -> None:
            """Preserve a fetched, relevant article for the single reflow pass."""
            checked = outcome.get("checked", {})
            if checked.get("retrieved") and not checked.get("matched") and checked.get("error") != "search_wrapper":
                collect_resolver_candidate(result, audit)
        # Existing reports are the cheapest and most reliable path to a
        # publisher page.  A report may still contain a Google/Bing wrapper;
        # the resolver audit records that separately instead of discarding it.
        existing_reports = list(event.get("discoveryReports") or [])
        # Some persisted/replayed event rows only retain ``sourceDomains``.
        # Reconstruct a publisher hint from that metadata so a wrapper result
        # can still reach the publisher's own search endpoint.  This is not
        # evidence and does not promote the domain; it only improves lookup.
        known_report_domains = set()
        for report in existing_reports:
            known_report_domains.update(publisher_domains(report))
        for domain in event.get("publisherDomains", []):
            if domain not in known_report_domains:
                existing_reports.append({"sourceDomain": domain, "title": event.get("representativeTitle", "")})
                known_report_domains.add(domain)
        for domain in event.get("sourceDomains", []):
            if domain not in known_report_domains and re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", str(domain or "").lower()):
                existing_reports.append({"sourceDomain": domain, "title": event.get("representativeTitle", "")})
                known_report_domains.add(domain)
        for report in existing_reports:
            report_url = canonical_url(report.get("url", ""))
            if report_url and report_url in seen_result_urls:
                continue
            if report_url:
                seen_result_urls.add(report_url)
                method = "existing_report"
                outcome, source = resolve_evidence_attempt(event, report, method)
                resolution_attempts.extend(outcome["attempts"])
                checked_sources.append(outcome["checked"])
                collect_unmatched_direct_result(report, {"actualQuery": "existing discovery report"}, outcome)
                had_resolution_failure = had_resolution_failure or bool(outcome["checked"].get("error"))
                if source:
                    publishable.append(source)
            # Some publishers expose a stable first-party search endpoint even
            # when Google/Bing returns only an opaque redirect.  Use the
            # existing discovery report's publisher identity as the next
            # resolution step; this remains generic and never trusts the
            # search result itself as final evidence.
            publisher_found, publisher_audit = publisher_search_results(
                event, report, required_date - timedelta(days=6), required_date
            )
            publisher_search_visited.update(publisher_domains(report))
            if publisher_audit:
                query_audits.append(publisher_audit)
                had_query_failure = had_query_failure or not publisher_audit.get("success")
            for result in publisher_found:
                result_url = canonical_url(result.get("url", ""))
                if not result_url or result_url in seen_result_urls:
                    continue
                seen_result_urls.add(result_url)
                outcome, source = resolve_evidence_attempt(event, result, "domain_search")
                resolution_attempts.extend(outcome["attempts"])
                checked_sources.append(outcome["checked"])
                collect_unmatched_direct_result(result, publisher_audit or {"actualQuery": "publisher domain search"}, outcome)
                had_resolution_failure = had_resolution_failure or bool(outcome["checked"].get("error"))
                if source:
                    publishable.append(source)
        for found, audit in sorted(query_results.get(event["eventId"], []), key=lambda row: (row[1].get("actualQuery", ""), row[1].get("executedAt", ""))):
            query_audits.append(audit)
            had_query_failure = had_query_failure or not audit.get("success")
            for result in found:
                result_url = canonical_url(result.get("url", ""))
                if result_url in seen_result_urls:
                    continue
                seen_result_urls.add(result_url)
                query_text = audit.get("actualQuery", "")
                if query_text.startswith("site:"):
                    method = "domain_search"
                elif "官方原文" in query_text or "official source" in query_text:
                    method = "official_search"
                else:
                    method = "broad_search"
                # A Google/Bing wrapper is a transport record, not an article.
                # If the result also identifies a known publisher, give that
                # publisher's own search adapter one chance before attempting
                # the wrapper itself.  This keeps the resolver generic and
                # prevents the RSS transport domain from becoming evidence.
                result_domains = set(publisher_domains(result))
                publisher_found = []
                if is_search_wrapper_url(result_url) and result_domains - publisher_search_visited:
                    publisher_search_visited.update(result_domains)
                    publisher_found, publisher_audit = publisher_search_results(
                        event, result, required_date - timedelta(days=6), required_date
                    )
                    if publisher_audit:
                        query_audits.append(publisher_audit)
                        had_query_failure = had_query_failure or not publisher_audit.get("success")
                    for direct_result in publisher_found:
                        direct_url = canonical_url(direct_result.get("url", ""))
                        if not direct_url or direct_url in seen_result_urls:
                            continue
                        seen_result_urls.add(direct_url)
                        outcome, source = resolve_evidence_attempt(event, direct_result, "domain_search")
                        resolution_attempts.extend(outcome["attempts"])
                        checked_sources.append(outcome["checked"])
                        collect_unmatched_direct_result(direct_result, publisher_audit or {"actualQuery": "publisher domain search"}, outcome)
                        had_resolution_failure = had_resolution_failure or bool(outcome["checked"].get("error"))
                        if source:
                            publishable.append(source)
                    if publisher_found:
                        continue
                # RSS searches often return a large page of unrelated stories
                # from the same publisher.  Screen by the event title before
                # opening article pages; this is a recall-preserving guard for
                # retrieval cost, not an evidence qualification decision.
                match_details = event_match_details(event, result, "")
                if not match_details.get("matched"):
                    collect_resolver_candidate(result, audit)
                    result_domain = (urlsplit(result.get("url", "")).hostname or "").lower()
                    resolution_attempts.append({
                        "method": method,
                        "inputUrl": result.get("url", ""),
                        "resolvedUrl": result.get("url", ""),
                        "domain": result_domain,
                        "publisherDomain": (publisher_domains(result) or [result_domain])[0],
                        "fetchStatus": "screened_out",
                        "articleMatched": False,
                        "matchScore": match_details.get("score", 0),
                        "matchReasons": match_details.get("reasons", []),
                        "evidenceTier": source_info(result.get("url", "")).get("tier", "C"),
                    })
                    checked_sources.append({
                        "discoveryUrl": result.get("url", ""),
                        "url": result.get("url", ""),
                        "publisherDomain": (publisher_domains(result) or [result_domain])[0],
                        "title": result.get("title", ""),
                        "tier": source_info(result.get("url", "")).get("tier", "C"),
                        "retrieved": False,
                        "matched": False,
                        "error": "title_not_matched_to_event",
                        "eventMatch": match_details,
                        "method": method,
                    })
                    continue
                outcome, source = resolve_evidence_attempt(event, result, method)
                resolution_attempts.extend(outcome["attempts"])
                checked_sources.append(outcome["checked"])
                collect_unmatched_direct_result(result, audit, outcome)
                had_resolution_failure = had_resolution_failure or bool(outcome["checked"].get("error"))
                if source:
                    publishable.append(source)
        unique_sources = {}
        for source in publishable:
            unique_sources[canonical_url(source["url"])] = source
        publishable = list(unique_sources.values())
        event["evidenceUpgradeAttempted"] = True
        event["evidenceUpgradeQueries"] = query_audits
        event["evidenceUpgradeSourcesChecked"] = checked_sources
        event["evidenceResolutionAttempts"] = resolution_attempts
        if publishable and evidence_sources_qualified(event, publishable):
            best = sorted(publishable, key=lambda row: ({"A": 0, "B": 1, "provisional_B": 2}.get(row["tier"], 9), row["url"]))[0]
            event["evidenceSources"] = publishable
            event["evidenceTierAfterUpgrade"] = best["tier"]
            event["evidenceUpgradeResult"] = "qualified"
            event["evidenceFailureReason"] = None
            event["evidenceFailureType"] = None
            event["candidateDisposition"] = "evidence_qualified"
            event["evidenceUpgradeStatus"] = "completed"
            qualified += 1
        else:
            if publishable:
                best = sorted(publishable, key=lambda row: ({"A": 0, "B": 1, "provisional_B": 2}.get(row["tier"], 9), row["url"]))[0]
                event["evidenceSources"] = publishable
                event["evidenceTierAfterUpgrade"] = best["tier"]
            else:
                event["evidenceTierAfterUpgrade"] = "C"
            event["evidenceUpgradeResult"] = "ambiguous" if had_query_failure or had_resolution_failure else "failed"
            if publishable and evidence_claim_risk(event) == "high":
                event["evidenceFailureReason"] = "high_risk_requires_independent_confirmation"
                event["evidenceFailureType"] = "high_risk_requires_independent_confirmation"
            else:
                event["evidenceFailureType"] = classify_evidence_failure(
                    event,
                    checked_sources,
                    had_query_failure=had_query_failure,
                    had_resolution_failure=had_resolution_failure,
                    publishable=publishable,
                )
                event["evidenceFailureReason"] = {
                    "query_failed": "search_query_failed",
                    "resolver_failed": "source_page_retrieval_failed",
                    "blocked_or_low_quality_source": "only_blocked_or_low_quality_sources_found",
                    "event_match_failed": "retrieved_article_did_not_match_event",
                    "no_reliable_evidence": "no_publishable_matching_A_or_B_source",
                }.get(event["evidenceFailureType"], "search_or_retrieval_incomplete")
            event["evidenceUpgradeStatus"] = event["evidenceUpgradeResult"]
            if event["evidenceUpgradeResult"] == "ambiguous":
                ambiguous += 1
            else:
                failed += 1
        upgrade_rows.append(event)
    return {
        "attempted": attempted,
        "qualified": qualified,
        "failed": failed,
        "ambiguous": ambiguous,
        "events": upgrade_rows,
        "resolverDiscoveredCandidates": resolver_discovered,
    }


def event_key(record: dict) -> str:
    explicit = record.get("canonicalEventId")
    if explicit:
        return str(explicit)
    identity = canonical_event_identity(record)
    if identity:
        return identity
    title = record.get("title", "") or ""
    # Policy documents are often republished by several official or media
    # pages with different prefixes.  Use the named instrument as the event
    # identity, while leaving unrelated policy titles on the normal path.
    policy_match = re.search(r"[\u4e00-\u9fff]{2,16}(?:管理办法|实施办法|保护条例|条例|办法|规定|规程)", title)
    if policy_match:
        return "policy|" + compact(policy_match.group(0))
    bits = [title]
    terms = sorted(meaningful_terms(" ".join(bits)))
    return "|".join(terms[:12])


def duplicate_relation(current: dict, previous: dict) -> tuple[str, str] | None:
    current_url = canonical_url(current.get("url") or current.get("evidenceUrl") or "")
    previous_url = canonical_url(previous.get("url") or previous.get("evidenceUrl") or "")
    current_title = normalized_event_title(current.get("title", ""))
    previous_title = normalized_event_title(previous.get("title", ""))
    if current_title and current_title == previous_title and has_specific_event_anchor(current) and has_specific_event_anchor(previous):
        try:
            distance = abs(date.fromisoformat(current.get("publishedDate", "")) - date.fromisoformat(previous.get("publishedDate", ""))).days
        except (TypeError, ValueError):
            distance = 0
        # A normalized exact title is stronger than a URL or source match.
        # Keep the window bounded so a genuinely recurring item can still be
        # reviewed as a new event after a long interval.
        if distance <= 14:
            return ("same_day_duplicate" if distance == 0 else "historical_duplicate", "same normalized title within event window")
    if current_url and previous_url and current_url == previous_url:
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical URL")
    current_identity = canonical_event_identity(current)
    previous_identity = canonical_event_identity(previous)
    if current_identity and current_identity == previous_identity:
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "same event identity but current record contains a substantive development marker")
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same event identity")
    matched_relation = event_match_relation(current, previous)
    if matched_relation:
        return matched_relation
    # The token fallback is useful only after both records expose a specific
    # event anchor. Generic titles such as “会议召开” must not become a
    # cross-day identity merely because their token sets are identical.
    if has_specific_event_anchor(current) and has_specific_event_anchor(previous):
        current_key = current_identity or event_key(current)
        previous_key = previous_identity or event_key(previous)
    else:
        current_key = previous_key = ""
    left = meaningful_terms(current.get("title", ""))
    right = meaningful_terms(previous.get("title", ""))
    shared = left & right
    # Similar subject matter is not enough.  Require a substantial overlap
    # plus a shared named anchor, so two different archaeological sites are
    # not silently merged.
    named_shared = {term for term in shared if len(term) >= 4 and term not in GENERIC_EVENT_WORDS}
    close_in_time = False
    try:
        close_in_time = abs(date.fromisoformat(current.get("publishedDate", "")) - date.fromisoformat(previous.get("publishedDate", ""))) <= timedelta(days=1)
    except ValueError:
        pass
    if len(named_shared) >= 2 and (
        len(shared) / max(1, min(len(left), len(right))) >= 0.4 or close_in_time
    ):
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "high-overlap event identity with a substantive development marker")
        return ("historical_duplicate", "high-overlap event identity")
    return None


def build_final_editorial_pool(evaluation: dict, historical_duplicate_count: int = 0) -> dict:
    """Expose one event-level, publishable input for the final editor.

    This is intentionally not the editorial selector.  Codex still decides
    selected/rejected/deferred after reviewing these events.  The pool only
    prevents the old candidate ledger and the evidence-upgrade audit from
    becoming two competing input sets.
    """
    qualified = [
        row for row in evaluation.get("pool", [])
        if row.get("candidateDisposition") == "evidence_qualified"
    ]
    canonical_events = {}
    for row in qualified:
        event_id = row.get("eventId")
        if event_id and event_id not in canonical_events:
            canonical_events[event_id] = row
    event_ids = set(canonical_events)
    fields = (
        "eventId", "title", "representativeTitle", "url", "publishedDate", "scope",
        "candidateDisposition",
        "reportCount", "sourceDomains", "publisherDomains", "freshnessTier", "newDevelopment", "claimRisk",
        "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons",
        "museumCollectionOrPublicIncident", "publicSalience", "independentCoverageCount",
        "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "evidenceUpgradeStatus",
        "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceSources",
        "evidenceResolutionAttempts", "discoveryReports",
    )
    return {
        "status": "pending_editorial_review",
        "rawQualifiedEvents": len(qualified),
        "canonicalUniqueEvents": len(event_ids),
        # Historical duplicates are removed before candidate evaluation. Keep
        # the count here as an explicit upstream exclusion, not as pool rows.
        "historicalDuplicates": historical_duplicate_count,
        "historicalDuplicateDefinition": "unique published-event targets excluded before evidence qualification",
        "editoriallyReviewed": 0,
        "events": [{key: row.get(key) for key in fields} for row in canonical_events.values()],
    }


def reflow_resolver_discovered_candidates(required_date: date, records: list[dict], known_events: list[dict]) -> dict:
    """Normalize resolver discoveries once without recursively upgrading them."""
    if not records:
        return {"records": [], "events": [], "evaluation": {"records": []}}
    history = load_history(required_date)
    annotated = []
    for original in records:
        row = dict(original)
        relation = None
        matched_previous = None
        for previous in known_events + annotated + history:
            relation = duplicate_relation(row, previous)
            if relation:
                matched_previous = previous
                break
        if relation:
            row["duplicateStatus"], row["duplicateReason"] = relation
            row["duplicateOf"] = (
                matched_previous.get("eventId")
                or matched_previous.get("historicalCanonicalEventId")
                or matched_previous.get("canonicalEventId")
                or matched_previous.get("title")
            )
            row["newDevelopment"] = relation[0] == "new_development"
        annotated.append(row)
    events = aggregate_event_candidates(annotated)
    evaluation = evaluate_candidate_pool(required_date, events)
    return {"records": annotated, "events": events, "evaluation": evaluation}


def freshness_tier(required_date: date, published_value: str) -> str:
    try:
        age = (required_date - date.fromisoformat(published_value)).days
    except (TypeError, ValueError):
        return "unknown"
    if 0 <= age <= 2:
        return "primary_0_48h"
    if 3 <= age <= 6:
        return "backfill_3_7d"
    return "outside_window"


def is_relevant_record(record: dict) -> bool:
    text = " ".join(str(record.get(key) or "") for key in ("title", "summary", "body", "notes")).lower()
    if any(term.lower() in text for term in RELEVANCE_TERMS):
        return True
    family_ids = list(record.get("queryFamilies") or [])
    if record.get("queryFamily"):
        family_ids.append(record.get("queryFamily"))
    family_terms = tuple(
        term
        for family_id in family_ids
        for term in QUERY_FAMILY_RELEVANCE_TERMS.get(family_id, ())
    )
    return any(term.lower() in text for term in family_terms)


def is_high_value_record(record: dict) -> bool:
    title = (record.get("title", "") or "").lower()
    return any(term.lower() in title for term in HIGH_VALUE_TERMS)


def evidence_claim_risk(record: dict) -> str:
    """Classify claim risk separately from editorial importance."""
    text = " ".join(str(record.get(key) or "") for key in ("title", "summary", "body", "notes")).lower()
    return "high" if any(term.lower() in text for term in HIGH_RISK_EVIDENCE_TERMS) else "ordinary"


def evidence_sources_qualified(record: dict, sources: list[dict]) -> bool:
    """Apply publication evidence rules without turning tier into news value."""
    usable = [source for source in sources if source.get("tier") in {"A", "B", "provisional_B"}]
    if any(source.get("tier") == "A" for source in usable):
        return True
    if evidence_claim_risk(record) == "high":
        b_domains = {
            (urlsplit(source.get("url", "")).hostname or "").lower()
            for source in usable
            if source.get("tier") == "B"
        }
        return len(b_domains) >= 2
    return bool(usable)


def classify_evidence_failure(record: dict, checked_sources: list[dict], *,
                              had_query_failure: bool, had_resolution_failure: bool,
                              publishable: list[dict]) -> str:
    """Classify why an upgrade did not reach the publication gate.

    The category describes the verification state, not the event's editorial
    value.  In particular, a high-value clue can remain ``source_unverified``
    or ``resolver_failed`` and therefore stay in needs_verification.
    """
    if publishable and evidence_claim_risk(record) == "high":
        return "high_risk_requires_independent_confirmation"
    if had_query_failure:
        return "query_failed"
    if had_resolution_failure:
        return "resolver_failed"
    for source in checked_sources:
        if source.get("error") in {"blocked_source", "search_wrapper", "source_unverified"}:
            return "blocked_or_low_quality_source"
        if source.get("error") == "title_not_matched_to_event":
            continue
        if source.get("retrieved") and source.get("matched") is False:
            return "event_match_failed"
    return "no_reliable_evidence"


def _editorial_context(record: dict) -> str:
    parts = [str(record.get(key) or "") for key in ("title", "summary", "body", "notes", "institution", "publisher", "entity", "eventType", "location")]
    for report in record.get("discoveryReports", []) if isinstance(record.get("discoveryReports"), list) else []:
        if isinstance(report, dict):
            parts.extend(str(report.get(key) or "") for key in ("title", "publisher", "sourceDomain", "publisherDomain"))
    for source in record.get("evidenceSources", []) if isinstance(record.get("evidenceSources"), list) else []:
        if isinstance(source, dict):
            parts.extend(str(source.get(key) or "") for key in ("name", "publisher", "publisherDomain"))
    return " ".join(part for part in parts if part).lower()


def museum_collection_or_public_incident(record: dict) -> bool:
    """Recognize a concrete museum collection/public incident by its anchors."""
    text = _editorial_context(record)
    return (
        any(term.lower() in text for term in MUSEUM_INSTITUTION_TERMS)
        and any(term.lower() in text for term in COLLECTION_OBJECT_TERMS)
        and any(term.lower() in text for term in PUBLIC_INCIDENT_TERMS)
    )


def _coverage_domain_family(value: str) -> str:
    text = str(value or "").strip().lower()
    host = (urlsplit(text).hostname or "").lower() if "://" in text else ""
    value = host or text
    value = value.removeprefix("www.").removeprefix("m.")
    aliases = {
        "news.xinhuanet.com": "xinhuanet.com",
        "www.xinhuanet.com": "xinhuanet.com",
        "www.news.cn": "news.cn",
        "society.people.com.cn": "people.com.cn",
        "people.cctv.com": "cctv.com",
    }
    value = aliases.get(value, value)
    if "." in value:
        parts = value.split(".")
        if len(parts) >= 3 and parts[-2:] in (("com", "cn"), ("org", "cn"), ("gov", "cn"), ("co", "uk")):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    return compact(value)


def _coverage_source_type(row: dict, family: str) -> str:
    explicit = str(row.get("sourceClass") or row.get("sourceType") or "").strip().lower()
    if explicit:
        return explicit
    text = " ".join(str(row.get(key) or "") for key in ("name", "publisher", "sourceDomain", "publisherDomain", "url")).lower()
    if any(family == _coverage_domain_family(domain) or family.endswith(domain) for domain in PUBLIC_SALIENCE_CENTRAL_DOMAINS):
        return "central_media"
    if any(term in text for term in ("博物馆", "博物院", "文物局", "考古院", "考古所", "gov.cn", ".edu", ".ac.")):
        return "official_institution"
    if any(term in text for term in ("thepaper", "考古杂志", "艺术新闻", "专业媒体")):
        return "professional_media"
    if any(term in text for term in ("川观", "日报", "新闻网", "地方媒体")):
        return "local_mainstream"
    return "other_publisher"


def _coverage_rows(record: dict) -> list[dict]:
    rows = []
    for key in ("discoveryReports", "evidenceSources"):
        values = record.get(key)
        if isinstance(values, list):
            rows.extend(row for row in values if isinstance(row, dict))
    if rows:
        return rows
    for domain in record.get("publisherDomains", []) if isinstance(record.get("publisherDomains"), list) else []:
        rows.append({"publisherDomain": domain})
    return rows


def public_salience(record: dict) -> dict:
    """Measure independent public attention without rewarding raw repost counts."""
    families = {}
    dates = set()
    source_types = set()
    for row in _coverage_rows(record):
        origin = str(row.get("canonicalPublisherDomain") or row.get("originalPublisherDomain") or "").strip()
        value = origin or row.get("publisherDomain") or row.get("sourceDomain") or row.get("publisher") or row.get("url") or ""
        family = _coverage_domain_family(str(value))
        if not family:
            continue
        families.setdefault(family, row)
        published = parse_date(str(row.get("publishedDate") or row.get("date") or ""))
        if published:
            dates.add(published.isoformat())
        source_types.add(_coverage_source_type(row, family))
    independent = len(families)
    if independent >= 5 or (len(dates) >= 2 and independent >= 2):
        level = "sustained_public_attention"
    elif independent >= 3 and len(source_types) >= 2:
        level = "cross_media_attention"
    else:
        level = "normal"
    return {
        "level": level,
        "independentCoverageCount": independent,
        "publisherDiversity": independent,
        "sourceTypeDiversity": len(source_types),
        "coverageDates": sorted(dates),
        "sourceTypes": sorted(source_types),
        "reason": level if level != "normal" else "limited_or_unconfirmed_independent_coverage",
    }


def editorial_priority(record: dict, required_date: date | None = None) -> dict:
    """Score news value before evidence qualification, without using source tier."""
    title = record.get("title", "") or ""
    context_parts = [title]
    for key in ("summary", "body", "notes", "institution", "publisher", "entity", "eventType", "location"):
        if record.get(key):
            context_parts.append(str(record[key]))
    for domain in record.get("sourceDomains", []) if isinstance(record.get("sourceDomains"), list) else [record.get("sourceDomain", "")]:
        if domain:
            context_parts.append(str(domain))
    for report in record.get("discoveryReports", []) if isinstance(record.get("discoveryReports"), list) else []:
        if isinstance(report, dict) and report.get("title"):
            context_parts.append(str(report["title"]))
    text = " ".join(context_parts).lower()
    score = 20
    reasons = []

    def hit(terms):
        return any(term.lower() in text for term in terms)

    policy = hit(POLICY_PRIORITY_TERMS)
    national_policy = policy and hit(NATIONAL_POLICY_TERMS)
    major_discovery = hit(MAJOR_DISCOVERY_TERMS)
    archaeology_discovery = hit(ARCHAEOLOGY_DISCOVERY_TERMS) and hit(("考古", "遗址", "墓", "文物"))
    security = hit(SECURITY_PRIORITY_TERMS)
    museum_collection_incident = museum_collection_or_public_incident(record)
    repatriation = hit(REPATRIATION_TERMS)
    heritage = hit(HERITAGE_RECOGNITION_TERMS)
    museum_project = hit(MUSEUM_PROJECT_TERMS)
    digital = hit(DIGITAL_PRIORITY_TERMS)
    cooperation = hit(COOPERATION_TERMS)
    routine = hit(ROUTINE_PRIORITY_TERMS)
    official_diplomatic_source = bool(re.search(r"(?:embassy|使馆|大使馆|外交|mfa|gov\.cn)", text))
    high_level_rep = hit(HIGH_LEVEL_REPRESENTATIVE_TERMS)
    foreign_national_rep = hit(FOREIGN_NATIONAL_REPRESENTATIVE_TERMS)
    national_cultural_object = hit(CULTURAL_DIPLOMACY_OBJECT_TERMS)
    museum_object = hit(("博物馆", "博物院", "纪念馆", "世界遗产", "文化遗产"))
    cultural_substance = hit(CULTURAL_DIPLOMACY_SUBSTANCE_TERMS)
    diplomatic_context = hit(DIPLOMATIC_CONTEXT_TERMS) or official_diplomatic_source
    high_level_cultural_diplomacy = (
        foreign_national_rep
        and high_level_rep
        and diplomatic_context
        and (national_cultural_object or museum_object)
        and (cultural_substance or (national_cultural_object and hit(("参观", "访问"))))
    )
    salience = public_salience(record)

    if national_policy:
        score += 58
        reasons.append("national_or_industry_policy")
    elif policy:
        score += 42
        reasons.append("policy_or_governance_update")
    if major_discovery:
        score += 48
        reasons.append("major_archaeological_or_heritage_discovery_signal")
    elif archaeology_discovery:
        score += 34
        reasons.append("substantive_archaeological_discovery_or_new_knowledge")
    if security:
        score += 43
        reasons.append("museum_or_cultural_property_security_event")
    if museum_collection_incident:
        if not security:
            score += 43
        reasons.append("museum_collection_or_public_incident")
    if repatriation:
        score += 36
        reasons.append("repatriation_or_recovery_update")
    if heritage:
        score += 36
        reasons.append("heritage_recognition_or_world_heritage_update")
    if museum_project:
        score += 28
        reasons.append("significant_museum_or_exhibition_project")
        if hit(MUSEUM_SCALE_TERMS):
            score += 20
            reasons.append("substantive_audience_or_operation_data")
    if digital:
        score += 24
        reasons.append("substantive_digital_or_technology_project")
    if cooperation:
        score += 20
        reasons.append("meaningful_institutional_or_international_cooperation")
    if high_level_cultural_diplomacy:
        score += 52
        reasons.append("high_level_cultural_diplomacy")
    salience_eligible = (
        museum_collection_incident or security or policy or archaeology_discovery or repatriation
        or heritage or (museum_project and hit(MUSEUM_SCALE_TERMS)) or digital or cooperation
    )
    if salience_eligible and salience["level"] == "cross_media_attention":
        score += 10
        reasons.append("cross_media_attention")
    elif salience_eligible and salience["level"] == "sustained_public_attention":
        score += 16
        reasons.append("sustained_public_attention")
    if record.get("newDevelopment") is True:
        score += 12
        reasons.append("new_development")
    if required_date:
        tier = freshness_tier(required_date, record.get("publishedDate"))
        if tier == "primary_0_48h":
            score += 8
            reasons.append("primary_freshness")
        elif tier == "backfill_3_7d":
            score += 2
            reasons.append("backfill_freshness")
    if routine:
        # Routine labels alone do not erase a substantive policy, discovery,
        # security or heritage signal, but they prevent ordinary activities
        # from outranking core industry events merely because they are easy to verify.
        if high_level_cultural_diplomacy:
            penalty = 0
        else:
            penalty = 12 if (national_policy or major_discovery or archaeology_discovery or security or repatriation or heritage) else 30
        score -= penalty
        if penalty:
            reasons.append("routine_or_peripheral_activity_penalty")
    if not reasons:
        reasons.append("general_relevance_only")
    score = max(0, min(100, score))
    label = "high" if score >= 70 else "medium" if score >= 45 else "low"
    return {
        "score": score,
        "label": label,
        "reasons": reasons,
        "highLevelCulturalDiplomacy": high_level_cultural_diplomacy,
        "museumCollectionOrPublicIncident": museum_collection_incident,
        "publicSalience": salience,
        "independentCoverageCount": salience["independentCoverageCount"],
    }


def evaluate_candidate_pool(required_date: date, records: list[dict], raw_priority_counts: dict | None = None, raw_record_count: int | None = None) -> dict:
    """Rank news value first, then apply transparent evidence/editorial gates."""
    evaluated = []
    ranked = sorted(
        records,
        key=lambda row: (
            editorial_priority(row, required_date)["score"],
            row.get("publishedDate", ""),
            row.get("title", ""),
        ),
        reverse=True,
    )
    for rank, original in enumerate(ranked, 1):
        record = dict(original)
        priority = editorial_priority(record, required_date)
        tier = freshness_tier(required_date, record.get("publishedDate"))
        reasons = []
        disposition = "candidate"
        if tier == "outside_window":
            reasons.append("outside_window")
            disposition = "rejected"
        if record.get("duplicateStatus") in {"same_day_duplicate", "historical_duplicate"}:
            reasons.append(record["duplicateStatus"])
            disposition = "rejected"
        if not is_relevant_record(record):
            reasons.append("not_wenbo_relevant")
            disposition = "rejected"
        high_value = is_high_value_record(record)
        routine = any(term.lower() in (record.get("title", "") or "").lower() for term in ROUTINE_TERMS)
        if disposition != "rejected" and routine and not high_value:
            reasons.append("routine_or_promotional")
            disposition = "rejected"
        if disposition != "rejected" and tier == "backfill_3_7d" and not high_value:
            reasons.append("backfill_low_priority")
            disposition = "deferred"
        direct_url = record.get("url", "")
        evidence = source_info(direct_url) if direct_url else {"tier": "C", "blocked": True}
        initial_evidence = [{"url": direct_url, "tier": evidence.get("tier", "C")}] if direct_url else []
        if disposition == "candidate" and (evidence.get("blocked") or not evidence_sources_qualified(record, initial_evidence)):
            reasons.append("discovery_only_needs_evidence_upgrade")
            disposition = "needs_verification"
        if disposition == "candidate":
            disposition = "evidence_qualified"
        record["freshnessTier"] = tier
        record["highValueSignal"] = high_value
        record["filterReasons"] = reasons
        record["candidateDisposition"] = disposition
        record["evidenceTierAtDiscovery"] = evidence.get("tier", "C")
        record["claimRisk"] = evidence_claim_risk(record)
        record["editorialPriorityScore"] = priority["score"]
        record["editorialPriorityLabel"] = priority["label"]
        record["editorialReasons"] = priority["reasons"]
        record["highLevelCulturalDiplomacy"] = priority["highLevelCulturalDiplomacy"]
        record["museumCollectionOrPublicIncident"] = priority["museumCollectionOrPublicIncident"]
        record["publicSalience"] = priority["publicSalience"]
        record["independentCoverageCount"] = priority["independentCoverageCount"]
        record["editorialPriorityRank"] = rank
        record["evidenceUpgradeStatus"] = "queued" if disposition == "needs_verification" else "not_needed" if disposition == "evidence_qualified" else "not_eligible"
        evaluated.append(record)
    pool = [r for r in evaluated if r["candidateDisposition"] in {"evidence_qualified", "needs_verification"}]
    high_priority_queue = [
        r for r in pool
        if r["editorialPriorityLabel"] == "high" and r["candidateDisposition"] == "needs_verification"
    ]
    high_priority_queue.sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
    medium_priority_queue = [
        r for r in pool
        if r["candidateDisposition"] == "needs_verification"
        and r["editorialPriorityLabel"] == "medium"
        and r["editorialPriorityScore"] >= 55
    ]
    medium_priority_queue.sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
    provisional = [
        r for r in pool
        if r["candidateDisposition"] == "evidence_qualified"
        and r["freshnessTier"] == "primary_0_48h"
        and r["editorialPriorityLabel"] == "high"
    ]
    def counts(rows):
        from collections import Counter
        return dict(Counter(r.get("candidateDisposition") for r in rows))
    return {
        "records": evaluated,
        "pool": pool,
        "highPriorityEvidenceQueue": high_priority_queue,
        "mediumPriorityEvidenceQueue": medium_priority_queue,
        "provisionalWouldBeSelected": provisional,
        "summary": {
            "rawRecords": raw_record_count if raw_record_count is not None else len(records),
            "eventCandidateCount": len(records),
            "deduplicatedReports": sum(r.get("reportCount", 1) for r in records),
            "candidateEvaluationPool": len(pool),
            "evidenceQualified": sum(r["candidateDisposition"] == "evidence_qualified" for r in pool),
            "needsVerification": sum(r["candidateDisposition"] == "needs_verification" for r in pool),
            "highPriorityCandidates": sum(r["editorialPriorityLabel"] == "high" for r in pool),
            "highPriorityEvidenceQueue": len(high_priority_queue),
            "highPriorityNeedsVerification": len(high_priority_queue),
            "highPriorityEvidenceQueueEvents": len(high_priority_queue),
            "mediumPriorityEvidenceQueueEvents": len(medium_priority_queue),
            "evidenceUpgradeAttempted": 0,
            "evidenceUpgradeQualified": 0,
            "evidenceUpgradeFailed": 0,
            "evidenceUpgradeAmbiguous": 0,
            "rejected": sum(r["candidateDisposition"] == "rejected" for r in evaluated),
            "deferred": sum(r["candidateDisposition"] == "deferred" for r in evaluated),
            "provisionalWouldBeSelected": len(provisional),
            "editorialPriorityCounts": {
                "high": sum(r["editorialPriorityLabel"] == "high" for r in evaluated),
                "medium": sum(r["editorialPriorityLabel"] == "medium" for r in evaluated),
                "low": sum(r["editorialPriorityLabel"] == "low" for r in evaluated),
            },
            "eventCandidatePriorityCounts": {
                "high": sum(r["editorialPriorityLabel"] == "high" for r in evaluated),
                "medium": sum(r["editorialPriorityLabel"] == "medium" for r in evaluated),
                "low": sum(r["editorialPriorityLabel"] == "low" for r in evaluated),
            },
            "rawRecordPriorityCounts": raw_priority_counts or {},
            "dispositionCounts": counts(evaluated),
        },
    }


def scan_page(spec: dict, start: date, end: date) -> tuple[dict, list[dict]]:
    status = {"sourceId": spec["sourceId"], "name": spec["name"], "scope": spec["scope"], "url": spec["url"], "status": "fetch_failed", "linksSeen": 0, "datedLinks": 0, "outsideWindow": 0, "undatedLinks": 0, "rawResults": 0, "windowResults": 0, "note": ""}
    try:
        page = fetch(spec["url"])
    except Exception as exc:
        status["note"] = str(exc)
        return status, []
    status["status"] = "checked"
    records = []
    for anchor_title, url in links(page, spec["url"]):
        status["linksSeen"] += 1
        published = parse_date(url) or parse_date(anchor_title)
        if not published:
            status["undatedLinks"] += 1
            continue
        status["datedLinks"] += 1
        status["rawResults"] += 1
        if not (start <= published <= end):
            status["outsideWindow"] += 1
            continue
        record = {
            "title": anchor_title.strip(),
            "publishedDate": published.isoformat(),
            "url": url,
            "discoveredVia": spec["sourceId"],
            "discoverySourceType": "source_scan",
            "scope": spec["scope"],
            "sourceDomain": spec["domain"],
        }
        records.append(record)
    status["windowResults"] = len(records)
    return status, records


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_history(required_date: date) -> list[dict]:
    rows = []
    daily_dir = ROOT / "content" / "日报"
    for path in sorted(daily_dir.glob("????-??-??.md")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        # The report being replayed is not historical evidence.  Including it
        # here would label a just-discovered item as a historical duplicate of
        # the very report the replay is meant to evaluate.
        if required_date - timedelta(days=30) <= day < required_date:
            try:
                from build import parse_md
                parsed = parse_md(path)
            except Exception:
                continue
            for item in parsed.get("domestic", []) + parsed.get("international", []):
                row = {
                    "title": item.get("title", ""),
                    "body": item.get("body", ""),
                    "notes": item.get("commentary", ""),
                    "publishedDate": parsed.get("date", ""),
                    "url": (item.get("sources") or [{}])[0].get("url", ""),
                    "historicalSource": "published_daily_markdown",
                }
                identity = canonical_event_identity(row)
                if identity:
                    row["canonicalIdentity"] = identity
                    row["historicalCanonicalEventId"] = "published-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
                rows.append(row)
    return rows


def build_query_family_summary(report_records: list[dict], query_audits: list[dict], event_candidates: list[dict], evaluated_events: list[dict]) -> dict:
    """Summarize the marginal contribution of each executable query family.

    ``firstDiscoveryEventCount`` is deliberately defined after global event
    aggregation: an event returned by several families is credited once, to
    the first family represented in the audit order.  This keeps family
    results useful for recall review without pretending that overlapping
    search results are independent news items.
    """
    family_order = [family["id"] for family in QUERY_FAMILIES]
    family_rank = {family_id: index for index, family_id in enumerate(family_order)}
    audits_by_family = {family_id: [] for family_id in family_order}
    for audit in query_audits or []:
        family_id = audit.get("queryFamily")
        if family_id in audits_by_family:
            audits_by_family[family_id].append(audit)
    event_family_map = {}
    for event in event_candidates:
        families = {
            report.get("queryFamily")
            for report in event.get("discoveryReports", [])
            if report.get("queryFamily") in family_rank
        }
        if families:
            event_family_map[event.get("eventId")] = families
    event_by_id = {event.get("eventId"): event for event in evaluated_events}
    result = {}
    for family_id in family_order:
        audits = audits_by_family[family_id]
        rows = [row for row in report_records if row.get("queryFamily") == family_id]
        event_ids = {
            row.get("eventId")
            for row in rows
            if row.get("eventId") in event_family_map
        }
        first_seen = {
            event_id
            for event_id in event_ids
            if min(event_family_map[event_id], key=lambda value: family_rank[value]) == family_id
        }
        family_events = [event_by_id[event_id] for event_id in event_ids if event_id in event_by_id]
        dispositions = [event.get("candidateDisposition") for event in family_events]
        result[family_id] = {
            "queriesAttempted": len(audits),
            "queriesSucceeded": sum(bool(audit.get("success")) for audit in audits),
            "queriesFailed": sum(not bool(audit.get("success")) for audit in audits),
            "returnedResults": sum(int(audit.get("returnedResultCount") or 0) for audit in audits),
            "acceptedRawRecords": sum(int(audit.get("acceptedRawCount") or 0) for audit in audits),
            "rawRecords": len(rows),
            "sameDayDuplicateRecords": sum(row.get("duplicateStatus") == "same_day_duplicate" for row in rows),
            "historicalDuplicateRecords": sum(row.get("duplicateStatus") == "historical_duplicate" for row in rows),
            "irrelevantNoiseRecords": sum(not is_relevant_record(row) for row in rows),
            "uniqueEventsTouched": len(event_ids),
            "firstDiscoveryEventCount": len(first_seen),
            "historicalDuplicateEvents": sum(event.get("duplicateStatus") == "historical_duplicate" for event in family_events),
            "evidenceUpgradeCandidates": sum(disposition in {"needs_verification", "evidence_qualified"} for disposition in dispositions),
        }
    return result


def build_audit(required_date: date, raw_records: list[dict], scan_statuses: list[dict], query_results: list[dict], query_audits: list[dict] | None = None, perform_evidence_upgrade: bool = False) -> dict:
    start = required_date - timedelta(days=6)
    history = load_history(required_date)
    combined = []
    seen_urls = set()
    for record in raw_records + query_results:
        url = canonical_url(record.get("url") or record.get("discoveryUrl") or "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        record = dict(record)
        record.setdefault("discoveredAt", now_cn())
        combined.append(record)
    same_day = historical = developments = 0
    annotated = []
    for record in combined:
        relation = None
        for previous in annotated + history:
            relation = duplicate_relation(record, previous)
            if relation:
                break
        if relation:
            status, reason = relation
            record["duplicateStatus"] = status
            record["duplicateReason"] = reason
            record["duplicateOf"] = (
                previous.get("historicalCanonicalEventId")
                or previous.get("canonicalEventId")
                or previous.get("title")
            )
            record["duplicateOfTitle"] = previous.get("title", "")
            record["newDevelopment"] = status == "new_development"
            if status == "same_day_duplicate":
                same_day += 1
            elif status == "historical_duplicate":
                historical += 1
            elif status == "new_development":
                developments += 1
        else:
            record.setdefault("duplicateStatus", "unique_event")
            record.setdefault("newDevelopment", False)
        annotated.append(record)
    raw_priority_counts = {"high": 0, "medium": 0, "low": 0}
    for row in annotated:
        raw_priority_counts[editorial_priority(row, required_date)["label"]] += 1
    report_records = annotated
    event_candidates = aggregate_event_candidates(report_records)
    evaluation = evaluate_candidate_pool(required_date, event_candidates, raw_priority_counts=raw_priority_counts, raw_record_count=len(report_records))
    if perform_evidence_upgrade:
        upgrade = run_evidence_upgrade(required_date, evaluation["records"])
        evaluation["summary"]["evidenceUpgradeAttempted"] = upgrade["attempted"]
        evaluation["summary"]["evidenceUpgradeQualified"] = upgrade["qualified"]
        evaluation["summary"]["evidenceUpgradeFailed"] = upgrade["failed"]
        evaluation["summary"]["evidenceUpgradeAmbiguous"] = upgrade["ambiguous"]
        evaluation["pool"] = [row for row in evaluation["records"] if row["candidateDisposition"] in {"evidence_qualified", "needs_verification"}]
        evaluation["highPriorityEvidenceQueue"] = [row for row in evaluation["pool"] if row["candidateDisposition"] == "needs_verification" and row["editorialPriorityLabel"] == "high"]
        evaluation["mediumPriorityEvidenceQueue"] = [row for row in evaluation["pool"] if row["candidateDisposition"] == "needs_verification" and row["editorialPriorityLabel"] == "medium" and row["editorialPriorityScore"] >= 55]
        evaluation["highPriorityEvidenceQueue"].sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
        evaluation["mediumPriorityEvidenceQueue"].sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
        evaluation["summary"]["candidateEvaluationPool"] = len(evaluation["pool"])
        evaluation["summary"]["evidenceQualified"] = sum(row["candidateDisposition"] == "evidence_qualified" for row in evaluation["pool"])
        evaluation["summary"]["needsVerification"] = sum(row["candidateDisposition"] == "needs_verification" for row in evaluation["pool"])
        evaluation["summary"]["highPriorityCandidates"] = sum(row["editorialPriorityLabel"] == "high" for row in evaluation["pool"])
        evaluation["summary"]["highPriorityEvidenceQueue"] = len(evaluation["highPriorityEvidenceQueue"])
        evaluation["summary"]["highPriorityNeedsVerification"] = len(evaluation["highPriorityEvidenceQueue"])
        evaluation["summary"]["highPriorityEvidenceQueueEvents"] = len(evaluation["highPriorityEvidenceQueue"])
        evaluation["summary"]["mediumPriorityEvidenceQueueEvents"] = len(evaluation["mediumPriorityEvidenceQueue"])
        evaluation["summary"]["provisionalWouldBeSelected"] = sum(
            row["candidateDisposition"] == "evidence_qualified"
            and row["freshnessTier"] == "primary_0_48h"
            and row["editorialPriorityLabel"] == "high"
            for row in evaluation["pool"]
        )
        evaluation["provisionalWouldBeSelected"] = [
            row for row in evaluation["pool"]
            if row["candidateDisposition"] == "evidence_qualified"
            and row["freshnessTier"] == "primary_0_48h"
            and row["editorialPriorityLabel"] == "high"
        ]
        evaluation["summary"]["dispositionCounts"] = {
            disposition: sum(row.get("candidateDisposition") == disposition for row in evaluation["records"])
            for disposition in {row.get("candidateDisposition") for row in evaluation["records"]}
        }
    evaluated_events = evaluation["records"]
    resolver_reflow = {"records": [], "events": [], "evaluation": {"records": []}}
    if perform_evidence_upgrade:
        resolver_reflow = reflow_resolver_discovered_candidates(
            required_date,
            locals().get("upgrade", {}).get("resolverDiscoveredCandidates", []),
            evaluated_events,
        )
        evaluation["resolverDiscoveredCandidates"] = resolver_reflow["records"]
        evaluation["resolverDiscoveredEvents"] = resolver_reflow["events"]
        evaluation["resolverReflow"] = resolver_reflow["evaluation"]
    event_by_id = {row.get("eventId"): row for row in evaluated_events}
    for report in report_records:
        event = event_by_id.get(report.get("eventId"))
        if event:
            report["eventCandidateDisposition"] = event.get("candidateDisposition")
            report["eventEditorialPriorityScore"] = event.get("editorialPriorityScore")
            report["eventEditorialPriorityLabel"] = event.get("editorialPriorityLabel")
    domestic = [row for row in report_records if row.get("scope", "domestic") != "international"]
    international = [row for row in report_records if row.get("scope") == "international"]
    def stats(rows):
        historical = [r for r in rows if r.get("duplicateStatus") == "historical_duplicate"]
        return {
            "rawResults": len(rows),
            "sameDayDuplicateRecords": sum(r.get("duplicateStatus") == "same_day_duplicate" for r in rows),
            "historicalDuplicateRecords": len(historical),
            "historicalDuplicateCanonicalTargets": len({r.get("duplicateOf") for r in historical if r.get("duplicateOf")}),
            "newDevelopmentRecords": sum(r.get("duplicateStatus") == "new_development" for r in rows),
            "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in rows),
        }
    historical_rows = [r for r in report_records if r.get("duplicateStatus") == "historical_duplicate"]
    final_editorial_pool = build_final_editorial_pool(
        evaluation,
        historical_duplicate_count=len({r.get("duplicateOf") for r in historical_rows if r.get("duplicateOf")}),
    )
    query_family_summary = build_query_family_summary(
        report_records,
        query_audits or [],
        event_candidates,
        evaluated_events,
    )
    return {
        "schema": "daily-discovery-v1",
        "date": required_date.isoformat(),
        "windowStart": start.isoformat(),
        "windowEnd": required_date.isoformat(),
        "cutoffTimezone": "Asia/Shanghai",
        "sourceScans": scan_statuses,
        "queryFamilies": [dict(f, queries=list(f["queries"])) for f in QUERY_FAMILIES],
        "queryAuditStatus": "checked" if query_audits else "not_replayed",
        "queryResults": query_results,
        "queryAudits": query_audits or [],
        "queryFamilySummary": query_family_summary,
        "records": report_records,
        "candidateEvaluation": {
            "summary": evaluation["summary"],
            "finalEditorialPool": final_editorial_pool,
            "eventCandidates": [
                {
                    "eventId": row.get("eventId"),
                    "representativeTitle": row.get("representativeTitle"),
                    "publishedDate": row.get("publishedDate"),
                    "scope": row.get("scope"),
                    "reportCount": row.get("reportCount"),
                    "queryFamilies": row.get("queryFamilies"),
                    "sourceDomains": row.get("sourceDomains"),
                    "publisherDomains": row.get("publisherDomains"),
                    "discoveryReports": row.get("discoveryReports"),
                }
                for row in event_candidates
            ],
            "pool": [
                {k: row.get(k) for k in ("eventId", "title", "representativeTitle", "url", "publishedDate", "scope", "reportCount", "sourceDomains", "publisherDomains", "freshnessTier", "candidateDisposition", "claimRisk", "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "filterReasons", "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons", "highLevelCulturalDiplomacy", "museumCollectionOrPublicIncident", "publicSalience", "independentCoverageCount", "editorialPriorityRank", "evidenceUpgradeStatus", "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceFailureReason", "evidenceFailureType", "evidenceSources", "evidenceUpgradeQueries", "evidenceUpgradeSourcesChecked", "evidenceResolutionAttempts")}
                for row in evaluation["pool"]
            ],
            "highPriorityEvidenceQueue": [
                {k: row.get(k) for k in ("eventId", "title", "representativeTitle", "url", "publishedDate", "scope", "reportCount", "sourceDomains", "publisherDomains", "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons", "highLevelCulturalDiplomacy", "claimRisk", "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceFailureReason", "evidenceFailureType", "evidenceSources", "evidenceUpgradeQueries", "evidenceUpgradeSourcesChecked", "evidenceResolutionAttempts")}
                for row in evaluation["highPriorityEvidenceQueue"]
            ],
            "mediumPriorityEvidenceQueue": [
                {k: row.get(k) for k in ("eventId", "title", "representativeTitle", "url", "publishedDate", "scope", "reportCount", "sourceDomains", "publisherDomains", "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons", "highLevelCulturalDiplomacy", "claimRisk", "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceFailureReason", "evidenceFailureType", "evidenceSources", "evidenceUpgradeQueries", "evidenceUpgradeSourcesChecked", "evidenceResolutionAttempts")}
                for row in evaluation["mediumPriorityEvidenceQueue"]
            ],
            "provisionalWouldBeSelected": [
                {k: row.get(k) for k in ("title", "url", "publishedDate", "scope", "freshnessTier", "candidateDisposition")}
                for row in evaluation["provisionalWouldBeSelected"]
            ],
            "resolverDiscoveredCandidates": [
                {k: row.get(k) for k in ("title", "url", "publishedDate", "sourceDomain", "resolverParentEventId", "resolverDepth", "duplicateStatus", "duplicateOf")}
                for row in evaluation.get("resolverDiscoveredCandidates", [])
            ],
            "resolverDiscoveredEvents": [
                {k: row.get(k) for k in ("eventId", "representativeTitle", "publishedDate", "reportCount", "candidateDisposition", "editorialPriorityScore", "editorialPriorityLabel")}
                for row in evaluation.get("resolverDiscoveredEvents", [])
            ],
        },
        "summary": {
            "sourceScansAttempted": len(scan_statuses),
            "sourceScansSucceeded": sum(s.get("status") == "checked" for s in scan_statuses),
            "queriesExecuted": sum(bool(a.get("success")) for a in (query_audits or [])),
            "queriesAttempted": len(query_audits or []),
            "queriesSucceeded": sum(bool(a.get("success")) for a in (query_audits or [])),
            "queriesFailed": sum(not bool(a.get("success")) for a in (query_audits or [])),
            "rawResults": len(report_records),
            "sameDayDuplicateRecords": same_day,
            "historicalDuplicateRecords": historical,
            "historicalDuplicateCanonicalTargets": len({r.get("duplicateOf") for r in historical_rows if r.get("duplicateOf")}),
            "newDevelopmentRecords": developments,
            "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in report_records),
            "candidateEvaluation": evaluation["summary"],
            "resolverDiscoveredCandidates": len(evaluation.get("resolverDiscoveredCandidates", [])),
            "resolverDiscoveredEvents": len(evaluation.get("resolverDiscoveredEvents", [])),
            "queryFamilySummary": query_family_summary,
            "deduplicatedReports": sum(row.get("reportCount", 0) for row in event_candidates),
            "uniqueEvents": len(event_candidates),
            "eventDuplicateReports": sum(max(0, row.get("reportCount", 0) - 1) for row in event_candidates),
            "domestic": stats(domestic),
            "international": stats(international),
        },
    }


def run(required_date: date, *, window_days: int = 7, query_results: list[dict] | None = None, query_audits: list[dict] | None = None, execute_query_search: bool = True, perform_evidence_upgrade: bool = True, write: bool = False, output_path: Path | None = None) -> dict:
    start = required_date - timedelta(days=window_days - 1)
    statuses, raw = [], []
    for spec in SOURCE_SCANS:
        status, rows = scan_page(spec, start, required_date)
        statuses.append(status)
        raw.extend(rows)
    if execute_query_search and query_audits is None:
        searched, audits = execute_queries(required_date, start, required_date)
        query_results = (query_results or []) + searched
        query_audits = audits
    audit = build_audit(required_date, raw, statuses, query_results or [], query_audits or [], perform_evidence_upgrade=perform_evidence_upgrade)
    if write:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        (DISCOVERY_DIR / "README.md").write_text(
            "# 日报 broad discovery 审计\n\n此目录只记录日报发现层，不进入 `content/监测/`，也不改变行业关注地图固定六源。未知公众号可以作为 discovery source，但不能直接作为最终 evidence。\n",
            encoding="utf-8",
        )
        target = output_path or (DISCOVERY_DIR / f"{required_date.isoformat()}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run auditable daily broad discovery source scans.")
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--query-results", type=Path, help="JSON list of Codex-executed search results")
    parser.add_argument("--no-query-search", action="store_true", help="Skip real RSS query execution (tests/replay only)")
    parser.add_argument("--no-evidence-upgrade", action="store_true", help="Skip evidence upgrade (tests/replay only)")
    parser.add_argument("--output", type=Path, help="Optional audit output path; defaults to content/发现/YYYY-MM-DD.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.window_days < 1:
        parser.error("--window-days must be positive")
    query_results = load_json(args.query_results, []) if args.query_results else []
    if not isinstance(query_results, list):
        parser.error("--query-results must contain a JSON list")
    audit = run(args.date, window_days=args.window_days, query_results=query_results, execute_query_search=not args.no_query_search, perform_evidence_upgrade=not args.no_evidence_upgrade, write=args.write, output_path=args.output)
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))
    for status in audit["sourceScans"]:
        print(f'{status["sourceId"]}: {status["status"]} raw={status["rawResults"]} window={status["windowResults"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

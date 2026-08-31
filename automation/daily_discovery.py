"""Auditable broad discovery helpers for the daily editorial report.

The map's fixed six-source monitoring remains separate.  This module records
the wider discovery pass used by the daily editor: source-driven scans,
real query-driven RSS searches, and lightweight event-level deduplication.  It
deliberately does not decide what should be published.
"""
from __future__ import annotations

import argparse
import email.utils
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener
from xml.etree import ElementTree

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[1]

from automation.backfill_monitoring import fetch, links
from automation.governance import canonical_url, source_info

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
    {"id": "policy-governance", "scope": "domestic", "queries": ("文物 政策 管理办法 通知 施行", "博物馆 管理 政策 文物局", "site:gov.cn 文物 博物馆 政策")},
    {"id": "archaeology-heritage", "scope": "domestic", "queries": ("考古 新发现 遗址 保护 研究成果", "文物保护 工程 遗产 条例", "site:chinanews.com.cn 考古 遗址 文明", "site:henandaily.cn 考古 文物")},
    {"id": "museum-public-culture", "scope": "domestic", "queries": ("博物馆 开馆 展览 重要馆藏 官方", "博物馆 安全 声明 重大事件", "site:thepaper.cn 博物馆 文物 安全", "site:gov.cn 博物馆 开馆 展览")},
    {"id": "digital-heritage", "scope": "domestic", "queries": ("数字文博 AI 三维 虚拟现实 博物馆", "文物 数字化 数据平台 保护")},
    {"id": "international-heritage", "scope": "international", "queries": ("museum archaeology cultural heritage", "archaeological discovery heritage site", "heritage protection museum theft", "repatriation museum policy", "digital heritage museum technology", "site:polizei.gv.at museum theft", "site:aa.com.tr archaeology heritage", "site:reuters.com museum archaeology heritage", "site:apnews.com museum archaeology heritage")},
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
DEVELOPMENT_WORDS = ("正式施行", "正式开幕", "正式开放", "揭牌", "签约", "完成交接", "追回", "落网", "发布结论", "新发现", "新增", "启动发掘", "落地")
HIGH_VALUE_TERMS = (
    "政策", "办法", "条例", "施行", "规范", "改革", "考古", "发掘", "新发现", "遗址", "遗产保护", "保护工程",
    "保护研究", "研究成果", "揭牌", "合作", "签约", "联合考古", "藏品", "安全", "盗窃", "追回", "调查结论", "总结会",
    "museum policy", "museum theft", "stolen", "repatriation", "archaeological discovery", "archaeologists",
    "heritage protection", "conservation", "excavation", "unearthed", "new discovery", "research findings",
)
ROUTINE_TERMS = ("报名", "招募", "研学", "常规讲座", "讲座预告", "市集", "音乐季", "周末活动", "打卡", "优惠", "routine", "workshop", "weekend events")
RELEVANCE_TERMS = (
    "文物", "博物馆", "考古", "遗址", "文化遗产", "世界遗产", "石窟", "古建筑", "古墓", "古迹", "发掘", "出土",
    "展览", "藏品", "标本", "保护", "修复", "博物馆", "museum", "archaeology", "heritage", "conservation", "excavation",
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
        records.append(record)
    return records, returned, undated


def _execute_one_query(family: dict, backend: dict, base_query: str, start: date, end: date) -> tuple[list[dict], dict]:
    query = actual_query(base_query, start, end)
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


def event_key(record: dict) -> str:
    explicit = record.get("canonicalEventId")
    if explicit:
        return str(explicit)
    structured = [record.get("entity", ""), record.get("eventType", ""), record.get("location", "")]
    if any(structured):
        return "|".join(compact(bit) for bit in structured)
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
    if current_url and previous_url and current_url == previous_url:
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical URL")
    current_key = event_key(current)
    previous_key = event_key(previous)
    if current_key and current_key == previous_key:
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "same event identity but current record contains a substantive development marker")
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same event identity")
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
    return any(term.lower() in (record.get("title", "") or "").lower() for term in RELEVANCE_TERMS)


def is_high_value_record(record: dict) -> bool:
    title = (record.get("title", "") or "").lower()
    return any(term.lower() in title for term in HIGH_VALUE_TERMS)


def evaluate_candidate_pool(required_date: date, records: list[dict]) -> dict:
    """Apply transparent pre-editorial gates; never truncates by count."""
    evaluated = []
    for original in records:
        record = dict(original)
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
        if disposition == "candidate" and (evidence.get("blocked") or evidence.get("tier") not in {"A", "B"}):
            reasons.append("discovery_only_needs_evidence_upgrade")
            disposition = "needs_verification"
        if disposition == "candidate":
            disposition = "evidence_qualified"
        record["freshnessTier"] = tier
        record["highValueSignal"] = high_value
        record["filterReasons"] = reasons
        record["candidateDisposition"] = disposition
        record["evidenceTierAtDiscovery"] = evidence.get("tier", "C")
        evaluated.append(record)
    pool = [r for r in evaluated if r["candidateDisposition"] in {"evidence_qualified", "needs_verification"}]
    provisional = [
        r for r in pool
        if r["candidateDisposition"] == "evidence_qualified" and r["freshnessTier"] == "primary_0_48h" and r["highValueSignal"]
    ]
    def counts(rows):
        from collections import Counter
        return dict(Counter(r.get("candidateDisposition") for r in rows))
    return {
        "records": evaluated,
        "pool": pool,
        "provisionalWouldBeSelected": provisional,
        "summary": {
            "rawRecords": len(records),
            "candidateEvaluationPool": len(pool),
            "evidenceQualified": sum(r["candidateDisposition"] == "evidence_qualified" for r in pool),
            "needsVerification": sum(r["candidateDisposition"] == "needs_verification" for r in pool),
            "rejected": sum(r["candidateDisposition"] == "rejected" for r in evaluated),
            "deferred": sum(r["candidateDisposition"] == "deferred" for r in evaluated),
            "provisionalWouldBeSelected": len(provisional),
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
                rows.append({"title": item.get("title", ""), "publishedDate": parsed.get("date", ""), "url": (item.get("sources") or [{}])[0].get("url", "")})
    return rows


def build_audit(required_date: date, raw_records: list[dict], scan_statuses: list[dict], query_results: list[dict], query_audits: list[dict] | None = None) -> dict:
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
            record["duplicateOf"] = previous.get("canonicalEventId") or previous.get("title")
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
    evaluation = evaluate_candidate_pool(required_date, annotated)
    annotated = evaluation["records"]
    domestic = [row for row in annotated if row.get("scope", "domestic") != "international"]
    international = [row for row in annotated if row.get("scope") == "international"]
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
    historical_rows = [r for r in annotated if r.get("duplicateStatus") == "historical_duplicate"]
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
        "records": annotated,
        "candidateEvaluation": {
            "summary": evaluation["summary"],
            "pool": [
                {k: row.get(k) for k in ("title", "url", "publishedDate", "scope", "freshnessTier", "candidateDisposition", "evidenceTierAtDiscovery", "filterReasons")}
                for row in evaluation["pool"]
            ],
            "provisionalWouldBeSelected": [
                {k: row.get(k) for k in ("title", "url", "publishedDate", "scope", "freshnessTier", "candidateDisposition")}
                for row in evaluation["provisionalWouldBeSelected"]
            ],
        },
        "summary": {
            "sourceScansAttempted": len(scan_statuses),
            "sourceScansSucceeded": sum(s.get("status") == "checked" for s in scan_statuses),
            "queriesExecuted": sum(bool(a.get("success")) for a in (query_audits or [])),
            "queriesAttempted": len(query_audits or []),
            "queriesSucceeded": sum(bool(a.get("success")) for a in (query_audits or [])),
            "queriesFailed": sum(not bool(a.get("success")) for a in (query_audits or [])),
            "rawResults": len(annotated),
            "sameDayDuplicateRecords": same_day,
            "historicalDuplicateRecords": historical,
            "historicalDuplicateCanonicalTargets": len({r.get("duplicateOf") for r in historical_rows if r.get("duplicateOf")}),
            "newDevelopmentRecords": developments,
            "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in annotated),
            "domestic": stats(domestic),
            "international": stats(international),
        },
    }


def run(required_date: date, *, window_days: int = 7, query_results: list[dict] | None = None, query_audits: list[dict] | None = None, execute_query_search: bool = True, write: bool = False, output_path: Path | None = None) -> dict:
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
    audit = build_audit(required_date, raw, statuses, query_results or [], query_audits or [])
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
    parser.add_argument("--output", type=Path, help="Optional audit output path; defaults to content/发现/YYYY-MM-DD.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.window_days < 1:
        parser.error("--window-days must be positive")
    query_results = load_json(args.query_results, []) if args.query_results else []
    if not isinstance(query_results, list):
        parser.error("--query-results must contain a JSON list")
    audit = run(args.date, window_days=args.window_days, query_results=query_results, execute_query_search=not args.no_query_search, write=args.write, output_path=args.output)
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))
    for status in audit["sourceScans"]:
        print(f'{status["sourceId"]}: {status["status"]} raw={status["rawResults"]} window={status["windowResults"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Auditable broad discovery helpers for the daily editorial report.

The map's fixed six-source monitoring remains separate.  This module records
the wider discovery pass used by the daily editor: source-driven scans,
query-driven search results supplied by Codex, and lightweight event-level
deduplication.  It deliberately does not decide what should be published.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

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

# These are repeatable source-driven entry points, not additions to the map
# panel.  A scan can fail independently and must never be recorded as
# ``no_update``.  Query-driven results are supplied by the Codex run after it
# executes the listed query families in a search-capable environment.
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
        "url": "https://www.unesco.org/en/news",
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
    {"id": "policy-governance", "scope": "domestic", "queries": ("文物 政策 管理办法 通知 施行", "博物馆 管理 政策 文物局")},
    {"id": "archaeology-heritage", "scope": "domestic", "queries": ("考古 新发现 遗址 保护 研究成果", "文物保护 工程 遗产 条例")},
    {"id": "museum-public-culture", "scope": "domestic", "queries": ("博物馆 开馆 展览 重要馆藏 官方", "博物馆 安全 声明 重大事件")},
    {"id": "digital-heritage", "scope": "domestic", "queries": ("数字文博 AI 三维 虚拟现实 博物馆", "文物 数字化 数据平台 保护")},
    {"id": "international-heritage", "scope": "international", "queries": ("museum archaeology cultural heritage", "heritage protection museum theft", "repatriation museum policy", "digital heritage museum technology")},
)

GENERIC_TITLE_WORDS = {
    "文物", "博物馆", "考古", "文化", "遗址", "发布", "举行", "召开", "相关", "我国", "中国", "国际",
    "正式", "工作", "活动", "项目", "新闻", "报道", "最新", "举行", "开展", "推出", "举办",
}
DEVELOPMENT_WORDS = ("正式施行", "正式开幕", "正式开放", "揭牌", "签约", "完成交接", "追回", "落网", "发布结论", "新发现", "新增", "启动发掘", "落地")


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


def compact(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def meaningful_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", (text or "").lower()))
    return {term for term in terms if term not in GENERIC_TITLE_WORDS and len(term) >= 2}


def event_key(record: dict) -> str:
    explicit = record.get("canonicalEventId")
    if explicit:
        return str(explicit)
    structured = [record.get("entity", ""), record.get("eventType", ""), record.get("location", "")]
    if any(structured):
        return "|".join(compact(bit) for bit in structured)
    bits = [record.get("title", "")]
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
    long_shared = {term for term in shared if len(term) >= 4}
    if long_shared and len(shared) >= 2 and len(shared) / max(1, min(len(left), len(right))) >= 0.75:
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "high-overlap event identity with a substantive development marker")
        return ("historical_duplicate", "high-overlap event identity")
    return None


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


def build_audit(required_date: date, raw_records: list[dict], scan_statuses: list[dict], query_results: list[dict]) -> dict:
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
    domestic = [row for row in annotated if row.get("scope", "domestic") != "international"]
    international = [row for row in annotated if row.get("scope") == "international"]
    def stats(rows):
        return {"rawResults": len(rows), "sameDayDuplicates": sum(r.get("duplicateStatus") == "same_day_duplicate" for r in rows), "historicalDuplicates": sum(r.get("duplicateStatus") == "historical_duplicate" for r in rows), "newDevelopments": sum(r.get("duplicateStatus") == "new_development" for r in rows), "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in rows)}
    return {
        "schema": "daily-discovery-v1",
        "date": required_date.isoformat(),
        "windowStart": start.isoformat(),
        "windowEnd": required_date.isoformat(),
        "cutoffTimezone": "Asia/Shanghai",
        "sourceScans": scan_statuses,
        "queryFamilies": [dict(f, queries=list(f["queries"])) for f in QUERY_FAMILIES],
        "queryAuditStatus": "checked" if query_results else "not_replayed",
        "queryResults": query_results,
        "records": annotated,
        "summary": {
            "sourceScansAttempted": len(scan_statuses),
            "sourceScansSucceeded": sum(s.get("status") == "checked" for s in scan_statuses),
            "queriesExecuted": len(query_results),
            "rawResults": len(annotated),
            "sameDayDuplicates": same_day,
            "historicalDuplicates": historical,
            "newDevelopments": developments,
            "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in annotated),
            "domestic": stats(domestic),
            "international": stats(international),
        },
    }


def run(required_date: date, *, window_days: int = 7, query_results: list[dict] | None = None, write: bool = False) -> dict:
    start = required_date - timedelta(days=window_days - 1)
    statuses, raw = [], []
    for spec in SOURCE_SCANS:
        status, rows = scan_page(spec, start, required_date)
        statuses.append(status)
        raw.extend(rows)
    audit = build_audit(required_date, raw, statuses, query_results or [])
    if write:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        (DISCOVERY_DIR / "README.md").write_text(
            "# 日报 broad discovery 审计\n\n此目录只记录日报发现层，不进入 `content/监测/`，也不改变行业关注地图固定六源。未知公众号可以作为 discovery source，但不能直接作为最终 evidence。\n",
            encoding="utf-8",
        )
        (DISCOVERY_DIR / f"{required_date.isoformat()}.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run auditable daily broad discovery source scans.")
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--query-results", type=Path, help="JSON list of Codex-executed search results")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.window_days < 1:
        parser.error("--window-days must be positive")
    query_results = load_json(args.query_results, []) if args.query_results else []
    if not isinstance(query_results, list):
        parser.error("--query-results must contain a JSON list")
    audit = run(args.date, window_days=args.window_days, query_results=query_results, write=args.write)
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))
    for status in audit["sourceScans"]:
        print(f'{status["sourceId"]}: {status["status"]} raw={status["rawResults"]} window={status["windowResults"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

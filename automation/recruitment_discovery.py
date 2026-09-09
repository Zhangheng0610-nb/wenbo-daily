#!/usr/bin/env python3
"""Auditable recruitment discovery, directory scans and persistent review queue.

Search and industry-radar results are leads.  Publication still requires a
readable detail/application page and a manual or deterministic verification
record.  This module deliberately does not share the daily-news candidate
pool or its evidence policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.recruitment_search import BACKENDS as QUERY_BACKENDS, execute_query as _execute_one_query
from automation.recruitment_sources import query_plan, scan_directories, navigational_url

CN_TZ = timezone(timedelta(hours=8))
RADAR_REGISTRY = ROOT / "content" / "招聘" / "recruitment-radar-registry.json"
DISCOVERY_DIR = ROOT / "content" / "招聘" / "发现"

RECRUITMENT_QUERY_FAMILIES = OrderedDict([
    ("official_institution", (
        "博物馆 招聘", "博物院 招聘", "博物馆 公开招聘", "博物馆 编外",
        "博物馆 讲解员 招聘", "博物馆 社教 招聘", "博物馆 展览 招聘",
        "博物馆 文保 招聘", "考古院 招聘", "考古研究院 招聘",
        "文物考古研究所 招聘", "文物保护 招聘", "文物保护中心 招聘",
        "文化遗产 招聘", "数字文博 招聘", "博物馆 数字化 招聘",
    )),
    ("government_umbrella", (
        "文化和旅游厅 直属事业单位 招聘", "文化和旅游局 下属事业单位 招聘",
        "文广旅局 下属事业单位 招聘", "文物局 直属事业单位 招聘",
        "文旅厅 事业单位 招聘", "文旅局 编外 招聘",
    )),
    ("professional_recruitment", (
        "site:gaoxiaojob.com 博物馆 招聘", "site:shiyebian.com 博物馆 招聘",
        "site:gaoxiaojob.com 考古 文物 招聘", "site:shiyebian.com 文旅厅 直属事业单位 招聘",
    )),
    ("school_employment", (
        "site:ncss.cn 博物馆 招聘", "site:edu.cn 博物馆 招聘",
        "site:edu.cn 考古 实习", "site:edu.cn 文物保护 招聘",
    )),
    ("zhejiang_regional", tuple(
        f"浙江 {city} 博物馆 招聘"
        for city in ("杭州", "宁波", "温州", "绍兴", "台州", "嘉兴", "湖州", "金华", "衢州", "舟山", "丽水")
    )),
])

RECRUITMENT_TERMS = ("招聘", "招录", "公开招聘", "编外", "岗位", "实习", "见习", "博士后", "招募", "實習", "見習", "博士後")
HERITAGE_TERMS = (
    "博物馆", "博物院", "纪念馆", "美术馆", "考古院", "考古研究院", "文物考古研究所", "文物保护研究所",
    "文物", "文博", "文保", "文化遗产", "数字文博", "博物館", "紀念館", "美術館", "文化遺產", "敦煌研究院",
)
HERITAGE_ROLE_TERMS = ("陈列", "展览", "社教", "公共教育", "讲解", "策展", "藏品")
UMBRELLA_TERMS = ("文化和旅游厅", "文化和旅游局", "文广旅局", "文旅厅", "文旅局", "文物局")


def now_cn() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def compact(value: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", "", str(value or "").lower())


def rolling_window(run_date: date, last_successful: date | None = None, *, overlap_days: int = 7) -> tuple[date, date]:
    """Return a bounded window that overlaps the previous successful run."""
    anchor = last_successful or run_date
    return min(run_date - timedelta(days=overlap_days - 1), anchor - timedelta(days=overlap_days - 1)), run_date


def is_recruitment_candidate(title: str, snippet: str = "") -> bool:
    text = f"{title} {snippet}"
    if not any(term in text for term in RECRUITMENT_TERMS):
        return False
    if any(term in text for term in HERITAGE_TERMS) or any(term in text for term in UMBRELLA_TERMS):
        return True
    # Role words such as "展览" are only meaningful beside an institution;
    # this keeps generic job fairs and exhibition-industry hiring out.
    return any(term in text for term in HERITAGE_ROLE_TERMS) and any(
        anchor in text for anchor in ("馆", "考古", "文化遗产")
    )


def _institution_from_title(title: str) -> str:
    patterns = (
        r"([一-鿿A-Za-z·、]{2,40}(?:博物馆|博物院|纪念馆|美术馆|考古研究院|考古院|文物考古研究所|文物保护研究所|文物保护中心|文博单位))",
        r"([一-鿿]{2,24}(?:文化和旅游厅|文化和旅游局|文广旅局|文物局))",
    )
    for pattern in patterns:
        match = re.search(pattern, title or "")
        if match:
            return match.group(1)
    return "待展开单位"


def _position_from_title(title: str) -> str:
    match = re.search(r"招聘(?:\d+名)?([^\s。，]{2,30}?(?:岗位|人员|研究员|讲解员))", title or "")
    return match.group(1) if match else (title or "待展开岗位")


def candidate_identity(candidate: dict) -> str:
    parts = (
        candidate.get("institution"), candidate.get("position"),
        candidate.get("recruitmentBatch") or candidate.get("deadline") or candidate.get("sourceSectionKey"),
        candidate.get("positionCode"),
        candidate.get("deadline"),
    )
    return "|".join(compact(part) for part in parts)


def build_candidate(record: dict) -> dict:
    title = str(record.get("title") or "").strip()
    institution = str(record.get("institution") or _institution_from_title(title)).strip()
    position = str(record.get("position") or _position_from_title(title)).strip()
    base = {
        "institution": institution,
        "position": position,
        "recruitmentBatch": record.get("recruitmentBatch") or ((re.search(r"(20\d{2}年(?:\d{1,2}月|上半年|下半年|第[一二三四五六七八九十\d]+批)?)", title) or [""])[0]),
        "announcementTitle": record.get("announcementTitle") or title,
        "discoveredAt": record.get("discoveredAt") or now_cn(),
        "discoverySource": record.get("sourceDomain") or record.get("discoverySource") or record.get("discoveredVia") or "query_search",
        "discoveryUrl": record.get("url") or record.get("discoveryUrl") or "",
        "discoveryQuery": record.get("discoveryQuery") or "",
        "publishedDate": record.get("publishedDate") or "",
        "deadline": record.get("deadline") or "",
        "targetPage": record.get("targetPage") or ("intern" if any(term in title for term in ("实习", "见习", "实践", "實習", "見習", "志愿", "志願")) else "jobs"),
        "opportunityType": record.get("opportunityType") or ("volunteer" if any(t in title for t in ("志愿","志願")) else "internship" if any(t in title for t in ("实习","實習","见习","見習")) else "postdoc" if any(t in title for t in ("博士后","博士後")) else "employment"),
        "verificationSource": record.get("verificationSource") or "",
        "verificationStatus": record.get("verificationStatus") or "pending",
        "verificationPageType": record.get("verificationPageType") or "",
        "decision": record.get("decision") or "pending",
        "decisionReason": record.get("decisionReason") or ("umbrella_notice_needs_attachment_inspection" if any(term in title for term in UMBRELLA_TERMS) else "detail_page_verification_required"),
        "missStage": record.get("missStage") or "search_not_recalled",
    }
    base.update({key: value for key, value in record.items() if key not in base and key not in {"url", "title", "sourceDomain", "discoveredVia"}})
    base["candidateId"] = record.get("candidateId") or "recruit-" + hashlib.sha1(candidate_identity(base).encode("utf-8")).hexdigest()[:12]
    return base


def expand_umbrella_rows(rows: list[list], source: dict) -> list[dict]:
    """Expand a parsed attachment table into one candidate per heritage row."""
    if not rows:
        return []
    header_index = next((i for i, row in enumerate(rows) if any("招聘单位" in str(cell) for cell in row)), 0)
    header = [str(value or "").replace("\n", "").strip() for value in rows[header_index]]
    institution_col = next((i for i, value in enumerate(header) if "招聘单位" in value), 1)
    position_col = next((i for i, value in enumerate(header) if "岗位名称" in value), 3 if len(header) > 3 else 2)
    code_col = next((i for i, value in enumerate(header) if "岗位代码" in value or "岗位编码" in value), None)
    count_col = next((i for i, value in enumerate(header) if "招聘人数" in value), None)
    found = []
    for row in rows[header_index + 1:]:
        values = list(row)
        institution = str(values[institution_col] if institution_col < len(values) else "").strip()
        position = str(values[position_col] if position_col < len(values) else "").strip()
        if not institution or not any(term in f"{institution} {position}" for term in HERITAGE_TERMS):
            continue
        candidate = build_candidate({
            **source,
            "institution": institution,
            "position": position,
            "positionCode": str(values[code_col]) if code_col is not None and code_col < len(values) else "",
            "headcount": values[count_col] if count_col is not None and count_col < len(values) else None,
            "missStage": "umbrella_notice_not_expanded",
            "decisionReason": "attachment_row_requires_verification",
        })
        found.append(candidate)
    return found


def publishable_recruitment_candidate(candidate: dict) -> bool:
    url = str(candidate.get("verificationSource") or "")
    page_type = candidate.get("verificationPageType")
    return bool(
        candidate.get("verificationStatus") == "verified"
        and page_type in {"detail", "application"}
        and url.startswith(("http://", "https://", "mailto:"))
        and candidate.get("institution")
        and candidate.get("position")
    )


def radar_lead_candidate(radar: dict, title: str) -> dict:
    return build_candidate({
        "title": title,
        "url": radar.get("url") or "",
        "discoverySource": radar.get("name") or "recruitment_radar",
        "verificationStatus": "pending",
        "decision": "pending",
        "decisionReason": "discovery_only_radar_requires_direct_source",
        "missStage": "radar_not_checked",
        "radarDiscoveryOnly": bool(radar.get("discoveryOnly", True)),
    })


def deduplicate_candidates(candidates: list[dict]) -> list[dict]:
    merged: OrderedDict[str, dict] = OrderedDict()
    for candidate in candidates:
        key = candidate_identity(candidate)
        if key not in merged:
            row = dict(candidate)
            row.setdefault("duplicateProvenance", [])
            merged[key] = row
            continue
        current = merged[key]
        preferred = candidate if publishable_recruitment_candidate(candidate) and not publishable_recruitment_candidate(current) else current
        other = current if preferred is candidate else candidate
        if preferred is candidate:
            preferred = dict(preferred)
            preferred["duplicateProvenance"] = list(current.get("duplicateProvenance") or [])
            merged[key] = preferred
            current = preferred
        current.setdefault("duplicateProvenance", []).append({
            "candidateId": other.get("candidateId"),
            "discoveryUrl": other.get("discoveryUrl"),
            "verificationSource": other.get("verificationSource"),
        })
    return list(merged.values())


def _load_registry() -> dict:
    if not RADAR_REGISTRY.exists():
        return {"schema": "recruitment-radar-registry-v1", "sources": []}
    return json.loads(RADAR_REGISTRY.read_text(encoding="utf-8"))


def _execute_queries(start: date, end: date, *, full_sweep=False, max_queries=None):
    plan = query_plan(end, RECRUITMENT_QUERY_FAMILIES, _load_registry(), full_sweep=full_sweep)
    tasks = [(task, backend) for task in plan for backend in QUERY_BACKENDS]
    if max_queries is not None:
        tasks = tasks[:max_queries]
    def execute(task_backend):
        task, backend = task_backend
        family = {"id": "recruitment-" + task["family"], "scope": "domestic"}
        window_start = min(start, end - timedelta(days=task["lookbackDays"] - 1))
        try:
            found, audit = _execute_one_query(family, backend, task["query"], window_start, end)
        except Exception as exc:
            found, audit = [], {"success": False, "failure": str(exc)[:240], "acceptedRawCount": 0}
        audit.update(recruitmentQueryFamily=task["family"], plannedQuery=task["query"], windowStart=window_start.isoformat(), windowEnd=end.isoformat())
        if task.get("sourceUrls"):audit["radarSourceUrls"] = task["sourceUrls"]
        if task.get("region"):audit["region"] = task["region"]
        return found, audit
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(execute,tasks))
    return [r for rows,_ in results for r in rows], [a for _,a in results]


def _source_coverage(audits: list[dict], registry: dict, directory_audits=None) -> list[dict]:
    rows = []
    channel_map = OrderedDict([
        ("official institution searches", "official_institution"),
        ("government / HR / culture-tourism umbrella searches", "government_umbrella"),
        ("professional recruitment sites", "professional_recruitment"),
        ("school employment sites", "school_employment"),
        ("Zhejiang regional searches", "zhejiang_regional"),
        ("internship searches", "internship"),
        ("nationwide rotation", "national_rotation"),
        ("long-running vacancies", "open_ended"),
    ])
    for name, family in channel_map.items():
        related = [row for row in audits if row.get("recruitmentQueryFamily") == family]
        successes = sum(bool(row.get("success")) for row in related)
        rows.append({
            "channel": name,
            "status": "not_checked" if not related else "success" if successes == len(related) else ("partial" if successes else "failed"),
            "attempted": len(related), "succeeded": successes,
            "result": "unknown" if not related or successes < len(related) else ("no_result" if not sum(row.get("acceptedRawCount", 0) for row in related) else "results_found"),
        })
    active = [row for row in registry.get("sources", []) if row.get("active")]
    for source in active:
        direct = [a for a in (directory_audits or []) if a.get("sourceUrl") == source["url"]]
        searches = [a for a in audits if source["url"] in a.get("radarSourceUrls", [])]
        rows.append({
            "channel": source["name"], "sourceUrl": source["url"],
            "status": direct[-1]["status"] if direct else "not_checked",
            "method": "direct_directory" if direct else "not_checked",
            "searchAttempts": len(searches), "searchSucceeded": sum(bool(a.get("success")) for a in searches),
            "result": direct[-1].get("result", "unknown") if direct else "directory_not_checked",
        })
    return rows


def keep_discovery_record(record):
    if navigational_url(record.get("url", "")):return False
    title=record.get("title", "")
    if is_recruitment_candidate(title,record.get("snippet", "")):return True
    # Government umbrella notices often name museums only in an attachment.
    family=record.get("queryFamily", "")
    query=record.get("discoveryQuery", "")
    umbrella="government_umbrella" in family or ("national_rotation" in family and "事业单位" in query)
    return umbrella and any(term in title for term in ("招聘","人才引进","招录"))


def build_ledger(run_date: date, records: list[dict], audits: list[dict], reviews: list[dict] | None = None, *, last_successful: date | None = None, directory_audits=None) -> dict:
    start, end = rolling_window(run_date, last_successful)
    candidates = [build_candidate(record) for record in records if keep_discovery_record(record)]
    candidates.extend(build_candidate(row) for row in (reviews or []))
    candidates = deduplicate_candidates(candidates)
    counts = {key: sum(row.get("decision") == key for row in candidates) for key in ("included", "rejected", "pending", "duplicate")}
    registry = _load_registry()
    family_summary = []
    for family in list(RECRUITMENT_QUERY_FAMILIES) + ["internship", "national_rotation", "registered_radar", "open_ended"]:
        related = [row for row in audits if row.get("recruitmentQueryFamily") == family]
        family_summary.append({
            "family": family,
            "queriesAttempted": len(related),
            "queriesSucceeded": sum(bool(row.get("success")) for row in related),
            "acceptedRawCount": sum(int(row.get("acceptedRawCount") or 0) for row in related),
        })
    return {
        "schema": "recruitment-discovery-v1",
        "date": run_date.isoformat(),
        "runType": "bounded_recovery" if reviews else "scheduled_discovery",
        "generatedAt": now_cn(),
        "lastSuccessfulRecruitmentRun": last_successful.isoformat() if last_successful else None,
        "windowStart": start.isoformat(),
        "windowEnd": end.isoformat(),
        "overlapDays": 7,
        "queriesAttempted": len(audits),
        "queriesSucceeded": sum(bool(row.get("success")) for row in audits),
        "queriesFailed": sum(not row.get("success") for row in audits),
        "sourceCoverage": _source_coverage(audits, registry, directory_audits),
        "directoryAudits": directory_audits or [],
        "rawRecords": records,
        "queryFamilySummary": family_summary,
        "queryAudits": audits,
        "rawResultCount": len(records),
        "candidateCount": len(candidates),
        "includedCount": counts["included"],
        "rejectedCount": counts["rejected"],
        "pendingCount": counts["pending"],
        "duplicateCount": counts["duplicate"],
        "candidates": candidates,
    }


def validate_ledger(payload: dict) -> list[str]:
    errors = []
    required = ("date", "windowStart", "windowEnd", "queriesAttempted", "queriesSucceeded", "sourceCoverage", "candidates")
    for key in required:
        if key not in payload:
            errors.append(f"missing {key}")
    candidates = payload.get("candidates") or []
    ids = [row.get("candidateId") for row in candidates]
    if len(ids) != len(set(ids)):
        errors.append("candidateId values must be unique")
    for row in candidates:
        if row.get("decision") == "included" and not publishable_recruitment_candidate(row):
            errors.append(f"included candidate lacks verified detail/application source: {row.get('candidateId')}")
        if row.get("radarDiscoveryOnly") and row.get("verificationSource") == row.get("discoveryUrl") and row.get("decision") == "included":
            errors.append(f"discovery-only radar used as final verification: {row.get('candidateId')}")
    for key, decision in (("includedCount", "included"), ("rejectedCount", "rejected"), ("pendingCount", "pending"), ("duplicateCount", "duplicate")):
        if payload.get(key) != sum(row.get("decision") == decision for row in candidates):
            errors.append(f"{key} does not reconcile")
    return errors


def persistent_review_queue(root, ledger):
    """Retain unresolved leads across runs; newest explicit decision wins."""
    root=Path(root); rows={}
    paths=sorted((root/"content/招聘/发现").glob("*.json"))
    ledgers=[json.loads(p.read_text(encoding="utf-8")) for p in paths if p.stem <= ledger["date"]]
    queue_path=root/"content/招聘/review-queue.json"
    if queue_path.exists():
        previous=json.loads(queue_path.read_text(encoding="utf-8"))
        if previous.get("asOf", "") <= ledger["date"]:
            ledgers.append({"date":previous.get("asOf",ledger["date"]),"candidates":previous.get("candidates",[])})
    ledgers.sort(key=lambda batch:batch["date"])
    for batch in ledgers+[ledger]:
        for candidate in batch.get("candidates",[]):
            key=candidate_identity(candidate)
            old=rows.get(key)
            current=dict(candidate)
            current["firstSeen"]=old.get("firstSeen") if old else candidate.get("firstSeen",batch["date"])
            current["lastSeen"]=batch["date"]
            # A raw rediscovery must not erase an explicit editorial decision.
            if old and old.get("decision") in ("included","rejected") and current.get("decision")=="pending":
                current={**old,"lastSeen":batch["date"]}
            rows[key]=current
    pending=[r for r in rows.values() if r.get("decision")=="pending"]
    def priority(row):
        year=re.search(r"20\d{2}",row.get("announcementTitle", ""))
        older=bool(year and int(year[0]) < int(ledger["date"][:4]))
        return (older,row.get("targetPage")!="intern",row["firstSeen"],row.get("institution",""))
    pending.sort(key=priority)
    return {"schema":"recruitment-review-queue-v1","asOf":ledger["date"],"pendingCount":len(pending),"candidates":pending}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--last-successful-date", type=date.fromisoformat)
    parser.add_argument("--review-file", type=Path)
    parser.add_argument("--input-results", type=Path)
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="Export queries for the existing Codex web-search tool; no network")
    parser.add_argument("--full-sweep", action="store_true", help="All provinces; 90-day catch-up")
    parser.add_argument("--max-queries", type=int, help="Bounded diagnostic sample, never a full coverage run")
    parser.add_argument("--inspect-limit", type=int, default=12, help="Bounded detail-page dossiers; no automatic verification")
    parser.add_argument("--output", type=Path, help="Separate audit output; does not overwrite production ledger")
    args = parser.parse_args()
    start, end = rolling_window(args.date, args.last_successful_date)
    if args.plan_only:
        payload={"date":args.date.isoformat(),"queryPlan":query_plan(args.date,RECRUITMENT_QUERY_FAMILIES,_load_registry(),full_sweep=args.full_sweep),"importFormat":{"records":[{"title":"公告标题","url":"原文或公告详情URL","snippet":"搜索摘要","publishedDate":"仅有明确依据才填","queryFamily":"recruitment-计划中的family"}],"queryAudits":[{"recruitmentQueryFamily":"计划中的family","actualQuery":"实际检索词","backend":"codex-web-search","success":True,"acceptedRawCount":0}]}}
        text=json.dumps(payload,ensure_ascii=False,indent=2)+"\n"
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding="utf-8")
        else:print(text)
        return 0
    if args.max_queries is not None and args.max_queries < 0:
        parser.error("--max-queries must be nonnegative")
    if args.write and args.max_queries is not None:
        parser.error("diagnostic samples must use --output, not --write")
    directory_audits=[]
    if args.input_results:
        source = json.loads(args.input_results.read_text(encoding="utf-8"))
        records, audits = source.get("records", []), source.get("queryAudits", [])
    elif args.no_live:
        records, audits = [], []
    else:
        records, audits = _execute_queries(start, end, full_sweep=args.full_sweep, max_queries=args.max_queries)
        from automation.backfill_monitoring import fetch
        direct_records, directory_audits = scan_directories(_load_registry(), fetch, checked_at=now_cn())
        records.extend(direct_records)
    reviews = json.loads(args.review_file.read_text(encoding="utf-8")).get("candidates", []) if args.review_file else []
    ledger = build_ledger(args.date, records, audits, reviews, last_successful=args.last_successful_date, directory_audits=directory_audits)
    ledger["queryPlan"]=query_plan(args.date, RECRUITMENT_QUERY_FAMILIES, _load_registry(), full_sweep=args.full_sweep)
    ledger["coverageMode"]="sample" if args.max_queries is not None else ("replay" if args.input_results or args.no_live else "full_sweep" if args.full_sweep else "daily_rotation")
    ledger["queryWindowStart"]=min((a.get("windowStart", start.isoformat()) for a in audits), default=start.isoformat())
    ledger["windowStart"]=ledger["queryWindowStart"]
    ledger["minimumQueryLookbackDays"]=90 if args.full_sweep else 30
    ledger["historicalDirectoryLeadsRetained"]=True
    ledger["reviewQueue"]=persistent_review_queue(ROOT, ledger)
    if not args.no_live and not args.input_results and args.inspect_limit > 0:
        from automation.recruitment_detail import inspect_candidates
        from automation.backfill_monitoring import fetch
        ledger["detailDossiers"]=inspect_candidates(ledger["reviewQueue"]["candidates"],fetch,now_cn(),min(args.inspect_limit,24))
    errors = validate_ledger(ledger)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if args.write:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        path = DISCOVERY_DIR / f"{args.date.isoformat()}.json"
        if path.exists():
            snapshots=DISCOVERY_DIR/"runs";snapshots.mkdir(exist_ok=True)
            stamp=datetime.now(CN_TZ).strftime("%Y%m%dT%H%M%S%f")
            (snapshots/f"{args.date.isoformat()}-before-{stamp}.json").write_bytes(path.read_bytes())
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (DISCOVERY_DIR.parent/"review-queue.json").write_text(json.dumps(ledger["reviewQueue"],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(path)
    print(json.dumps({key: ledger[key] for key in (
        "date", "windowStart", "windowEnd", "queriesAttempted", "queriesSucceeded",
        "queriesFailed", "rawResultCount", "candidateCount", "includedCount", "rejectedCount", "pendingCount",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

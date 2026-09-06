#!/usr/bin/env python3
"""Small, auditable discovery layer for the two-day recruitment update.

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.daily_discovery import QUERY_BACKENDS, _execute_one_query

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

RECRUITMENT_TERMS = ("招聘", "招录", "公开招聘", "编外", "岗位", "实习", "见习", "博士后", "招募")
HERITAGE_TERMS = (
    "博物馆", "博物院", "纪念馆", "美术馆", "考古院", "考古研究院", "文物考古研究所", "文物保护研究所",
    "文物", "文博", "文保", "文化遗产", "数字文博",
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
        candidate.get("recruitmentBatch"),
    )
    return "|".join(compact(part) for part in parts)


def build_candidate(record: dict) -> dict:
    title = str(record.get("title") or "").strip()
    institution = str(record.get("institution") or _institution_from_title(title)).strip()
    position = str(record.get("position") or _position_from_title(title)).strip()
    base = {
        "institution": institution,
        "position": position,
        "recruitmentBatch": record.get("recruitmentBatch") or ((re.search(r"(20\d{2}年(?:\d{1,2}月|上半年|下半年))", title) or [""])[0]),
        "announcementTitle": record.get("announcementTitle") or title,
        "discoveredAt": record.get("discoveredAt") or now_cn(),
        "discoverySource": record.get("sourceDomain") or record.get("discoverySource") or record.get("discoveredVia") or "query_search",
        "discoveryUrl": record.get("url") or record.get("discoveryUrl") or "",
        "discoveryQuery": record.get("discoveryQuery") or "",
        "publishedDate": record.get("publishedDate") or "",
        "deadline": record.get("deadline") or "",
        "targetPage": record.get("targetPage") or ("intern" if any(term in title for term in ("实习", "见习", "实践")) else "jobs"),
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


def _execute_queries(start: date, end: date) -> tuple[list[dict], list[dict]]:
    tasks = []
    for family_id, queries in RECRUITMENT_QUERY_FAMILIES.items():
        family = {"id": f"recruitment-{family_id}", "scope": "domestic"}
        for backend in QUERY_BACKENDS:
            for query in queries:
                tasks.append((family_id, family, backend, query))
    results = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=min(16, len(tasks))) as pool:
        futures = {
            pool.submit(_execute_one_query, family, backend, query, start, end): index
            for index, (_, family, backend, query) in enumerate(tasks)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    records, audits = [], []
    for task, result in zip(tasks, results):
        family_id, _, _, _ = task
        found, audit = result
        audit["recruitmentQueryFamily"] = family_id
        records.extend(found)
        audits.append(audit)
    return records, audits


def _source_coverage(audits: list[dict], registry: dict) -> list[dict]:
    rows = []
    channel_map = OrderedDict([
        ("official institution searches", "official_institution"),
        ("government / HR / culture-tourism umbrella searches", "government_umbrella"),
        ("professional recruitment sites", "professional_recruitment"),
        ("school employment sites", "school_employment"),
        ("Zhejiang regional searches", "zhejiang_regional"),
    ])
    for name, family in channel_map.items():
        related = [row for row in audits if row.get("recruitmentQueryFamily") == family]
        successes = sum(bool(row.get("success")) for row in related)
        rows.append({
            "channel": name,
            "status": "success" if related and successes == len(related) else ("partial" if successes else "failed"),
            "attempted": len(related), "succeeded": successes,
            "result": "no_result" if related and not sum(row.get("acceptedRawCount", 0) for row in related) else "results_found",
        })
    active = [row for row in registry.get("sources", []) if row.get("active")]
    radar_families = {
        "professional_recruitment_site": "professional_recruitment",
        "school_employment_site": "school_employment",
    }
    radar_checks = []
    for source in active:
        family = radar_families.get(source.get("type"))
        related = [row for row in audits if row.get("recruitmentQueryFamily") == family]
        radar_checks.append(bool(related and any(row.get("success") for row in related)))
    rows.append({
        "channel": "recruitment radar",
        "status": "success" if radar_checks and all(radar_checks) else ("partial" if any(radar_checks) else "failed"),
        "attempted": len(active), "succeeded": sum(radar_checks),
        "result": "discovery-only radar queries checked; direct detail verification still required" if active else "no active machine-readable radar endpoint",
    })
    return rows


def build_ledger(run_date: date, records: list[dict], audits: list[dict], reviews: list[dict] | None = None, *, last_successful: date | None = None) -> dict:
    start, end = rolling_window(run_date, last_successful)
    candidates = [build_candidate(record) for record in records if is_recruitment_candidate(record.get("title", ""), record.get("snippet", ""))]
    candidates.extend(build_candidate(row) for row in (reviews or []))
    candidates = deduplicate_candidates(candidates)
    counts = {key: sum(row.get("decision") == key for row in candidates) for key in ("included", "rejected", "pending", "duplicate")}
    registry = _load_registry()
    family_summary = []
    for family in RECRUITMENT_QUERY_FAMILIES:
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
        "sourceCoverage": _source_coverage(audits, registry),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--last-successful-date", type=date.fromisoformat)
    parser.add_argument("--review-file", type=Path)
    parser.add_argument("--input-results", type=Path)
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    start, end = rolling_window(args.date, args.last_successful_date)
    if args.input_results:
        source = json.loads(args.input_results.read_text(encoding="utf-8"))
        records, audits = source.get("records", []), source.get("queryAudits", [])
    elif args.no_live:
        records, audits = [], []
    else:
        records, audits = _execute_queries(start, end)
    reviews = json.loads(args.review_file.read_text(encoding="utf-8")).get("candidates", []) if args.review_file else []
    ledger = build_ledger(args.date, records, audits, reviews, last_successful=args.last_successful_date)
    errors = validate_ledger(ledger)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    if args.write:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        path = DISCOVERY_DIR / f"{args.date.isoformat()}.json"
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)
    print(json.dumps({key: ledger[key] for key in (
        "date", "windowStart", "windowEnd", "queriesAttempted", "queriesSucceeded",
        "queriesFailed", "rawResultCount", "candidateCount", "includedCount", "rejectedCount", "pendingCount",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""One-time migration from heatmap schema v2 into the independent corpus.

The migration intentionally retains only reports whose original URL belongs to
the fixed map source panel.  It does not claim historical coverage completeness.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.governance import canonical_url, map_source_id


def record_id(date, url):
    seed = f"legacy|{date}|{canonical_url(url)}"
    return "mon-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def main():
    source = ROOT / "heatmap-data.json"
    target = ROOT / "content" / "监测" / "baseline.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    records = []
    seen = set()
    if data.get("version") == 2:
        event_buckets = [data.get(bucket, []) for bucket in (
            "events", "nationalEvents", "internationalEvents"
        )]
        baseline_period = {"start": data.get("start", ""), "end": data.get("asOf", "")}
    elif target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        event_buckets = []
        baseline_period = existing.get("period") or {"start": "", "end": ""}
        records = existing.get("records") or []
    else:
        raise SystemExit("no schema-v2 heatmap or existing baseline to migrate")

    for events in event_buckets:
        for event in events:
            for report in event.get("reports", []):
                panel_sources = []
                for source_row in report.get("sources", []):
                    source_id = map_source_id(source_row.get("url", ""))
                    if not source_id:
                        continue
                    panel_sources.append({
                        "sourceId": source_id,
                        "name": source_row.get("name", "原文"),
                        "url": canonical_url(source_row.get("url", "")),
                    })
                if not panel_sources:
                    continue
                key = panel_sources[0]["url"]
                if key in seen:
                    continue
                seen.add(key)
                records.append({
                    "recordId": record_id(report.get("date", ""), key),
                    "date": report.get("date", event.get("lastDate", "")),
                    "title": report.get("title", event.get("title", "")),
                    "sources": panel_sources,
                    "scope": event.get("scope", "province"),
                    "primaryProvince": event.get("primaryProvince", ""),
                    "relatedProvinces": event.get("relatedProvinces", []),
                    "locationTier": event.get("locationTier", "unassigned"),
                    "locationConfidence": event.get("locationConfidence", 0),
                    "themes": event.get("themes", []),
                    "tags": event.get("tags", []),
                    "impact": event.get("impact", 48),
                    "selectedForDaily": True,
                    "origin": "legacy-daily-selection",
                })

    deduped = {}
    for record in records:
        sources = record.get("sources") or []
        key = canonical_url(sources[0].get("url", "")) if sources else record.get("recordId", "")
        deduped[key] = record
    records = sorted(deduped.values(), key=lambda row: (row["date"], row["title"]))
    payload = {
        "version": 1,
        "kind": "legacy-baseline",
        "period": baseline_period,
        "coverageComplete": False,
        "note": "由旧日报精选样本迁移，仅保留固定信源池原文；历史覆盖率不可审计。",
        "records": records,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"migrated {len(records)} fixed-panel records to {target}")


if __name__ == "__main__":
    main()

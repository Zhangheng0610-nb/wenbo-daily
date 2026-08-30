#!/usr/bin/env python3
"""Validation for the shared weekly/monthly report layer."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build import parse_md
from automation.periodic_reports import build_periodic_model, load_editorial


def load_daily():
    rows = []
    for path in sorted((ROOT / "content" / "日报").glob("????-??-??.md")):
        data = parse_md(path)
        if data.get("date"):
            rows.append(data)
    return rows


def _all_rows(model):
    return {row.get("key"): row for row in model.get("items", []) if row.get("key")}


def _is_trend_claim(text):
    return bool(re.search(r"升温|降温|增加|减少|增长|下降|转向|趋于|持续|扩大|收缩|变化|结构", text or ""))


def check_editorial(model, editorial, expected_type, expected_key, preview=False):
    errors = []
    rows = _all_rows(model)
    if not editorial:
        return ["missing editorial layer"]
    if editorial.get("schema") != "periodic-editorial-v1":
        errors.append("editorial schema must be periodic-editorial-v1")
    if editorial.get("type") != expected_type or editorial.get("periodKey") != expected_key:
        errors.append("editorial period identity does not match model")
    expected_status = "preview" if preview else "final"
    if editorial.get("editorialStatus") != expected_status:
        errors.append(f"editorialStatus must be {expected_status}")
    if not editorial.get("oneLiner"):
        errors.append("editorial oneLiner is empty")
    for key in editorial.get("oneLinerSupportItemKeys", []):
        if key not in rows:
            errors.append(f"oneLiner support item missing: {key}")
    expected_highlights = 3 if expected_type == "weekly" else 5
    highlights = editorial.get("highlights", [])
    if len(highlights) != expected_highlights:
        errors.append("editorial highlight count does not match report type")
    seen = set()
    for highlight in highlights:
        key = highlight.get("itemKey")
        if key in seen:
            errors.append(f"duplicate highlight item: {key}")
        seen.add(key)
        if key not in rows:
            errors.append(f"highlight item missing: {key}")
        if not highlight.get("whyImportant"):
            errors.append(f"highlight lacks event-level whyImportant: {key}")
        elif key in rows and not rows[key].get("sources"):
            errors.append(f"highlight lacks publishable evidence: {key}")
    valid_topics = {row.get("topic") for row in model.get("sections", [])}
    for section in editorial.get("sectionInsights", []):
        topic = section.get("topic")
        support = section.get("supportItemKeys", [])
        item_keys = section.get("itemKeys", [])
        if topic not in valid_topics:
            errors.append(f"section insight topic missing: {topic}")
        if not section.get("insight"):
            errors.append(f"section insight empty: {topic}")
        if not support:
            errors.append(f"section insight lacks support: {topic}")
        if _is_trend_claim(section.get("insight", "")) and len(set(support)) < 2:
            errors.append(f"trend-like section insight needs two support items: {topic}")
        for key in set(support + item_keys):
            if key not in rows:
                errors.append(f"section item missing: {topic} -> {key}")
    digital = editorial.get("digitalInsight", {})
    if not digital.get("text"):
        errors.append("digital insight is empty")
    if not digital.get("supportItemKeys"):
        errors.append("digital insight lacks support")
    if _is_trend_claim(digital.get("text", "")) and len(set(digital.get("supportItemKeys", []))) < 2:
        errors.append("trend-like digital insight needs two support items")
    for key in set(digital.get("supportItemKeys", []) + digital.get("itemKeys", [])):
        if key not in rows:
            errors.append(f"digital item missing: {key}")
    comparison = editorial.get("comparisonInsight", {})
    if not comparison.get("text"):
        errors.append("comparison insight is empty")
    for key in comparison.get("supportItemKeys", []):
        if key not in rows:
            errors.append(f"comparison support item missing: {key}")
    for upcoming in editorial.get("upcoming", []):
        if not upcoming.get("date") or not upcoming.get("text"):
            errors.append("upcoming item lacks date/text")
        if upcoming.get("itemKey") and upcoming["itemKey"] not in rows:
            errors.append(f"upcoming item missing: {upcoming.get('itemKey')}")
    return errors


def check_model(model, editorial, expected_type, expected_key, html_path, preview=False):
    errors = check_editorial(model, editorial, expected_type, expected_key, preview)
    errors = []
    if model.get("layout") != "periodic-v2":
        errors.append("layout must be periodic-v2")
    if model.get("type") != expected_type:
        errors.append(f"type must be {expected_type}")
    if model.get("periodKey") != expected_key:
        errors.append(f"periodKey must be {expected_key}")
    metrics = model.get("metrics", {})
    for key, value in metrics.items():
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            errors.append(f"metric {key} is not finite")
    daily_counts = model.get("dailyCounts", [])
    if sum(row.get("count", 0) for row in daily_counts) != metrics.get("publishedEvents", 0):
        errors.append("daily cadence does not equal publishedEvents")
    for row in model.get("highlights", []):
        if not row.get("report") or not row.get("sources"):
            errors.append(f"highlight lacks report/evidence: {row.get('title', '')}")
        elif not (ROOT / row["report"].split("#", 1)[0]).exists():
            errors.append(f"highlight report missing: {row.get('report', '')}")
        if not any(evidence.get("title") == row.get("title") for evidence in model.get("evidence", [])):
            errors.append(f"highlight absent from evidence index: {row.get('title', '')}")
    if len(model.get("highlights", [])) != (3 if expected_type == "weekly" else 5):
        errors.append("highlight count does not match report type")
    if not html_path.exists() or html_path.stat().st_size == 0:
        errors.append(f"missing or empty HTML: {html_path.relative_to(ROOT)}")
    else:
        text = html_path.read_text(encoding="utf-8")
        if "NaN" in text or "Infinity" in text:
            errors.append("HTML contains NaN/Infinity")
        if text.count("periodic-highlight") < len(model.get("highlights", [])):
            errors.append("HTML highlight cards do not match model")
    return errors


def validate(expected_type, expected_key, model_path, html_path):
    try:
        model = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid model JSON: {exc}"]
    preview = model.get("preview", False)
    editorial = load_editorial(ROOT, expected_type, expected_key, preview=preview)
    errors = check_model(model, editorial, expected_type, expected_key, html_path, preview)
    daily = load_daily()
    expected = build_periodic_model(daily, expected_type, expected_key, preview=model.get("preview", False))
    for key in ("periodStart", "periodEnd", "metrics", "topicDistribution", "dailyCounts", "items"):
        if model.get(key) != expected.get(key):
            errors.append(f"model drift in {key}")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=("weekly", "monthly"), required=True)
    ap.add_argument("--key", required=True, help="weekly: YYYY-MM-DD; monthly: YYYY-MM")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args(argv)
    if args.preview:
        model_path = ROOT / "content" / "报告" / f"monthly-{args.key}-preview.json"
        html_path = ROOT / "reports" / f"monthly-{args.key}-preview.html"
    else:
        model_path = ROOT / "content" / "报告" / f"{args.type}-{args.key}.json" if args.type == "weekly" else ROOT / "content" / "报告" / f"monthly-{args.key}.json"
        html_path = ROOT / "reports" / (f"weekly-{args.key}.html" if args.type == "weekly" else f"monthly-{args.key}-28.html")
    errors = validate(args.type, args.key, model_path, html_path)
    if errors:
        print("PERIODIC VALIDATION FAILED")
        print("\n".join(errors))
        return 1
    print(f"PERIODIC VALIDATION OK: {args.type} {args.key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

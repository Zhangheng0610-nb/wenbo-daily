#!/usr/bin/env python3
"""Generate the shared periodic-report data models.

Examples:
  python automation/generate_periodic_reports.py --weekly 2026-08-30
  python automation/generate_periodic_reports.py --monthly-preview 2026-08
  python automation/generate_periodic_reports.py --monthly 2026-08

Formal monthly generation refuses an incomplete month.  Use the explicit
preview command while the final day is not yet available.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build import parse_digest, parse_md
from automation.periodic_reports import apply_editorial, build_periodic_html, build_periodic_model, load_editorial


def load_daily_reports():
    reports = []
    for path in sorted((ROOT / "content" / "日报").glob("*.md")):
        first = path.read_text(encoding="utf-8").splitlines()[0] if path.exists() else ""
        if "周报" in first or "月报" in first:
            continue
        data = parse_md(path)
        if data.get("date"):
            reports.append(data)
    return reports


def save_json(model, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def month_key(value):
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("月份必须是 YYYY-MM")
    return value


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weekly", metavar="YYYY-MM-DD", help="生成周报模型")
    ap.add_argument("--monthly", metavar="YYYY-MM", help="生成完整月报；缺日报时拒绝")
    ap.add_argument("--monthly-preview", metavar="YYYY-MM", help="生成带不完整标识的本地月报预览")
    args = ap.parse_args(argv)
    selected = [bool(args.weekly), bool(args.monthly), bool(args.monthly_preview)]
    if sum(selected) != 1:
        ap.error("三种模式只能选择一种")

    daily = load_daily_reports()
    report_dir = ROOT / "content" / "报告"
    output = []
    if args.weekly:
        key = args.weekly
        model = build_periodic_model(daily, "weekly", key)
        existing_path = ROOT / "content" / "日报" / f"weekly-{key}.md"
        if existing_path.exists():
            model = build_periodic_model(daily, "weekly", key, existing=parse_digest(existing_path, "weekly"))
        editorial = load_editorial(ROOT, "weekly", key)
        if not editorial:
            raise SystemExit(f"缺少 editorial layer：content/报告/weekly-{key}-editorial.json")
        model = apply_editorial(model, editorial)
        output.append(save_json(model, report_dir / f"weekly-{key}.json"))
        if not existing_path.exists():
            existing_path.write_text(
                f"# 📰 文博资讯周报 | {model['periodStart'][:4]}年{int(model['periodStart'][5:7])}月{int(model['periodStart'][8:10])}日 — "
                f"{int(model['periodEnd'][5:7])}月{int(model['periodEnd'][8:10])}日\n\n"
                "<!-- 周期报告组件：页面数据见 content/报告/ -->\n\n"
                f"*本周报由周期报告组件生成 | 数据周期：{model['periodStart']}—{model['periodEnd']}*\n",
                encoding="utf-8",
            )
            print(f"weekly source: {existing_path}")
        print(f"weekly model: {output[-1]}")
    elif args.monthly_preview:
        key = month_key(args.monthly_preview)
        model = build_periodic_model(daily, "monthly", key, preview=True)
        editorial = load_editorial(ROOT, "monthly", key, preview=True)
        if not editorial:
            raise SystemExit(f"缺少 editorial layer：content/报告/monthly-{key}-editorial.json")
        model = apply_editorial(model, editorial)
        data_path = save_json(model, report_dir / f"monthly-{key}-preview.json")
        html_path = ROOT / "reports" / f"monthly-{key}-preview.html"
        html_path.write_text(build_periodic_html(model), encoding="utf-8")
        print(f"monthly preview model: {data_path}")
        print(f"monthly preview HTML: {html_path}")
        return 0
    else:
        key = month_key(args.monthly)
        model = build_periodic_model(daily, "monthly", key)
        if not model["metrics"]["coverageComplete"]:
            missing = model["metrics"]["expectedDays"] - model["metrics"]["coveredDays"]
            raise SystemExit(f"拒绝生成正式月报：仍缺少 {missing} 天日报；请使用 --monthly-preview")
        editorial = load_editorial(ROOT, "monthly", key)
        if not editorial:
            raise SystemExit(f"缺少 editorial layer：content/报告/monthly-{key}-editorial.json")
        model = apply_editorial(model, editorial)
        output.append(save_json(model, report_dir / f"monthly-{key}.json"))
        source_path = ROOT / "content" / "日报" / f"月报-{key}.md"
        source_path.write_text(
            f"# 📚 文博资讯月报 | {key[:4]}年{int(key[5:]):d}月\n\n"
            "<!-- 周期报告组件：页面数据见 content/报告/ -->\n\n"
            f"*本月报由周期报告组件生成 | 数据周期：{model['periodStart']}—{model['periodEnd']}*\n",
            encoding="utf-8",
        )
        print(f"monthly model: {output[-1]}")
        print(f"monthly source: {source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

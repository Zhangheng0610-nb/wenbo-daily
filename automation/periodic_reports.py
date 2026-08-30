#!/usr/bin/env python3
"""Shared, deterministic data model and renderer for weekly/monthly reports.

This module deliberately consumes parsed daily reports.  It does not alter the
daily parser, source governance, map corpus, or digital-trend data model.
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from automation.governance import source_info


TOPICS = (
    "政策与治理",
    "考古与文物保护",
    "博物馆与公共文化",
    "数字化与创新",
    "国际与区域",
    "其他行业动态",
)

TOPIC_LABELS = {
    "政策与治理": "政策、制度与行业治理",
    "考古与文物保护": "考古、保护与研究",
    "博物馆与公共文化": "博物馆、展览与公共文化",
    "数字化与创新": "数字化与创新",
    "国际与区域": "国际合作与区域交流",
    "其他行业动态": "其他行业动态",
}


def _parse_iso(value):
    return date.fromisoformat(value)


def _period_bounds(period_type, period_key):
    if period_type == "weekly":
        end = _parse_iso(period_key)
        return end - timedelta(days=6), end
    year, month = (int(x) for x in period_key.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1)
    return start, end


def _compact(value, limit=100):
    value = re.sub(r"<[^>]+>", "", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip("，。；、 ") + "…"


def _scope(item, section):
    if section != "international":
        return "domestic"
    text = f"{item.get('title', '')} {' '.join(item.get('tags') or [])}"
    return "regional" if re.search(r"香港|澳门|台湾|粤港澳|大湾区|区域交流", text) else "international"


def _primary_topic(item, scope):
    tags = set(item.get("tags") or [])
    title = item.get("title", "")
    if tags & {"政策行业", "政策", "法规", "文物法规", "行业治理"} or re.search(r"办法|条例|通知|政策|规划|审核", title):
        return "政策与治理"
    if tags & {"考古", "文物保护", "文物修复", "世界遗产", "遗产", "文物追索"}:
        return "考古与文物保护"
    if "数字化" in tags or "科技" in tags:
        return "数字化与创新"
    if scope in {"regional", "international"} or tags & {"国际交流", "国际", "对外交流"}:
        return "国际与区域"
    if tags & {"博物馆", "展览", "公共文化", "文化遗产", "文创", "公众互动"}:
        return "博物馆与公共文化"
    return "其他行业动态"


def _item_record(report, item, section):
    topic = _primary_topic(item, _scope(item, section))
    body = item.get("body", "")
    summary = re.split(r"(?<=[。！？])", body)[0] if body else item.get("title", "")
    return {
        "key": f"{report['date']}#{item.get('id', '')}",
        "title": item.get("title", ""),
        "summary": _compact(summary, 120),
        "topic": topic,
        "scope": _scope(item, section),
        "date": report["date"],
        "report": f"reports/{report['date']}.html#{item.get('id', '')}",
        "reportLabel": f"{report['date']} 日报",
        "tags": list(item.get("tags") or []),
        "sources": _publishable_sources(item.get("sources") or []),
    }


def _publishable_sources(sources):
    """Reuse daily evidence without exposing blocked or unapproved links."""
    result = []
    seen = set()
    for source in sources:
        url = source.get("url", "")
        if not url or url in seen:
            continue
        info = source_info(url)
        if info.get("blocked") or info.get("tier") not in ("A", "B"):
            continue
        seen.add(url)
        result.append({"name": source.get("name", "原始来源"), "url": url})
    return result


def _flatten_reports(daily_reports, start, end):
    rows = []
    for report in daily_reports:
        rdate = report.get("date", "")
        if not rdate or not (start.isoformat() <= rdate <= end.isoformat()):
            continue
        for section in ("domestic", "international"):
            for item in report.get(section, []):
                rows.append(_item_record(report, item, section))
    return rows


def _metrics(rows, expected_days, available_days):
    scopes = Counter(row["scope"] for row in rows)
    return {
        "publishedEvents": len(rows),
        "coveredDays": len(available_days),
        "expectedDays": expected_days,
        "coverageComplete": len(available_days) == expected_days,
        "domestic": scopes.get("domestic", 0),
        "regional": scopes.get("regional", 0),
        "international": scopes.get("international", 0),
        "digital": sum(row["topic"] == "数字化与创新" or "数字化" in row["tags"] for row in rows),
    }


def _topic_distribution(rows):
    counts = Counter(row["topic"] for row in rows)
    return [{"topic": topic, "label": TOPIC_LABELS[topic], "count": counts.get(topic, 0)} for topic in TOPICS if counts.get(topic, 0)]


def _daily_counts(rows, start, end):
    counts = Counter(row["date"] for row in rows)
    available = set(counts)
    return [{"date": (start + timedelta(days=i)).isoformat(), "count": counts.get((start + timedelta(days=i)).isoformat(), 0), "report": f"reports/{(start + timedelta(days=i)).isoformat()}.html" if (start + timedelta(days=i)).isoformat() in available else ""} for i in range((end - start).days + 1)]


def _comparison(current, previous):
    if not previous:
        return {"available": False, "note": "暂无可比较的上一周期数据。"}
    fields = ("publishedEvents", "digital", "domestic", "regional", "international")
    comparable = bool(current.get("coverageComplete") and previous.get("coverageComplete"))
    note = "数量变化仅作样本对照；小样本不自动推导行业趋势。"
    if not comparable:
        note = "上一周期数据不完整，仅作已有样本参考，不与完整周期直接比较。"
    return {
        "available": True,
        "comparable": comparable,
        "previousCoveredDays": previous.get("coveredDays", 0),
        "previousExpectedDays": previous.get("expectedDays", 0),
        "current": {field: current.get(field, 0) for field in fields},
        "previous": {field: previous.get(field, 0) for field in fields},
        "note": note,
    }


def _weekly_rollup(rows, start, end):
    weeks = []
    cursor = start
    index = 1
    while cursor <= end:
        week_end = min(cursor + timedelta(days=6), end)
        subset = [row for row in rows if cursor.isoformat() <= row["date"] <= week_end.isoformat()]
        weeks.append({
            "label": f"第{index}周",
            "start": cursor.isoformat(),
            "end": week_end.isoformat(),
            "count": len(subset),
            "topics": _topic_distribution(subset),
        })
        cursor = week_end + timedelta(days=1)
        index += 1
    return weeks


def _sections(rows):
    sections = []
    for topic in TOPICS:
        subset = [row for row in rows if row["topic"] == topic]
        if not subset:
            continue
        sections.append({
            "topic": topic,
            "title": TOPIC_LABELS[topic],
            "summary": "",
            "items": subset,
        })
    return sections


def _evidence(rows):
    result = []
    for row in rows:
        if not row["sources"]:
            continue
        result.append({
            "title": row["title"],
            "report": row["report"],
            "reportLabel": row["reportLabel"],
            "sources": row["sources"][:3],
        })
    return result


def build_periodic_model(daily_reports, period_type, period_key, *, existing=None, preview=False):
    start, end = _period_bounds(period_type, period_key)
    expected_days = (end - start).days + 1
    available_dates = sorted({report.get("date") for report in daily_reports if start.isoformat() <= report.get("date", "") <= end.isoformat()})
    rows = _flatten_reports(daily_reports, start, end)
    metrics = _metrics(rows, expected_days, available_dates)

    if period_type == "weekly":
        previous_start = start - timedelta(days=7)
        previous_rows = _flatten_reports(daily_reports, previous_start, start - timedelta(days=1))
        period_label = f"{start.isoformat()} — {end.isoformat()}"
        title = "文博行业周报"
    else:
        previous_start = date(start.year - (start.month == 1), 12 if start.month == 1 else start.month - 1, 1)
        previous_end = start - timedelta(days=1)
        previous_rows = _flatten_reports(daily_reports, previous_start, previous_end)
        period_label = f"{start.isoformat()} — {end.isoformat()}"
        title = f"文博行业月报 · {start.year}年{start.month}月"

    previous_metrics = _metrics(previous_rows, (start - previous_start).days, sorted({row["date"] for row in previous_rows})) if previous_rows else None
    digital_rows = [row for row in rows if "数字化" in row["tags"] or row["topic"] == "数字化与创新"]
    quality_notes = ["周期统计以实际存在的日报为准；未覆盖日期不外推。"]
    if not metrics["coverageComplete"]:
        missing = [
            (start + timedelta(days=i)).isoformat()
            for i in range(expected_days)
            if (start + timedelta(days=i)).isoformat() not in set(available_dates)
        ]
        quality_notes.append(f"当前为{'月报' if period_type == 'monthly' else '周报'}不完整预览：缺少 {', '.join(missing)} 的日报。")
    quality_notes.append("候选账本只从 2026-08-29 起建立；本周期不展示候选发现量或采用率作为整期指标。")
    if period_type == "monthly":
        quality_notes.append("摘编/日报中的事件按日报收录条目统计，不等同于整个行业发生量。")

    existing_upcoming = []
    if existing:
        for row in existing.get("upcoming_table", []):
            if row and not all(str(cell).startswith("-") for cell in row):
                existing_upcoming.append(row)

    return {
        "layout": "periodic-v2",
        "type": period_type,
        "title": title,
        "label": "周报" if period_type == "weekly" else "月报",
        "periodKey": period_key,
        "periodStart": start.isoformat(),
        "periodEnd": end.isoformat(),
        "date_range": period_label,
        "ref_date": end.isoformat() if period_type == "weekly" else f"{start.year}-{start.month:02d}-28",
        "preview": bool(preview or not metrics["coverageComplete"]),
        "overview": "",
        "oneLiner": "",
        "metrics": metrics,
        "topicDistribution": _topic_distribution(rows),
        "dailyCounts": _daily_counts(rows, start, end),
        "highlights": [],
        "items": rows,
        "sections": _sections(rows),
        "weeklyRollup": _weekly_rollup(rows, start, end) if period_type == "monthly" else [],
        "comparison": _comparison(metrics, previous_metrics),
        "digitalObservation": {
            "count": len(digital_rows),
            "items": digital_rows,
            "note": "",
        },
        "upcoming": existing_upcoming,
        "evidence": _evidence(rows),
        "qualityNotes": quality_notes,
        "source": "日报档案与可回溯原始来源",
    }


def apply_editorial(model, editorial):
    """Merge a Codex-authored editorial layer onto deterministic period data."""
    if not editorial:
        return model
    rows = {row.get("key"): row for row in model.get("items", []) if row.get("key")}

    def with_reason(ref):
        row = dict(rows[ref["itemKey"]])
        row["whyImportant"] = ref.get("whyImportant", "")
        row["periodRelevance"] = ref.get("periodRelevance", "")
        row["impactLevel"] = ref.get("impactLevel", "")
        row["supportItemKeys"] = ref.get("supportItemKeys", [ref["itemKey"]])
        return row

    model["editorial"] = editorial
    model["editorialStatus"] = editorial.get("editorialStatus", "")
    model["overview"] = editorial.get("oneLiner", "")
    model["oneLiner"] = editorial.get("oneLiner", "")
    model["highlights"] = [with_reason(ref) for ref in editorial.get("highlights", []) if ref.get("itemKey") in rows]

    section_by_topic = {section.get("topic"): section for section in model.get("sections", [])}
    for insight in editorial.get("sectionInsights", []):
        section = section_by_topic.get(insight.get("topic"))
        if not section:
            continue
        section["summary"] = insight.get("insight", "")
        section["items"] = [dict(rows[key]) for key in insight.get("itemKeys", []) if key in rows]

    digital = editorial.get("digitalInsight", {})
    model["digitalObservation"] = {
        "count": sum(1 for row in rows.values() if "数字化" in row.get("tags", []) or row.get("topic") == "数字化与创新"),
        "items": [dict(rows[key]) for key in digital.get("itemKeys", []) if key in rows],
        "note": digital.get("text", ""),
    }
    comparison_insight = editorial.get("comparisonInsight", {})
    if comparison_insight and model.get("comparison"):
        model["comparison"]["note"] = comparison_insight.get("text", model["comparison"].get("note", ""))

    model["upcoming"] = editorial.get("upcoming", [])
    return model


def load_editorial(root, period_type, period_key, *, preview=False):
    root = Path(root)
    suffix = "-editorial.json"
    filename = f"weekly-{period_key}{suffix}" if period_type == "weekly" else f"monthly-{period_key}{suffix}"
    path = root / "content" / "报告" / filename
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload


def _source_link(source):
    name = html.escape(source.get("name", "原始来源"))
    url = html.escape(source.get("url", ""), quote=True)
    return f'<a href="{url}" target="_blank" rel="noopener">{name}</a>'


def _item_card(row, *, highlight=False, include_why=False):
    cls = "periodic-highlight" if highlight else "periodic-item"
    tags = " ".join(f'<span class="periodic-tag">{html.escape(tag)}</span>' for tag in row.get("tags", [])[:3])
    sources = " ".join(_source_link(source) for source in row.get("sources", [])[:3])
    why_html = f'<p class="periodic-why"><strong>为什么值得注意：</strong>{html.escape(row.get("whyImportant", ""))}</p>' if include_why and row.get("whyImportant") else ""
    sources_html = f'<p class="periodic-sources">证据：{sources}</p>' if sources else '<p class="periodic-sources muted">暂无可回溯原始来源</p>'
    return f'''<article class="{cls}">
  <div class="periodic-item-head"><span class="periodic-topic">{html.escape(row.get("topic", ""))}</span><span class="periodic-date">{html.escape(row.get("date", ""))}</span></div>
  <h3>{html.escape(row.get("title", ""))}</h3>
  <p>{html.escape(row.get("summary", ""))}</p>
{why_html}
  <p class="periodic-links"><a href="../{html.escape(row.get('report', ''), quote=True)}">{html.escape(row.get("reportLabel", "对应日报"))}</a>{(' · ' + tags) if tags else ''}</p>
{sources_html}
</article>'''


def build_periodic_html(data):
    if not data.get("editorial") or data.get("editorialStatus") not in ("final", "preview"):
        raise ValueError("周期报告缺少 editorial layer；正式报告不得退回模板化判断")
    dtype = data.get("type", "weekly")
    label = "周报" if dtype == "weekly" else "月报"
    period_word = "本周" if dtype == "weekly" else "本月"
    slug = f"{dtype}-{data.get('ref_date', '')}"
    metrics = data.get("metrics", {})
    preview = data.get("preview")
    preview_banner = ''
    if preview:
        preview_banner = '<div class="periodic-quality"><strong>本地预览：</strong>当前周期数据尚未完整，页面只展示已经存在的日报，不作为正式整期结论。</div>'

    metric_cards = [
        (metrics.get("publishedEvents", 0), "本期收录事件", "日报条目"),
        (f"{metrics.get('coveredDays', 0)}/{metrics.get('expectedDays', 0)}", "日报覆盖", "实际有日报的天数"),
        (f"{metrics.get('domestic', 0)} / {metrics.get('regional', 0)} / {metrics.get('international', 0)}", "国内 / 区域 / 国际", "按日报栏目语义归类"),
        (metrics.get("digital", 0), "数字化相关事件", "本站样本内"),
    ]
    metric_html = "".join(f'<div class="periodic-metric"><strong>{html.escape(str(value))}</strong><span>{html.escape(title)}</span><small>{html.escape(note)}</small></div>' for value, title, note in metric_cards)

    topics = data.get("topicDistribution", [])
    max_topic = max((row["count"] for row in topics), default=1)
    topics_html = "".join(f'''<div class="periodic-bar-row"><span>{html.escape(row["label"])}</span><div class="periodic-bar"><i style="width:{round(row["count"] / max_topic * 100)}%"></i></div><b>{row["count"]}</b></div>''' for row in topics)

    cadence = data.get("dailyCounts", [])
    max_day = max((row["count"] for row in cadence), default=1)
    cadence_html = "".join((f'''<a class="periodic-day" href="../{html.escape(row["report"], quote=True)}"><span>{html.escape(row["date"][5:])}</span><i style="height:{max(4, round(row["count"] / max_day * 100))}%"></i><b>{row["count"]}</b></a>''' if row.get("report") else f'''<div class="periodic-day unavailable"><span>{html.escape(row["date"][5:])}</span><i style="height:4%"></i><b>—</b></div>''') for row in cadence)

    highlight_html = "".join(_item_card(row, highlight=True, include_why=True) for row in data.get("highlights", [])) or '<p class="muted">本期暂无可展示重点。</p>'
    section_html = ""
    for section in data.get("sections", []):
        cards = "".join(_item_card(row) for row in section.get("items", []))
        section_html += f'<section class="periodic-section"><h2>{html.escape(section["title"])}</h2><p class="section-lead">{html.escape(section["summary"])}</p>{cards}</section>'

    comparison = data.get("comparison", {})
    comparison_html = f'<p class="muted">{html.escape(comparison.get("note", "暂无可比较数据"))}</p>'
    if comparison.get("available") and comparison.get("comparable", True):
        fields = (("publishedEvents", "总事件量"), ("digital", "数字化相关"), ("domestic", "国内"), ("regional", "区域"), ("international", "国际"))
        comparison_html = '<div class="periodic-compare">' + "".join(f'<div><span>{title}</span><strong>{comparison["previous"][key]} → {comparison["current"][key]}</strong></div>' for key, title in fields) + '</div><p class="muted">' + html.escape(comparison.get("note", "")) + '</p>'
    elif comparison.get("available"):
        comparison_html = '<p class="muted">上一自然周期仅覆盖 ' + html.escape(str(comparison.get("previousCoveredDays", 0))) + '/' + html.escape(str(comparison.get("previousExpectedDays", 0))) + ' 天；当前周期覆盖 ' + html.escape(str(metrics.get("coveredDays", 0))) + '/' + html.escape(str(metrics.get("expectedDays", 0))) + ' 天。' + html.escape(comparison.get("note", "数据不完整，不进行完整周期比较。")) + '</p>'

    digital = data.get("digitalObservation", {})
    digital_html = ''.join(_item_card(row) for row in digital.get("items", [])) or '<p class="muted">本期没有足够数字化相关样本。</p>'

    rollup_html = ""
    if dtype == "monthly":
        rollup_html = '<section class="periodic-section"><h2>四周节奏</h2><div class="periodic-rollup">' + ''.join(f'<div><strong>{html.escape(row["label"])}</strong><span>{html.escape(row["start"])} — {html.escape(row["end"])}</span><b>{row["count"]} 条</b></div>' for row in data.get("weeklyRollup", [])) + '</div></section>'

    upcoming_html = ""
    if data.get("upcoming"):
        rows = []
        for row in data["upcoming"]:
            item = row.get("itemKey")
            report = data.get("items", [])
            source_row = next((candidate for candidate in report if candidate.get("key") == item), None)
            report_link = f'<a href="../{html.escape(source_row.get("report", ""), quote=True)}">对应日报</a>' if source_row else ''
            rows.append(f'<tr><td>{html.escape(str(row.get("date", "")))}</td><td>{html.escape(str(row.get("text", "")))}</td><td>{report_link}</td></tr>')
        upcoming_html = '<section class="periodic-section"><h2>下期值得继续关注</h2><table><tbody>' + ''.join(rows) + '</tbody></table><p class="muted">仅保留已有公开确定节点，不对未知事件做预测。</p></section>'

    evidence_rows = []
    for row in data.get("evidence", []):
        sources = " ".join(_source_link(source) for source in row.get("sources", []))
        evidence_rows.append(f'<li><strong>{html.escape(row.get("title", ""))}</strong> · <a href="../{html.escape(row.get("report", ""), quote=True)}">{html.escape(row.get("reportLabel", "日报"))}</a><br>{sources}</li>')
    evidence_html = '<details class="periodic-evidence"><summary>🔎 来源与证据索引（默认折叠）</summary><p class="muted">报告判断 → 对应日报条目 → 原始来源。以下证据仅来自已有日报。</p><ol>' + ''.join(evidence_rows) + '</ol></details>' if evidence_rows else '<details class="periodic-evidence"><summary>🔎 来源与证据索引（默认折叠）</summary><p class="muted">当前没有可回溯的来源记录。</p></details>'
    quality_html = ''.join(f'<li>{html.escape(note)}</li>' for note in data.get("qualityNotes", []))

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title if (title := data.get("title", f"文博行业{label}")) else f"文博行业{label}")} | {html.escape(data.get("date_range", ""))}</title>
<meta name="description" content="{html.escape(data.get("date_range", ""))} 文博行业{label}，基于本站日报样本的周期观察。">
<style>
:root{{--bg:#f5f0eb;--card:#fff;--text:#2c2416;--muted:#806d57;--accent:#8b4513;--soft:#f0e6d3;--border:#e0d5c1;--shadow:0 8px 22px rgba(82,54,24,.07)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1a1815;--card:#252320;--text:#e8e0d0;--muted:#aa9a89;--accent:#d4a76a;--soft:#302920;--border:#463b30;--shadow:none}}}}
*{{box-sizing:border-box}} body{{margin:0;padding:24px;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.7}} main{{max-width:1160px;margin:0 auto}} a{{color:var(--accent);word-break:break-word}} header{{padding:20px 0 22px;border-bottom:2px solid var(--accent);margin-bottom:20px}} header h1{{margin:0;font-size:clamp(1.55rem,3vw,2.25rem)}} .meta{{color:var(--muted);margin:6px 0}} .back{{font-size:.9rem}} .periodic-quality{{background:var(--soft);border-left:4px solid var(--accent);padding:12px 15px;margin:0 0 18px;border-radius:6px}} .periodic-kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}} .periodic-metric,.periodic-highlight,.periodic-item,.periodic-section,.periodic-evidence{{background:var(--card);border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow)}} .periodic-metric{{padding:16px}} .periodic-metric strong{{display:block;font-size:1.65rem;font-variant-numeric:tabular-nums;color:var(--accent)}} .periodic-metric span,.periodic-metric small{{display:block}} .periodic-metric small,.muted{{color:var(--muted);font-size:.88rem}} .periodic-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}} .periodic-section{{padding:18px;margin:16px 0}} .periodic-grid>.periodic-section{{margin:0}} h2{{font-size:1.15rem;color:var(--accent);margin:0 0 12px}} .section-lead{{color:var(--muted);margin-top:-4px}} .periodic-highlights{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0}} .periodic-highlight,.periodic-item{{padding:16px}} .periodic-item{{margin:10px 0;box-shadow:none}} .periodic-item-head{{display:flex;justify-content:space-between;gap:8px;color:var(--muted);font-size:.82rem}} .periodic-topic{{color:var(--accent)}} .periodic-highlight h3,.periodic-item h3{{font-size:1.02rem;line-height:1.45;margin:8px 0}} .periodic-highlight p,.periodic-item p{{margin:7px 0;font-size:.92rem}} .periodic-why{{color:var(--text)}} .periodic-links,.periodic-sources{{font-size:.82rem!important}} .periodic-tag{{display:inline-block;background:var(--soft);padding:1px 6px;border-radius:10px;margin-left:4px}} .periodic-bar-row{{display:grid;grid-template-columns:150px 1fr 28px;align-items:center;gap:8px;margin:11px 0;font-size:.9rem}} .periodic-bar{{height:9px;border-radius:9px;background:var(--soft);overflow:hidden}} .periodic-bar i{{display:block;height:100%;background:var(--accent);border-radius:inherit}} .periodic-day-wrap{{display:flex;align-items:flex-end;gap:5px;height:145px;overflow-x:auto;padding:8px 2px}} .periodic-day{{min-width:30px;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;text-decoration:none;font-size:.68rem}} .periodic-day i{{width:18px;min-height:4px;background:var(--accent);border-radius:4px 4px 0 0}} .periodic-day b{{font-size:.72rem;color:var(--text)}} .periodic-day span{{color:var(--muted);order:3;white-space:nowrap}} .periodic-compare{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}} .periodic-compare div,.periodic-rollup div{{background:var(--soft);padding:10px;border-radius:8px}} .periodic-compare span,.periodic-compare strong,.periodic-rollup span,.periodic-rollup b{{display:block}} .periodic-compare strong,.periodic-rollup b{{font-variant-numeric:tabular-nums;color:var(--accent)}} .periodic-rollup{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}} .periodic-evidence{{padding:14px 18px;margin:18px 0}} .periodic-evidence summary{{cursor:pointer;color:var(--accent);font-weight:700}} .periodic-evidence li{{margin:10px 0}} table{{width:100%;border-collapse:collapse;font-size:.9rem}} td,th{{border:1px solid var(--border);padding:8px;text-align:left}} footer{{color:var(--muted);font-size:.85rem;border-top:1px solid var(--border);padding:18px 0;margin-top:22px}}
@media(max-width:760px){{body{{padding:14px}} .periodic-kpis{{grid-template-columns:repeat(2,1fr)}} .periodic-highlights,.periodic-grid{{grid-template-columns:1fr}} .periodic-grid>*,.periodic-section,.periodic-bar-row,.periodic-bar,.periodic-day-wrap{{min-width:0}} .periodic-rollup{{grid-template-columns:repeat(2,1fr)}} .periodic-bar-row{{grid-template-columns:120px minmax(0,1fr) 24px}} .periodic-compare{{grid-template-columns:repeat(2,1fr)}} .periodic-metric strong{{font-size:1.35rem;white-space:nowrap}} table{{display:block;overflow-x:auto;white-space:nowrap}}}}
@media(max-width:380px){{.periodic-kpis{{gap:8px}} .periodic-metric{{padding:11px}} .periodic-metric strong{{font-size:1.15rem}} .periodic-bar-row{{grid-template-columns:100px minmax(0,1fr) 22px;font-size:.82rem}}}}
</style>
</head>
<body><main>
<header><p><a class="back" href="../index.html">← 返回首页</a></p><h1>{html.escape(data.get("title", f"文博行业{label}"))}</h1><p class="meta">{html.escape(data.get("date_range", ""))} · 基于本站已收录日报样本</p></header>
{preview_banner}
<section class="periodic-section"><h2>{period_word}一句话</h2><p>{html.escape(data.get("oneLiner", ""))}</p></section>
<section class="periodic-kpis">{metric_html}</section>
<section class="periodic-section"><h2>{period_word}最值得记住的{3 if dtype == 'weekly' else 5}件事</h2><div class="periodic-highlights">{highlight_html}</div></section>
<div class="periodic-grid"><section class="periodic-section"><h2>主题分布</h2>{topics_html or '<p class="muted">暂无数据</p>'}</section><section class="periodic-section"><h2>{period_word}节奏</h2><div class="periodic-day-wrap">{cadence_html or '<p class="muted">暂无数据</p>'}</div></section></div>
{rollup_html}
<section class="periodic-section"><h2>相比上一自然周期</h2>{comparison_html}</section>
{section_html}
<section class="periodic-section"><h2>{period_word}数字文博观察</h2><p class="section-lead">{html.escape(digital.get("note", ""))}</p>{digital_html}<p><a href="../command-center/index.html">进入数字驾驶舱 →</a></p></section>
{upcoming_html}
<section class="periodic-section"><h2>数据质量与适用范围</h2><ul>{quality_html}</ul></section>
{evidence_html}
<footer>本页面由周期报告组件生成。报告事实来自日报及其可回溯来源；编辑性归纳只表示本站样本内观察，不代表全国行业统计。</footer>
</main></body></html>'''


def load_periodic_data(root, data):
    """Load the companion model for a parsed digest, if one exists."""
    root = Path(root)
    directory = root / "content" / "报告"
    if data.get("type") == "weekly":
        path = directory / f"weekly-{data.get('ref_date', '')}.json"
    else:
        match = re.search(r"(\d{4})年(\d{1,2})月", data.get("date_range", ""))
        path = directory / f"monthly-{int(match.group(1)):04d}-{int(match.group(2)):02d}.json" if match else None
    if not path or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("layout") != "periodic-v2":
        return None
    editorial = load_editorial(root, payload.get("type"), payload.get("periodKey"), preview=payload.get("preview", False))
    return apply_editorial(payload, editorial) if editorial else payload

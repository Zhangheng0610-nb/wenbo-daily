#!/usr/bin/env python3
"""Portable, deterministic checks for the native Codex publishing workflow."""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'content'
REPORTS = ROOT / 'reports'

import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
from automation.governance import (
    MAP_SOURCE_PANEL, canonical_url, map_source_id, source_info,
)
from automation.validate_candidates import validate as validate_candidate_ledger
from build import parse_md

ALLOWED = (
    'chinawenbao.com.cn', 'zhongguowenwubao.com', 'chinamuseum.org.cn', 'chinamuseums.org.cn',
    'kaogu.cn', 'kaogu.cssn.cn', 'ncha.gov.cn', 'news.cn',
    'xinhuanet.com', 'cctv.com', 'people.com.cn', 'chinanews.com.cn',
    'gmw.cn', 'cnr.cn', 'china.org.cn', 'unesco.org', 'whc.unesco.org',
    'iccrom.org', 'icom.museum', 'apnews.com', 'reuters.com', 'bbc.com',
    'archaeology.org', 'theartnewspaper.com', 'thepaper.cn',
    'chinadaily.com.cn', 'cri.cn', 'dpm.org.cn', 'chnmus.net',
    'shanghaimuseum.net', 'capitalmuseum.org.cn', 'chnmuseum.cn', 'namoc.org',
)
BANNED = (
    'weixin.sogou.com/link', 'mp.weixin.qq.com', 'baijiahao.baidu.com',
    'sohu.com/a/', 'toutiao.com', '163.com', 'baike.baidu.com',
    'zhidao.baidu.com', 'zhihu.com/question', 'zhihu.com/topic',
)
URL_RE = re.compile(r'https?://[^\s)<>]+', re.I)
MONITORING = CONTENT / '监测'
DIGITAL_MONITORING = CONTENT / '数字趋势监测'
DIGITAL_MONITORING_START = date(2026, 8, 29)
FIXED_PANEL_OPERATIONAL_START = date(2026, 8, 29)
MONITOR_STATUSES = {'success', 'no_update', 'partial', 'failed'}
MONITOR_MODES = {'archive-backfill', 'operational'}
MONITOR_RUN_TYPES = {'live', 'replay'}
MONITOR_ORIGINS = {'legacy-daily-selection', 'archive-backfill', 'fixed-panel-monitoring'}
MONITOR_SCOPES = {'province', 'national', 'international', 'unassigned'}
CN_TZ = timezone(timedelta(hours=8))
CHECKED_AT_SKEW = timedelta(minutes=5)
PROVINCES = {
    '北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江',
    '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
    '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州',
    '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆', '台湾',
    '香港', '澳门',
}


def host_allowed(url):
    return source_info(url)['tier'] in ('A', 'B')


def _daily_html_metrics(path):
    """Read only deterministic structure markers from a generated report."""
    text = path.read_text(encoding='utf-8')
    card_ids = re.findall(r'<h3\s+id="(item\d+)"', text)
    toc_ids = re.findall(r'href="#(item\d+)"', text)
    meta = re.search(r'共\s+(\d+)\s+条（国内\s+(\d+)\s*\+\s*国际(?:/区域)?\s+(\d+)\s*）', text)
    ld_match = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', text, re.S)
    ld = {}
    if ld_match:
        try:
            ld = json.loads(ld_match.group(1))
        except json.JSONDecodeError:
            pass
    ld_count = re.search(r'共\s+(\d+)\s+条', str(ld.get('description', '')))
    return {
        'cards': card_ids,
        'toc': toc_ids,
        'meta': tuple(int(x) for x in meta.groups()) if meta else None,
        'ld_count': int(ld_count.group(1)) if ld_count else None,
    }


def check_daily_structure(path):
    """Check Markdown, parser output, and generated HTML agree on item shape."""
    errors = []
    text = path.read_text(encoding='utf-8')
    markdown_count = len(re.findall(r'^###\s+\d+\.\s+.+$', text, re.M))
    data = parse_md(path)
    items = data.get('ordered_items') or data['domestic'] + data['international']
    if markdown_count != len(items):
        errors.append(f'Markdown news headers {markdown_count} != parsed items {len(items)}')
    ids = [item.get('id') for item in items]
    if len(ids) != len(set(ids)):
        errors.append('daily item IDs must be unique')
    for item in items:
        if not item.get('sources'):
            errors.append(f'daily item {item.get("id", "?")} has no source')
        if re.search(r'^###\s+\d+\.\s+', item.get('body', ''), re.M):
            errors.append(f'daily item {item.get("id", "?")} body contains another news header')
    html_path = REPORTS / f'{data["date"]}.html'
    if not html_path.exists():
        errors.append(f'missing generated report HTML: {html_path.relative_to(ROOT)}')
        return errors
    metrics = _daily_html_metrics(html_path)
    if len(metrics['cards']) != len(items):
        errors.append(f'HTML news cards {len(metrics["cards"])} != parsed items {len(items)}')
    if len(metrics['toc']) != len(items):
        errors.append(f'HTML TOC items {len(metrics["toc"])} != parsed items {len(items)}')
    expected_ids = [item.get('id') for item in items]
    if metrics['toc'] != expected_ids:
        errors.append(f'HTML TOC order {metrics["toc"]} != parsed order {expected_ids}')
    if metrics['cards'] != expected_ids:
        errors.append(f'HTML body order {metrics["cards"]} != parsed order {expected_ids}')
    if len(metrics['cards']) != len(set(metrics['cards'])):
        errors.append('HTML news card IDs must be unique')
    if metrics['meta'] != (len(items), data['domestic_count'], data['international_count']):
        errors.append(
            f'HTML metadata count {metrics["meta"]} != parsed count '
            f'{(len(items), data["domestic_count"], data["international_count"])}'
        )
    if metrics['ld_count'] != len(items):
        errors.append(f'NewsArticle count {metrics["ld_count"]} != parsed items {len(items)}')
    return errors


def daily_structure_warnings(path):
    """Report suspicious cross-item source reuse without guessing semantics."""
    data = parse_md(path)
    by_url = {}
    items = data.get('ordered_items') or data['domestic'] + data['international']
    for item in items:
        for source in item.get('sources') or []:
            normalized = canonical_url(source.get('url', ''))
            by_url.setdefault(normalized, []).append(item.get('title', ''))
    return [
        f'source URL shared by distinct daily items: {url} ({" / ".join(titles)})'
        for url, titles in by_url.items()
        if url and len(set(titles)) > 1
    ]


def _provisional_evidence_urls_for_report(path):
    """Return article-level provisional evidence explicitly approved by its ledger."""
    try:
        report_date = date.fromisoformat(path.stem)
    except ValueError:
        return set()
    ledger_path = CONTENT / '候选' / f'{report_date}.json'
    try:
        payload = json.loads(ledger_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return set()
    urls = set()
    for candidate in payload.get('candidates') or []:
        for source in candidate.get('evidenceSources') or []:
            if source.get('tier') == 'provisional_B' and source.get('articleVerified'):
                urls.add(canonical_url(source.get('url', '')))
    return {url for url in urls if url}


def check_daily(path, strict=True):
    errors = []
    if not path.exists() or path.stat().st_size == 0:
        return [f'missing or empty: {path}']
    text = path.read_text(encoding='utf-8')
    urls = URL_RE.findall(text)
    provisional_urls = _provisional_evidence_urls_for_report(path)
    seen = set()
    for url in urls:
        info = source_info(url)
        if info['tier'] == 'C' and canonical_url(url) not in provisional_urls:
            message = f"{'unapproved source' if not info['blocked'] else 'banned source'}: {url}"
            if strict:
                errors.append(message)
        normalized = canonical_url(url)
        if normalized in seen and strict:
            errors.append(f'duplicate source URL in report: {normalized}')
        seen.add(normalized)
    if text.count('### ') and len(urls) < text.count('### '):
        errors.append('each news item must include at least one source link')
    errors.extend(check_daily_structure(path))
    return sorted(set(errors))


def today_cn():
    return datetime.now(timezone(timedelta(hours=8))).date()


def check_monitor_record(record, label):
    errors = []
    if not record.get('recordId'):
        errors.append(f'{label}: missing recordId')
    if not record.get('title'):
        errors.append(f'{label}: missing title')
    try:
        date.fromisoformat(record.get('date', ''))
    except (TypeError, ValueError):
        errors.append(f'{label}: invalid date')
    scope = record.get('scope')
    if scope not in MONITOR_SCOPES:
        errors.append(f'{label}: invalid scope {scope!r}')
    if scope == 'province' and record.get('primaryProvince') not in PROVINCES:
        errors.append(f'{label}: invalid or missing primaryProvince')
    if not isinstance(record.get('selectedForDaily'), bool):
        errors.append(f'{label}: selectedForDaily must be true or false')
    confidence = record.get('locationConfidence')
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append(f'{label}: invalid locationConfidence')
    sources = record.get('sources')
    if not isinstance(sources, list) or not sources:
        errors.append(f'{label}: missing fixed-panel source')
        return errors
    for source in sources:
        actual_id = map_source_id(source.get('url', ''))
        if not actual_id:
            errors.append(f'{label}: source outside fixed panel: {source.get("url", "")}')
        elif source.get('sourceId') != actual_id:
            errors.append(f'{label}: sourceId/domain mismatch: {source.get("sourceId", "")}')
    return errors


def check_monitoring(required_date=None):
    errors = []
    baseline_path = MONITORING / 'baseline.json'
    if not baseline_path.exists():
        return ['missing content/监测/baseline.json']
    files = [baseline_path] + sorted(MONITORING.glob('????-??-??.json'))
    if required_date:
        required = MONITORING / f'{required_date}.json'
        if not required.exists():
            errors.append(f'missing daily fixed-panel monitor: content/监测/{required_date}.json')
    seen_ids, seen_urls = set(), set()
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f'{path.relative_to(ROOT)}: invalid JSON: {exc}')
            continue
        if payload.get('version') != 1:
            errors.append(f'{path.relative_to(ROOT)}: version must be 1')
        records = payload.get('records') if path == baseline_path else payload.get('items')
        if not isinstance(records, list):
            errors.append(f'{path.relative_to(ROOT)}: records/items must be a list')
            records = []
        if path != baseline_path:
            file_date = path.stem
            if payload.get('date') != file_date:
                errors.append(f'{path.relative_to(ROOT)}: date must match filename')
            mode = payload.get('mode')
            if mode not in MONITOR_MODES:
                errors.append(f'{path.relative_to(ROOT)}: mode must be archive-backfill or operational')
            if mode == 'operational' and date.fromisoformat(file_date) >= FIXED_PANEL_OPERATIONAL_START:
                if payload.get('runType') not in MONITOR_RUN_TYPES:
                    errors.append(f'{path.relative_to(ROOT)}: operational runType must be live or replay')
            coverage = payload.get('coverage')
            if not isinstance(coverage, list):
                errors.append(f'{path.relative_to(ROOT)}: coverage must be a list')
                coverage = []
            ids = [row.get('sourceId') for row in coverage]
            if len(ids) != len(set(ids)):
                errors.append(f'{path.relative_to(ROOT)}: duplicate coverage sourceId')
            missing = sorted(set(MAP_SOURCE_PANEL) - set(ids))
            extra = sorted(set(ids) - set(MAP_SOURCE_PANEL))
            if missing:
                errors.append(f'{path.relative_to(ROOT)}: missing coverage sources: {", ".join(missing)}')
            if extra:
                errors.append(f'{path.relative_to(ROOT)}: unknown coverage sources: {", ".join(extra)}')
            for row in coverage:
                if row.get('mode') not in MONITOR_MODES:
                    errors.append(f'{path.relative_to(ROOT)}: invalid coverage mode for {row.get("sourceId", "?")}')
                elif mode in MONITOR_MODES and row.get('mode') != mode:
                    errors.append(f'{path.relative_to(ROOT)}: coverage mode mismatch for {row.get("sourceId", "?")}')
                if mode == 'operational' and row.get('runType') not in MONITOR_RUN_TYPES:
                    errors.append(f'{path.relative_to(ROOT)}: operational coverage needs runType for {row.get("sourceId", "?")}')
                elif mode == 'operational' and row.get('runType') != payload.get('runType'):
                    errors.append(f'{path.relative_to(ROOT)}: coverage runType mismatch for {row.get("sourceId", "?")}')
                if row.get('status') not in MONITOR_STATUSES:
                    errors.append(f'{path.relative_to(ROOT)}: invalid coverage status for {row.get("sourceId", "?")}')
                count = row.get('candidateCount')
                if not isinstance(count, int) or count < 0:
                    errors.append(f'{path.relative_to(ROOT)}: invalid candidateCount for {row.get("sourceId", "?")}')
                checked_at = row.get('checkedAt')
                if checked_at in (None, ''):
                    if row.get('checkedAtStatus') not in {'unknown', 'reconstructed'}:
                        errors.append(
                            f'{path.relative_to(ROOT)}: unknown checkedAt needs '
                            f'checkedAtStatus for {row.get("sourceId", "?")}'
                        )
                    if not row.get('checkedAtNote'):
                        errors.append(
                            f'{path.relative_to(ROOT)}: unknown checkedAt needs '
                            f'checkedAtNote for {row.get("sourceId", "?")}'
                        )
                else:
                    try:
                        checked_dt = datetime.fromisoformat(checked_at)
                        if checked_dt.tzinfo is None:
                            raise ValueError('timezone required')
                        checked_dt = checked_dt.astimezone(CN_TZ)
                        if mode == 'operational' and checked_dt > datetime.now(CN_TZ) + CHECKED_AT_SKEW:
                            errors.append(
                                f'{path.relative_to(ROOT)}: checkedAt is in the future '
                                f'for {row.get("sourceId", "?")}'
                            )
                        if mode == 'archive-backfill' and checked_dt.date().isoformat() != file_date:
                            errors.append(
                                f'{path.relative_to(ROOT)}: archive checkedAt date must '
                                f'match file date for {row.get("sourceId", "?")}'
                            )
                    except (TypeError, ValueError):
                        errors.append(f'{path.relative_to(ROOT)}: invalid checkedAt for {row.get("sourceId", "?")}')
                if row.get('status') in {'partial', 'failed'} and not row.get('note'):
                    errors.append(f'{path.relative_to(ROOT)}: partial/failed coverage needs a note for {row.get("sourceId", "?")}')
            observed = {source_id: 0 for source_id in MAP_SOURCE_PANEL}
            for record in records:
                record_source_ids = {
                    source.get('sourceId') for source in (record.get('sources') or [])
                }
                for source_id in record_source_ids:
                    if source_id in observed:
                        observed[source_id] += 1
            for row in coverage:
                source_id = row.get('sourceId')
                if source_id in observed and row.get('candidateCount') != observed[source_id]:
                    errors.append(f'{path.relative_to(ROOT)}: candidateCount mismatch for {source_id}')
            if mode == 'operational' and date.fromisoformat(file_date) >= FIXED_PANEL_OPERATIONAL_START:
                scan_audit = payload.get('scanAudit')
                if not isinstance(scan_audit, dict) or scan_audit.get('completed') is not True:
                    errors.append(
                        f'{path.relative_to(ROOT)}: operational monitoring needs a completed scanAudit'
                    )
                else:
                    if scan_audit.get('mode') != 'operational':
                        errors.append(f'{path.relative_to(ROOT)}: scanAudit mode must be operational')
                    if scan_audit.get('runType') != payload.get('runType'):
                        errors.append(f'{path.relative_to(ROOT)}: scanAudit runType mismatch')
                    source_audit = scan_audit.get('sources')
                    if not isinstance(source_audit, dict):
                        errors.append(f'{path.relative_to(ROOT)}: scanAudit sources must be an object')
                    else:
                        coverage_by_source = {row.get('sourceId'): row for row in coverage}
                        for source_id in MAP_SOURCE_PANEL:
                            audit_row = source_audit.get(source_id)
                            if not isinstance(audit_row, dict):
                                errors.append(f'{path.relative_to(ROOT)}: scanAudit missing {source_id}')
                                continue
                            accepted = audit_row.get('acceptedCount', 0)
                            if not isinstance(accepted, int) or accepted < 0:
                                errors.append(f'{path.relative_to(ROOT)}: invalid scanAudit acceptedCount for {source_id}')
                            if accepted > 0 and coverage_by_source.get(source_id, {}).get('candidateCount') == 0:
                                errors.append(
                                    f'{path.relative_to(ROOT)}: scanner found eligible {source_id} records '
                                    'but candidateCount/items are zero'
                                )
        for index, record in enumerate(records):
            label = f'{path.relative_to(ROOT)} record {index + 1}'
            origin = record.get('origin')
            if origin not in MONITOR_ORIGINS:
                errors.append(f'{label}: invalid origin {origin}')
            elif path == baseline_path and origin != 'legacy-daily-selection':
                errors.append(f'{label}: baseline origin must be legacy-daily-selection')
            elif path != baseline_path and payload.get('mode') in MONITOR_MODES:
                expected_origin = 'archive-backfill' if payload['mode'] == 'archive-backfill' else 'fixed-panel-monitoring'
                if origin != expected_origin:
                    errors.append(f'{label}: origin does not match mode {payload["mode"]}')
            errors.extend(check_monitor_record(record, label))
            record_id = record.get('recordId')
            if record_id in seen_ids:
                errors.append(f'{label}: duplicate recordId {record_id}')
            seen_ids.add(record_id)
            sources = record.get('sources') or []
            if sources:
                url = canonical_url(sources[0].get('url', ''))
                if url in seen_urls:
                    errors.append(f'{label}: duplicate monitored URL {url}')
                seen_urls.add(url)
    return sorted(set(errors))


def check_heatmap():
    """Validate the public industry-attention dataset and its source gate."""
    path = ROOT / 'heatmap-data.json'
    if not path.exists():
        return ['missing heatmap-data.json']
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return [f'invalid heatmap-data.json: {exc}']
    errors = []
    if data.get('version') != 3:
        errors.append('heatmap-data.json must use schema version 3')
    panel_ids = {row.get('id') for row in (data.get('coverage') or {}).get('panel', [])}
    if panel_ids != set(MAP_SOURCE_PANEL):
        errors.append('heatmap-data.json fixed source panel does not match governance')
    events = data.get('events')
    if not isinstance(events, list):
        return errors + ['heatmap-data.json events must be a list']
    seen = set()
    all_events = []
    for bucket in ('events', 'nationalEvents', 'internationalEvents'):
        rows = data.get(bucket, [])
        if not isinstance(rows, list):
            errors.append(f'heatmap-data.json {bucket} must be a list')
            continue
        all_events.extend(rows)
    for event in all_events:
        event_id = event.get('eventId', '')
        if not event_id or event_id in seen:
            errors.append(f'duplicate or missing heatmap event id: {event_id or "<empty>"}')
        seen.add(event_id)
        if event.get('sourceTier') not in ('A', 'B'):
            errors.append(f'non-qualified heatmap event: {event_id}')
        if event.get('scope') == 'province' and not event.get('primaryProvince'):
            errors.append(f'missing primary province: {event_id}')
        confidence = event.get('locationConfidence')
        if not isinstance(confidence, (int, float)) or not 0 < confidence <= 1:
            errors.append(f'invalid location confidence: {event_id}')
        for source in event.get('sources', []):
            info = source_info(source.get('url', ''))
            if info['blocked'] or info['tier'] not in ('A', 'B'):
                errors.append(f'blocked source leaked into heatmap event {event_id}: {source.get("url", "")}')
            if source.get('sourceId') != map_source_id(source.get('url', '')):
                errors.append(f'non-panel source leaked into heatmap event {event_id}: {source.get("url", "")}')
    return sorted(set(errors))


def check_candidate_ledger(required_date):
    """Make the daily candidate ledger a required editorial quality gate."""
    ledger_path = CONTENT / '候选' / f'{required_date}.json'
    report_path = CONTENT / '日报' / f'{required_date}.md'
    if not ledger_path.exists():
        return [f'missing daily candidate ledger: {ledger_path.relative_to(ROOT)}']
    return validate_candidate_ledger(ledger_path, report_path=report_path)


def check_digital_trend_monitor(required_date):
    """Require a truthful daily digital-trend scan record."""
    try:
        monitor_date = date.fromisoformat(required_date)
    except ValueError:
        return [f'digital-trend monitoring date is invalid: {required_date}']

    # Coverage files were introduced when formal daily monitoring began. Do
    # not fabricate historical records or fail older dates for their absence.
    if monitor_date < DIGITAL_MONITORING_START:
        return []

    path = DIGITAL_MONITORING / f'{required_date}.json'
    if not path.exists():
        return [f'missing daily digital-trend monitor: {path.relative_to(ROOT)}']
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return [f'{path.relative_to(ROOT)}: invalid JSON: {exc}']
    errors = []
    if payload.get('version') != 1:
        errors.append(f'{path.relative_to(ROOT)}: version must be 1')
    if payload.get('date') != required_date:
        errors.append(f'{path.relative_to(ROOT)}: date must match requested date')
    if payload.get('scanMode') != 'incremental':
        errors.append(f'{path.relative_to(ROOT)}: scanMode must be incremental')
    status = payload.get('status')
    allowed = {'scan_success_no_update', 'scan_success_with_update',
               'fetch_failed', 'parse_failed', 'not_run'}
    if status not in allowed:
        errors.append(f'{path.relative_to(ROOT)}: invalid status {status!r}')
    if status in {'fetch_failed', 'parse_failed', 'not_run'}:
        errors.append(f'{path.relative_to(ROOT)}: digital-trend scan did not complete ({status})')
    window = payload.get('scanWindow')
    if not isinstance(window, dict) or window.get('end') != required_date:
        errors.append(f'{path.relative_to(ROOT)}: scanWindow must end on requested date')
    for field in ('sourcePagesChecked', 'sourcePagesNew', 'contentItemsNew',
                  'duplicatesSkipped', 'fetchFailed', 'parseFailed'):
        value = payload.get(field)
        if not isinstance(value, int) or value < 0:
            errors.append(f'{path.relative_to(ROOT)}: invalid {field}')
    if status == 'scan_success_no_update' and (
            payload.get('sourcePagesNew', 0) or payload.get('contentItemsNew', 0)):
        errors.append(f'{path.relative_to(ROOT)}: no_update cannot contain new data')
    if status == 'scan_success_with_update' and not (
            payload.get('sourcePagesNew', 0) or payload.get('contentItemsNew', 0)):
        errors.append(f'{path.relative_to(ROOT)}: with_update must contain new data')
    checked_at = payload.get('checkedAt')
    try:
        checked_dt = datetime.fromisoformat(checked_at)
        if checked_dt.tzinfo is None:
            raise ValueError('timezone required')
        if checked_dt.astimezone(CN_TZ) > datetime.now(CN_TZ) + CHECKED_AT_SKEW:
            errors.append(f'{path.relative_to(ROOT)}: checkedAt is in the future')
    except (TypeError, ValueError):
        errors.append(f'{path.relative_to(ROOT)}: invalid checkedAt')
    return sorted(set(errors))


def check_weekly_evidence(required_date):
    """Ensure a weekly evidence index does not silently have no evidence."""
    path = REPORTS / f'weekly-{required_date}.html'
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8')
    match = re.search(r'<details class="digest-sources">.*?</details>', text, re.S)
    if not match:
        return []
    block = match.group(0)
    titles = re.findall(r'class="digest-evidence-title"', block)
    if not titles:
        return []
    rows = re.findall(r'<li>(.*?)</li>', block, re.S)
    if rows and len(rows) == len(titles) and all('<a ' not in row for row in rows):
        return [f'{path.relative_to(ROOT)}: all weekly highlights lack traceable evidence']
    return []


def _fixed_scope_url(source_id, url):
    """Return whether a URL is in the fixed panel's practical daily scope."""
    if not map_source_id(url) == source_id:
        return False
    if source_id == 'xinhua-wenbo':
        path = urlparse(url).path.lower()
        return path.startswith('/ci/') or path.startswith('/culture/')
    return True


def check_daily_monitor_reconciliation(required_date):
    """Warn only when a same-day fixed-panel URL has no monitor explanation."""
    ledger_path = CONTENT / '候选' / f'{required_date}.json'
    monitor_path = MONITORING / f'{required_date}.json'
    if not ledger_path.exists() or not monitor_path.exists():
        return []
    try:
        ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
        monitor = json.loads(monitor_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []
    monitored_urls = {
        canonical_url(source.get('url', ''))
        for record in monitor.get('items', [])
        for source in (record.get('sources') or [])
    }
    warnings = []
    for candidate in ledger.get('candidates', []):
        if candidate.get('publishedDate') != required_date:
            continue
        urls = [candidate.get('discoveryUrl', '')] + [
            source.get('url', '') for source in candidate.get('evidenceSources') or []
        ]
        for url in urls:
            source_id = map_source_id(url)
            if not source_id or not _fixed_scope_url(source_id, url):
                continue
            if canonical_url(url) not in monitored_urls:
                warnings.append(
                    f'{candidate.get("candidateId", "?")}: fixed-panel URL not found in '
                    f'{required_date} monitoring items ({source_id})'
                )
                break
    return warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='YYYY-MM-DD; defaults to Asia/Shanghai today')
    ap.add_argument('--all', action='store_true', help='audit all daily reports')
    ap.add_argument('--strict-all', action='store_true', help='treat legacy archive source gaps as failures')
    args = ap.parse_args()
    errors = []
    warnings = []
    for required in (CONTENT / '日报', CONTENT / '招聘', ROOT / 'build.py'):
        if not required.exists():
            errors.append(f'missing required path: {required.relative_to(ROOT)}')
    if args.all:
        paths = sorted((CONTENT / '日报').glob('????-??-??.md'))
    else:
        d = date.fromisoformat(args.date) if args.date else today_cn()
        paths = [CONTENT / '日报' / f'{d.isoformat()}.md']
        html_path = REPORTS / f'{d.isoformat()}.html'
        if not html_path.exists():
            errors.append(f'missing report HTML: {html_path.relative_to(ROOT)}')
    for path in paths:
        errors.extend(f'{path.relative_to(ROOT)}: {e}' for e in check_daily(path, strict=(not args.all or args.strict_all)))
        warnings.extend(f'{path.relative_to(ROOT)}: WARNING: {e}' for e in daily_structure_warnings(path))
    errors.extend(check_monitoring(None if args.all else (args.date or today_cn().isoformat())))
    errors.extend(check_heatmap())
    if not args.all:
        required_date = args.date or today_cn().isoformat()
        errors.extend(
            f'content/候选/{required_date}.json: {e}'
            for e in check_candidate_ledger(required_date)
        )
        errors.extend(
            f'content/数字趋势监测/{required_date}.json: {e}'
            for e in check_digital_trend_monitor(required_date)
        )
        errors.extend(check_weekly_evidence(required_date))
        warnings.extend(
            f'content/候选/{required_date}.json: WARNING: {e}'
            for e in check_daily_monitor_reconciliation(required_date)
        )
    if errors:
        print('VALIDATION FAILED')
        print('\n'.join(sorted(set(errors))))
        return 1
    if warnings:
        print('VALIDATION WARNINGS')
        print('\n'.join(sorted(set(warnings))))
    print(f'VALIDATION OK: {len(paths)} daily report(s), source allowlist passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

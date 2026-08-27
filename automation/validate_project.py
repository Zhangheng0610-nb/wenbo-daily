#!/usr/bin/env python3
"""Portable, deterministic checks for the native Codex publishing workflow."""
import argparse
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
from automation.governance import canonical_url, source_info

ALLOWED = (
    'chinawenbao.com.cn', 'chinamuseum.org.cn', 'chinamuseums.org.cn',
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


def host_allowed(url):
    return source_info(url)['tier'] in ('A', 'B')


def check_daily(path, strict=True):
    errors = []
    if not path.exists() or path.stat().st_size == 0:
        return [f'missing or empty: {path}']
    text = path.read_text(encoding='utf-8')
    urls = URL_RE.findall(text)
    seen = set()
    for url in urls:
        info = source_info(url)
        if info['tier'] == 'C':
            message = f"{'unapproved source' if not info['blocked'] else 'banned source'}: {url}"
            if strict:
                errors.append(message)
        normalized = canonical_url(url)
        if normalized in seen and strict:
            errors.append(f'duplicate source URL in report: {normalized}')
        seen.add(normalized)
    if text.count('### ') and len(urls) < text.count('### '):
        errors.append('each news item must include at least one source link')
    return sorted(set(errors))


def today_cn():
    return datetime.now(timezone(timedelta(hours=8))).date()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='YYYY-MM-DD; defaults to Asia/Shanghai today')
    ap.add_argument('--all', action='store_true', help='audit all daily reports')
    ap.add_argument('--strict-all', action='store_true', help='treat legacy archive source gaps as failures')
    args = ap.parse_args()
    errors = []
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
    if errors:
        print('VALIDATION FAILED')
        print('\n'.join(sorted(set(errors))))
        return 1
    print(f'VALIDATION OK: {len(paths)} daily report(s), source allowlist passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

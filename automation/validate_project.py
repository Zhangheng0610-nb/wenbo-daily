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
    host = urlparse(url).netloc.lower().split(':', 1)[0].rstrip('.')
    return any(host == d or host.endswith('.' + d) for d in ALLOWED) or host.endswith('.museum') or host.endswith('.museum.cn')


def check_daily(path):
    errors = []
    if not path.exists() or path.stat().st_size == 0:
        return [f'missing or empty: {path}']
    text = path.read_text(encoding='utf-8')
    urls = URL_RE.findall(text)
    for url in urls:
        low = url.lower()
        if any(x in low for x in BANNED):
            errors.append(f'banned source: {url}')
        elif not host_allowed(url):
            errors.append(f'unapproved source: {urlparse(url).netloc}')
    return sorted(set(errors))


def today_cn():
    return datetime.now(timezone(timedelta(hours=8))).date()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='YYYY-MM-DD; defaults to Asia/Shanghai today')
    ap.add_argument('--all', action='store_true', help='audit all daily reports')
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
        errors.extend(f'{path.relative_to(ROOT)}: {e}' for e in check_daily(path))
    if errors:
        print('VALIDATION FAILED')
        print('\n'.join(sorted(set(errors))))
        return 1
    print(f'VALIDATION OK: {len(paths)} daily report(s), source allowlist passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

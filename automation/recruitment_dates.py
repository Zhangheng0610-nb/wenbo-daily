"""Conservative application windows; never infer an unknown overseas timezone."""
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CN_TZ = timezone(timedelta(hours=8))
DATE = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')


def deadline_datetime(text, *, opening=False):
    text = text or ''
    # Parentheses usually describe payment, qualifications or examinations.
    primary = re.split(r'[（(]', text, maxsplit=1)[0]
    matches = list(DATE.finditer(primary))
    if not matches or re.search(r'发布|实习期|入职', primary):
        return None
    if opening and (len(matches) < 2 or not re.search(r'至|到|~|～', primary)):
        return None
    match = matches[0] if opening else matches[-1]
    tail = primary[match.end():]
    clock = re.match(r'\s*(\d{1,2}):([0-5]\d)', tail)
    h, m, s = (int(clock[1]), int(clock[2]), 0) if clock else ((0, 0, 0) if opening else (23, 59, 59))
    zone = CN_TZ
    if '英国时间' in text:
        try:
            zone = ZoneInfo('Europe/London')
        except ZoneInfoNotFoundError:
            return None
    elif re.search(r'当地时间|美国时间|欧洲时间|EST|EDT|PST|PDT', text, re.I):
        return None
    try:
        return datetime(*(int(v) for v in match.groups()), h, m, s, tzinfo=zone)
    except ValueError:
        return None


def application_status(text, now):
    end = deadline_datetime(text)
    start = deadline_datetime(text, opening=True)
    if end is None:
        return 'check', None, None
    if now >= end:
        return 'closed', start, end
    if start and now < start:
        return 'upcoming', start, end
    return 'open', start, end

"""Shared editorial governance rules for the Wenbo Daily site.

The public site is static, but its quality rules must be executable.  This
module is deliberately dependency-free so it works on Windows and macOS.
"""

import json
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]


SOURCE_GROUPS = OrderedDict([
    ("A", {
        "label": "A级｜一手/官方",
        "description": "政府主管部门、官方机构、博物馆、考古机构和国际专业组织的一手信息。",
        "domains": (
            "ncha.gov.cn", "chinawenbao.com.cn", "zhongguowenwubao.com",
            "ccrnews.com.cn", "chinamuseum.org.cn",
            "chinamuseums.org.cn", "kaogu.cn", "kaogu.cssn.cn",
            "news.cn", "xinhuanet.com", "xinhuanet.com.cn", "cctv.com",
            "people.com.cn", "people.cn", "chinanews.com.cn", "chinanews.com",
            "gmw.cn", "cnr.cn", "cctv.cn", "mrdx.cn", "workercn.cn",
            "china.org.cn", "dpm.org.cn", "chnmus.net", "chnmuseum.cn",
            "shanghaimuseum.net", "capitalmuseum.org.cn", "namoc.org",
            "cssn.cn", "xinhua.org", "sxhm.com", "sdmuseum.com",
            # Official institutional sites that appear in the recruitment and
            # internship boards. They are primary sources even without a
            # .gov.cn/.edu.cn suffix.
            "mplus.org.hk", "hbww.org.cn", "hnmuseum.com", "hylmuseum.cn",
            "aec1971.org.cn", "bjast.ac.cn", "brightonmuseums.org.uk",
            "unesco.org", "whc.unesco.org", "iccrom.org", "icom.museum",
            # Official government / police domains used by international
            # heritage reporting.  They remain article-level evidence, not
            # blanket approval of every page on the host.
            "polizei.gv.at",
        ),
    }),
    ("B", {
        "label": "B级｜专业补充",
        "description": "高质量新闻机构、专业刊物和研究机构；应尽量与A级来源交叉核验。",
        "domains": (
            "apnews.com", "reuters.com", "bbc.com", "rtve.es", "efe.com", "archaeology.org",
            "theartnewspaper.com", "thepaper.cn", "chinadaily.com.cn",
            "cri.cn", "nationalgeographic.com", "artnews.com", "ap.org",
            "nature.com", "shobserver.cn", "nfnews.com", "bjnews.com.cn",
            "zjol.com.cn", "dayoo.com", "cqcb.com", "caixin.com",
            "globaltimes.cn", "cnn.com", "bbc.co.uk",
            # Recognized mainstream media domains added to avoid false C-level
            # classification during broad daily discovery; they remain B-level
            # supplementary evidence and should be cross-checked when material.
            "asahi.com", "bjd.com.cn", "nmgnews.com.cn",
            "henandaily.cn", "yzwb.net", "enorth.com.cn", "orf.at",
            "aa.com.tr",
        ),
    }),
    ("C", {
        "label": "C级｜仅作线索",
        "description": "聚合、转载、社交平台和未登记来源，不得作为最终发布依据。",
        "domains": (),
    }),
])


# A WeChat article URL does not prove who operates the account.  Accounts are
# therefore opt-in: add a stable __biz value only after recording the account
# identity, institution type, official-site backlink, and original-publishing
# evidence.  Only explicitly registered accounts can leave the unknown-account
# state; all other accounts remain blocked as final evidence.  Keep the
# registry outside Python so each account is an auditable data change.
OFFICIAL_WECHAT_REGISTRY_PATH = ROOT / "content" / "候选" / "official-wechat-registry.json"
WECHAT_SOURCE_TIERS = frozenset({"A", "B", "discovery_only"})


def _load_official_wechat_accounts():
    try:
        payload = json.loads(OFFICIAL_WECHAT_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        return {}
    return {
        account.get("biz"): account
        for account in accounts
        if isinstance(account, dict) and account.get("biz")
    }


OFFICIAL_WECHAT_ACCOUNTS = _load_official_wechat_accounts()


def _valid_http_url(value):
    try:
        parts = urlsplit(value or "")
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def validate_official_wechat_registry(path=None):
    """Validate the opt-in WeChat account registry without trusting nicknames."""
    path = path or OFFICIAL_WECHAT_REGISTRY_PATH
    errors = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid official WeChat registry: {exc}"]
    if not isinstance(payload, dict) or payload.get("schema") != "official-wechat-registry-v2":
        errors.append("official WeChat registry schema must be official-wechat-registry-v2")
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        return errors + ["official WeChat registry accounts must be a list"]
    seen = set()
    required_text = (
        "biz", "accountName", "institution", "institutionType",
        "verifiedEvidence", "officialSite", "verifiedAt",
    )
    for index, account in enumerate(accounts, 1):
        label = f"official WeChat account {index}"
        if not isinstance(account, dict):
            errors.append(f"{label}: must be an object")
            continue
        missing = [key for key in required_text if not isinstance(account.get(key), str) or not account[key].strip()]
        if missing:
            errors.append(f"{label}: missing fields: {', '.join(missing)}")
        biz = account.get("biz")
        if biz in seen:
            errors.append(f"{label}: duplicate biz {biz}")
        if biz:
            seen.add(biz)
        if account.get("sourceTier") not in WECHAT_SOURCE_TIERS:
            errors.append(f"{label}: sourceTier must be A, B, or discovery_only")
        if not _valid_http_url(account.get("verifiedEvidence")):
            errors.append(f"{label}: verifiedEvidence must be an HTTP(S) URL")
        if not _valid_http_url(account.get("officialSite")):
            errors.append(f"{label}: officialSite must be an HTTP(S) URL")
        if not isinstance(account.get("originalOnly"), bool):
            errors.append(f"{label}: originalOnly must be boolean")
    return errors


# Explainable institutional suffixes for reputable non-Chinese university and
# research-organization sites.  They are still evidence requiring ordinary
# article-level checks; this rule only avoids treating every foreign official
# university page as an unregistered C-level domain.
INSTITUTIONAL_EDU_SUFFIXES = (
    '.edu', '.ac.uk', '.edu.au', '.edu.hk', '.ac.jp', '.edu.sg',
    '.ac.nz', '.edu.ca',
)


# These are discovery layers, not extra map sources and not automatic A-level
# evidence.  The named industry radars are intentionally discovery-only.
DAILY_DISCOVERY_LAYERS = OrderedDict([
    ('central_professional', ('国家文物局', '中国文物报', '中国博物馆协会', '中国考古网')),
    ('local_authorities', ('各省级文物局', '各省级文旅厅文物频道', '重要城市文物主管部门')),
    ('institutions', ('国家级博物馆', '省级及重点一级博物馆', '重要考古院所', '文保研究机构')),
    ('industry_radars', ('文博圈', '博物馆圈', '博物馆头条')),
    ('international', ('UNESCO', 'World Heritage Centre', 'ICOM', 'ICCROM', 'ICOMOS', '重要博物馆与大学')),
])
RECRUITMENT_DISCOVERY_RADARS = ('文博人才', '博物馆官网', '考古院官网', '高校就业网', '人社部门', '正规招聘平台')


# The public regional map deliberately uses a much smaller, fixed panel than
# the general A/B publishing allowlist above.  This prevents a changing mix of
# local outlets and one-off search results from silently changing the meaning
# of the provincial index.  Each source is inspected every day even when none
# of its items is selected for the editorial digest.
MAP_SOURCE_PANEL = OrderedDict([
    ("ncha", {
        "name": "国家文物局",
        "role": "国家主管部门",
        "domains": ("ncha.gov.cn",),
        "entry_urls": (
            "https://www.ncha.gov.cn/",
            "https://www.ncha.gov.cn/col/col722/index.html",
        ),
    }),
    ("cultural-relics-news", {
        "name": "中国文物报",
        "role": "全国文博行业专业报",
        "domains": ("zhongguowenwubao.com",),
        "entry_urls": ("https://www.zhongguowenwubao.com/",),
    }),
    ("archaeology", {
        "name": "中国考古网",
        "role": "中国社会科学院考古研究所专业平台",
        "domains": ("kaogu.cssn.cn", "kaogu.cn"),
        "entry_urls": ("https://kaogu.cssn.cn/",),
    }),
    ("museum-association", {
        "name": "中国博物馆协会",
        "role": "全国博物馆行业组织",
        "domains": ("chinamuseum.org.cn",),
        "entry_urls": ("https://www.chinamuseum.org.cn/",),
    }),
    ("xinhua-wenbo", {
        "name": "新华网文博",
        "role": "中央重点新闻网站文博栏目",
        "domains": ("news.cn", "xinhuanet.com", "xinhuanet.com.cn"),
        "entry_urls": (
            "https://www.news.cn/ci/wb.html",
            "https://www.news.cn/culture/cysj/index.html",
        ),
    }),
    ("cctv-wenbo", {
        "name": "央视网文博与央视新闻",
        "role": "中央广播电视总台文博报道与新闻频道",
        "domains": ("cctv.com", "cctv.cn"),
        "entry_urls": (
            "https://style.cctv.com/special/wenbo/lxwm/index.shtml",
            "https://yangbo.cctv.cn/",
            "https://news.cctv.com/",
            "https://news.cctv.com/news/index.shtml",
            "https://news.cctv.com/special/index.shtml",
        ),
    }),
])


BLOCKED_HOSTS = (
    "weixin.sogou.com", "mp.weixin.qq.com", "baijiahao.baidu.com",
    "sohu.com", "toutiao.com", "163.com", "baike.baidu.com",
    "zhidao.baidu.com", "zhihu.com",
)


def _host(url):
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def host_matches(host, domain):
    return host == domain or host.endswith("." + domain)


def canonical_url(url):
    """Remove tracking parameters while preserving meaningful query values."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return url
    try:
        parts = urlsplit(url)
        ignored = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "originReferrer", "spm"}
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if k not in ignored]
        return urlunsplit((parts.scheme.lower(), (parts.netloc or "").lower(),
                           parts.path.rstrip("/") or "/", urlencode(query), ""))
    except ValueError:
        return url


def official_wechat_account(url):
    """Return a verified account record, or None for an unknown account."""
    if _host(url) != 'mp.weixin.qq.com':
        return None
    try:
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    except ValueError:
        return None
    account = OFFICIAL_WECHAT_ACCOUNTS.get(query.get('__biz', ''))
    if not account:
        return None
    required = ('accountName', 'institution', 'institutionType',
                'verifiedEvidence', 'officialSite', 'verifiedAt', 'sourceTier')
    if not all(isinstance(account.get(key), str) and account[key].strip() for key in required):
        return None
    if account.get('sourceTier') not in WECHAT_SOURCE_TIERS:
        return None
    if not isinstance(account.get('originalOnly'), bool):
        return None
    return account


def wechat_evidence_issues(source, selected=False):
    """Return article-level governance issues for a WeChat evidence record."""
    url = source.get('url', '') if isinstance(source, dict) else ''
    if _host(url) != 'mp.weixin.qq.com':
        return []
    account = official_wechat_account(url)
    if not account:
        return ['wechat_account_not_registered_or_registry_invalid']
    tier = account.get('sourceTier')
    if tier == 'discovery_only':
        return ['discovery_only_wechat_account_cannot_be_publishable_evidence']
    if tier not in {'A', 'B'}:
        return ['wechat_account_has_no_publishable_source_tier']
    if account.get('originalOnly') is not True:
        return ['wechat_account_is_not_approved_for_original_evidence']
    if selected and source.get('articleOriginal') is not True:
        return ['selected_wechat_evidence_requires_articleOriginal_true']
    return []


def source_info(url):
    """Return a stable, display-ready source classification."""
    host = _host(url)
    if not host:
        return {"tier": "C", "label": "C级｜无效链接", "host": "", "blocked": True}
    if host == 'mp.weixin.qq.com':
        account = official_wechat_account(url)
        if account and account.get('sourceTier') in {'A', 'B'} and account.get('originalOnly') is True:
            tier = account['sourceTier']
            label = "A级｜机构官方公众号" if tier == 'A' else "B级｜媒体官方公众号"
            return {"tier": tier, "sourceTier": tier, "label": label, "host": host,
                    "blocked": False, "wechatAccount": account}
        if account and account.get('sourceTier') == 'discovery_only':
            return {"tier": "C", "sourceTier": "discovery_only",
                    "label": "C级｜行业公众号，仅作发现线索", "host": host,
                    "blocked": True, "wechatAccount": account}
        if account:
            return {"tier": "C", "sourceTier": account.get('sourceTier'),
                    "label": "C级｜公众号原创关系未满足发布要求", "host": host,
                    "blocked": True, "wechatAccount": account}
        return {"tier": "C", "label": "C级｜未核验公众号", "host": host, "blocked": True}
    if any(host_matches(host, blocked) for blocked in BLOCKED_HOSTS):
        return {"tier": "C", "label": "C级｜禁止作为最终来源", "host": host, "blocked": True}
    # Chinese government and university domains are institution-controlled
    # primary sources.  Keeping this as a suffix rule avoids a brittle registry
    # of every provincial bureau, museum authority, and research university.
    if host.endswith(".gov.cn") or host == "gov.cn":
        return {"tier": "A", "label": "A级｜政府官方", "host": host, "blocked": False}
    if host.endswith(".edu.cn") or host == "edu.cn":
        return {"tier": "A", "label": "A级｜高校官方", "host": host, "blocked": False}
    if any(host.endswith(suffix) for suffix in INSTITUTIONAL_EDU_SUFFIXES):
        return {"tier": "A", "label": "A级｜海外高校/研究机构官方", "host": host, "blocked": False}
    for tier, spec in SOURCE_GROUPS.items():
        if any(host_matches(host, domain) for domain in spec["domains"]):
            return {"tier": tier, "label": spec["label"], "host": host, "blocked": False}
        if tier == "A" and (host.endswith(".museum") or host.endswith(".museum.cn")):
            return {"tier": "A", "label": "A级｜博物馆官方", "host": host, "blocked": False}
    return {"tier": "C", "label": "C级｜待登记来源", "host": host, "blocked": False}


# Recruitment is a practical service, not a news publishing tier. A valid
# job-board link can be useful even when it is not a newsroom or government
# domain, so the UI uses human-readable provenance labels instead of A/B/C.
RECRUITMENT_PLATFORM_DOMAINS = (
    "gaoxiaojob.com", "zhaopin.com", "zhipin.com", "liepin.com", "51job.com",
    "597.com", "offcn.com", "shiyebian.com", "zgsydw.com", "bianzhia.com",
    "wondercv.com", "fenbi.com", "ncss.cn", "quanzhi.com", "jrzp.com",
)
RECRUITMENT_EMPLOYMENT_DOMAINS = (
    "nbhr.org.cn", "career.zju.edu.cn", "culr.edu.cn",
)


def recruitment_source_info(url):
    """Return a plain-language provenance label for a job listing link."""
    host = _host(url)
    if not host:
        return {"label": "🔎 二手线索", "kind": "lead", "host": ""}
    if any(host_matches(host, domain) for domain in RECRUITMENT_EMPLOYMENT_DOMAINS):
        return {"label": "🎓 高校/就业平台", "kind": "employment", "host": host}
    if any(host_matches(host, domain) for domain in RECRUITMENT_PLATFORM_DOMAINS):
        return {"label": "💼 主流招聘平台", "kind": "platform", "host": host}
    info = source_info(url)
    if info["tier"] == "A":
        return {"label": "🏛️ 官方来源", "kind": "official", "host": host}
    return {"label": "🔎 二手线索", "kind": "lead", "host": host}


def map_source_id(url):
    """Return the fixed map-panel source id for a URL, or an empty string."""
    host = _host(url)
    if not host:
        return ""
    for source_id, spec in MAP_SOURCE_PANEL.items():
        if any(host_matches(host, domain) for domain in spec["domains"]):
            return source_id
    return ""


def map_source_registry_rows():
    """Return display-ready rows for the fixed attention-map source panel."""
    return [
        {
            "id": source_id,
            "name": spec["name"],
            "role": spec["role"],
            "domains": list(spec["domains"]),
            "entryUrls": list(spec["entry_urls"]),
        }
        for source_id, spec in MAP_SOURCE_PANEL.items()
    ]


def source_stats(reports):
    """Count source tiers and return a compact audit object."""
    stats = {"A": 0, "B": 0, "C": 0, "total": 0, "hosts": {}}
    for report in reports:
        for item in report.get("domestic", []) + report.get("international", []):
            for source in item.get("sources", []):
                info = source_info(source.get("url", ""))
                stats[info["tier"]] += 1
                stats["total"] += 1
                if info["host"]:
                    stats["hosts"][info["host"]] = stats["hosts"].get(info["host"], 0) + 1
    stats["legacy"] = stats["C"] > 0
    return stats


def source_link_html(source):
    """Render a source link with its governance badge."""
    info = source_info(source.get("url", ""))
    tier_class = "source-" + info["tier"].lower()
    warning = " title=\"历史内容：该来源尚未纳入本站白名单\"" if info["tier"] == "C" else ""
    account = info.get("wechatAccount")
    if account and info["tier"] in {"A", "B"}:
        display_name = f'{account["institution"]}官方公众号' if info["tier"] == "A" else f'{account["accountName"]}官方公众号'
    else:
        display_name = source.get("name", info["host"] or "原文")
    return (f'<span class="source-chip {tier_class}"{warning}>'
            f'<b>{info["tier"]}</b> '
            f'<a href="{source["url"]}" target="_blank" rel="noopener">'
            f'{display_name}</a></span>')


def source_registry_rows():
    rows = []
    for tier, spec in SOURCE_GROUPS.items():
        domains = list(spec["domains"])
        if tier == "A":
            domains += ["*.gov.cn", "*.edu.cn", "*.museum", "*.museum.cn"]
        rows.append({"tier": tier, "label": spec["label"],
                     "description": spec["description"], "domains": domains})
    return rows

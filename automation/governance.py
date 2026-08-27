"""Shared editorial governance rules for the Wenbo Daily site.

The public site is static, but its quality rules must be executable.  This
module is deliberately dependency-free so it works on Windows and macOS.
"""

from collections import OrderedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SOURCE_GROUPS = OrderedDict([
    ("A", {
        "label": "A级｜一手/官方",
        "description": "政府主管部门、官方机构、博物馆、考古机构和国际专业组织的一手信息。",
        "domains": (
            "ncha.gov.cn", "chinawenbao.com.cn", "chinamuseum.org.cn",
            "chinamuseums.org.cn", "kaogu.cn", "kaogu.cssn.cn",
            "news.cn", "xinhuanet.com", "xinhuanet.com.cn", "cctv.com",
            "people.com.cn", "chinanews.com.cn", "gmw.cn", "cnr.cn",
            "china.org.cn", "dpm.org.cn", "chnmus.net", "chnmuseum.cn",
            "shanghaimuseum.net", "capitalmuseum.org.cn", "namoc.org",
            "unesco.org", "whc.unesco.org", "iccrom.org", "icom.museum",
        ),
    }),
    ("B", {
        "label": "B级｜专业补充",
        "description": "高质量新闻机构、专业刊物和研究机构；应尽量与A级来源交叉核验。",
        "domains": (
            "apnews.com", "reuters.com", "bbc.com", "archaeology.org",
            "theartnewspaper.com", "thepaper.cn", "chinadaily.com.cn",
            "cri.cn", "nationalgeographic.com", "artnews.com",
        ),
    }),
    ("C", {
        "label": "C级｜仅作线索",
        "description": "聚合、转载、社交平台和未登记来源，不得作为最终发布依据。",
        "domains": (),
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


def source_info(url):
    """Return a stable, display-ready source classification."""
    host = _host(url)
    if not host:
        return {"tier": "C", "label": "C级｜无效链接", "host": "", "blocked": True}
    if any(host_matches(host, blocked) for blocked in BLOCKED_HOSTS):
        return {"tier": "C", "label": "C级｜禁止作为最终来源", "host": host, "blocked": True}
    for tier, spec in SOURCE_GROUPS.items():
        if any(host_matches(host, domain) for domain in spec["domains"]):
            return {"tier": tier, "label": spec["label"], "host": host, "blocked": False}
        if tier == "A" and (host.endswith(".museum") or host.endswith(".museum.cn")):
            return {"tier": "A", "label": "A级｜博物馆官方", "host": host, "blocked": False}
    return {"tier": "C", "label": "C级｜待登记来源", "host": host, "blocked": False}


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
    return (f'<span class="source-chip {tier_class}"{warning}>'
            f'<b>{info["tier"]}</b> '
            f'<a href="{source["url"]}" target="_blank" rel="noopener">'
            f'{source.get("name", info["host"] or "原文")}</a></span>')


def source_registry_rows():
    rows = []
    for tier, spec in SOURCE_GROUPS.items():
        domains = list(spec["domains"])
        if tier == "A":
            domains += ["*.museum", "*.museum.cn"]
        rows.append({"tier": tier, "label": spec["label"],
                     "description": spec["description"], "domains": domains})
    return rows

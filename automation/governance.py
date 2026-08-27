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
            "ncha.gov.cn", "chinawenbao.com.cn", "zhongguowenwubao.com",
            "ccrnews.com.cn", "chinamuseum.org.cn",
            "chinamuseums.org.cn", "kaogu.cn", "kaogu.cssn.cn",
            "news.cn", "xinhuanet.com", "xinhuanet.com.cn", "cctv.com",
            "people.com.cn", "people.cn", "chinanews.com.cn", "chinanews.com",
            "gmw.cn", "cnr.cn", "cctv.cn", "mrdx.cn", "workercn.cn",
            "china.org.cn", "dpm.org.cn", "chnmus.net", "chnmuseum.cn",
            "shanghaimuseum.net", "capitalmuseum.org.cn", "namoc.org",
            "cssn.cn", "xinhua.org", "sxhm.com", "sdmuseum.com",
            "unesco.org", "whc.unesco.org", "iccrom.org", "icom.museum",
        ),
    }),
    ("B", {
        "label": "B级｜专业补充",
        "description": "高质量新闻机构、专业刊物和研究机构；应尽量与A级来源交叉核验。",
        "domains": (
            "apnews.com", "reuters.com", "bbc.com", "archaeology.org",
            "theartnewspaper.com", "thepaper.cn", "chinadaily.com.cn",
            "cri.cn", "nationalgeographic.com", "artnews.com", "ap.org",
            "nature.com", "shobserver.cn", "nfnews.com", "bjnews.com.cn",
            "zjol.com.cn", "dayoo.com", "cqcb.com", "caixin.com",
            "globaltimes.cn", "cnn.com", "bbc.co.uk",
        ),
    }),
    ("C", {
        "label": "C级｜仅作线索",
        "description": "聚合、转载、社交平台和未登记来源，不得作为最终发布依据。",
        "domains": (),
    }),
])


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
        "entry_urls": ("https://www.news.cn/ci/wb.html",),
    }),
    ("cctv-wenbo", {
        "name": "央视网文博",
        "role": "中央广播电视总台文博报道",
        "domains": ("cctv.com", "cctv.cn"),
        "entry_urls": (
            "https://style.cctv.com/special/wenbo/lxwm/index.shtml",
            "https://yangbo.cctv.cn/",
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


def source_info(url):
    """Return a stable, display-ready source classification."""
    host = _host(url)
    if not host:
        return {"tier": "C", "label": "C级｜无效链接", "host": "", "blocked": True}
    if any(host_matches(host, blocked) for blocked in BLOCKED_HOSTS):
        return {"tier": "C", "label": "C级｜禁止作为最终来源", "host": host, "blocked": True}
    # Chinese government and university domains are institution-controlled
    # primary sources.  Keeping this as a suffix rule avoids a brittle registry
    # of every provincial bureau, museum authority, and research university.
    if host.endswith(".gov.cn") or host == "gov.cn":
        return {"tier": "A", "label": "A级｜政府官方", "host": host, "blocked": False}
    if host.endswith(".edu.cn") or host == "edu.cn":
        return {"tier": "A", "label": "A级｜高校官方", "host": host, "blocked": False}
    for tier, spec in SOURCE_GROUPS.items():
        if any(host_matches(host, domain) for domain in spec["domains"]):
            return {"tier": tier, "label": spec["label"], "host": host, "blocked": False}
        if tier == "A" and (host.endswith(".museum") or host.endswith(".museum.cn")):
            return {"tier": "A", "label": "A级｜博物馆官方", "host": host, "blocked": False}
    return {"tier": "C", "label": "C级｜待登记来源", "host": host, "blocked": False}


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
    return (f'<span class="source-chip {tier_class}"{warning}>'
            f'<b>{info["tier"]}</b> '
            f'<a href="{source["url"]}" target="_blank" rel="noopener">'
            f'{source.get("name", info["host"] or "原文")}</a></span>')


def source_registry_rows():
    rows = []
    for tier, spec in SOURCE_GROUPS.items():
        domains = list(spec["domains"])
        if tier == "A":
            domains += ["*.gov.cn", "*.edu.cn", "*.museum", "*.museum.cn"]
        rows.append({"tier": tier, "label": spec["label"],
                     "description": spec["description"], "domains": domains})
    return rows

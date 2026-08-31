#!/usr/bin/env python3
"""
Build HTML reports from Markdown files and rebuild index.html.
Handles daily reports (日报), weekly digests (周报), and monthly digests (月报).
Usage: python build.py
"""
import os, re, glob, json, sys, hashlib
from difflib import SequenceMatcher
from urllib.parse import quote
from datetime import date as _date, datetime, timedelta, timezone

from automation.governance import (
    MAP_SOURCE_PANEL, SOURCE_GROUPS, canonical_url, map_source_id,
    map_source_registry_rows, source_info, source_link_html,
    source_registry_rows, source_stats, recruitment_source_info,
)
from automation.theme_rules import classify_themes

CN_TZ = timezone(timedelta(hours=8))


def china_today():
    return datetime.now(CN_TZ).date()

if sys.stdout.encoding and sys.stdout.encoding.lower().replace('-', '') != 'utf8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass  # 控制台不支持 UTF-8 时保持默认,不阻断构建

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(SITE_DIR, 'reports')
# The repository is self-contained. Keep a legacy fallback so the older
# Windows/Claude checkout can still be built while the migration is staged.
PROJECT_DIR = os.path.join(SITE_DIR, 'content') if os.path.isdir(os.path.join(SITE_DIR, 'content')) else os.path.dirname(SITE_DIR)
MD_DIR = os.path.join(PROJECT_DIR, '日报')
JOBS_MD = os.path.join(PROJECT_DIR, '招聘', 'jobs.md')
INTERN_MD = os.path.join(PROJECT_DIR, '招聘', 'intern.md')
MONITOR_DIR = os.path.join(PROJECT_DIR, '监测')

WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

# ───────────────── 热点地图 · 省份归类词表 ─────────────────
# 严格规则:省份词只用"标准短名",单字简称(晋/湘/冀)一律不用(防人名地名撞字);
# "中国/全国/国家/国际"绝不在省份词表(FORBIDDEN 双保险),避免把全国性新闻误标到某省。
DECAY = 0.93          # 热力时间衰减系数(每天)

PROVINCES = ['北京','天津','河北','山西','内蒙古','辽宁','吉林','黑龙江','上海','江苏','浙江',
             '安徽','福建','江西','山东','河南','湖北','湖南','广东','广西','海南','重庆','四川',
             '贵州','云南','西藏','陕西','甘肃','青海','宁夏','新疆','台湾','香港','澳门']
FORBIDDEN = ('中国','全国','国家','国际','中外','内地','大陆')

# 城市→省词典:只收本语料中"无歧义"的地级市/文化名城(≥2字)。
# 多义词一律不收或长词限定:北海(与广西北海撞)→不收;"朝阳"只作辽宁朝阳市(北京朝阳区不收);
# 红山/龙山/花山/阿里/昭陵 跨省多义→不收。收词即写注释说明归因理由。
CITY2PROV = {
    # 河南
    '郑州':'河南','洛阳':'河南','安阳':'河南','开封':'河南','三门峡':'河南','南阳':'河南',
    # 陕西
    '西安':'陕西','咸阳':'陕西','宝鸡':'陕西','榆林':'陕西','延安':'陕西',
    # 四川
    '成都':'四川','广汉':'四川',            # 广汉=三星堆所在
    # 浙江
    '杭州':'浙江','衢州':'浙江','绍兴':'浙江','宁波':'浙江','湖州':'浙江','温州':'浙江','台州':'浙江',
    # 江苏
    '南京':'江苏','苏州':'江苏','无锡':'江苏','扬州':'江苏','常州':'江苏','镇江':'江苏',
    # 安徽
    '马鞍山':'安徽',   # 朱然墓所在
    # 湖北
    '武汉':'湖北','随州':'湖北','荆州':'湖北','宜昌':'湖北','襄阳':'湖北',
    # 湖南
    '长沙':'湖南','益阳':'湖南','株洲':'湖南','岳阳':'湖南',
    # 江西
    '南昌':'江西','景德镇':'江西','赣州':'江西','九江':'江西','鹰潭':'江西',
    # 山东
    '济南':'山东','青岛':'山东','曲阜':'山东','滕州':'山东','日照':'山东','菏泽':'山东','淄博':'山东',   # 淄博=陶瓷琉璃博物馆
    # 辽宁
    '沈阳':'辽宁','大连':'辽宁','朝阳':'辽宁',   # 辽宁朝阳市(牛河梁);北京朝阳区不通过此词命中
    # 山西
    '太原':'山西','大同':'山西','侯马':'山西','临汾':'山西',
    # 河北
    '石家庄':'河北','保定':'河北','正定':'河北','邯郸':'河北','承德':'河北',   # 避暑山庄所在
    # 黑龙江 / 吉林
    '哈尔滨':'黑龙江','长春':'吉林','集安':'吉林',   # 集安=高句丽
    # 甘肃
    '兰州':'甘肃','天水':'甘肃','敦煌':'甘肃','武威':'甘肃','张掖':'甘肃',
    # 宁夏 / 青海 / 西藏
    '银川':'宁夏','固原':'宁夏','西宁':'青海','拉萨':'西藏','日喀则':'西藏',
    # 新疆
    '乌鲁木齐':'新疆','喀什':'新疆','吐鲁番':'新疆','和田':'新疆',
    # 内蒙古
    '呼和浩特':'内蒙古','赤峰':'内蒙古','呼伦贝尔':'内蒙古','阿拉善':'内蒙古',
    # 云南 / 贵州 / 广西
    '昆明':'云南','大理':'云南','丽江':'云南','保山':'云南',
    '贵阳':'贵州','遵义':'贵州',
    '南宁':'广西','桂林':'广西','合浦':'广西',       # 合浦=海上丝路始发港
    # 广东 / 福建 / 海南
    '广州':'广东','深圳':'广东','佛山':'广东','东莞':'广东','汕头':'广东','惠州':'广东','韶关':'广东',   # 韶关=张九龄墓所在
    '福州':'福建','泉州':'福建','厦门':'福建','漳州':'福建',
    '海口':'海南','三亚':'海南',
}

# 遗址/博物馆→省词典:≥3字、无歧义,把"不带省名但指向明确的地点"归对省。
# 多义词限定长词:故宫不收(误伤香港故宫)→必须"故宫博物院";国博不收(歧义)→用全称。
SITE2PROV = {
    '殷墟':'河南','二里头':'河南','龙门石窟':'河南','巩义':'河南',
    '三星堆':'四川','金沙遗址':'四川','宝墩':'四川','蜀王':'四川',
    '良渚':'浙江','河姆渡':'浙江','上山遗址':'浙江','跨湖桥':'浙江',
    '莫高窟':'甘肃','麦积山':'甘肃','马家窑':'甘肃','悬泉置':'甘肃',
    '秦始皇陵':'陕西','兵马俑':'陕西','石峁':'陕西','半坡遗址':'陕西','法门寺':'陕西',
    '马王堆':'湖南','里耶':'湖南','城头山':'湖南',
    '海昏侯':'江西','紫金城':'江西','朱然墓':'安徽',   # 马鞍山朱然家族墓地
    '云冈石窟':'山西','晋南':'山西','晋北':'山西','晋中':'山西','平遥':'山西','陶寺':'山西','侯马盟书':'山西',
    '曾侯乙':'湖北','盘龙城':'湖北','石家河':'湖北','云梦':'湖北',
    '牛河梁':'辽宁','红山文化':'辽宁','张学良':'辽宁',
    '大足石刻':'重庆','合川':'重庆',
    '布达拉宫':'西藏','大昭寺':'西藏','罗布林卡':'西藏','唐竺古道':'西藏',
    '黑水城':'内蒙古','额济纳':'内蒙古','成吉思汗陵':'内蒙古','辽上京':'内蒙古',
    '大汶口':'山东','城子崖':'山东','孔庙':'山东',
    '中国国家博物馆':'北京','故宫博物院':'北京','首都博物馆':'北京','颐和园':'北京',
    '观复博物馆':'北京','避暑山庄':'河北',   # 观复=马未都北京馆;避暑山庄=承德(河北)
    # ⚠️ 圆明园 2026-08-21 从词表移除:语料中 5 条"圆明园"新闻全是圆明园文物在他省展览(浙博/深圳/福建),
    #    "圆明园"是文物来源地而非事件地;移除后由 杭州/深圳(标题)、浙江(标签)、浙江省博物馆/福建博物院(正文)归位。
    '陕西历史博物馆':'陕西','南京博物院':'江苏','南博':'江苏','河南博物院':'河南','湖北省博物馆':'湖北','浙江省博物馆':'浙江',
    '浙博':'浙江',   # 2026-08-21 加:浙江省博物馆简称(标题层)。修"太平年·天下同宁"大展标题含浙博、正文列出国博/陕历博/南博等出借方→误归北京+浙江双省。标题含"浙博"=主办馆在浙,标题层直接命中,正文出借方列表不再参与;事件地=浙江,出借方≠事件地。
    '上博':'上海','辽博':'辽宁','磁州窑址':'河北',
    '福建博物院':'福建',   # 2026-08-21 加:马首入闽首展地(正文强信号,早于全国性判定)
    '三星堆博物馆':'四川','殷墟博物馆':'河南','良渚博物院':'浙江',
    '故宫博物院香港':'香港',
}

# 全国性关键词:命中即判定为"全国性/行业/政策/科技"主题 → 不归任何省(用户确认不展示)
NATIONAL_KEYWORDS = ('全国','国家文物局','国家文物','中国考古','考古中国','中国文物','中国博物馆',
                     '行业','政策','法规','办法','条例','通知','立法','规划','白皮书','报告','会议',
                     '论坛','标准','数字化','数字','科技','AI','人工智能','大数据','发布','解读',
                     '研讨','纪要','统计','公布','启动','工程','系统','平台','联盟','协会','学会')

# 强政策词(2026-08-21 拆分):标题/标签命中即"全国性政策/通知/规划"→ 不归省,且优先于正文强信号。
# 与 NATIONAL_KEYWORDS(含 数字/科技/AI 等弱词)区分:弱词只拦"正文也无明确馆名的纯科技综述"，
# 不拦"故宫数字文物库""白鹤梁数字建档"这类明确地方事件(正文强信号已先归省)。
# 例:防汛通知/十五五规划/免预约政策/云鸮专项行动 即使正文点名某省机构,本质仍是全国性→不展示。
STRONG_POLICY = ('国家文物局','政策','法规','条例','办法','通知','立法','规划','白皮书','部署',
                 '专项行动','专项核查','印发','行业动态')
# 注意:'国家考古遗址公园'、'国家一级博物馆' 这类含"国家"的也会命中全国性——这是预期的(它们通常
# 是行业性消息,不指向具体事件省份)。若未来发现某条该归省却被全国化,加回该省标签即可。

# 对外交流:事件在境外(或涉外),不归国内任何省 → 归全国性-对外交流(用户确认国际不进地图)
OUTREACH_TAGS = ('对外交流','文物出海','文明互鉴','文明桥梁','国际交流','援外','出海','联展','出境展','国际合作')
OUTREACH_TITLE = ('中吉','中哈','中乌','中埃','中法','中英','中意','中美','中俄','中蒙',
                  '中缅','中柬','中越','中老','中泰','中朝','中尼','中巴','中埃塞','中非')

# ───────────────── 主题体系(2026-08-21 建立) ─────────────────
# 主题筛选器的标准:今后日报标签中的"主题词"统一按这 9 类打(未雨绸缪,未来做 地区×主题×时间 三维检索)。
# 省份摘要页(heatmap.html 点省)按此归一化统计"主要主题";建三维检索时前端/后端直接复用。
# 键 = 归一化大类名;值 = 该类的标准词 + 历史同义词(AI 历史标签自动归一化)。
# ⚠️ 地名/遗址名(浙江/三星堆/姑蔑)不是主题,标签里照旧单独打,供省份归类用(SITE2PROV/CITY2PROV)。
# 主题判定由 automation.theme_rules 统一维护。这里保留这段注释，提醒
# 生成日报和生成行业地图必须使用同一套保守口径，避免同一条新闻在两处
# 出现不同归类。

CSS = """<style>
  :root {
    --bg: #f5f0eb; --card: #fff; --text: #2c2416; --muted: #8b7355;
    --accent: #8b4513; --tag-bg: #f0e6d3; --border: #e0d5c1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1815; --card: #252320; --text: #e8e0d0; --muted: #9b8b7a;
      --accent: #d4a76a; --tag-bg: #2a2520; --border: #3a3530;
    }
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.85;
    padding: 16px; max-width: 720px; margin: 0 auto; font-size: 16px;
  }
  header {
    text-align: center; padding: 20px 0 16px;
    border-bottom: 2px solid var(--accent); margin-bottom: 20px;
  }
  header h1 { font-size: 1.3em; }
  header .meta { color: var(--muted); font-size: .88em; margin-top: 6px; }
  header a { color: var(--accent); }
  h2.section {
    font-size: 1.1em; color: var(--accent); margin: 28px 0 14px;
    padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }
  h3 { font-size: 1.02em; margin: 20px 0 8px; }
  p { margin: 8px 0; }
  a { color: var(--accent); word-break: break-all; }
  a:visited { color: var(--muted); }
  a:focus-visible, button:focus-visible, input:focus-visible, summary:focus-visible {
    outline: 3px solid var(--accent); outline-offset: 3px;
  }
  blockquote {
    border-left: 3px solid var(--accent); padding: 6px 14px;
    margin: 10px 0; background: var(--tag-bg); border-radius: 0 6px 6px 0;
    color: var(--muted); font-size: .95em;
  }
  .news-img {
    max-width: 100%; border-radius: 8px; margin: 4px 0;
    border: 1px solid var(--border);
  }
  .tag {
    display: inline-block; font-size: .72em; padding: 2px 8px;
    border-radius: 10px; margin-right: 4px; margin-bottom: 6px;
    font-weight: 600; letter-spacing: .02em;
	    background: var(--tag-bg); color: var(--muted);
  }
  .tag-考古 { background: #fce4d6; color: #a0522d; }
  .tag-博物馆 { background: #dbe9f5; color: #2c5f8a; }
  .tag-展览 { background: #e8dbf0; color: #6b3a8b; }
  .tag-文物追索 { background: #fde0dc; color: #b03a2e; }
  .tag-科技 { background: #ccfbf1; color: #0d6b5e; }
  .tag-文化遗产 { background: #d9f0d1; color: #3d6b2e; }
  .tag-国际 { background: #fef3c7; color: #8b6914; }
	  .tag-世界遗产 { background: #fde8c8; color: #92400e; }
	  .tag-政策 { background: #e2e8f0; color: #475569; }
	  .tag-数字化 { background: #dbeafe; color: #1e40af; }
	  .tag-文物保护 { background: #ffe4d6; color: #9a3412; }
	  .tag-文物修复 { background: #fce7f3; color: #9d174d; }
  a.tag { text-decoration: none; }
  @media (prefers-color-scheme: dark) {
    .tag-考古 { background: #3d2010; color: #e8a87c; }
    .tag-博物馆 { background: #1a2d3d; color: #7ab8e0; }
    .tag-展览 { background: #2a1a3d; color: #b88ada; }
    .tag-文物追索 { background: #3d1a16; color: #e8786e; }
    .tag-科技 { background: #0d332e; color: #5eeadb; }
    .tag-文化遗产 { background: #1a3316; color: #7cc46e; }
    .tag-国际 { background: #3d3010; color: #e8c84a; }
	    .tag-世界遗产 { background: #3d2808; color: #fbbf24; }
	    .tag-政策 { background: #1e293b; color: #94a3b8; }
	    .tag-数字化 { background: #1e3a5f; color: #93c5fd; }
	    .tag-文物保护 { background: #3d2010; color: #f97316; }
	    .tag-文物修复 { background: #3d1028; color: #f472b6; }
  }
  .toc {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 18px; margin: 0 0 20px;
  }
  .toc summary {
    font-size: 1em; color: var(--accent); cursor: pointer;
    padding: 4px 0; user-select: none;
  }
  .toc ol {
    margin: 10px 0 0 20px; font-size: .92em; line-height: 2;
  }
  .toc ol a {
    color: var(--text); text-decoration: none;
    border-bottom: 1px dotted var(--border);
  }
  .toc ol a:hover { color: var(--accent); }
  hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: .85em; }
  td, th { border: 1px solid var(--border); padding: 7px 10px; }
  strong { color: var(--accent); }
  .top10-table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: .88em; }
  .top10-table thead th {
    background: var(--accent); color: #fff; padding: 10px 12px;
    text-align: left; font-weight: 600; border: none;
  }
  .top10-table tbody td {
    padding: 10px 12px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .top10-table tbody tr:hover { background: var(--tag-bg); }
  .top10-table .rank {
    font-weight: 700; font-size: 1.15em; color: var(--accent);
    text-align: center; width: 36px;
  }
  .top10-table .news-title { font-weight: 600; }
  .top10-table .date {
    color: var(--muted); font-size: .82em; white-space: nowrap;
    width: 60px;
  }
  .top10-table .sig { color: var(--muted); font-size: .85em; line-height: 1.5; }
  footer {
    text-align: center; padding: 28px 0 16px;
    color: var(--muted); font-size: .78em;
    border-top: 1px solid var(--border); margin-top: 24px;
  }
  footer a { color: var(--accent); }
  #back-to-top {
    position: fixed; bottom: 24px; right: 24px; z-index: 999;
    width: 44px; height: 44px; border-radius: 50%;
    background: var(--accent); color: #fff; border: none;
    font-size: 1.3em; cursor: pointer; opacity: 0;
    transition: opacity .25s; display: flex;
    align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
  }
  #back-to-top.show { opacity: .85; }
  #back-to-top:hover { opacity: 1; }
  #reading-progress {
    position: fixed; top: 0; left: 0; height: 3px; z-index: 999;
    background: var(--accent); width: 0%; transition: width .1s;
  }
  .nav-prev-next {
    display: flex; justify-content: space-between; gap: 12px;
    margin: 20px 0; flex-wrap: wrap;
  }
  .nav-prev-next a {
    flex: 1; min-width: 120px; padding: 10px 14px;
    border: 1px solid var(--border); border-radius: 8px;
    text-decoration: none; color: var(--text);
    background: var(--card); font-size: .88em;
    transition: border-color .15s;
  }
  .nav-prev-next a:hover { border-color: var(--accent); }
  .nav-prev-next a.next { text-align: right; }
  .nav-prev-next a .nav-label { color: var(--muted); font-size: .8em; }
  .share-row { text-align: center; margin: 20px 0 8px; }
  #share-btn {
    background: var(--card); color: var(--accent);
    border: 1px solid var(--border); border-radius: 20px;
    padding: 8px 24px; font-size: .88em; cursor: pointer;
    font-family: inherit;
  }
  #share-btn:hover { border-color: var(--accent); }
  .share-tip { display: block; color: var(--muted); font-size: .75em; margin-top: 6px; opacity: .7; }
  .quality-banner {
    background: var(--card); border: 1px solid var(--border); border-left: 4px solid var(--accent);
    border-radius: 10px; padding: 12px 14px; margin: 14px 0 20px; font-size: .88em;
  }
  .quality-banner.legacy { border-left-color: #b45309; }
  .quality-banner strong { color: var(--text); }
  .quality-banner summary, .digest-sources summary {
    cursor: pointer; user-select: none; list-style: none;
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
  }
  .quality-banner summary::-webkit-details-marker, .digest-sources summary::-webkit-details-marker { display: none; }
  .quality-banner summary::after, .digest-sources summary::after {
    content: '＋'; color: var(--muted); font-size: 1.1em; flex: 0 0 auto;
  }
  .quality-banner[open] summary::after, .digest-sources[open] summary::after { content: '−'; }
  .source-summary { color: var(--muted); font-size: .9em; text-align: right; }
  .source-chip { display: inline-block; margin: 2px 5px 4px 0; padding: 2px 7px;
    border-radius: 10px; font-size: .76em; border: 1px solid var(--border); }
  .source-chip b { font-size: .82em; margin-right: 2px; }
  .source-chip a { text-decoration: none; word-break: normal; }
  .source-a { background: #e8f5e9; color: #216e39; }
  .source-b { background: #fff7ed; color: #9a3412; }
  .source-c { background: #fef2f2; color: #b91c1c; }
  @media (prefers-color-scheme: dark) {
    .source-a { background: #16351f; color: #86efac; }
    .source-b { background: #3b2516; color: #fdba74; }
    .source-c { background: #3f1d1d; color: #fca5a5; }
  }
  .source-note { color: var(--muted); font-size: .78em; margin-top: 4px; }
  .digest-sources { background: var(--tag-bg); border-radius: 10px; padding: 12px 14px; margin: 22px 0 18px; }
  .digest-sources summary { font-weight: 600; color: var(--accent); }
  .digest-sources summary + p { margin-top: 10px; }
  .digest-sources h3 { margin: 0 0 6px; font-size: .98em; }
  .digest-sources li { margin: 3px 0; font-size: .86em; }
  .digest-evidence-title { font-weight: 600; }
  .status-badge { display: inline-block; padding: 2px 7px; border-radius: 9px; font-size: .72em; font-weight: 600; }
  .status-open { color: #216e39; background: #e8f5e9; }
  .status-closed { color: #991b1b; background: #fee2e2; }
  .status-check { color: #92400e; background: #fef3c7; }
  @media (prefers-color-scheme: dark) {
    .status-open { color: #86efac; background: #16351f; }
    .status-closed { color: #fca5a5; background: #3f1d1d; }
    .status-check { color: #fcd34d; background: #3b2a12; }
  }
</style>"""


# ───────────────── 热点地图 · 省份归类 ─────────────────
# 逐级降置信:标题 > 标签 > 正文遗址 > 正文省份 > 全国性/对外交流。
# 低置信字段永不覆盖高置信字段的命中。所有归属构建时打印 WARN 供人工抽检。

def _scan(text, use_city=True, use_site=True):
    """返回 text 中出现的省份短名,按在文中的首次出现位置排序(去重)。"""
    occ = []
    # 省份短名直接匹配;FORBIDDEN 双保险(即使词表未来被改,全国性词也绝不落省)
    for p in PROVINCES:
        if p in FORBIDDEN:
            continue
        i = text.find(p)
        if i >= 0:
            occ.append((i, p))
    # 城市/遗址长词在后追加,不覆盖已有省份
    pool = []
    if use_city:
        pool += list(CITY2PROV.items())
    if use_site:
        pool += list(SITE2PROV.items())
    found = {p for _, p in occ}
    for kw, p in pool:
        i = text.find(kw)
        if i >= 0 and p not in found:
            occ.append((i, p))
            found.add(p)
    occ.sort()
    return [p for _, p in occ]


def _title_event_destination(title):
    """Prefer a host venue or explicit destination over an object's origin."""
    institution_aliases = {
        '国博': '北京', '上博': '上海', '南博': '江苏', '浙博': '浙江', '辽博': '辽宁',
        '故宫博物院': '北京', '首都博物馆': '北京', '陕西历史博物馆': '陕西',
        '河南博物院': '河南', '湖北省博物馆': '湖北', '浙江省博物馆': '浙江',
        '福建博物院': '福建', '山东博物馆': '山东',
    }
    prefix = title[:22]
    for name, province in institution_aliases.items():
        if name == '国博':
            if re.search(r'(?<![全中])国博', prefix):
                return province
        elif name in prefix:
            return province
    terms = [(p, p) for p in PROVINCES]
    terms += list(CITY2PROV.items())
    # A destination verb followed by a place is stronger than a subject's
    # place of origin: "马王堆帛画亮相上海" belongs primarily to Shanghai.
    verbs = ('亮相', '登陆', '落地', '巡展至', '巡展到', '赴', '入驻', '移师')
    hits = []
    for term, province in sorted(terms, key=lambda x: len(x[0]), reverse=True):
        for verb in verbs:
            match = re.search(re.escape(verb) + r'[^，。；：—]{0,8}' + re.escape(term), title)
            if match:
                hits.append((match.start(), province))
        match = re.search(re.escape(term) + r'[^，。；：—]{0,6}(?:开幕|开展|启幕|开放|举行)', title)
        if match:
            hits.append((match.start(), province))
    if hits:
        hits.sort()
        return hits[-1][1]
    return ''


def _is_outreach(item, title, tags):
    """事件在境外/涉外的对外交流 → 不归国内省。"""
    if any(t in (item.get('tags') or []) for t in OUTREACH_TAGS):
        return True
    if any(k in title for k in OUTREACH_TITLE):
        return True
    return False


def _is_national(title, tags):
    """全国性/行业/政策/科技主题 → 不归省。"""
    if any(k in title for k in NATIONAL_KEYWORDS):
        return True
    if any(t in (tags or []) for t in NATIONAL_KEYWORDS):
        return True
    return False


def attribute_item(item):
    """为单条新闻判定省份归属。

    返回 {'provinces': [短名...], 'tier': str}。
    tier: title/tags/site/body/national/outreach/unassigned
    """
    title = item['title']
    tags = item.get('tags') or []
    tags_txt = ' '.join(tags)
    body = item.get('body', '')

    # 1) 标题命中(最高置信,含城市/遗址)
    destination = _title_event_destination(title)
    th = _scan(title)
    if th or destination:
        if destination:
            th = [destination] + [p for p in th if p != destination]
        return {'provinces': th, 'tier': 'title'}

    # 2) 标签命中(AI 编辑写在标签里的省份,如"姑蔑·浙江")
    gh = _scan(tags_txt)
    if gh:
        return {'provinces': gh, 'tier': 'tags'}

    # 3) 对外交流:标题/标签无省、事件在境外 → 不归省(用户确认国际不进地图)
    if _is_outreach(item, title, tags):
        return {'provinces': [], 'tier': 'outreach'}

    # 4) 强政策词(标题/标签命中,如"国家文物局发布…通知""…规划印发")→ 不归省
    #    优先于正文强信号:政策通知即使正文点名某省机构,本质仍是全国性(用户确认政策不展示)
    if any(k in title for k in STRONG_POLICY) or any(t in (tags or []) for t in STRONG_POLICY):
        return {'provinces': [], 'tier': 'national'}

    # 5) 正文"强信号"遗址/馆名(≥3字无歧义,如"福建博物院""殷墟")→ 优先于弱科技词:
    #    正文点名明确遗址/馆 = 明确地方事件,即使标题/标签带"数字化"等词也不该归全国性
    #    (2026-08-21:解决"马首入闽"因标签含'数字化'被误判为全国性而不展示)
    sh_site = _scan(body, use_city=False, use_site=True)
    if sh_site:
        return {'provinces': sh_site[:2], 'tier': 'site'}

    # 6) 弱科技词(数字/科技/AI 等,此时正文无明确馆名 = 纯科技综述)→ 不归省
    if _is_national(title, tags):
        return {'provinces': [], 'tier': 'national'}

    # 7) 正文城市/省名信号(置信度低于遗址/馆名)
    sh = _scan(body)
    if sh:
        return {'provinces': sh[:2], 'tier': 'body'}

    return {'provinces': [], 'tier': 'unassigned'}


def theme_of(tags, title=''):
    """把日报/历史监测标签归一为统一的、保守的主题 facets。"""
    return classify_themes(title=title, tags=tags)


HEATMAP_VERSION = 3
LOCATION_CONFIDENCE = {
    'title': 0.96, 'tags': 0.90, 'site': 0.78, 'body': 0.58,
    'national': 0.85, 'outreach': 0.85, 'unassigned': 0.0,
}


def _source_grade(item):
    """Return executable source governance for a report item."""
    rows = []
    for source in item.get('sources') or []:
        info = source_info(source.get('url', ''))
        rows.append({
            'name': source.get('name') or info.get('host') or '原文',
            'url': canonical_url(source.get('url', '')),
            'host': info.get('host', ''),
            'tier': info.get('tier', 'C'),
            'blocked': bool(info.get('blocked')),
            'sourceId': source.get('sourceId') or map_source_id(source.get('url', '')),
        })
    tiers = {row['tier'] for row in rows}
    best = 'A' if 'A' in tiers else ('B' if 'B' in tiers else 'C')
    blocked = any(row['blocked'] for row in rows)
    return {
        'tier': best,
        'blocked': blocked,
        'eligible': bool(rows) and best in ('A', 'B') and not blocked,
        'sources': rows,
    }


def _impact_score(item):
    """Transparent editorial impact rubric, independent from title emoji."""
    text = ' '.join([item.get('title', ''), ' '.join(item.get('tags') or [])])
    score = 48
    if any(k in text for k in ('讲座', '报名', '征集', '招募', '预告', '文创上新', '打卡')):
        score = 34
    if any(k in text for k in ('展览', '特展', '开馆', '博物馆', '遗址公园')):
        score = max(score, 56)
    if any(k in text for k in ('数字化', '人工智能', 'AI', '保护工程', '修复', '科技保护')):
        score = max(score, 66)
    if any(k in text for k in ('考古发现', '新发现', '发掘', '遗址', '墓葬', '石窟')):
        score = max(score, 76)
    if any(k in text for k in ('返还', '追索', '被盗', '失窃', '损毁', '火灾', '盗掘', '文物安全')):
        score = max(score, 84)
    if any(k in text for k in ('国家文物局', '条例', '立法', '规划', '国家标准', '世界遗产名录',
                               '全国十大考古新发现', '重大考古发现', '一级文物')):
        score = max(score, 90)
    return min(score, 100)


def _impact_label(score):
    if score >= 88:
        return '重大'
    if score >= 74:
        return '重要'
    if score >= 58:
        return '关注'
    return '一般'


def _event_norm(title):
    text = re.sub(r'^[🔥\s]+', '', title or '').lower()
    for phrase in ('今日', '正式', '首次', '最新', '持续', '再度', '集中', '重磅', '即将',
                   '开幕', '开展', '亮相', '发布', '公布', '启动', '启幕', '落幕'):
        text = text.replace(phrase, '')
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', text)


def _trigrams(text):
    if len(text) < 3:
        return {text} if text else set()
    return {text[i:i + 3] for i in range(len(text) - 2)}


def _same_event(candidate, event):
    if candidate.get('primaryProvince', '') != event.get('primaryProvince', ''):
        return False
    cthemes = set(candidate.get('themes') or [])
    ethemes = set(event.get('themes') or [])
    if cthemes and ethemes and not cthemes.intersection(ethemes):
        return False
    cdate = _date.fromisoformat(candidate['date'])
    edate = _date.fromisoformat(event['lastDate'])
    if abs((cdate - edate).days) > 45:
        return False
    left, right = candidate['_norm'], event['_norm']
    if min(len(left), len(right)) >= 10 and (left in right or right in left):
        return True
    ratio = SequenceMatcher(None, left, right).ratio()
    if ratio >= 0.58:
        return True
    a, b = _trigrams(left), _trigrams(right)
    jaccard = len(a & b) / max(1, len(a | b))
    return jaccard >= 0.36


def _candidate(rdate, item, att, grade, scope='province'):
    provinces = att.get('provinces') or []
    display_title = re.sub(r'^[🔥\s]+', '', item.get('title', '')).strip()
    return {
        'date': rdate,
        'itemId': item.get('id', ''),
        'title': display_title,
        '_norm': _event_norm(display_title),
        'url': f"reports/{rdate}.html#{item.get('id', '')}",
        'primaryProvince': provinces[0] if provinces else '',
        'relatedProvinces': provinces[1:] if len(provinces) > 1 else [],
        'locationTier': att.get('tier', 'unassigned'),
        'locationConfidence': LOCATION_CONFIDENCE.get(att.get('tier'), 0.0),
        'themes': theme_of(item.get('tags', []), item.get('title', '')),
        'tags': item.get('tags', []),
        'impact': _impact_score(item),
        'sourceTier': grade['tier'],
        'sources': grade['sources'],
        'scope': scope,
    }


def _cluster_events(candidates):
    """Conservatively merge follow-up reports into independently scored events."""
    events = []
    for cand in sorted(candidates, key=lambda x: (x['date'], x['title'])):
        match = None
        for event in reversed(events):
            if _same_event(cand, event):
                match = event
                break
        report = {
            'date': cand['date'], 'title': cand['title'], 'url': cand['url'],
            'sourceTier': cand['sourceTier'],
            'sources': cand['sources'],
        }
        if match is None:
            events.append({
                '_norm': cand['_norm'], '_seed': cand['_norm'],
                'title': cand['title'], 'firstDate': cand['date'], 'lastDate': cand['date'],
                'primaryProvince': cand['primaryProvince'],
                'relatedProvinces': list(cand['relatedProvinces']),
                'locationTier': cand['locationTier'],
                'locationConfidence': cand['locationConfidence'],
                'themes': list(cand['themes']), 'tags': list(cand['tags']),
                'impact': cand['impact'], 'scope': cand['scope'],
                'reports': [report],
            })
            continue
        match['firstDate'] = min(match['firstDate'], cand['date'])
        match['lastDate'] = max(match['lastDate'], cand['date'])
        if cand['impact'] > match['impact'] or (cand['impact'] == match['impact'] and cand['date'] >= match['lastDate']):
            match['title'] = cand['title']
            match['_norm'] = cand['_norm']
        match['impact'] = max(match['impact'], cand['impact'])
        match['locationConfidence'] = max(match['locationConfidence'], cand['locationConfidence'])
        for province in cand['relatedProvinces']:
            if province != match['primaryProvince'] and province not in match['relatedProvinces']:
                match['relatedProvinces'].append(province)
        for theme in cand['themes']:
            if theme not in match['themes']:
                match['themes'].append(theme)
        for tag in cand['tags']:
            if tag not in match['tags']:
                match['tags'].append(tag)
        match['reports'].append(report)

    for event in events:
        source_map = {}
        for report in event['reports']:
            for source in report['sources']:
                key = source.get('host') or source.get('url')
                source_map[key] = source
        sources = list(source_map.values())
        tiers = {source['tier'] for source in sources}
        tier = 'A' if 'A' in tiers else ('B' if 'B' in tiers else 'C')
        source_count = len(source_map)
        event['eventId'] = 'evt-' + hashlib.sha1(
            (event['scope'] + '|' + event['primaryProvince'] + '|' + event['_seed']).encode('utf-8')
        ).hexdigest()[:10]
        event['sourceTier'] = tier
        event['sourceCount'] = source_count
        event['reportCount'] = len(event['reports'])
        event['evidence'] = 100 if tier == 'A' else 72
        event['breadth'] = min(100, 40 + max(0, source_count - 1) * 25)
        event['impactLabel'] = _impact_label(event['impact'])
        event['primaryTheme'] = event['themes'][0] if event['themes'] else '其他'
        event['sources'] = sources
        event['reports'].sort(key=lambda x: x['date'], reverse=True)
        del event['_norm']
        del event['_seed']
    events.sort(key=lambda x: (x['lastDate'], x['impact'], x['sourceCount']), reverse=True)
    return events


def load_monitoring_corpus():
    """Load the map corpus without consulting the editorial daily reports."""
    corpus = {
        'records': [], 'coverage': [], 'dailyFiles': [],
        'baseline': {'period': {'start': '', 'end': ''}, 'recordCount': 0,
                     'coverageComplete': False, 'note': ''},
    }
    baseline_path = os.path.join(MONITOR_DIR, 'baseline.json')
    if os.path.isfile(baseline_path):
        with open(baseline_path, encoding='utf-8') as f:
            baseline = json.load(f)
        records = baseline.get('records') or []
        for record in records:
            row = dict(record)
            row.setdefault('origin', 'legacy-daily-selection')
            corpus['records'].append(row)
        corpus['baseline'] = {
            'period': baseline.get('period') or {'start': '', 'end': ''},
            'recordCount': len(records),
            'coverageComplete': bool(baseline.get('coverageComplete')),
            'note': baseline.get('note', ''),
        }

    pattern = os.path.join(MONITOR_DIR, '????-??-??.json')
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding='utf-8') as f:
            daily = json.load(f)
        file_date = os.path.splitext(os.path.basename(path))[0]
        corpus['dailyFiles'].append(file_date)
        daily_mode = daily.get('mode') or daily.get('monitoringMode') or ''
        if daily_mode not in {'archive-backfill', 'operational'}:
            item_origins = {item.get('origin') for item in (daily.get('items') or [])}
            daily_mode = 'archive-backfill' if 'archive-backfill' in item_origins else 'unknown'
        for coverage in daily.get('coverage') or []:
            row = dict(coverage)
            row['date'] = daily.get('date') or file_date
            row.setdefault('mode', daily_mode)
            corpus['coverage'].append(row)
        for record in daily.get('items') or []:
            row = dict(record)
            row.setdefault('date', daily.get('date') or file_date)
            row.setdefault('origin', daily_mode if daily_mode in {
                'archive-backfill', 'fixed-panel-monitoring'
            } else 'fixed-panel-monitoring')
            corpus['records'].append(row)

    # Coverage is keyed by source and observation date.  Keep the newest
    # observation; if timestamps tie, prefer the more conservative status.
    coverage_status_rank = {'no_update': 1, 'success': 2, 'partial': 3, 'failed': 4}
    unique_coverage = {}
    for row in corpus['coverage']:
        key = (row.get('date', ''), row.get('sourceId', ''))
        old = unique_coverage.get(key)
        if old is None:
            unique_coverage[key] = row
            continue
        old_checked = old.get('checkedAt', '') or ''
        new_checked = row.get('checkedAt', '') or ''
        if new_checked > old_checked or (
            new_checked == old_checked and
            coverage_status_rank.get(row.get('status', ''), 0) >
            coverage_status_rank.get(old.get('status', ''), 0)
        ):
            unique_coverage[key] = row
    corpus['coverage'] = sorted(
        unique_coverage.values(),
        key=lambda row: (row.get('date', ''), row.get('sourceId', ''))
    )

    # A source URL is an immutable observation key.  If a manual correction
    # creates a duplicate, keep the newest copy rather than double-counting it.
    unique = {}
    for record in corpus['records']:
        sources = record.get('sources') or []
        key_url = canonical_url(sources[0].get('url', '')) if sources else ''
        key = key_url or record.get('recordId') or (
            record.get('date', '') + '|' + record.get('title', '')
        )
        unique[key] = record
    corpus['records'] = sorted(unique.values(), key=lambda row: (
        row.get('date', ''), row.get('title', '')
    ))
    corpus['baseline']['recordCount'] = sum(
        1 for row in corpus['records'] if row.get('origin') == 'legacy-daily-selection'
    )
    return corpus


def _monitor_candidate(record, grade):
    """Convert an independent monitoring record to the event-cluster schema."""
    display_title = re.sub(r'^[🔥\s]+', '', record.get('title', '')).strip()
    scope = record.get('scope', 'province')
    primary = record.get('primaryProvince', '') if scope == 'province' else ''
    # Recompute legacy monitoring themes so old broad tags cannot keep a
    # systematic false positive such as “古文字展”→“考古”.
    themes = theme_of(record.get('tags', []), record.get('title', ''))
    confidence = record.get('locationConfidence')
    location_tier = record.get('locationTier', 'unassigned')
    if not isinstance(confidence, (int, float)):
        confidence = LOCATION_CONFIDENCE.get(location_tier, 0.0)
    impact = record.get('impact')
    if not isinstance(impact, (int, float)):
        impact = _impact_score(record)
    sources = grade['sources']
    return {
        'date': record.get('date', ''),
        'itemId': record.get('recordId', ''),
        'title': display_title,
        '_norm': _event_norm(display_title),
        'url': sources[0]['url'] if sources else '',
        'primaryProvince': primary,
        'relatedProvinces': list(record.get('relatedProvinces') or []),
        'locationTier': location_tier,
        'locationConfidence': confidence,
        'themes': themes,
        'tags': list(record.get('tags') or []),
        'impact': min(max(float(impact), 0), 100),
        'sourceTier': grade['tier'],
        'sources': sources,
        'scope': scope,
    }


def build_heatmap_data(corpus):
    """Build the map exclusively from the fixed-panel monitoring corpus."""
    dates = sorted({r.get('date', '') for r in corpus['records'] if r.get('date')})
    coverage_dates = sorted({r.get('date', '') for r in corpus['coverage'] if r.get('date')})
    baseline_end = (corpus.get('baseline', {}).get('period') or {}).get('end', '')
    all_dates = sorted(set(dates + coverage_dates + ([baseline_end] if baseline_end else [])))
    as_of = all_dates[-1] if all_dates else ''
    audit = []
    provincial_candidates, national_candidates, international_candidates = [], [], []
    excluded_non_panel = unassigned = 0
    source_records = {source_id: 0 for source_id in MAP_SOURCE_PANEL}
    provenance_records = {
        'legacy-daily-selection': 0,
        'archive-backfill': 0,
        'fixed-panel-monitoring': 0,
    }
    other_provenance_records = {}
    analysis_provenance_records = {
        'archive-backfill': 0,
        'fixed-panel-monitoring': 0,
    }

    for record in corpus['records']:
        origin = record.get('origin', 'unknown')
        if origin in provenance_records:
            provenance_records[origin] += 1
        else:
            other_provenance_records[origin] = other_provenance_records.get(origin, 0) + 1
        # The legacy daily-selection corpus is retained for audit and evidence
        # provenance only. Its editorial selection bias must not affect map
        # scoring, event clustering, or regional comparisons.
        if origin == 'legacy-daily-selection':
            continue
        rdate = record.get('date', '')
        record_id = record.get('recordId', '')
        title = record.get('title', '')
        panel_sources = []
        for source in record.get('sources') or []:
            actual_id = map_source_id(source.get('url', ''))
            declared_id = source.get('sourceId') or actual_id
            if actual_id and declared_id == actual_id:
                row = dict(source)
                row['sourceId'] = actual_id
                panel_sources.append(row)
                source_records[actual_id] += 1
        grade = _source_grade({'sources': panel_sources})
        if not panel_sources or not grade['eligible']:
            excluded_non_panel += 1
            audit.append(('non-panel', rdate, record_id, title, '-', record.get('locationTier', 'unassigned')))
            continue
        if origin in analysis_provenance_records:
            analysis_provenance_records[origin] += 1
        scope = record.get('scope', 'province')
        candidate = _monitor_candidate(record, grade)
        if scope == 'province' and record.get('primaryProvince'):
            provincial_candidates.append(candidate)
            provinces = [record.get('primaryProvince')] + list(record.get('relatedProvinces') or [])
            audit.append(('included', rdate, record_id, title, '/'.join(provinces), candidate['locationTier']))
        elif scope == 'national':
            national_candidates.append(candidate)
            audit.append(('national', rdate, record_id, title, '-', candidate['locationTier']))
        elif scope == 'international':
            international_candidates.append(candidate)
            audit.append(('international', rdate, record_id, title, '-', candidate['locationTier']))
        else:
            unassigned += 1
            audit.append(('unassigned', rdate, record_id, title, '-', candidate['locationTier']))

    events = _cluster_events(provincial_candidates)
    national_events = _cluster_events(national_candidates)
    international_events = _cluster_events(international_candidates)
    good_statuses = {'success', 'no_update'}
    coverage_statuses = {'success': 0, 'no_update': 0, 'partial': 0, 'failed': 0}
    coverage_by_date = {}
    coverage_by_mode = {}
    for row in corpus['coverage']:
        status = row.get('status', '')
        if status in coverage_statuses:
            coverage_statuses[status] += 1
        coverage_by_date.setdefault(row.get('date', ''), {})[row.get('sourceId', '')] = status
        mode = row.get('mode', 'unknown')
        mode_stats = coverage_by_mode.setdefault(mode, {'checks': 0, 'good': 0, 'dates': set()})
        mode_stats['checks'] += 1
        mode_stats['dates'].add(row.get('date', ''))
        if status in good_statuses:
            mode_stats['good'] += 1
    complete_coverage_days = sum(
        1 for day in coverage_by_date.values()
        if all(day.get(source_id) in good_statuses for source_id in MAP_SOURCE_PANEL)
    )
    coverage_by_mode = {
        mode: {'checks': values['checks'], 'good': values['good'],
               'days': len({day for day in values['dates'] if day})}
        for mode, values in coverage_by_mode.items()
    }
    mode_dates = {}
    for row in corpus['coverage']:
        mode_dates.setdefault(row.get('mode', 'unknown'), set()).add(row.get('date', ''))
    mode_dates = {
        mode: sorted(day for day in dates if day)
        for mode, dates in mode_dates.items()
    }
    legacy_records = provenance_records['legacy-daily-selection']
    archive_records = provenance_records['archive-backfill']
    operational_records = provenance_records['fixed-panel-monitoring']
    operational_record_types = {'live': 0, 'replay': 0, 'unknown': 0}
    for record in corpus['records']:
        if record.get('origin') != 'fixed-panel-monitoring':
            continue
        run_type = record.get('runType') or 'unknown'
        operational_record_types[run_type] = operational_record_types.get(run_type, 0) + 1
    operational_coverage_by_run_type = {}
    for row in corpus['coverage']:
        if row.get('mode') != 'operational':
            continue
        run_type = row.get('runType') or 'unknown'
        bucket = operational_coverage_by_run_type.setdefault(run_type, {'checks': 0, 'good': 0, 'dates': set()})
        bucket['checks'] += 1
        bucket['dates'].add(row.get('date', ''))
        if row.get('status') in good_statuses:
            bucket['good'] += 1
    operational_coverage_by_run_type = {
        run_type: {'checks': value['checks'], 'good': value['good'], 'days': len({d for d in value['dates'] if d})}
        for run_type, value in operational_coverage_by_run_type.items()
    }
    stats = {
        'totalMonitoredRecords': len(corpus['records']),
        'includedProvincialRecords': len(provincial_candidates),
        'provincialEvents': len(events),
        'nationalEvents': len(national_events),
        'internationalEvents': len(international_events),
        'legacyBaselineRecords': legacy_records,
        'archiveBackfillRecords': archive_records,
        'fixedPanelMonitoringRecords': operational_records,
        'operationalRecords': operational_records,
        'operationalRecordTypes': operational_record_types,
        'provenanceRecords': provenance_records,
        'otherProvenanceRecords': other_provenance_records,
        'provenanceReconciled': sum(provenance_records.values()) + sum(other_provenance_records.values()) == len(corpus['records']),
        'analysisRecords': sum(analysis_provenance_records.values()),
        'analysisProvenanceRecords': analysis_provenance_records,
        'excludedNonPanel': excluded_non_panel,
        'unassigned': unassigned,
        'panelSourceCount': len(MAP_SOURCE_PANEL),
        'coverageDays': len(set(coverage_dates)),
        'completeCoverageDays': complete_coverage_days,
        'successfulSourceChecks': sum(1 for row in corpus['coverage'] if row.get('status') in good_statuses),
        'coverageStatuses': coverage_statuses,
        'coverageByMode': coverage_by_mode,
        'archiveBackfillCoverageChecks': coverage_by_mode.get('archive-backfill', {}).get('checks', 0),
        'operationalCoverageChecks': coverage_by_mode.get('operational', {}).get('checks', 0),
        'archiveBackfillCoverageDays': coverage_by_mode.get('archive-backfill', {}).get('days', 0),
        'operationalCoverageDays': coverage_by_mode.get('operational', {}).get('days', 0),
        'operationalCoverageByRunType': operational_coverage_by_run_type,
        'liveOperationalCoverageChecks': operational_coverage_by_run_type.get('live', {}).get('checks', 0),
        'liveOperationalCoverageDays': operational_coverage_by_run_type.get('live', {}).get('days', 0),
        'replayOperationalCoverageChecks': operational_coverage_by_run_type.get('replay', {}).get('checks', 0),
        'replayOperationalCoverageDays': operational_coverage_by_run_type.get('replay', {}).get('days', 0),
        'recordsBySource': source_records,
    }
    samples = [{
        'reason': kind, 'date': rdate, 'title': title, 'tier': tier,
    } for kind, rdate, _iid, title, _provs, tier in audit if kind != 'included'][:24]
    data = {
        'version': HEATMAP_VERSION,
        'generated': as_of,
        'asOf': as_of,
        'start': dates[0] if dates else '',
        'decay': DECAY,
        'methodology': {
            'name': '固定权威信源行业关注指数',
            'weights': {'impact': 35, 'evidence': 30, 'breadth': 20, 'recency': 15},
            'impactRubric': {
                '重大': '国家级政策、世界遗产、重大考古发现、一级文物和文物安全事件',
                '重要': '一般考古发现、文物返还追索、重要保护工程',
                '关注': '数字化、科技保护、重要展览和开馆等行业项目',
                '一般': '讲座、报名、征集、常规宣传和一般活动',
            },
            'sourceGate': '仅固定权威信源池原文进入指数；日报编辑选择不影响收录',
            'corpus': '每日先完整巡检固定信源，再从候选中精选日报',
            'geography': '主要发生地计分，关联地区仅展示，不重复分摊',
            'comparability': '按所选时间窗的信源日覆盖率判断是否适合地区横向比较',
        },
        'coverage': {
            'panel': map_source_registry_rows(),
            'checks': corpus['coverage'],
            'monitoringStart': coverage_dates[0] if coverage_dates else '',
            'archiveBackfillStart': (mode_dates.get('archive-backfill') or [''])[0],
            'operationalStart': (mode_dates.get('operational') or [''])[0],
            'baseline': corpus['baseline'],
        },
        'stats': stats,
        'events': events,
        'nationalEvents': national_events,
        'internationalEvents': international_events,
        'auditSamples': samples,
    }
    return data, audit


def _audit_print(audit):
    """Print quality-gate and attribution diagnostics for every build."""
    included = sum(1 for a in audit if a[0] == 'included')
    national = sum(1 for a in audit if a[0] == 'national')
    non_panel = sum(1 for a in audit if a[0] == 'non-panel')
    unassigned = sum(1 for a in audit if a[0] == 'unassigned')
    print(f'[HEATMAP V3] 纳入 {included} 条 | 全国性 {national} 条 | 非固定池隔离 {non_panel} 条 | 地理待核 {unassigned} 条')
    print('[HEATMAP V3] 抽检重点(低置信地域/多地区/被隔离):')
    shown = 0
    for kind, rdate, iid, title, provs, tier in audit:
        if kind in ('non-panel', 'unassigned') or tier in ('site', 'body') or '/' in provs:
            print(f'  [{kind}/{tier}] {rdate} #{iid} {title[:36]} → {provs}')
            shown += 1
            if shown >= 36:
                print('  ... 其余记录已写入 heatmap-data.json 审计摘要')
                break


def build_heatmap_html():
    """Generate the evidence-gated industry attention map."""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>文博行业关注地图 | 每日文博资讯</title>
<meta name="description" content="基于权威公开报道、独立事件与可解释指标生成的中国文博行业关注地图。">
<link rel="canonical" href="https://zhangheng666.top/heatmap.html">
<meta property="og:title" content="文博行业关注地图 | 每日文博资讯">
<meta property="og:description" content="从地区、事件、来源与趋势四个维度观察中国文博行业动态。">
<style>
  :root {
    --bg:#f4f1eb; --card:#fffdf9; --text:#28231d; --muted:#786f64;
    --border:#ded7ca; --accent:#8a4b27; --accent-soft:#f2e6da; --tag:#eee8de;
    --good:#2f6b4f; --warn:#a15c16; --bad:#a33b34; --shadow:0 12px 36px rgba(75,55,35,.08);
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#171513; --card:#23201d; --text:#eee8df; --muted:#aaa095; --border:#3a342e; --accent:#d5a06f; --accent-soft:#392a20; --tag:#302b26; --good:#86c7a6; --warn:#e3ac69; --bad:#ef928b; --shadow:none; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior:smooth; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); line-height:1.65; }
  button,select { font:inherit; }
  button:focus-visible,select:focus-visible,a:focus-visible { outline:3px solid var(--accent); outline-offset:3px; }
  a { color:var(--accent); }
  .wrap { max-width:1120px; margin:0 auto; padding:0 22px 54px; }
  header { padding:30px 0 20px; }
  .back { display:inline-block; margin-bottom:14px; color:var(--accent); text-decoration:none; font-size:.86em; }
  h1 { font-size:clamp(1.55rem,3vw,2.15rem); letter-spacing:-.02em; }
  .meta { margin-top:12px; color:var(--muted); font-size:.8em; }
  .method-strip { display:flex; flex-wrap:wrap; gap:8px 18px; margin:0 0 18px; padding:12px 15px; border:1px solid var(--border); border-radius:12px; background:var(--card); color:var(--muted); font-size:.78em; }
  .method-strip strong { color:var(--text); }
  .mobile-guide { display:none; }
  .toolbar { display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; margin-bottom:16px; }
  .win-tabs { display:flex; gap:7px; flex-wrap:wrap; }
  .win-tab { padding:7px 15px; border:1px solid var(--border); border-radius:999px; color:var(--text); background:var(--card); cursor:pointer; }
  .win-tab.active { color:#fff; border-color:var(--accent); background:var(--accent); }
  .theme-control { display:flex; align-items:center; gap:8px; color:var(--muted); font-size:.84em; }
  .theme-control select { max-width:170px; padding:7px 30px 7px 10px; border:1px solid var(--border); border-radius:9px; background:var(--card); color:var(--text); }
  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:16px; }
  .stat { padding:14px 15px; background:var(--card); border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); }
  .stat strong { display:block; font-size:1.45em; line-height:1.15; color:var(--accent); }
  .stat span { display:block; margin-top:5px; color:var(--muted); font-size:.76em; }
  .workspace { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(330px,.85fr); gap:16px; align-items:start; }
  .panel { background:var(--card); border:1px solid var(--border); border-radius:16px; box-shadow:var(--shadow); overflow:hidden; }
  .panel-head { display:flex; justify-content:space-between; align-items:baseline; gap:12px; padding:15px 17px 0; }
  .panel-head h2 { font-size:1em; }
  .panel-head span { color:var(--muted); font-size:.75em; }
  #map { width:100%; height:520px; }
  .map-note { padding:0 17px 15px; color:var(--muted); font-size:.74em; }
  .rank-scroll { max-height:500px; overflow:auto; padding:8px 10px 12px; }
  table { width:100%; border-collapse:collapse; font-size:.79em; }
  th { position:sticky; top:0; z-index:2; padding:8px 7px; color:var(--muted); background:var(--card); text-align:right; font-weight:500; border-bottom:1px solid var(--border); }
  th:nth-child(2) { text-align:left; }
  td { padding:9px 7px; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
  td:nth-child(2) { text-align:left; }
  .province-btn { border:0; background:none; color:var(--text); cursor:pointer; font-weight:650; }
  .province-btn:hover { color:var(--accent); }
  .rank { color:var(--muted); }
  .index { color:var(--accent); font-weight:750; }
  .trend-up { color:var(--good); } .trend-down { color:var(--bad); } .trend-flat { color:var(--muted); }
  .detail { display:none; margin-top:16px; padding:20px; background:var(--card); border:1px solid var(--border); border-radius:16px; box-shadow:var(--shadow); }
  .detail.show { display:block; }
  .detail-head { display:flex; align-items:flex-start; gap:12px; flex-wrap:wrap; }
  .detail-title { font-size:1.28em; }
  .detail-metrics { color:var(--muted); font-size:.82em; }
  .detail-close { margin-left:auto; border:1px solid var(--border); border-radius:8px; padding:5px 9px; color:var(--muted); background:transparent; cursor:pointer; }
  .event-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:14px; }
  .event { padding:14px; border:1px solid var(--border); border-radius:12px; background:color-mix(in srgb,var(--card) 88%,var(--tag)); }
  .event h3 { font-size:.92em; line-height:1.5; }
  .event h3 a { color:var(--text); text-decoration:none; }
  .event h3 a:hover { color:var(--accent); }
  .badges { display:flex; gap:5px; flex-wrap:wrap; margin:8px 0 6px; }
  .badge { display:inline-block; padding:2px 7px; border-radius:999px; background:var(--tag); color:var(--muted); font-size:.68em; }
  .badge.a { color:var(--good); } .badge.b { color:var(--warn); } .badge.impact { color:var(--accent); }
  .event-meta { color:var(--muted); font-size:.72em; }
  .source-row { margin-top:6px; color:var(--muted); font-size:.7em; }
  .source-row a { margin-right:7px; text-decoration:none; }
  .followups { margin-top:8px; color:var(--muted); font-size:.73em; }
  .followups summary { cursor:pointer; }
  .followups a { display:block; margin-top:5px; text-decoration:none; }
  .secondary-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
  details.box { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:14px 16px; }
  details.box > summary { cursor:pointer; font-weight:700; }
  .scope-list { margin-top:10px; }
  .scope-item { padding:9px 0; border-bottom:1px dashed var(--border); }
  .scope-item:last-child { border-bottom:0; }
  .scope-item a { color:var(--text); text-decoration:none; font-size:.86em; }
  .scope-item span { display:block; color:var(--muted); font-size:.7em; }
  .quality { margin-top:16px; padding:16px; border:1px solid var(--border); border-left:4px solid var(--good); border-radius:12px; background:var(--card); }
  .quality[data-state="partial"] { border-left-color:var(--warn); }
  .quality[data-state="insufficient"] { border-left-color:var(--bad); }
  .quality h2 { font-size:.95em; }
  .quality p { margin-top:6px; color:var(--muted); font-size:.78em; }
  .quality strong { color:var(--text); }
  .coverage-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:12px; }
  .coverage-cell { padding:10px; border:1px solid var(--border); border-radius:9px; background:var(--tag); }
  .coverage-cell strong { display:block; font-size:1.15em; }
  .coverage-cell span { color:var(--muted); font-size:.7em; }
  .panel-details { margin-top:10px; color:var(--muted); font-size:.76em; }
  .panel-details summary { cursor:pointer; color:var(--text); font-weight:650; }
  .panel-source { display:flex; justify-content:space-between; gap:10px; padding:7px 0; border-bottom:1px dashed var(--border); }
  .panel-source:last-child { border-bottom:0; }
  .panel-source small { color:var(--muted); }
  .formula { margin-top:10px; padding:10px 12px; border-radius:9px; background:var(--tag); color:var(--muted); font-size:.75em; }
  .err { padding:34px 18px; color:var(--muted); text-align:center; }
  footer { margin-top:24px; padding:22px 0; color:var(--muted); text-align:center; font-size:.75em; border-top:1px solid var(--border); }
  @media (max-width:850px) {
    .workspace { grid-template-columns:1fr; }
    .map-panel { order:1; } .rank-panel { order:2; }
    .rank-scroll { max-height:360px; }
    #map { height:430px; }
  }
  @media (max-width:620px) {
    .wrap { padding:0 14px 40px; }
    header { padding-top:20px; }
    header .meta,.method-strip,.stats { display:none; }
    .mobile-guide { display:block; margin:-2px 0 9px; padding:10px 13px; border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:10px; background:var(--card); font-size:.8em; }
    .mobile-guide strong { color:var(--text); }
    .mobile-guide p { color:var(--muted); line-height:1.5; }
    .mobile-guide p + p { margin-top:2px; }
    .event-list,.secondary-grid { grid-template-columns:1fr; }
    .coverage-grid { grid-template-columns:repeat(2,1fr); }
    .toolbar { align-items:flex-start; margin-bottom:9px; }
    .theme-control { width:100%; justify-content:space-between; }
    .theme-control select { flex:1; max-width:none; }
    #map { height:370px; }
    .map-note { display:none; }
    .rank-scroll { max-height:300px; }
    th:nth-child(5),td:nth-child(5) { display:none; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="back" href="./">← 返回首页</a>
    <h1>文博行业关注地图</h1>
    <p class="meta" id="meta">正在读取事件索引…</p>
  </header>
  <div class="method-strip">
    <span><strong>做法</strong> 先查全来源，再制作日报</span>
    <span><strong>来源</strong> 固定 6 个全国权威平台</span>
    <span><strong>地区</strong> 一件事只归到主要发生地</span>
    <span><strong>提醒</strong> 反映报道关注，不等同实际活动总量</span>
  </div>
  <section class="mobile-guide" aria-label="地图阅读提示">
    <p>颜色越深，表示权威来源近期关注更集中；点击省份查看事项。</p>
    <p id="mobile-guide-status">资料积累中，仅作线索参考。</p>
  </section>
  <div class="toolbar">
    <div class="win-tabs" aria-label="时间范围">
      <button class="win-tab" data-days="7">近7天</button>
      <button class="win-tab active" data-days="30">近30天</button>
      <button class="win-tab" data-days="90">近90天</button>
    </div>
    <label class="theme-control">主题
      <select id="theme"><option value="">全部主题</option></select>
    </label>
  </div>
  <section class="stats" aria-label="当前窗口概况">
    <div class="stat"><strong id="s-events">—</strong><span>本期重点事项</span></div>
    <div class="stat"><strong id="s-provinces">—</strong><span>涉及地区</span></div>
    <div class="stat"><strong id="s-a">—</strong><span>本期收录来源</span></div>
    <div class="stat"><strong id="s-reports">—</strong><span>收录信息</span></div>
  </section>
  <section class="workspace">
    <div class="panel map-panel">
      <div class="panel-head"><h2>地区关注度分布</h2><span>本页最高值为 100</span></div>
      <div id="map"><div class="err" id="map-fallback">地图加载中…</div></div>
      <p class="map-note">颜色越深，表示本页追踪的权威来源近期更集中地报道了该地区。无色不等于当地没有文博活动；资料积累不足时，不应用它判断各地真实活跃程度。</p>
    </div>
    <div class="panel rank-panel">
      <div class="panel-head"><h2>地区关注度排序</h2><span id="rank-note">正在核对资料完整度</span></div>
      <div class="rank-scroll">
        <table>
          <thead><tr><th>#</th><th>地区</th><th>关注度</th><th>事项</th><th>来源</th><th>趋势</th></tr></thead>
          <tbody id="ranking"></tbody>
        </table>
      </div>
    </div>
  </section>
  <section class="detail" id="detail" aria-live="polite">
    <div class="detail-head">
      <div><h2 class="detail-title" id="d-name"></h2><p class="detail-metrics" id="d-metrics"></p></div>
      <button class="detail-close" id="d-close" aria-label="关闭地区详情">关闭</button>
    </div>
    <div class="event-list" id="d-events"></div>
  </section>
  <section class="secondary-grid">
    <details class="box"><summary>全国性政策与对外合作 <span id="national-count"></span></summary><div class="scope-list" id="national-list"></div></details>
    <details class="box"><summary>国际文博观察 <span id="international-count"></span></summary><div class="scope-list" id="international-list"></div></details>
  </section>
  <section class="quality" id="quality" data-state="insufficient">
    <h2>本页数据说明</h2>
    <p id="coverage-status">正在核对本页资料是否足够用于地区比较…</p>
    <div class="coverage-grid">
      <div class="coverage-cell"><strong id="c-coverage">—</strong><span>本窗口检查完成度</span></div>
      <div class="coverage-cell"><strong id="c-days">—</strong><span>全部来源已检查</span></div>
      <div class="coverage-cell"><strong id="c-sources">—</strong><span>追踪的权威来源</span></div>
      <div class="coverage-cell"><strong id="c-window">—</strong><span>查看范围</span></div>
    </div>
    <details class="panel-details"><summary>查看我们每天检查哪些来源</summary><div id="panel-list"></div></details>
    <p id="quality-text">正在计算信源与地域质量…</p>
    <div class="formula"><strong>关注度如何计算：</strong>事情的重要程度占 35%，来源可靠程度占 30%，是否有不同来源印证占 20%，发布时间新近程度占 15%。同一件事的后续报道会合并计算；只收录本页列出的固定权威来源。</div>
    <div class="formula"><strong>重要性分档：</strong>重大＝国家级政策、世界遗产、重大考古、一级文物或文物安全；重要＝一般考古、文物返还追索或重要保护工程；关注＝数字化、科技保护、重要展览或开馆；一般＝讲座、报名、征集和常规活动。分档由标题与标签规则触发，可在<a href="sources.html">信源与方法</a>复核。</div>
  </section>
  <footer><a href="index.html">每日文博资讯</a> ｜ <a href="sources.html">信源与方法</a> ｜ 数据与算法均可追溯至原始报道</footer>
</div>
<script src="lib/wenbo-analysis.js"></script>
<script src="lib/echarts.min.js"></script>
<script>
var SHORT2GEO = {
  '北京':'北京市','天津':'天津市','河北':'河北省','山西':'山西省','内蒙古':'内蒙古自治区',
  '辽宁':'辽宁省','吉林':'吉林省','黑龙江':'黑龙江省','上海':'上海市','江苏':'江苏省',
  '浙江':'浙江省','安徽':'安徽省','福建':'福建省','江西':'江西省','山东':'山东省',
  '河南':'河南省','湖北':'湖北省','湖南':'湖南省','广东':'广东省','广西':'广西壮族自治区',
  '海南':'海南省','重庆':'重庆市','四川':'四川省','贵州':'贵州省','云南':'云南省',
  '西藏':'西藏自治区','陕西':'陕西省','甘肃':'甘肃省','青海':'青海省','宁夏':'宁夏回族自治区',
  '新疆':'新疆维吾尔自治区','台湾':'台湾省','香港':'香港特别行政区','澳门':'澳门特别行政区'
};
var GEO2SHORT = {};
for (var s in SHORT2GEO) GEO2SHORT[SHORT2GEO[s]] = s;
var RAW=null, VIEW=[], PREVIOUS=[], chart=null, MAP_READY=false, CUR_COVERAGE=null, PREVIOUS_COVERAGE=null;
var CUR_WINDOW={label:'近30天',days:30}, CUR_THEME='';
var AS_OF_UTC=0, AS_OF_STR='';
function parseUTC(s) {
  var a = s.split('-');
  return Date.UTC(+a[0], +a[1] - 1, +a[2]);
}
function isDark() { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
function palette() {
  var dark = isDark();
  return {
    colors: dark ? ['#342d27','#65503d','#9a6743','#ce7046','#ef8b63'] : ['#eee8df','#e5c5aa','#d79568','#bd633d','#884226'],
    empty: dark ? '#292622' : '#ebe7df', border: dark ? '#4a443e' : '#fffdf9',
    tooltipBg: dark ? '#22222a' : '#ffffff',
    tooltipText: dark ? '#eee' : '#333', label: dark ? '#c9c0b6' : '#5f554b'
  };
}
function eventScore(event) {
  return window.WenboAnalysis.eventScore(event, RAW.asOf, RAW.decay);
}
function eventInRange(event, days, previous) {
  return window.WenboAnalysis.eventInRange(event, RAW.asOf, days, previous);
}
function computeView(days, previous) {
  return window.WenboAnalysis.provinceRows(RAW.events||[], {
    asOf:RAW.asOf, decay:RAW.decay, days:days, previous:previous, theme:CUR_THEME
  });
}
function findProvince(name) {
  for (var i=0;i<VIEW.length;i++) if (VIEW[i].name===name) return VIEW[i];
  return null;
}
function badge(text, cls) {
  var span=document.createElement('span'); span.className='badge '+(cls||''); span.textContent=text; return span;
}
function eventCard(entry) {
  var event=entry.event, article=document.createElement('article'); article.className='event';
  var h=document.createElement('h3'), link=document.createElement('a'); link.href=event.reports[0].url; link.textContent=event.title;
  h.appendChild(link); article.appendChild(h);
  var badges=document.createElement('div'); badges.className='badges';
  badges.appendChild(badge('事项级别：'+event.impactLabel,'impact'));
  badges.appendChild(badge('来源已核对','a'));
  badges.appendChild(badge(event.primaryTheme));
  badges.appendChild(badge('指数 '+entry.score.toFixed(0)));
  article.appendChild(badges);
  var meta=document.createElement('p'); meta.className='event-meta';
  meta.textContent=event.lastDate+' · '+event.sourceCount+' 个不同来源 · 地点明确度 '+Math.round(event.locationConfidence*100)+'%'+(event.relatedProvinces.length?' · 关联 '+event.relatedProvinces.join('、'): '');
  article.appendChild(meta);
  var sourceRow=document.createElement('p'); sourceRow.className='source-row'; sourceRow.appendChild(document.createTextNode('来源：'));
  event.sources.slice(0,4).forEach(function(source){var a=document.createElement('a');a.href=source.url;a.target='_blank';a.rel='noopener';a.textContent=source.name+'（'+source.tier+'）';sourceRow.appendChild(a);});
  article.appendChild(sourceRow);
  if (event.reports.length>1) {
    var details=document.createElement('details'); details.className='followups';
    var summary=document.createElement('summary'); summary.textContent='查看 '+event.reports.length+' 条连续报道'; details.appendChild(summary);
    event.reports.forEach(function(report){ var a=document.createElement('a'); a.href=report.url; a.textContent=report.date+'｜'+report.title; details.appendChild(a); });
    article.appendChild(details);
  }
  return article;
}
function showDetail(name) {
  var row=findProvince(name), box=document.getElementById('detail');
  if(!row){box.classList.remove('show');return;}
  document.getElementById('d-name').textContent=row.name+'｜地区关注度 '+row.index.toFixed(0);
  document.getElementById('d-metrics').textContent=row.eventCount+' 件重点事项 · '+row.reportCount+' 条收录信息 · '+row.evidenceCount+' 条已核对来源 · 平均地点明确度 '+Math.round(row.confidence*100)+'%';
  var list=document.getElementById('d-events'); list.innerHTML=''; row.events.forEach(function(entry){list.appendChild(eventCard(entry));});
  box.classList.add('show'); box.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function trendFor(row) {
  var span=document.createElement('span');
  if(!CUR_COVERAGE||!CUR_COVERAGE.ready||!PREVIOUS_COVERAGE||!PREVIOUS_COVERAGE.ready){span.className='trend-flat';span.textContent='样本不足';return span;}
  var archiveDays=RAW.start?Math.floor((AS_OF_UTC-parseUTC(RAW.start))/86400000)+1:0;
  if(archiveDays<CUR_WINDOW.days*2){span.className='trend-flat';span.textContent='基线不足';return span;}
  var old=null; for(var i=0;i<PREVIOUS.length;i++) if(PREVIOUS[i].name===row.name) old=PREVIOUS[i];
  if(!old||old.raw===0){span.className='trend-up';span.textContent='新进入';return span;}
  var change=(row.raw-old.raw)/old.raw*100;
  span.className=Math.abs(change)<5?'trend-flat':(change>0?'trend-up':'trend-down');
  span.textContent=(change>0?'↑ ':change<0?'↓ ':'')+Math.abs(change).toFixed(0)+'%'; return span;
}
function renderRanking() {
  var body=document.getElementById('ranking'); body.innerHTML='';
  if(!VIEW.length){var tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=6;td.className='err';td.textContent='当前筛选下暂无合格地域事件。';tr.appendChild(td);body.appendChild(tr);return;}
  VIEW.forEach(function(row,i){
    var tr=document.createElement('tr');
    [String(i+1),'',row.index.toFixed(0),String(row.eventCount),String(row.evidenceCount),''].forEach(function(text,idx){var td=document.createElement('td');td.textContent=text;if(idx===0)td.className='rank';if(idx===2)td.className='index';tr.appendChild(td);});
    var btn=document.createElement('button');btn.className='province-btn';btn.textContent=row.name;btn.onclick=function(){showDetail(row.name);};tr.children[1].appendChild(btn);tr.children[5].appendChild(trendFor(row));body.appendChild(tr);
  });
}
var lastMapTapName='', lastMapTapAt=0;
function openProvinceNews(name) {
  var row=findProvince(name);
  if(!row||!row.events.length||!row.events[0].event.reports.length) return;
  var url=row.events[0].event.reports[0].url;
  if(url) window.location.href=url;
}
function handleMapTap(name) {
  if(!window.matchMedia || !window.matchMedia('(max-width:620px)').matches){showDetail(name);return;}
  var now=Date.now();
  if(lastMapTapName===name && now-lastMapTapAt<5000){lastMapTapName='';openProvinceNews(name);return;}
  lastMapTapName=name;lastMapTapAt=now;showDetail(name);
  var hint=document.getElementById('mobile-guide-status');
  if(hint) hint.textContent='已显示 '+name+' 的事项；再次点击打开最新原文。';
}
function renderMap() {
  if(!window.echarts||!MAP_READY){
    document.getElementById('map-fallback').textContent='地图组件暂时不可用，可使用地区排名查看全部数据。';
    return;
  }
  var p=palette(),el=document.getElementById('map');if(chart)chart.dispose();chart=echarts.init(el);
  var data=VIEW.map(function(row){return{name:SHORT2GEO[row.name]||row.name,value:+row.index.toFixed(1),events:row.eventCount,evidence:row.evidenceCount};});
  chart.setOption({
    tooltip:{trigger:'item',backgroundColor:p.tooltipBg,borderColor:p.border,textStyle:{color:p.tooltipText,fontSize:13},formatter:function(params){var row=findProvince(GEO2SHORT[params.name]||params.name);return row?'<b>'+row.name+'</b><br/>地区关注度：'+row.index.toFixed(0)+'<br/>重点事项：'+row.eventCount+'<br/>已核对来源：'+row.evidenceCount:'<b>'+params.name+'</b><br/>当前筛选下暂无收录信息';}},
    visualMap:{min:0,max:100,left:14,bottom:8,text:['高','低'],calculable:false,inRange:{color:p.colors},textStyle:{color:p.label}},
    series:[{type:'map',map:'china',roam:false,selectedMode:false,data:data,label:{show:false},itemStyle:{areaColor:p.empty,borderColor:p.border,borderWidth:.8},emphasis:{label:{show:true,color:p.tooltipText,fontWeight:700},itemStyle:{areaColor:p.colors[p.colors.length-1]}}}]
  });
  chart.off('click');chart.on('click',function(params){if(params&&params.name)handleMapTap(GEO2SHORT[params.name]||params.name);});
}
function renderStats() {
  var events=VIEW.reduce(function(n,x){return n+x.eventCount;},0),reports=VIEW.reduce(function(n,x){return n+x.reportCount;},0),sources={};
  VIEW.forEach(function(row){row.events.forEach(function(entry){(entry.event.sources||[]).forEach(function(source){if(source.sourceId)sources[source.sourceId]=true;});});});
  document.getElementById('s-events').textContent=events;document.getElementById('s-provinces').textContent=VIEW.length;document.getElementById('s-a').textContent=Object.keys(sources).length;document.getElementById('s-reports').textContent=reports;
}
function renderScope(events,id,countId) {
  var list=(events||[]).filter(function(e){return eventInRange(e,CUR_WINDOW.days,false)&&(CUR_THEME?(e.themes||[]).indexOf(CUR_THEME)!==-1:true);}).slice(0,12);
  document.getElementById(countId).textContent='（'+list.length+'）';var box=document.getElementById(id);box.innerHTML='';
  if(!list.length){box.textContent='当前筛选下暂无合格事件。';return;}
  list.forEach(function(event){var div=document.createElement('div');div.className='scope-item';var a=document.createElement('a');a.href=event.reports[0].url;a.textContent=event.title;var span=document.createElement('span');span.textContent=event.lastDate+' · '+event.sourceTier+'级证据 · '+event.primaryTheme;div.appendChild(a);div.appendChild(span);box.appendChild(div);});
}
function coverageForWindow(days, previous) {
  var coverage=window.WenboAnalysis.coverageForWindow(RAW.coverage, RAW.asOf, days, previous);
  coverage.sourceGood={};
  coverage.rows.forEach(function(row){coverage.sourceGood[row.id]=row.good;});
  coverage.ready=coverage.state==='ready';
  return coverage;
}
function renderCoverage() {
  CUR_COVERAGE=coverageForWindow(CUR_WINDOW.days,false);PREVIOUS_COVERAGE=coverageForWindow(CUR_WINDOW.days,true);var c=CUR_COVERAGE,quality=document.getElementById('quality');quality.setAttribute('data-state',c.state);
  document.getElementById('c-coverage').textContent=Math.round(c.rate*100)+'%';document.getElementById('c-days').textContent=c.completeDays+'/'+CUR_WINDOW.days;document.getElementById('c-sources').textContent=c.panel.length;document.getElementById('c-window').textContent=CUR_WINDOW.label;
  var status=document.getElementById('coverage-status');
  if(c.ready)status.innerHTML='<strong>资料已足够：</strong>当前范围内，可以比较这些权威来源对不同地区的相对关注；但它不等同于各地真实文博活动总量。';
  else if(c.successful)status.innerHTML='<strong>资料仍在积累：</strong>当前已完成 '+c.successful+'/'+c.planned+' 次来源检查。地图可供浏览，但暂不适合拿来比较不同地区。';
  else status.innerHTML='<strong>资料刚开始积累：</strong>从下一次自动更新起，网站会每天检查固定的权威来源。当前展示的是从旧日报整理出的历史资料，只供了解，不用于比较不同地区。';
  var mobileGuide=document.getElementById('mobile-guide-status');
  if(c.ready)mobileGuide.textContent='资料较充分，可用地图比较近期报道关注。';
  else mobileGuide.textContent='资料积累中，仅作行业线索参考。';
  document.getElementById('rank-note').textContent=c.ready?'资料充足｜点击查看来源':'资料积累中｜暂不比较地区';
  var list=document.getElementById('panel-list');list.innerHTML='';c.panel.forEach(function(source){
    var row=document.createElement('div');row.className='panel-source';var left=document.createElement('span'),link=document.createElement('a');link.href=(source.entryUrls||[])[0]||'#';link.target='_blank';link.rel='noopener';link.textContent=source.name;left.appendChild(link);var role=document.createElement('small');role.textContent=' · '+source.role;left.appendChild(role);var right=document.createElement('small');right.textContent='已检查 '+(c.sourceGood[source.id]||0)+'/'+CUR_WINDOW.days+' 天';row.appendChild(left);row.appendChild(right);list.appendChild(row);
  });
}
function renderQuality() {
  var s=RAW.stats,b=(RAW.coverage&&RAW.coverage.baseline)||{};
  document.getElementById('quality-text').innerHTML='本页目前收录 <strong>'+s.totalMonitoredRecords+'</strong> 条来自固定权威来源的历史资料，其中 <strong>'+s.includedProvincialRecords+'</strong> 条涉及具体地区，合并为 <strong>'+s.provincialEvents+'</strong> 件事项；另有 <strong>'+s.nationalEvents+'</strong> 条全国性动态。这些历史资料来自旧日报整理，无法确认当时是否每天都查全了，所以暂不用于地区比较。新的每日检查目前已积累 <strong>'+s.operationalRecords+'</strong> 条资料。';
}
function updateMeta() {
  var label=CUR_THEME?' · '+CUR_THEME:'',quality=CUR_COVERAGE&&CUR_COVERAGE.ready?'资料充足':'资料积累中';document.getElementById('meta').textContent=CUR_WINDOW.label+label+' · 数据截至 '+AS_OF_STR+' · '+quality+' · 本页最高关注度显示为 100';
}
function refresh() {
  if(!RAW)return;VIEW=computeView(CUR_WINDOW.days,false);PREVIOUS=computeView(CUR_WINDOW.days,true);
  renderCoverage();renderStats();renderRanking();renderMap();renderScope(RAW.nationalEvents,'national-list','national-count');renderScope(RAW.internationalEvents,'international-list','international-count');renderQuality();updateMeta();
  document.getElementById('detail').classList.remove('show');
}
document.querySelectorAll('.win-tab').forEach(function(btn){
  btn.addEventListener('click', function(){
    CUR_WINDOW={label:btn.textContent,days:parseInt(btn.getAttribute('data-days'),10)};
    document.querySelectorAll('.win-tab').forEach(function(x){x.classList.toggle('active',x===btn);});refresh();
  });
});
document.getElementById('theme').addEventListener('change',function(){CUR_THEME=this.value;refresh();});
document.getElementById('d-close').addEventListener('click',function(){document.getElementById('detail').classList.remove('show');});
window.addEventListener('resize',function(){if(chart)chart.resize();});
if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(){ renderMap(); });
}
fetch('lib/china.json').then(function(r){
  return r.ok ? r.json() : Promise.reject();
}).then(function(geo){
  geo.features=geo.features.filter(function(f){return f.properties&&f.properties.name;});echarts.registerMap('china',geo);MAP_READY=true;if(RAW)renderMap();
}).catch(function(){
  document.getElementById('map-fallback').textContent='地图数据加载失败，可使用地区排名查看全部数据。';
});
fetch('heatmap-data.json').then(function(r){
  return r.ok ? r.json() : Promise.reject();
}).then(function(d){
  if(!d||d.version<3||!Array.isArray(d.events)||!d.coverage)throw new Error('schema');
  RAW=d;AS_OF_STR=d.asOf;AS_OF_UTC=d.asOf?parseUTC(d.asOf):0;
  var themes={};d.events.forEach(function(e){(e.themes||[]).forEach(function(t){themes[t]=true;});});
  Object.keys(themes).sort().forEach(function(t){var option=document.createElement('option');option.value=t;option.textContent=t;document.getElementById('theme').appendChild(option);});
  document.getElementById('map-fallback').style.display='none';refresh();
}).catch(function(){
  document.getElementById('meta').textContent='事件索引暂时不可用';document.getElementById('map-fallback').textContent='数据加载失败，请稍后刷新页面重试。';
});
</script>
</body>
</html>'''


def _classify_daily_section(heading):
    """Classify a level-2 daily heading without depending on one exact label."""
    text = re.sub(r'^[^\u4e00-\u9fffA-Za-z0-9]+', '', heading or '').strip()
    if not text:
        return None
    if any(token in text for token in ('目录', '今日趋势', '趋势总结', '方法说明', '信源与方法', '免责声明')):
        return 'nonnews'
    if any(token in text for token in ('国际', '海外', '区域')) and any(token in text for token in ('要闻', '新闻', '动态', '交流', '观察')):
        return 'international'
    if any(token in text for token in ('国内', '中国')) and any(token in text for token in ('要闻', '新闻', '动态', '观察')):
        return 'domestic'
    return None


def parse_md(filepath):
    """Parse a daily markdown report and return structured data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'title': '', 'date': '', 'weekday': '',
        'domestic': [], 'international': [], 'trends': [],
        'notes': [],  # standalone blockquotes (e.g. 编辑说明) after items
        'domestic_count': 0, 'international_count': 0,
        'toc_items': []
    }

    lines = content.split('\n')

    # Parse title line: # 🏛️ 每日文博资讯 | 2026年7月11日（周六）
    title_match = re.match(r'# .+?\|\s*(\d{4})年(\d{1,2})月(\d{1,2})日（(.+?)）', lines[0])
    if title_match:
        y, m, d, wd = title_match.groups()
        data['date'] = f'{y}-{int(m):02d}-{int(d):02d}'
        data['weekday'] = wd
        data['title'] = lines[0].lstrip('# ')

    current_section = None
    current_item = None
    item_idx = 0

    i = 1
    while i < len(lines):
        line = lines[i]

        # Section headers.  A new level-2 section always ends the previous
        # item; otherwise a renamed international section can swallow the
        # next item's source/body into the preceding domestic item.
        if line.startswith('## '):
            heading = line[3:].strip()
            classified = _classify_daily_section(heading)
            if classified in ('domestic', 'international'):
                current_section = classified
            elif '趋势' in heading:
                current_section = 'trends'
            elif '目录' in heading:
                current_section = 'toc'
            else:
                current_section = None
            current_item = None
            i += 1
            continue
        elif line.startswith('# '):
            current_section = None
            current_item = None
            i += 1
            continue

        # News item header: ### N. title
        item_match = re.match(r'### (\d+)\.\s*(.+)', line)
        if item_match and current_section in ('domestic', 'international'):
            num = int(item_match.group(1))
            title = item_match.group(2).strip()
            title = re.sub(r'\s*\{#[^}]*\}\s*$', '', title)  # strip {#anchor} from title
            item_idx += 1
            current_item = {
                'id': f'item{item_idx}',
                'number': item_idx,
                'title': title,
                'sources': [],
                'tags': [],
                'body': '',
                'commentary': ''
            }
            data[current_section].append(current_item)
            data['toc_items'].append({'id': f'item{item_idx}', 'title': title})
            i += 1
            continue

        # Tag line: 🏷️ tag1 · tag2 · tag3
        tag_match = re.match(r'🏷️\s*(.+)', line)
        if tag_match and current_item:
            tags = [t.strip() for t in re.split(r'[·,，、]\s*', tag_match.group(1))]
            current_item['tags'] = [t for t in tags if t]
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Source links line
        src_match = re.findall(r'(?:📎\s*|\|\s*)\[(.+?)\]\((.+?)\)', line)
        if src_match and current_item:
            current_item['sources'] = [{'name': s[0], 'url': s[1]} for s in src_match]
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Image line
        img_match = re.match(r'!\[.*?\]\((.+?)\)', line)
        if img_match and current_item:
            current_item['image'] = img_match.group(1)
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Blockquote: 点评 (within a news item) or standalone note (e.g. 编辑说明
        # after the trends table).
        if line.startswith('> '):
            bq_text = line.lstrip('> ').strip()
            bq_text = re.sub(r'\*\*点评[：:]\*\*\s*', '', bq_text)
            if current_section in ('domestic', 'international') and current_item:
                current_item['commentary'] = bq_text
            else:
                data['notes'].append(bq_text)
            i += 1
            continue

        # Table rows (trends section)
        if line.startswith('|') and current_section == 'trends':
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and not all(c.startswith('-') for c in cells):
                data['trends'].append(cells)
            i += 1
            continue

        # Skip markdown footer metadata
        if line.strip().startswith('*本日报由'):
            i += 1
            continue

        # Body text
        if current_item and line.strip() and not line.startswith('---') and not line.startswith('>'):
            if current_item['body']:
                current_item['body'] += '\n' + line
            else:
                current_item['body'] = line

        i += 1

    data['domestic_count'] = len(data['domestic'])
    data['international_count'] = len(data['international'])

    return data


def build_report_html(data, prev_report=None, next_report=None):
    """Generate HTML for a daily report.

    prev_report/next_report: dict with 'date' and 'weekday' or None.
    """
    total = data['domestic_count'] + data['international_count']
    report_source_stats = source_stats([data])
    is_legacy_report = bool(data.get('date')) and data['date'] < '2026-08-28'
    if report_source_stats['C']:
        quality_html = f'''<details class="quality-banner legacy">
  <summary><strong>🧭 来源与核验</strong><span class="source-summary">A级 {report_source_stats['A']} · B级 {report_source_stats['B']} · 待复核 {report_source_stats['C']}</span></summary>
  <p>本期属于历史档案，仍保留原始发布记录；待复核来源不会进入新的自动发布。</p>
  <p class="source-note">点击每条内容旁的来源名称核对原文。A级为官方/一手来源，B级为专业补充来源。</p>
</details>'''
    else:
        quality_html = f'''<details class="quality-banner">
  <summary><strong>🧭 来源与核验</strong><span class="source-summary">本期 {report_source_stats['total']} 个来源均通过 A/B 门槛</span></summary>
  <p>本期来源全部通过本站 A/B 级发布门槛。</p>
  <p class="source-note">点击每条内容旁的来源名称核对原文。A级为官方/一手来源，B级为专业补充来源。</p>
</details>'''

    toc_html = '<div class="toc">\n  <details open>\n    <summary><strong>📑 目录</strong></summary>\n    <ol>\n'
    for item in data['toc_items']:
        toc_html += f'      <li><a href="#{item["id"]}">{item["title"]}</a></li>\n'
    toc_html += '    </ol>\n  </details>\n</div>'

    def render_items(items, section_label):
        html = f'<h2 class="section">{section_label}</h2>\n\n'
        for item in items:
            tags_html = ''
            if item.get('tags'):
                for tag in item['tags']:
                    cls = f'tag tag-{tag}'
                    tags_html += f' <a class="{cls}" href="../search.html?q={quote(tag)}">#{tag}</a>'

            html += f'<h3 id="{item["id"]}">{item["number"]}. {item["title"]}{tags_html}</h3>\n'

            if item['sources']:
                src_parts = [source_link_html(s) for s in item['sources']]
                html += '<p class="source-row">📎 ' + ' '.join(src_parts) + '</p>\n'

            if item.get('image'):
                html += f'<p><img src="{item["image"]}" class="news-img" loading="lazy" alt="配图" onerror="this.style.display=\'none\'"></p>\n'

            if item['body']:
                html += f'<p>{md_inline(item["body"])}</p>\n'

            if item['commentary']:
                html += f'<blockquote><strong>点评：</strong> {md_inline(item["commentary"])}</blockquote>\n'

            html += '<hr>\n\n'
        return html

    domestic_html = render_items(data['domestic'], '🇨🇳 国内要闻')
    international_html = render_items(data['international'], '🌏 国际/区域交流')

    trends_html = '<h2 class="section">📊 今日趋势总结</h2>\n\n<table>\n'
    for i, row in enumerate(data['trends']):
        tag = 'th' if i == 0 else 'td'
        trends_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
    trends_html += '</table>\n'

    notes_html = ''
    if data.get('notes'):
        notes_html = '\n'
        for note in data['notes']:
            notes_html += f'<blockquote>{md_inline(note)}</blockquote>\n'

    # Pre-compute prev/next navigation
    if prev_report:
        prev_html = f'''<a class="prev" href="{prev_report['date']}.html">
    <div class="nav-label">← 上一篇</div>
    📅 {prev_report['date']} {prev_report['weekday']}
  </a>'''
    else:
        prev_html = '<a class="prev" style="visibility:hidden"></a>'

    if next_report:
        next_html = f'''<a class="next" href="{next_report['date']}.html">
    <div class="nav-label">下一篇 →</div>
    📅 {next_report['date']} {next_report['weekday']}
  </a>'''
    else:
        next_html = '<a class="next" style="visibility:hidden"></a>'

    nav_html = f'<div class="nav-prev-next">\n  {prev_html}\n  {next_html}\n</div>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>每日文博资讯 | {data['date']}</title>
<meta name="description" content="{data['date']} 每日文博资讯，共 {total} 条（国内 {data['domestic_count']} + 国际/区域 {data['international_count']}）。{data['toc_items'][0]['title'][:60] if data['toc_items'] else ''}">
<meta name="keywords" content="文博,考古,博物馆,文化遗产,文物,每日文博资讯,{data['date']}">
<link rel="canonical" href="https://zhangheng666.top/reports/{data['date']}.html">
<meta property="og:title" content="每日文博资讯 | {data['date']}">
<meta property="og:description" content="{data['date']} 每日文博资讯，共 {total} 条（国内 {data['domestic_count']} + 国际/区域 {data['international_count']}）">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/reports/{data['date']}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "NewsArticle",
  "headline": "每日文博资讯 | {data['date']}",
  "datePublished": "{data['date']}T07:13:00+08:00",
  "dateModified": "{data['date']}T07:13:00+08:00",
  "description": "{data['date']} 每日文博资讯，共 {total} 条",
  "url": "https://zhangheng666.top/reports/{data['date']}.html",
  "publisher": {{
    "@type": "Organization",
    "name": "每日文博资讯",
    "url": "https://zhangheng666.top/"
  }}
}}
</script>
{CSS}
</head>
<body>

<header>
  <h1>🏛️ 每日文博资讯</h1>
  <p class="meta">{data['date']} · {data['weekday']} ｜ 共 {total} 条（国内 {data['domestic_count']} + 国际/区域 {data['international_count']}）</p>
  <p style="margin-top:4px;font-size:.85em"><a href="../index.html">← 返回目录</a></p>
  {('<div class="quality-banner legacy" style="text-align:left;margin:12px 0 0"><strong>历史档案：</strong>本日报生成于现行信源分级规则启用前，页面中的来源等级为后续审计标注；请以原文为准。</div>') if is_legacy_report else ''}
</header>

<main>

{toc_html}

{domestic_html}
{international_html}
{trends_html}{notes_html}

{quality_html}

<hr>

<p><em>本日报由 AI 自动采集编撰 | {data['date']}</em></p>

{nav_html}

<div class="share-row">
  <button id="share-btn" aria-label="分享本文">🔗 分享 / 复制链接</button>
  <span class="share-tip">转发给文博同好</span>
</div>

</main>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 每日早 7:13（北京时间）自动更新 ｜ <a href="../sources.html">信源与方法</a> ｜ <a href="../about.html">关于本站</a></p>
</footer>

<div id="reading-progress"></div>
<button id="back-to-top" aria-label="回到顶部">↑</button>

<script>
window.addEventListener('scroll', function() {{
  var st = window.pageYOffset || document.documentElement.scrollTop;
  var sh = document.documentElement.scrollHeight - document.documentElement.clientHeight;
  var pct = sh > 0 ? (st / sh * 100) : 0;
  document.getElementById('reading-progress').style.width = pct + '%';
  var btn = document.getElementById('back-to-top');
  if (st > 300) btn.classList.add('show'); else btn.classList.remove('show');
}});
document.getElementById('back-to-top').addEventListener('click', function() {{
  window.scrollTo({{top: 0, behavior: 'smooth'}});
}});
document.getElementById('share-btn').addEventListener('click', function() {{
  const url = location.href;
  const title = document.title;
  if (navigator.share) {{
    navigator.share({{title: title, url: url}}).catch(function(){{}});
  }} else if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(title + ' ' + url).then(function() {{
      const b = document.getElementById('share-btn');
      b.textContent = '✅ 链接已复制';
      setTimeout(function() {{ b.textContent = '🔗 分享 / 复制链接'; }}, 2000);
    }});
  }} else {{
    prompt('复制链接：', url);
  }}
}});
</script>

</body>
</html>'''
    return '\n'.join(line.rstrip() for line in html.splitlines()) + '\n'


# ───────────────── 周报 / 月报 解析器 ─────────────────

def parse_digest(filepath, dtype='weekly'):
    """Parse a weekly or monthly digest markdown file.

    dtype: 'weekly' | 'monthly'
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'type': dtype,
        'title': '',
        'label': '',
        'date_range': '',
        'ref_date': '',   # YYYY-MM-DD for sorting/URL
        'overview': '',
        'overview_table': [],
        'items': [],
        'upcoming_title': '',
        'upcoming_table': [],
        'trends': [],
        'rich_sections': [],  # monthly report: arbitrary rich-text sections
        'footer': ''
    }

    lines = content.split('\n')

    # Parse title line
    if dtype == 'weekly':
        # # 📰 文博资讯周报 | 2026年7月6日 — 7月12日
        # Second date may omit year
        title_match = re.match(
            r'# .+?\|\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*[—\-]\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日', lines[0])
        if title_match:
            y1, m1, d1, y2, m2, d2 = title_match.groups()
            if not y2:
                y2 = y1
            data['date_range'] = f'{y1}-{int(m1):02d}-{int(d1):02d} — {y2}-{int(m2):02d}-{int(d2):02d}'
            data['ref_date'] = f'{y2}-{int(m2):02d}-{int(d2):02d}'
            data['label'] = '周报'
    else:
        # # 📚 文博资讯月报 | 2026年7月
        title_match = re.match(r'# .+?\|\s*(\d{4})年(\d{1,2})月', lines[0])
        if title_match:
            y, m = title_match.groups()
            data['date_range'] = f'{y}年{int(m)}月'
            data['ref_date'] = f'{y}-{int(m):02d}-28'  # fallback for sorting
            data['label'] = '月报'

    data['title'] = lines[0].lstrip('# ')

    # Parse sections
    current_section = None
    current_item = None
    current_rich = None
    i = 1
    while i < len(lines):
        line = lines[i]

        # Section headers
        if line.startswith('## 📊') and '概览' in line:
            current_section = 'overview'
            current_item = None; current_rich = None
            i += 1
            continue
        elif line.startswith('## 🔟') or line.startswith('## 🔝') or ('要闻' in line and '##' in line and '趋势' not in line):
            current_section = 'items'
            current_item = None; current_rich = None
            i += 1
            continue
        elif line.startswith('## 🗓️') or line.startswith('## 📅'):
            current_section = 'upcoming'
            current_item = None; current_rich = None
            i += 1
            data['upcoming_title'] = line.lstrip('# ').strip()
            continue
        elif line.startswith('## 📊') and '趋势' in line:
            # Monthly report: trends are rich-text sections, not just tables
            if dtype == 'monthly':
                current_section = 'rich'
                title = line.lstrip('# ').strip()
                title = re.sub(r'\s*\{#.*?\}\s*$', '', title)
                current_rich = {'icon': '📊', 'title': title, 'raw_lines': []}
                data['rich_sections'].append(current_rich)
            else:
                current_section = 'trends'
            current_item = None
            i += 1
            continue

        # Rich sections: 🌍, 💡, 📈, 🏆, 📂, etc.
        # For monthly/weekly reports, every unhandled ## header starts a new rich section
        if dtype in ('monthly', 'weekly') and line.startswith('## ') and not line.startswith('## 📑'):
            # Skip TOC section
            if '目录' in line:
                current_section = 'skip'
                current_item = None; current_rich = None
                i += 1
                continue
            # Start a new rich section (handles section transitions)
            icon_match = re.match(r'##\s+(\S)\s', line)
            icon = icon_match.group(1) if icon_match else '📄'
            title = line.lstrip('# ').strip()
            title = re.sub(r'\s*\{#.*?\}\s*$', '', title)
            current_section = 'rich'
            current_rich = {'icon': icon, 'title': title, 'raw_lines': []}
            data['rich_sections'].append(current_rich)
            current_item = None
            i += 1
            continue
        elif line.startswith('## ') or line.startswith('# '):
            current_section = None
            current_item = None; current_rich = None
            i += 1
            continue

        # Handle rich section content (monthly report)
        if current_section == 'rich' and current_rich is not None:
            current_rich['raw_lines'].append(line)
            i += 1
            continue

        # Item header: ### N. title
        item_match = re.match(r'### (\d+)\.\s*(.+)', line)
        if item_match and current_section == 'items':
            title = item_match.group(2).strip()
            current_item = {
                'id': f'item{item_match.group(1)}',
                'title': title,
                'sources': [],
                'body': '',
                'progress': ''
            }
            data['items'].append(current_item)
            i += 1
            continue

        # Source links (at end of item, after blockquote or body)
        src_match = re.findall(r'(?:📎\s*|\|\s*)\[(.+?)\]\((.+?)\)', line)
        if src_match and current_item:
            current_item['sources'] = [{'name': s[0], 'url': s[1]} for s in src_match]
            i += 1
            if i < len(lines) and lines[i].strip() == '':
                i += 1
            continue

        # Blockquote (本周新进展 / 本月新进展 for digest items)
        if line.startswith('> ') and current_item:
            progress = line.lstrip('> ').strip()
            progress = re.sub(r'\*\*本周新进展[：:]\*\*\s*', '', progress)
            progress = re.sub(r'\*\*本月新进展[：:]\*\*\s*', '', progress)
            current_item['progress'] = progress
            i += 1
            continue

        # Table rows
        if line.startswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and not all(c.startswith('-') for c in cells):
                if current_section == 'overview':
                    data['overview_table'].append(cells)
                elif current_section == 'upcoming':
                    data['upcoming_table'].append(cells)
                elif current_section == 'trends':
                    data['trends'].append(cells)
                elif current_section == 'items' and dtype == 'monthly':
                    # Monthly report top-10 table: | rank | title | date | significance |
                    if len(cells) >= 3 and cells[0].isdigit():
                        rank = cells[0]
                        title = cells[1] if len(cells) > 1 else ''
                        date_info = cells[2] if len(cells) > 2 else ''
                        significance = cells[3] if len(cells) > 3 else ''
                        current_item = {
                            'id': f'item{rank}',
                            'title': title,
                            'sources': [],
                            'body': f'📅 {date_info} ｜ {significance}' if significance else date_info,
                            'progress': ''
                        }
                        data['items'].append(current_item)
            i += 1
            continue

        # Footer
        if line.strip().startswith('*本周报由') or line.strip().startswith('*本月报由'):
            data['footer'] = line.strip().strip('*')
            i += 1
            continue

        # Body text for overview or current item
        if current_section == 'overview' and line.strip() and not line.startswith('---'):
            if data['overview']:
                data['overview'] += '\n' + line.strip()
            else:
                data['overview'] = line.strip()

        elif current_item and current_section == 'items' and line.strip() and not line.startswith('---') and not line.startswith('>'):
            if current_item['body']:
                current_item['body'] += '\n' + line.strip()
            else:
                current_item['body'] = line.strip()

        i += 1

    return data


def md_inline(text):
    """Convert markdown inline formatting to HTML."""
    if not text:
        return text
    # **bold**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *italic*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # `code`
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


# ───────────────── 招聘信息 解析器 ─────────────────

def extract_deadline_date(text):
    """Use the final date in a deadline range as the actual closing date."""
    matches = re.findall(r'(\d{4})-(\d{1,2})-(\d{1,2})', text or '')
    return matches[-1] if matches else None


def extract_deadline_datetime(text):
    """Return an ISO-8601 Beijing deadline, or None when the text is vague.

    Date-only deadlines close at 23:59:59 Beijing time. Chinese prose such as
    “2026年6月18日发布” is deliberately not treated as a deadline because it
    describes the announcement date rather than an application closing time.
    """
    matches = list(re.finditer(r'(\d{4})-(\d{1,2})-(\d{1,2})', text or ''))
    if not matches:
        return None
    match = matches[-1]
    y, m, d = (int(value) for value in match.groups())
    tail = (text or '')[match.end():match.end() + 80]
    time_match = re.search(r'(\d{1,2}):([0-5]\d)', tail)
    hour, minute, second = (int(time_match.group(1)), int(time_match.group(2)), 0) if time_match else (23, 59, 59)
    if hour > 23:
        return None
    try:
        return f'{y:04d}-{m:02d}-{d:02d}T{hour:02d}:{minute:02d}:{second:02d}+08:00'
    except ValueError:
        return None

def parse_jobs(filepath):
    """Parse recruitment markdown file and return structured data.

    Returns dict with:
      - update_date: 'YYYY-MM-DD'
      - summary: str (intro paragraph)
      - sections: [{category, icon, items: [{number, institution, position,
          education, location, deadline, link_url, link_text, urgent, days_left}]}]
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    data = {
        'update_date': '',
        'summary': '',
        'sections': []
    }

    lines = content.split('\n')

    # Parse title line for update date
    if lines:
        title_match = re.match(
            r'# .+?\|\s*(\d{4})[年-](\d{1,2})[月-](\d{1,2})(?:日)?', lines[0])
        if title_match:
            y, m, d = title_match.groups()
            data['update_date'] = f'{y}-{int(m):02d}-{int(d):02d}'

    # Expiry must be evaluated against today's Beijing date, not the file's
    # update date; otherwise stale listings can look active forever.
    today = china_today().isoformat()

    current_section = None  # dict with category, icon, items
    current_item = None

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith('---'):
            continue

        # Summary line: > text
        if stripped.startswith('> '):
            prefix = stripped[2:].strip()
            if data['summary']:
                data['summary'] += ' ' + prefix
            else:
                data['summary'] = prefix
            continue

        # Section header: ## 🏛️ 博物馆 etc.
        sec_match = re.match(r'##\s+(.{1,2})\s+(.+)', stripped)
        if sec_match:
            icon = sec_match.group(1)
            category = sec_match.group(2)
            current_section = {'category': category, 'icon': icon, 'items': []}
            data['sections'].append(current_section)
            current_item = None
            continue

        # Item header: ### N. Institution — Position  (or ### N. ⏰ ...)
        item_match = re.match(r'###\s+(\d+)\.\s+(⏰\s*)?(.+?)\s*[—\-]\s*(.+)', stripped)
        if item_match:
            number = int(item_match.group(1))
            urgent = bool(item_match.group(2))
            institution = item_match.group(3).strip()
            position = item_match.group(4).strip()

            current_item = {
                'number': number,
                'urgent': urgent,
                'institution': institution,
                'position': position,
                'education': '',
                'location': '',
                'deadline': '',
                'link_url': '',
                'link_text': '招聘公告',
                'days_left': None,
                'deadline_at': None,
                'note': '',
                'status': 'check'
            }
            if current_section is None:
                # Default section
                current_section = {'category': '招聘', 'icon': '💼', 'items': []}
                data['sections'].append(current_section)
            current_section['items'].append(current_item)
            continue

        # Field lines: - 🎓 **学历要求**：value
        if current_item:
            field_match = re.match(r'-\s*.+?\*\*(.+?)\*\*\s*[：:]\s*(.+)', stripped)
            if field_match:
                field_name = field_match.group(1).strip()
                field_value = field_match.group(2).strip()

                if '学历' in field_name:
                    current_item['education'] = field_value
                elif '地点' in field_name:
                    current_item['location'] = field_value
                elif '截止' in field_name:
                    current_item['deadline'] = field_value
                elif '待遇' in field_name:
                    current_item['note'] = field_value
                continue

            # Link line: - 🔗 [text](url)
            link_match = re.match(r'-\s*🔗\s*\[(.+?)\]\((.+?)\)', stripped)
            if link_match:
                current_item['link_text'] = link_match.group(1)
                current_item['link_url'] = link_match.group(2)
                continue

            # Email line: - 📧 投递：email@addr  or  📧 email@addr
            email_match = re.match(r'-\s*📧\s*(?:投递[：:]\s*)?([a-zA-Z0-9._%+-]+@[^\s|]+)', stripped)
            if email_match:
                email = email_match.group(1).strip()
                current_item['link_url'] = f'mailto:{email}'
                current_item['link_text'] = email
                continue

    # Compute days_left and urgent flag for each item
    for section in data['sections']:
        for item in section['items']:
            dl = item['deadline']
            if dl and today:
                dl_match = extract_deadline_date(dl)
                if dl_match:
                    try:
                        from datetime import date
                        dl_date = date(
                            int(dl_match[0]), int(dl_match[1]), int(dl_match[2])
                        )
                        today_date = date.fromisoformat(today)
                        item['days_left'] = (dl_date - today_date).days
                        if item['days_left'] < 0:
                            item['status'] = 'closed'
                        else:
                            item['status'] = 'open'
                        if 0 <= item['days_left'] <= 3:
                            item['urgent'] = True
                        item['deadline_at'] = extract_deadline_datetime(dl)
                    except (ValueError, KeyError):
                        pass

    # Sort items within each section by deadline (earliest first, no-deadline last)
    for section in data['sections']:
        def sort_key(item):
            if item['status'] == 'open':
                return (0, item['days_left'] if item['days_left'] is not None else 9999)
            if item['status'] == 'check':
                return (1, 9999)
            return (2, item['days_left'] if item['days_left'] is not None else 9999)
        section['items'].sort(key=sort_key)

    return data


def build_jobs_html(data, page_type='jobs'):
    """Generate HTML for the recruitment page (jobs.html) or internship page (intern.html)."""
    total = sum(len(s['items']) for s in data['sections'])
    urgent_count = sum(1 for s in data['sections'] for it in s['items'] if it['urgent'])
    closed_count = sum(1 for s in data['sections'] for it in s['items'] if it.get('status') == 'closed')
    check_count = sum(1 for s in data['sections'] for it in s['items'] if it.get('status') == 'check')
    active_count = sum(1 for s in data['sections'] for it in s['items'] if it.get('status') == 'open')
    is_intern = (page_type == 'intern')
    page_title = '🌱 文博实习招聘' if is_intern else '💼 文博招聘信息'
    page_url = 'intern.html' if is_intern else 'jobs.html'

    # Build sections
    sections_html = ''
    for sec in data['sections']:
        items_html = ''
        for item in sec['items']:
            # Urgency badge — use specific date, not relative ("今天"/"明天")
            urgent_badge = ''
            if item['urgent'] and item['days_left'] is not None:
                dl = item['deadline']
                dl_match = extract_deadline_date(dl) if dl else None
                if dl_match:
                    m, d = int(dl_match[1]), int(dl_match[2])
                    urgent_badge = f' <span class="closing-badge">{m}月{d}日截止</span>'
                else:
                    urgent_badge = ' <span class="closing-badge">即将截止</span>'

            row_class = ' urgent-row' if item['urgent'] else (' closed-row' if item.get('status') == 'closed' else '')
            if item.get('status') == 'closed':
                status_badge = '<span class="status-badge status-closed">已截止</span>'
            elif item.get('status') == 'open':
                status_badge = '<span class="status-badge status-open">可申请</span>'
            else:
                status_badge = '<span class="status-badge status-check">待核截止</span>'
            if item.get('link_url', '').startswith(('http://', 'https://')):
                link_info = recruitment_source_info(item['link_url'])
                link_badge = f' <span class="source-note">{link_info["label"]}</span>'
            else:
                link_badge = ''

            deadline_attr = item.get('deadline_at') or ''
            static_status = item.get('status', 'check')
            items_html += f'''
        <div class="job-item{row_class}" data-deadline-at="{deadline_attr}" data-static-status="{static_status}">
          <div class="job-header">
            <span class="job-number">#{item['number']}</span>
            <span class="job-title">{item['institution']} — {item['position']}</span>
            {status_badge.replace('status-badge ', 'status-badge job-status ', 1)}
            {urgent_badge}
          </div>
          <div class="job-meta">
            <span>🎓 {item['education'] or '见公告'}</span>
            <span>📍 {item['location'] or '见公告'}</span>
            <span class="job-deadline">📅 {item['deadline'] or '见公告'}</span>
            {('<span>💰 ' + item['note'] + '</span>') if item.get('note') else ''}
          </div>
          <div class="job-link">
            {'<a href="' + item['link_url'] + '" target="_blank" rel="noopener">🔗 ' + item['link_text'] + '</a>' + link_badge if item['link_url'] else '<span style="color:var(--muted);font-size:.85em">📧 ' + (item.get("link_text") or "见公告") + '</span>'}
          </div>
        </div>'''

        sections_html += f'''
    <div class="job-section">
      <h2 class="section">{sec['icon']} {sec['category']} <span class="count-badge">{len(sec['items'])} 岗</span></h2>
      {items_html}
    </div>'''

    # Summary
    summary_html = ''
    if data['summary']:
        summary_html = f'<p class="job-summary">{md_inline(data["summary"])}</p>'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>{page_title} | {data['update_date']}</title>
<meta property="og:title" content="{page_title} | {data['update_date']}">
<meta property="og:description" content="{'文博实习岗位，面向在读学生，共 ' + str(total) + ' 个岗位' if is_intern else '省级以上博物馆、考古院所、高校文博专业招聘信息，共 ' + str(total) + ' 个岗位。即将截止 ' + str(urgent_count) + ' 个。'}">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/jobs.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
{CSS}
<style>
  .job-summary {{
    background: var(--card); border-left: 3px solid var(--accent);
    padding: 12px 16px; margin: 16px 0; border-radius: 0 8px 8px 0;
    font-size: .9em; color: var(--muted);
  }}
  .job-section {{
    margin: 24px 0;
  }}
  .job-item {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px; margin: 10px 0;
    transition: box-shadow .15s;
  }}
  .job-item:hover {{
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
  }}
  .job-item.urgent-row {{
    border-left: 4px solid #e74c3c;
  }}
  .job-item.closed-row {{ opacity: .62; border-left: 4px solid var(--border); }}
  @media (prefers-color-scheme: dark) {{
    .job-item.urgent-row {{
      border-left-color: #ff6b5b;
    }}
  }}
  .job-header {{
    display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
    margin-bottom: 6px;
  }}
  .job-number {{
    color: var(--muted); font-size: .8em; min-width: 24px;
  }}
  .job-title {{
    font-weight: 700; font-size: 1.05em; color: var(--text);
  }}
  .closing-badge {{
    display: inline-block; font-size: .75em; padding: 2px 10px;
    border-radius: 10px; background: #e74c3c; color: #fff;
    font-weight: 600; white-space: nowrap;
  }}
  @media (prefers-color-scheme: dark) {{
    .closing-badge {{
      background: #c0392b;
    }}
  }}
  .job-meta {{
    display: flex; gap: 16px; flex-wrap: wrap; font-size: .85em;
    color: var(--muted); margin: 6px 0;
  }}
  .job-deadline {{
    font-weight: 600;
  }}
  .job-link {{
    margin-top: 4px;
  }}
  .job-link a {{
    font-size: .9em; color: var(--accent); font-weight: 600;
    text-decoration: none;
  }}
  .job-link a:hover {{
    text-decoration: underline;
  }}
  .stats-bar {{
    display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0;
  }}
  .stat-item {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 16px; font-size: .85em;
  }}
  .stat-item strong {{ color: var(--accent); }}
</style>
</head>
<body>

<header>
  <h1>{page_title}</h1>
  <p class="meta">{data['update_date']} 更新 ｜ 共 {total} 个{'实习岗位' if is_intern else '岗位'} ｜ 可申请 <span id="job-open-count">{active_count}</span> ｜ 已截止 <span id="job-closed-count">{closed_count}</span></p>
  <p style="margin-top:4px;font-size:.85em"><a href="index.html">← 返回首页</a></p>
</header>

{summary_html}

<div class="stats-bar">
  <div class="stat-item">📋 总岗位数：<strong>{total}</strong></div>
  <div class="stat-item">🟢 可申请：<strong id="job-open-stat">{active_count}</strong></div>
  <div class="stat-item">⏰ 3天内截止：<strong id="job-urgent-stat">{urgent_count}</strong></div>
  <div class="stat-item">🔴 已截止：<strong id="job-closed-stat">{closed_count}</strong></div>
  <div class="stat-item">🧭 待核截止：<strong>{check_count}</strong></div>
  <div class="stat-item">🔄 每两天更新一次</div>
</div>

{sections_html}

<hr>
<p style="font-size:.82em; color: var(--muted);">⚠️ 状态按北京时间动态更新，精确到公告给出的截止时刻；申请前仍请核对原文和投递入口。本页保留已截止条目作为档案，“待核截止”表示公告未给出标准日期或需人工确认。来源标签采用“官方来源 / 高校·就业平台 / 主流招聘平台 / 二手线索”，不与日报 A/B/C 新闻等级混用。</p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 招聘栏目 · 每两日更新 ｜ <a href="sources.html">信源与方法</a> ｜ <a href="about.html">关于本站</a></p>
</footer>

<script>
(function() {{
  var rows = Array.prototype.slice.call(document.querySelectorAll('.job-item'));
  function beijingNow() {{
    var parts = new Intl.DateTimeFormat('en-CA', {{ timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }}).formatToParts(new Date());
    var out = {{}}; parts.forEach(function(p) {{ if (p.type !== 'literal') out[p.type] = p.value; }});
    return new Date(out.year + '-' + out.month + '-' + out.day + 'T' + out.hour + ':' + out.minute + ':' + out.second + '+08:00');
  }}
  function refreshStatuses() {{
    var now = beijingNow(), open = 0, closed = 0, urgent = 0;
    rows.forEach(function(row) {{
      var status = row.querySelector('.job-status'), deadline = row.getAttribute('data-deadline-at');
      var isOpen = row.getAttribute('data-static-status') === 'open';
      var isClosed = row.getAttribute('data-static-status') === 'closed';
      if (deadline) {{
        var end = new Date(deadline);
        isClosed = now >= end;
        isOpen = !isClosed;
        if (isOpen && end - now <= 3 * 86400000) urgent += 1;
      }}
      if (status && (deadline || isOpen || isClosed)) {{
        status.textContent = isClosed ? '已截止' : '可申请';
        status.className = 'status-badge job-status ' + (isClosed ? 'status-closed' : 'status-open');
      }}
      row.classList.toggle('closed-row', isClosed);
      if (isClosed) row.classList.remove('urgent-row');
      if (isOpen) open += 1;
      if (isClosed) closed += 1;
    }});
    var set = function(id, value) {{ var node = document.getElementById(id); if (node) node.textContent = value; }};
    set('job-open-count', open); set('job-open-stat', open); set('job-closed-count', closed); set('job-closed-stat', closed); set('job-urgent-stat', urgent);
  }}
  refreshStatuses();
  window.setInterval(refreshStatuses, 60000);
}})();
</script>

</body>
</html>'''
    return '\n'.join(line.rstrip() for line in html.splitlines()) + '\n'


def _render_md_block(lines):
    """Convert a list of raw markdown lines to HTML.
    Handles: paragraphs, ### headers, bullet lists, tables, blockquotes.
    """
    html = ''
    i = 0
    while i < len(lines):
        line = lines[i]

        # Blank line or horizontal rule
        if not line.strip() or line.strip() == '---':
            i += 1
            continue

        # Sub-header: ### Title
        sub_match = re.match(r'###\s+(.+)', line)
        if sub_match:
            title = md_inline(sub_match.group(1).strip())
            # Remove {#anchor}
            title = re.sub(r'\s*\{#.*?\}\s*$', '', title)
            html += f'<h3>{title}</h3>\n'
            i += 1
            continue

        # Table
        if line.startswith('|'):
            table_rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [c.strip() for c in lines[i].split('|')[1:-1]]
                if not all(c.startswith('-') for c in cells):
                    table_rows.append(cells)
                elif table_rows:
                    # separator row — skip but it marks header
                    pass
                i += 1
            if table_rows:
                html += '<table>\n'
                for ri, row in enumerate(table_rows):
                    tag = 'th' if ri == 0 else 'td'
                    html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
                html += '</table>\n'
            continue

        # Blockquote
        if line.startswith('> '):
            content = line[2:].strip()
            content = re.sub(r'\*\*点评[：:]\*\*\s*', '', content)
            html += f'<blockquote>{md_inline(content)}</blockquote>\n'
            i += 1
            continue

        # Unordered list
        if re.match(r'^-\s+', line):
            html += '<ul>\n'
            while i < len(lines) and re.match(r'^-\s+', lines[i]):
                item_text = md_inline(re.sub(r'^-\s+', '', lines[i]))
                html += f'<li>{item_text}</li>\n'
                i += 1
            html += '</ul>\n'
            continue

        # Ordered list
        if re.match(r'^\d+\.\s+', line):
            html += '<ol>\n'
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                item_text = md_inline(re.sub(r'^\d+\.\s+', '', lines[i]))
                html += f'<li>{item_text}</li>\n'
                i += 1
            html += '</ol>\n'
            continue

        # Regular paragraph — collect consecutive text lines
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|', '>', '-')) and not re.match(r'^\d+\.\s+', lines[i]):
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            text = ' '.join(para_lines)
            html += f'<p>{md_inline(text)}</p>\n'
            continue

        # Fallback: skip unrecognized lines
        i += 1

    return html


def _compact_title(text):
    return re.sub(r'[^0-9a-zA-Z\u4e00-\u9fff]', '', (text or '')).lower()


def related_digest_sources(title, daily_reports, context=''):
    """Recover evidence for legacy weekly/monthly summaries from daily items.

    New digest Markdown should carry 📎 links itself. This fallback only links
    an aggregate item when its title clearly matches a daily item title.
    """
    if not title or not daily_reports:
        return []
    target = _compact_title(title)
    context_compact = _compact_title(context)
    if len(target) < 8 and len(context_compact) < 8:
        return []
    if not context_compact:
        # Preserve the established exact-title fallback for older weekly and
        # monthly pages. The contextual matching below is only for the new
        # aggregate weekly headings that carry local paragraph context.
        for report in daily_reports:
            for item in report.get('domestic', []) + report.get('international', []):
                candidate = _compact_title(item.get('title', ''))
                if not candidate:
                    continue
                shared = target in candidate or candidate in target
                if not shared:
                    shared = len(target[:12]) >= 8 and target[:12] in candidate
                if shared:
                    return (item.get('sources') or [])[:2]
        return []
    matches = []
    for report in daily_reports:
        for item in report.get('domestic', []) + report.get('international', []):
            candidate = _compact_title(item.get('title', ''))
            if not candidate:
                continue
            shared = target in candidate or candidate in target
            if not shared:
                # Long common prefix is safer than a loose keyword match.
                shared = len(target[:12]) >= 8 and target[:12] in candidate
            if not shared and context_compact:
                # Aggregate weekly headings rarely repeat a daily headline
                # verbatim. Use deterministic four-character evidence
                # fragments from the daily title, and require two fragments
                # for short/noisy titles. This is matching, not an AI claim.
                fragments = {candidate[i:i + 4] for i in range(len(candidate) - 3)}
                hit_count = sum(fragment in context_compact for fragment in fragments)
                shared = hit_count >= (2 if len(candidate) < 12 else 3)
            if shared:
                score = 2 if target and (target in candidate or candidate in target) else 1
                if context_compact:
                    fragments = {candidate[i:i + 4] for i in range(len(candidate) - 3)}
                    score += sum(fragment in context_compact for fragment in fragments)
                matches.append((score, item))
    matches.sort(key=lambda value: value[0], reverse=True)
    # A contextual aggregate is only a safe match when it has the strongest
    # identity evidence.  Previously the best title match could have no
    # publishable source, after which the code fell through to weaker matches
    # from unrelated stories and borrowed their URLs (the 2026-08-23
    # Ma-wang-dui/Sicily error).  If the strongest match is unresolved, keep
    # it unresolved instead of attaching a less certain article's evidence.
    if matches:
        best_score = matches[0][0]
        matches = [match for match in matches if match[0] == best_score]
    sources = []
    seen = set()
    for _score, item in matches[:3]:
        for source in item.get('sources', []):
            # A weekly evidence index must not resurrect a blocked or
            # unapproved historical URL merely because it was attached to an
            # older daily item. Reuse only sources that are still publishable.
            info = source_info(source.get('url', ''))
            if info['blocked'] or info['tier'] not in ('A', 'B'):
                continue
            key = canonical_url(source.get('url', ''))
            if key and key not in seen:
                seen.add(key)
                sources.append(source)
    return sources[:3]


def build_digest_html(data, daily_reports=None):
    """Generate HTML for a weekly or monthly digest."""
    if data.get('layout') == 'periodic-v2':
        from automation.periodic_reports import build_periodic_html
        return build_periodic_html(data)

    dtype = data['type']
    emoji = '📰' if dtype == 'weekly' else '📊'
    monthly_reading_note = ''
    if dtype == 'monthly':
        monthly_reading_note = '''<div class="quality-banner"><strong>阅读提示：</strong>本月报把“事实盘点”和“AI趋势观察”分开呈现。前者用于回看本月收录事件；后者是基于本站样本的编辑性归纳，不代表全国行业统计结论。</div>'''

    # Overview
    overview_html = f'<h2 class="section">📊 本期概览</h2>\n'
    if data['overview']:
        overview_html += f'<p>{md_inline(data["overview"])}</p>\n'
    if data['overview_table']:
        overview_html += '<table>\n'
        for i, row in enumerate(data['overview_table']):
            tag = 'th' if i == 0 else 'td'
            overview_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
        overview_html += '</table>\n'

    # Items
    if dtype == 'monthly' and data['items']:
        # Monthly report: render top 10 as a styled ranking table
        items_html = f'<h2 class="section">🔟 事实盘点 · {data["date_range"]}十大文博新闻</h2>\n\n'
        items_html += '<p>本月文博领域重大事件精选，按重要性和影响力综合排序。</p>\n'
        items_html += '<table class="top10-table">\n'
        items_html += '<thead><tr><th>#</th><th>新闻</th><th>日期</th><th>为什么重要</th></tr></thead>\n<tbody>\n'
        for item in data['items']:
            rank = item['id'].replace('item', '')
            # body format: "📅 date | significance"
            body = item.get('body', '')
            date_str = ''
            sig_str = ''
            if '｜' in body:
                parts = body.split('｜', 1)
                date_str = parts[0].replace('📅', '').strip()
                sig_str = parts[1].strip()
            elif '|' in body:
                parts = body.split('|', 1)
                date_str = parts[0].replace('📅', '').strip()
                sig_str = parts[1].strip()
            items_html += f'<tr id="{item["id"]}"><td class="rank">{rank}</td><td class="news-title">{md_inline(item["title"])}</td><td class="date">{date_str}</td><td class="sig">{md_inline(sig_str)}</td></tr>\n'
        items_html += '</tbody>\n</table>\n'
    else:
        # Weekly report: flat item list (only if there are items)
        items_html = ''
        if data['items']:
            items_html = '<h2 class="section">🔟 本期要闻</h2>\n\n'
            for item in data['items']:
                items_html += f'<h3 id="{item["id"]}">{md_inline(item["title"])}</h3>\n'

                if item['body']:
                    items_html += f'<p>{md_inline(item["body"])}</p>\n'

                if item['progress']:
                    items_html += f'<blockquote><strong>{data["label"]}新进展：</strong> {md_inline(item["progress"])}</blockquote>\n'

                if item['sources']:
                    src_parts = []
                    for s in item['sources']:
                        src_parts.append(f'<a href="{s["url"]}" target="_blank" rel="noopener">{s["name"]}</a>')
                    items_html += '<p>📎 ' + ' | '.join(src_parts) + '</p>\n'

                items_html += '<hr>\n\n'

    # Legacy digest files often omitted source links. Recover direct evidence
    # from matching daily items and make any remaining gap visible to readers.
    evidence_targets = list(data.get('items', []))
    if not evidence_targets and data.get('type') == 'weekly':
        # The newer weekly format stores its headline list inside the first
        # rich section (usually “本周重磅”) instead of item records.
        rich_lines = (data.get('rich_sections') or [{}])[0].get('raw_lines', [])
        for line_index, line in enumerate(rich_lines):
            match = re.match(r'###\s+(.+)', line)
            if match:
                next_heading = next(
                    (index for index in range(line_index + 1, len(rich_lines))
                     if rich_lines[index].startswith('### ')),
                    len(rich_lines),
                )
                evidence_targets.append({
                    'title': match.group(1).strip(),
                    'sources': [],
                    'context': '\n'.join(rich_lines[line_index:next_heading]),
                })
    evidence_rows = []
    missing_evidence = 0
    for item in evidence_targets:
        sources = item.get('sources') or related_digest_sources(
            item.get('title', ''), daily_reports or [], item.get('context', '')
        )
        unique = []
        seen = set()
        for source in sources:
            key = canonical_url(source.get('url', ''))
            if key and key not in seen:
                seen.add(key)
                unique.append(source)
        if unique:
            evidence_rows.append('<li><span class="digest-evidence-title">' + md_inline(item.get('title', '')) + '</span><br>' +
                                 ' '.join(source_link_html(s) for s in unique) + '</li>')
        else:
            missing_evidence += 1
            evidence_rows.append('<li><span class="digest-evidence-title">' + md_inline(item.get('title', '')) +
                                  '</span> <span class="status-badge status-check">待补原始来源</span></li>')
    evidence_html = ''
    if evidence_rows:
        warning = f' 仍有 {missing_evidence} 条要闻未能从日报回溯来源。' if missing_evidence else ''
        evidence_state = (f'<span class="status-badge status-check">{missing_evidence} 条待补</span>'
                          if missing_evidence else '<span class="status-badge status-open">全部可回溯</span>')
        evidence_html = (f'<details class="digest-sources">'
                         f'<summary><span>🔎 本期来源与证据索引</span>{evidence_state}</summary>'
                         f'<p class="source-note">优先展示日报中可回溯的原始来源；{warning}</p>'
                         f'<ol>' + ''.join(evidence_rows) + '</ol></details>')

    # Upcoming / forecast
    upcoming_html = ''
    if data['upcoming_table']:
        upcoming_title = data.get('upcoming_title', '🗓️ 下期预告' if dtype == 'weekly' else '🗓️ 下月预告')
        upcoming_html = f'<h2 class="section">{upcoming_title}</h2>\n\n<table>\n'
        for i, row in enumerate(data['upcoming_table']):
            tag = 'th' if i == 0 else 'td'
            upcoming_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
        upcoming_html += '</table>\n'

    # Trends
    trends_html = ''
    if data['trends']:
        trends_html = '<h2 class="section">📊 趋势总结</h2>\n\n<table>\n'
        for i, row in enumerate(data['trends']):
            tag = 'th' if i == 0 else 'td'
            trends_html += '<tr>' + ''.join(f'<{tag}>{md_inline(c)}</{tag}>' for c in row) + '</tr>\n'
        trends_html += '</table>\n'

    # Rich sections (monthly report)
    rich_html = ''
    if data.get('rich_sections'):
        for sec in data['rich_sections']:
            # Title already includes emoji, don't duplicate
            title = f'AI趋势观察 · {sec["title"]}' if dtype == 'monthly' else sec['title']
            rich_html += f'<h2 class="section">{title}</h2>\n\n'
            rich_html += _render_md_block(sec['raw_lines'])
            rich_html += '\n'

    og_label = '文博资讯周报' if dtype == 'weekly' else '文博资讯月报'
    url_slug = f'{dtype}-{data["ref_date"]}'

    # Count display: use items count, or fall back to overview-based text
    item_count = len(data['items'])
    if item_count == 0 and data.get('rich_sections'):
        count_text = '综合周报'
    elif item_count > 0:
        count_text = f'共 {item_count} 条要闻'
    else:
        count_text = ''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>{og_label} | {data['date_range']}</title>
<meta property="og:title" content="{og_label} | {data['date_range']}">
<meta property="og:description" content="{data['date_range']} {og_label}{'，' + count_text if count_text else ''}">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/reports/{url_slug}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
{CSS}
</head>
<body>

<header>
  <h1>{emoji} {og_label}</h1>
  <p class="meta">{data['date_range']} ｜ {count_text}</p>
  <p style="margin-top:4px;font-size:.85em"><a href="../index.html">← 返回目录</a></p>
</header>

{overview_html}

{monthly_reading_note}

{items_html}

{upcoming_html}

{trends_html}

{rich_html}

{evidence_html}

<hr>

<p><em>{data['footer']}</em></p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 每日早 7:13（北京时间）自动更新 ｜ <a href="../sources.html">信源与方法</a></p>
</footer>

</body>
</html>'''
    return html


# ───────────────── 首页构建 ─────────────────

def build_index(daily_reports, weekly_reports=None, monthly_reports=None, recruitment_data=None, intern_data=None):
    """Rebuild index.html with daily, weekly, monthly, and recruitment sections."""
    if weekly_reports is None:
        weekly_reports = []
    if monthly_reports is None:
        monthly_reports = []

    daily_reports = sorted(daily_reports, key=lambda r: r['date'], reverse=True)
    latest_daily_href = f"reports/{daily_reports[0]['date']}.html" if daily_reports else "#daily-list"

    # Daily cards — build list, limit to latest 3 by default
    DAILY_LIMIT = 2
    card_items = []
    for i, r in enumerate(daily_reports):
        total = r['domestic_count'] + r['international_count']
        badge = '<span class="badge">最新</span>' if i == 0 else ''
        card_items.append(f'''
<a class="day-card" href="reports/{r['date']}.html">
  <span class="date">📅 {r['date']}</span>
  <span class="weekday">{r['weekday']}</span>
{badge}
  <div class="count">📰 共 {total} 条 ｜ 国内 {r['domestic_count']} + 国际 {r['international_count']}</div>
</a>''')

    latest_cards = '\n'.join(card_items[:DAILY_LIMIT])
    older_cards_html = ''
    if len(card_items) > DAILY_LIMIT:
        older_count = len(card_items) - DAILY_LIMIT
        older_cards_joined = '\n'.join(card_items[DAILY_LIMIT:])
        older_cards_html = f'''
<div class="older-cards" style="display:none;">
{older_cards_joined}
</div>
<button class="show-more-btn" onclick="toggleOlder(this)" data-expand-text="📅 展开更早的日报（{older_count} 天）" data-collapse-text="📅 收起">📅 展开更早的日报（{older_count} 天）</button>'''

    # Weekly cards — build list, limit to latest 1 by default
    weekly_card_items = []
    WEEKLY_LIMIT = 1
    weekly_reports = sorted(weekly_reports, key=lambda r: r['ref_date'], reverse=True)
    for r in weekly_reports:
        w_count = len(r['items'])
        if w_count == 0 and r.get('rich_sections'):
            w_count_text = '综合周报'
        elif w_count > 0:
            w_count_text = f'共 {w_count} 条要闻'
        else:
            w_count_text = ''
        weekly_card_items.append(f'''
<a class="day-card weekly-card" href="reports/weekly-{r['ref_date']}.html">
  <span class="date">📰 {r['date_range']}</span>
  <div class="count">📋 {w_count_text}</div>
</a>''')
    weekly_latest = '\n'.join(weekly_card_items[:WEEKLY_LIMIT])
    weekly_older_html = ''
    if len(weekly_card_items) > WEEKLY_LIMIT:
        w_older_count = len(weekly_card_items) - WEEKLY_LIMIT
        weekly_older_html = f'''
<div class="older-cards" style="display:none;">
{'\n'.join(weekly_card_items[WEEKLY_LIMIT:])}
</div>
<button class="show-more-btn" onclick="toggleOlder(this)" data-expand-text="📰 展开更早的周报（{w_older_count} 期）" data-collapse-text="📰 收起">📰 展开更早的周报（{w_older_count} 期）</button>'''

    # Monthly cards — build list, limit to latest 1 by default
    monthly_card_items = []
    MONTHLY_LIMIT = 1
    monthly_reports = sorted(monthly_reports, key=lambda r: r['ref_date'], reverse=True)
    for r in monthly_reports:
        monthly_card_items.append(f'''
<a class="day-card monthly-card" href="reports/monthly-{r['ref_date']}.html">
  <span class="date">📊 {r['date_range']}</span>
  <div class="count">📋 共 {len(r['items'])} 条要闻</div>
</a>''')
    monthly_latest = '\n'.join(monthly_card_items[:MONTHLY_LIMIT])
    monthly_older_html = ''
    if len(monthly_card_items) > MONTHLY_LIMIT:
        m_older_count = len(monthly_card_items) - MONTHLY_LIMIT
        monthly_older_html = f'''
<div class="older-cards" style="display:none;">
{'\n'.join(monthly_card_items[MONTHLY_LIMIT:])}
</div>
<button class="show-more-btn" onclick="toggleOlder(this)" data-expand-text="📊 展开更早的月报（{m_older_count} 期）" data-collapse-text="📊 收起">📊 展开更早的月报（{m_older_count} 期）</button>'''

    index_css = """<style>
  :root {
    --bg: #f5f0eb; --card: #fff; --text: #2c2416; --muted: #8b7355;
    --accent: #8b4513; --tag-bg: #f0e6d3; --border: #e0d5c1;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1a1815; --card: #252320; --text: #e8e0d0; --muted: #9b8b7a;
      --accent: #d4a76a; --tag-bg: #2a2520; --border: #3a3530;
    }
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.7;
    padding: 16px; max-width: 720px; margin: 0 auto;
  }
  header {
    text-align: center; padding: 32px 0 20px;
    border-bottom: 2px solid var(--accent); margin-bottom: 24px;
  }
  header h1 { font-size: 1.6em; letter-spacing: .05em; }
  header p.sub { color: var(--muted); font-size: .9em; margin-top: 4px; }
  /* Search */
  .search-wrap { display: flex; gap: 8px; margin-bottom: 20px; }
  .search-wrap input {
    flex: 1; min-width: 0; padding: 12px 16px;
    font-size: .95em; border: 1px solid var(--border);
    border-radius: 24px; background: var(--card); color: var(--text);
    outline: none; transition: border-color .2s;
    -webkit-appearance: none;
  }
  .search-wrap input:focus { border-color: var(--accent); }
  .search-wrap input::placeholder { color: var(--muted); opacity: .7; }
  .search-submit {
    flex: 0 0 auto; padding: 0 16px; border: 1px solid var(--accent); border-radius: 24px;
    background: var(--accent); color: #fff; font: inherit; font-size: .88em; cursor: pointer;
    transition: opacity .15s, transform .15s;
  }
  .search-submit:hover { opacity: .88; transform: translateY(-1px); }
  /* Section headers */
  .section-header {
    font-size: 1.05em; color: var(--accent); margin: 28px 0 12px;
    padding-bottom: 8px; border-bottom: 2px solid var(--border);
    display: flex; align-items: center; gap: 8px;
  }
  .section-header .count-badge {
    font-size: .75em; background: var(--tag-bg); color: var(--muted);
    padding: 2px 10px; border-radius: 10px; font-weight: normal;
  }
  a.day-card {
    background: var(--card); border-radius: 10px; padding: 18px 20px;
    margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06);
    border: 1px solid var(--border);
    display: block; text-decoration: none; color: var(--text);
    transition: transform .15s, box-shadow .15s, border-color .15s;
  }
  a.day-card:hover { transform: translateY(-2px); box-shadow: 0 5px 14px rgba(60,40,20,.10); border-color: var(--accent); }
  a.day-card:active { transform: scale(.98); }
  a.day-card.hidden { display: none; }
  a.day-card .date { font-weight: 700; font-size: 1.1em; color: var(--accent); }
  a.day-card .weekday { color: var(--muted); font-size: .85em; margin-left: 8px; }
  a.day-card .badge {
    display: inline-block; background: var(--accent); color: #fff;
    font-size: .72em; padding: 2px 8px; border-radius: 10px;
    margin-left: 6px; vertical-align: middle;
  }
  a.day-card .count { font-size: .82em; color: var(--muted); margin-top: 4px; }
  a.day-card .match-preview {
    font-size: .8em; color: var(--muted); margin-top: 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  footer {
    text-align: center; padding: 32px 0 20px;
    color: var(--muted); font-size: .8em;
    border-top: 1px solid var(--border); margin-top: 24px;
  }
  footer a { color: var(--accent); }
  .empty { text-align: center; color: var(--muted); padding: 36px 0; font-size: .9em; }
  /* Collapsible sections */
  .section-header.collapsible {
    cursor: pointer; user-select: none;
    position: relative; padding-right: 28px;
  }
  .section-header.collapsible:hover { color: var(--text); }
  .section-header.collapsible::after {
    content: '▾'; position: absolute; right: 4px; top: 50%;
    transform: translateY(-50%); font-size: .85em;
    transition: transform .2s; color: var(--muted);
  }
  .section-header.collapsible.collapsed::after {
    transform: translateY(-50%) rotate(-90deg);
  }
  .section-body { transition: opacity .15s; }
  .section-body.hidden { display: none; }
  /* Show more button */
  .show-more-btn {
    display: block; width: 100%; padding: 10px;
    background: var(--card); border: 1px dashed var(--border);
    border-radius: 10px; color: var(--accent); font-size: .88em;
    cursor: pointer; margin-bottom: 14px; text-align: center;
    transition: background .15s;
  }
  .show-more-btn:hover { background: var(--tag-bg); }
  .older-cards { }
  .collapse-floating {
    display: none; position: fixed; right: max(16px, calc((100vw - 720px) / 2 + 16px)); bottom: 18px;
    z-index: 20; padding: 9px 14px; border: 1px solid var(--accent); border-radius: 999px;
    background: var(--accent); color: #fff; font: inherit; font-size: .82em; cursor: pointer;
    box-shadow: 0 4px 14px rgba(0,0,0,.22); transition: transform .15s, opacity .15s;
  }
  .collapse-floating.show { display: block; }
  .collapse-floating:hover { transform: translateY(-2px); }
  .quick-nav { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: -4px 0 18px; }
  .quick-nav a { display: inline-block; padding: 5px 11px; border: 1px solid var(--border); border-radius: 999px; background: var(--card); color: var(--text); text-decoration: none; font-size: .8em; transition: border-color .15s, color .15s, background .15s; }
  .quick-nav a:hover { border-color: var(--accent); color: var(--accent); background: var(--tag-bg); }
  .quick-nav a.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  @media (max-width: 520px) {
    body { padding: 12px; }
    header { padding-top: 24px; }
    header h1 { font-size: 1.4em; }
    .quick-nav { justify-content: flex-start; }
    a.day-card { padding: 15px 16px; }
    .collapse-floating { right: 12px; bottom: 14px; }
  }
</style>"""

    # Build section blocks
    weekly_block = ''
    if weekly_card_items:
        weekly_block = f'<div class="section-header collapsible" onclick="toggleSection(this)">📰 周报 <span class="count-badge">{len(weekly_reports)} 期</span></div>\n<div class="section-body"><div id="weekly-list">{weekly_latest}\n{weekly_older_html}</div></div>\n'
    else:
        weekly_block = '<div class="section-header collapsible collapsed" onclick="toggleSection(this)">📰 周报 <span class="count-badge">0 期</span></div>\n<div class="section-body hidden"><div class="empty">周报每周日发布，敬请期待</div></div>\n'

    monthly_block = ''
    if monthly_card_items:
        monthly_block = f'<div class="section-header collapsible" onclick="toggleSection(this)">📊 月报 <span class="count-badge">{len(monthly_reports)} 期</span></div>\n<div class="section-body"><div id="monthly-list">{monthly_latest}\n{monthly_older_html}</div></div>\n'
    else:
        monthly_block = '<div class="section-header collapsible collapsed" onclick="toggleSection(this)">📊 月报 <span class="count-badge">0 期</span></div>\n<div class="section-body hidden"><div class="empty">月报每月 1 日发布，敬请期待</div></div>\n'

    # Recruitment section (正职 + 实习 as sub-sections)
    recruitment_block = ''
    has_jobs = recruitment_data and recruitment_data.get('sections')
    has_intern = intern_data and intern_data.get('sections')

    total_jobs = sum(len(s['items']) for s in recruitment_data['sections']) if has_jobs else 0
    total_intern = sum(len(s['items']) for s in intern_data['sections']) if has_intern else 0
    total_all = total_jobs + total_intern

    if has_jobs or has_intern:
        # Job sub-card
        jobs_card = ''
        if has_jobs:
            section_labels = [f'{s["icon"]} {s["category"]} {len(s["items"])} 条' for s in recruitment_data['sections']]
            section_summary = ' · '.join(section_labels)
            jobs_card = f'''<a class="day-card" href="jobs.html">
  <span class="date">💼 正职招聘</span>
  <div class="count">{section_summary} ｜ {total_jobs} 个岗位 · 更新于 {recruitment_data['update_date']}</div>
</a>
'''
        # Intern sub-card
        intern_card = ''
        if has_intern:
            intern_labels = [f'{s["icon"]} {s["category"]} {len(s["items"])} 条' for s in intern_data['sections']]
            intern_summary = ' · '.join(intern_labels)
            intern_card = f'''<a class="day-card" href="intern.html">
  <span class="date">🌱 实习招聘</span>
  <div class="count">{intern_summary} ｜ {total_intern} 个岗位 · 更新于 {intern_data['update_date']}</div>
</a>
'''
        recruitment_block = f'''<div class="section-header collapsible" onclick="toggleSection(this)">💼 招聘信息 <span class="count-badge">{total_all} 个岗位</span></div>
<div class="section-body">
{intern_card}{jobs_card}
</div>
'''
    else:
        recruitment_block = '<div class="section-header collapsible collapsed" onclick="toggleSection(this)">💼 招聘信息 <span class="count-badge">0 岗位</span></div>\n<div class="section-body hidden"><div class="empty">招聘信息每两日更新，敬请期待</div></div>\n'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>每日文博资讯 | 文博·考古·博物馆行业日报</title>
<meta name="description" content="每日文博资讯 — 国内外文物博物馆、考古、文化遗产领域每日推送。AI 自动采集编撰，每天早 7:13（北京时间）更新，已有 {len(daily_reports)} 天日报">
<meta name="keywords" content="文博,考古,博物馆,文化遗产,文物,文博资讯,文博日报,每日文博">
<link rel="canonical" href="https://zhangheng666.top/">
<meta property="og:title" content="每日文博资讯">
<meta property="og:description" content="国内外文物博物馆 · 考古 · 文化遗产 · 每日推送">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://zhangheng666.top/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
<meta name="twitter:card" content="summary_large_image">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="文博日报">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "每日文博资讯",
  "url": "https://zhangheng666.top/",
  "description": "国内外文物博物馆、考古、文化遗产领域每日推送",
  "potentialAction": {{
    "@type": "SearchAction",
    "target": "https://zhangheng666.top/search.html?q={{search_term_string}}",
    "query-input": "required name=search_term_string"
  }}
}}
</script>
{index_css}
</head>
<body>

<header>
  <h1>🏛️ 每日文博资讯</h1>
<p class="sub">国内外文物博物馆 · 考古 · 文化遗产 ｜ 每日推送</p>
</header>

<main>

<nav class="quick-nav" aria-label="主要栏目">
  <a class="primary" href="{latest_daily_href}">今日精选</a>
  <a href="#daily-list">日报档案</a>
  <a href="command-center/">🛰️ 数字驾驶舱</a>
  <a href="intern.html">实习</a>
  <a href="jobs.html">招聘</a>
</nav>

<form class="search-wrap" action="search.html" method="get" role="search">
  <input type="search" name="q" placeholder="🔍 输入关键词，查看全部相关文章" autocomplete="off" aria-label="搜索新闻" required>
  <button class="search-submit" type="submit">搜索</button>
</form>

<div class="section-header collapsible" onclick="toggleSection(this)">📅 日报 <span class="count-badge">{len(daily_reports)} 天</span></div>
<div class="section-body">
<div id="daily-list">
{latest_cards}
{older_cards_html}
</div>
</div>

{weekly_block}

{monthly_block}

{recruitment_block}

</main>

<footer>
  <p>由 <a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> 自动生成 ｜ <a href="command-center/">数字驾驶舱</a> ｜ 每日早 7:13（北京时间）更新 ｜ <a href="sources.html">信源与方法</a> ｜ <a href="about.html">关于本站</a></p>
</footer>

<button id="collapse-floating" class="collapse-floating" type="button" onclick="collapseActiveSection()" aria-label="收起已展开的历史栏目">↑ 收起本栏</button>

</body>
</html>'''
    # Inject JS (toggles + search)
    html = html.replace('</body>', '''<script>
let activeOlderButton = null;
function showCollapseFloating(btn) {
  activeOlderButton = btn;
  const floating = document.getElementById('collapse-floating');
  if (floating) floating.classList.add('show');
}
function hideCollapseFloating(btn) {
  if (btn && activeOlderButton !== btn) return;
  activeOlderButton = null;
  const floating = document.getElementById('collapse-floating');
  if (floating) floating.classList.remove('show');
}
function toggleSection(header) {
  header.classList.toggle('collapsed');
  const body = header.nextElementSibling;
  if (body && body.classList.contains('section-body')) {
    body.classList.toggle('hidden');
    if (body.classList.contains('hidden') && activeOlderButton && body.contains(activeOlderButton)) {
      const olderDiv = activeOlderButton.previousElementSibling;
      if (olderDiv && olderDiv.classList.contains('older-cards')) olderDiv.style.display = 'none';
      hideCollapseFloating(activeOlderButton);
    }
  }
}
function toggleOlder(btn) {
  const olderDiv = btn.previousElementSibling;
  if (olderDiv && olderDiv.classList.contains('older-cards')) {
    const isHidden = olderDiv.style.display === 'none';
    olderDiv.style.display = isHidden ? '' : 'none';
    if (isHidden) {
      btn.textContent = btn.getAttribute('data-collapse-text') || '收起 ▲';
      showCollapseFloating(btn);
    } else {
      btn.textContent = btn.getAttribute('data-expand-text') || btn.textContent;
      hideCollapseFloating(btn);
    }
  }
}
function collapseActiveSection() {
  const btn = activeOlderButton;
  if (!btn) return;
  const olderDiv = btn.previousElementSibling;
  const header = btn.closest('.section-body')?.previousElementSibling;
  if (olderDiv && olderDiv.classList.contains('older-cards')) {
    olderDiv.style.display = 'none';
    btn.textContent = btn.getAttribute('data-expand-text') || btn.textContent;
  }
  hideCollapseFloating(btn);
  if (header && header.classList.contains('section-header')) {
    header.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
}
</script>
</body>''')
    return html


# ───────────────── 搜索结果页 ─────────────────

def build_search_html():
    """Generate the standalone keyword search page.

    The page reads the unified search index in the browser, then flattens
    matching article items into one deduplicated result stream.
    """
    search_css = '''<style>
  .search-head { text-align: left; padding-bottom: 14px; }
  .search-head h1 { font-size: 1.35em; }
  .search-head .back { font-size: .86em; }
  .search-wrap { display: flex; gap: 8px; margin: 18px 0 10px; }
  .search-wrap input { flex: 1; min-width: 0; padding: 11px 14px; border: 1px solid var(--border); border-radius: 24px; background: var(--card); color: var(--text); font: inherit; outline: none; }
  .search-wrap input:focus { border-color: var(--accent); }
  .search-submit { flex: 0 0 auto; padding: 0 16px; border: 1px solid var(--accent); border-radius: 24px; background: var(--accent); color: #fff; font: inherit; font-size: .88em; cursor: pointer; }
  .search-summary { color: var(--muted); font-size: .84em; margin: 12px 0 16px; }
  .search-result { background: var(--card); border: 1px solid var(--border); border-radius: 10px; margin: 0 0 10px; overflow: hidden; }
  .search-result summary { cursor: pointer; list-style: none; padding: 14px 16px; color: var(--text); font-size: 1em; font-weight: 600; line-height: 1.55; }
  .search-result summary::-webkit-details-marker { display: none; }
  .search-result summary::after { content: '＋'; float: right; margin-left: 12px; color: var(--muted); font-size: 1.05em; font-weight: 400; line-height: 1.45; }
  .search-result[open] summary { color: var(--accent); }
  .search-result[open] summary::after { content: '−'; }
  .search-detail { border-top: 1px solid var(--border); padding: 0 16px 14px; }
  .search-meta { color: var(--muted); font-size: .78em; }
  .search-kind { display: inline-block; padding: 2px 7px; margin-right: 6px; border-radius: 9px; background: var(--tag-bg); color: var(--accent); }
  .search-snippet { color: var(--muted); font-size: .86em; line-height: 1.65; margin: 6px 0; }
  .search-source { color: var(--muted); font-size: .78em; margin-top: 8px; }
  .search-source a { margin-right: 8px; }
  .search-open { margin: 10px 0 0; font-size: .82em; }
  .search-open a { text-decoration: none; }
  .search-tag { display: inline-block; margin: 2px 5px 0 0; padding: 1px 6px; border-radius: 8px; background: var(--tag-bg); color: var(--muted); font-size: .72em; }
  mark { background: #f0c040; color: inherit; border-radius: 2px; padding: 0 1px; }
  .search-empty { text-align: center; color: var(--muted); padding: 42px 0; }
  @media (max-width: 520px) {
    .search-wrap { gap: 6px; }
    .search-submit { padding: 0 13px; }
    .search-result summary { padding: 13px 14px; }
    .search-detail { padding: 0 14px 13px; }
  }
</style>'''

    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>搜索文博新闻 | 每日文博资讯</title>
<meta name="description" content="搜索每日文博资讯中的考古、博物馆、文物保护、文化遗产和行业新闻。">
<meta property="og:title" content="搜索文博新闻 | 每日文博资讯">
<meta property="og:description" content="从每日文博资讯历史档案中集中检索相关报道。">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
__SEARCH_CSS__
</head>
<body>
<header class="search-head">
  <p><a class="back" href="index.html">← 返回首页</a></p>
  <h1>🔎 搜索文博新闻</h1>
  <p class="meta">从日报、周报、月报及招聘档案中集中检索</p>
</header>

<main>
  <form class="search-wrap" action="search.html" method="get" role="search">
    <input id="query" name="q" type="search" placeholder="输入关键词，例如：国家文物局、考古、数字化" autocomplete="off" aria-label="搜索关键词" required>
    <button class="search-submit" type="submit">搜索</button>
  </form>
  <p id="summary" class="search-summary">请输入关键词开始搜索。</p>
  <section id="results" aria-live="polite"><div class="search-empty">正在加载搜索索引…</div></section>
</main>

<footer>
  <p><a href="index.html">每日文博资讯</a> ｜ 每日早 7:13（北京时间）自动更新 ｜ <a href="sources.html">信源与方法</a></p>
</footer>

<script>
const queryInput = document.getElementById('query');
const summary = document.getElementById('summary');
const results = document.getElementById('results');
const typeLabels = {daily: '日报', weekly: '周报', monthly: '月报', jobs: '招聘', intern: '实习'};

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, function(ch) {
    return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[ch];
  });
}
function escapeRegExp(value) {
  const slash = String.fromCharCode(92);
  const special = '.^$*+?()[]{}|' + slash;
  return Array.from(value).map(function(ch) { return special.includes(ch) ? slash + ch : ch; }).join('');
}
function cleanText(value) {
  return String(value || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/!\\[[^\\]]*\\]\\([^)]*\\)/g, ' ')
    .replace(/\\[([^\\]]+)\\]\\([^)]*\\)/g, '$1')
    .replace(/\\*\\*/g, '')
    .replace(/\\s+/g, ' ')
    .trim();
}
function highlight(value, words) {
  let out = escapeHtml(value);
  words.slice().sort((a, b) => b.length - a.length).forEach(function(word) {
    if (!word) return;
    const safe = escapeHtml(word);
    out = out.replace(new RegExp('(' + escapeRegExp(safe) + ')', 'gi'), '<mark>$1</mark>');
  });
  return out;
}
function compact(value) { return String(value || '').toLowerCase().replace(/[^0-9a-z\\u4e00-\\u9fff]+/g, ''); }
function sourceList(sources) {
  return (Array.isArray(sources) ? sources : []).map(function(source) {
    const item = typeof source === 'string' ? {name: source, url: ''} : source;
    const name = escapeHtml(item.name || '');
    return item.url ? '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + name + '</a>' : name;
  }).filter(Boolean).join(' · ');
}
function itemText(item) {
  return [item.title, item.body, item.commentary, (item.progress || ''), (item.tags || []).join(' '), (item.sources || []).map(function(s) { return typeof s === 'string' ? s : s.name; }).join(' ')].join(' ');
}
function matches(text, words) {
  const lower = String(text || '').toLowerCase();
  return words.every(function(word) { return lower.includes(word); });
}
function snippet(text, words) {
  const clean = cleanText(text);
  if (!clean) return '';
  const lower = clean.toLowerCase();
  const hit = words.map(function(word) { return lower.indexOf(word); }).filter(function(index) { return index >= 0; }).sort(function(a, b) { return a - b; })[0] || 0;
  const start = Math.max(0, hit - 48);
  const end = Math.min(clean.length, start + 180);
  return (start > 0 ? '…' : '') + highlight(clean.slice(start, end), words) + (end < clean.length ? '…' : '');
}
function renderHit(hit, words) {
  const record = hit.record;
  const item = hit.item;
  const title = item ? item.title : record.title;
  const href = record.path + (item && item.id ? '#' + item.id : '');
  const body = item ? (item.body || item.commentary || item.progress || '') : (record.text || '');
  const tags = item && Array.isArray(item.tags) ? item.tags.map(function(tag) { return '<span class="search-tag">#' + escapeHtml(tag) + '</span>'; }).join('') : '';
  const sources = item ? sourceList(item.sources) : '';
  return '<details class="search-result">' +
    '<summary>' + highlight(title, words) + '</summary>' +
    '<div class="search-detail">' +
      '<div class="search-meta"><span class="search-kind">' + escapeHtml(typeLabels[record.type] || '档案') + '</span>' + escapeHtml(record.date || '') + '</div>' +
      (body ? '<p class="search-snippet">' + snippet(body, words) + '</p>' : '') +
      (tags ? '<div>' + tags + '</div>' : '') +
      (sources ? '<div class="search-source">来源：' + sources + '</div>' : '') +
      '<p class="search-open"><a href="' + escapeHtml(href) + '">打开所在报告 →</a></p>' +
    '</div>' +
    '</details>';
}
function renderSearch(data, rawQuery) {
  const query = String(rawQuery || '').trim().toLowerCase();
  queryInput.value = rawQuery || '';
  if (!query) {
    summary.textContent = '请输入关键词开始搜索。';
    results.innerHTML = '<div class="search-empty">搜索日报、周报、月报及招聘档案中的完整关键词。</div>';
    return;
  }
  const words = query.split(/\\s+/).filter(Boolean);
  const hits = [];
  const seen = new Set();
  const records = (Array.isArray(data) ? data : []).slice().sort(function(a, b) { return String(b.date || '').localeCompare(String(a.date || '')); });
  records.forEach(function(record) {
    const items = Array.isArray(record.items) ? record.items : [];
    if (items.length) {
      items.forEach(function(item) {
        if (!matches(itemText(item), words)) return;
        const key = compact(item.title) || (record.path + (item.id || ''));
        if (seen.has(key)) return;
        seen.add(key);
        hits.push({record: record, item: item});
      });
    } else if (matches([record.title, record.text].join(' '), words)) {
      const key = 'page:' + record.path;
      if (!seen.has(key)) {
        seen.add(key);
        hits.push({record: record, item: null});
      }
    }
  });
  summary.textContent = '找到 ' + hits.length + ' 条匹配新闻（已合并重复标题，优先显示最新记录）';
  results.innerHTML = hits.length ? hits.map(function(hit) { return renderHit(hit, words); }).join('') : '<div class="search-empty">没有找到匹配新闻。可以换一个更具体或更常见的关键词。</div>';
}

const params = new URLSearchParams(location.search);
const initialQuery = params.get('q') || '';
fetch('search-index.json').then(function(response) {
  if (!response.ok) throw new Error('search index unavailable');
  return response.json();
}).then(function(data) {
  renderSearch(data, initialQuery);
}).catch(function() {
  summary.textContent = '搜索索引暂时不可用。';
  results.innerHTML = '<div class="search-empty">请稍后刷新重试。</div>';
});
</script>
</body>
</html>'''
    return html.replace('__SEARCH_CSS__', CSS + search_css)


# ───────────────── sitemap.xml ─────────────────

def build_sitemap(daily_reports, weekly_reports=None, monthly_reports=None):
    """Generate sitemap.xml listing all pages."""
    from datetime import datetime

    base = 'https://zhangheng666.top'
    urls = []

    # Homepage
    urls.append(f'''  <url>
    <loc>{base}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/search.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>''')

    # Jobs & intern pages
    urls.append(f'''  <url>
    <loc>{base}/jobs.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/about.html</loc>
    <changefreq>yearly</changefreq>
    <priority>0.3</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/sources.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/intern.html</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/heatmap.html</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/digital-trends.html</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>''')
    urls.append(f'''  <url>
    <loc>{base}/command-center/</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>''')

    # Daily reports
    for r in sorted(daily_reports, key=lambda r: r['date'], reverse=True):
        urls.append(f'''  <url>
    <loc>{base}/reports/{r['date']}.html</loc>
    <lastmod>{r['date']}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>''')

    # Weekly reports
    if weekly_reports:
        for r in sorted(weekly_reports, key=lambda r: r['ref_date'], reverse=True):
            urls.append(f'''  <url>
    <loc>{base}/reports/weekly-{r['ref_date']}.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>''')

    # Monthly reports
    if monthly_reports:
        for r in sorted(monthly_reports, key=lambda r: r['ref_date'], reverse=True):
            urls.append(f'''  <url>
    <loc>{base}/reports/monthly-{r['ref_date']}.html</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>''')

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>'''
    return xml


# ───────────────── 关于页面 ─────────────────

def build_about_html():
    """Generate the about page."""
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>关于本站 | 每日文博资讯</title>
<meta name="description" content="每日文博资讯 — 网站介绍、内容来源、编撰流程与免责声明">
<link rel="canonical" href="https://zhangheng666.top/about.html">
<meta property="og:title" content="关于本站 | 每日文博资讯">
<meta property="og:description" content="每日文博资讯 — 国内外文物博物馆、考古、文化遗产领域每日推送">
<meta property="og:image" content="https://zhangheng666.top/cover.png">
<meta property="og:url" content="https://zhangheng666.top/about.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="每日文博资讯">
{CSS}
</head>
<body>
<main>
<header>
  <h1>🏛️ 关于本站</h1>
  <p class="meta">每日文博资讯 · 网站说明</p>
  <p style="margin-top:4px;font-size:.85em"><a href="index.html">← 返回首页</a></p>
</header>

<h2 class="section">📖 这是什么</h2>
<p>「每日文博资讯」是一个聚焦<strong>文物、博物馆、考古、文化遗产</strong>领域的每日资讯站点，通常精选约 4–8 条国内外要闻，内容充足时适当增加，新闻不足时宁缺毋滥，附带专业点评与趋势总结。内容由 AI 自动采集、筛选并编撰，不以凑数为目标。</p>

<h2 class="section">🕐 更新节奏</h2>
<table>
<tr><th>栏目</th><th>更新频率</th></tr>
<tr><td>📅 日报</td><td>每天早 7:13（北京时间）</td></tr>
<tr><td>📰 周报</td><td>每周日</td></tr>
<tr><td>📊 月报</td><td>每月 1 日</td></tr>
<tr><td>💼 招聘 / 🌱 实习</td><td>每两天（偶数日期）</td></tr>
</table>

<h2 class="section">🗞️ 信源说明</h2>
<p>本站采用<strong>可执行的信源分级机制</strong>：A级为国家文物局、新华社、央视、中国文物报、专业机构和博物馆官网，以及 UNESCO、ICOM、ICCROM 等国际组织；B级为 Reuters、AP、BBC、专业刊物和研究机构，用于高质量补充；公众号、百家号、头条号、搜索引擎跳转页和聚合转载页为 C 级，仅作线索，不能进入新的最终稿。完整登记表和历史档案审计见<a href="sources.html">《信源与方法》</a>。</p>

<h2 class="section">🤖 AI 编撰流程与声明</h2>
<blockquote><strong>重要声明：</strong>本站内容由 AI 自动生成，未经人工逐条核实。AI 可能出错——请务必以文末附带的原始来源链接为准，重要信息请查证官方原文后再引用。</blockquote>
<p>流程分为两条：行业地图先逐一巡检固定的 6 个全国权威信源，把符合文博范围的全部新内容写入独立监测库；日报再从监测库和更广的 A/B 级来源中按实质增量与行业价值精选。两者分别去重、核验和执行质量门禁，因此一条内容没有进入日报，不会从地图样本中消失；地方媒体数量变化也不会直接改变地区排名。日报按“国内要闻 / 国际要闻”组织，标签归一到九类主题。招聘和实习使用独立的来源标签，不与新闻 A/B/C 等级混用。历史内容不会被静默删除；若旧稿含未登记来源，页面会明确标为历史档案。若发现错误，欢迎在 GitHub 仓库提 issue 反馈。</p>

<h2 class="section">🔒 隐私</h2>
<p>本站为纯静态网站：<strong>不收集任何个人信息、不使用 Cookie、不接入任何统计或广告脚本</strong>。你只是阅读，我们只是展示。</p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ <a href="index.html">返回首页</a></p>
</footer>
</main>
</body>
</html>'''
    return html


def build_sources_html(daily_reports, heat_data=None):
    """Generate a reader-facing source registry and archive audit page."""
    stats = source_stats(daily_reports)
    heat_data = heat_data or {}
    heat_stats = heat_data.get('stats') or {}
    panel_cards = []
    for row in map_source_registry_rows():
        entry = row['entryUrls'][0] if row['entryUrls'] else '#'
        panel_cards.append(f'''<div class="panel-card">
  <h3><a href="{entry}" target="_blank" rel="noopener">{row['name']}</a></h3>
  <p>{row['role']}</p>
  <p class="source-note">监测域名：{'、'.join(row['domains'])}</p>
</div>''')
    tier_cards = []
    for row in source_registry_rows():
        tier = row['tier']
        domains = '、'.join(row['domains'])
        tier_cards.append(f'''<div class="registry-card source-{tier.lower()}">
  <h3>{row['label']}</h3>
  <p>{row['description']}</p>
  <p class="source-note">登记范围：{domains}</p>
</div>''')
    legacy_hosts = sorted(stats['hosts'].items(), key=lambda x: (-x[1], x[0]))
    legacy_lines = []
    for host, count in legacy_hosts:
        if source_info('https://' + host)['tier'] == 'C':
            legacy_lines.append(f'<li>{host}（{count} 次）</li>')
    legacy_html = ''.join(legacy_lines[:24]) or '<li>当前没有待复核来源</li>'
    audit_class = ' legacy' if stats['C'] else ''
    audit_text = ('历史档案中仍存在未登记来源；它们被保留用于完整记录，但不会进入新的自动发布。'
                  if stats['C'] else '当前档案来源均已登记，可按 A/B 级发布门槛继续维护。')
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>信源与方法 | 每日文博资讯</title>
<meta name="description" content="每日文博资讯的信源分级、内容筛选、去重和核验方法。">
{CSS}
<style>
  .registry-card {{ border: 1px solid var(--border); border-left: 4px solid var(--accent); background: var(--card); border-radius: 10px; padding: 14px; margin: 12px 0; }}
  .registry-card h3 {{ margin: 0 0 5px; }}
  .registry-card.source-c {{ border-left-color: #b91c1c; }}
  .audit-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 14px 0; }}
  .audit-cell {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 10px; text-align: center; }}
  .audit-cell strong {{ display: block; font-size: 1.25em; }}
  .panel-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:12px 0; }}
  .panel-card {{ border:1px solid var(--border); border-radius:10px; padding:13px; background:var(--card); }}
  .panel-card h3 {{ margin:0 0 4px; font-size:1em; }}
  .panel-card p {{ margin:3px 0; }}
  @media (max-width: 520px) {{ .audit-grid {{ grid-template-columns: repeat(2, 1fr); }} .panel-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<main>
<header>
  <h1>🧭 信源与方法</h1>
  <p class="meta">把“可信”变成可检查的发布规则</p>
  <p style="margin-top:4px;font-size:.85em"><a href="index.html">← 返回首页</a></p>
</header>

<div class="quality-banner{audit_class}"><strong>档案审计：</strong>已检查 {len(daily_reports)} 份日报、{stats['total']} 个来源链接；A级 {stats['A']} 个，B级 {stats['B']} 个，待复核 {stats['C']} 个。{audit_text}</div>

<h2 class="section">🛰️ 地图固定信源池</h2>
<p>行业关注地图与日报已经分开：地图每天逐一巡检下面 6 个固定来源，收录其中全部符合文博范围的新内容；日报仍从固定池和更广的 A/B 级来源中做编辑精选。地方官网或临时媒体报道不会直接改变地区排名。</p>
<div class="panel-grid">{''.join(panel_cards)}</div>
<div class="quality-banner"><strong>迁移状态：</strong>监测库现有 {heat_stats.get('totalMonitoredRecords', 0)} 条固定池记录，其中 {heat_stats.get('legacyBaselineRecords', 0)} 条来自历史日报迁移，历史覆盖率不可审计；已尝试逐源巡检 {heat_stats.get('coverageDays', 0)} 天，其中 6 源全部完成 {heat_stats.get('completeCoverageDays', 0)} 天。地图会按 7/30/90 日窗口分别显示覆盖率，覆盖不足时不主张严谨地区排名。</div>

<h2 class="section">📚 信源分级</h2>
<p>以下是日报和其他栏目使用的更广发布白名单，不等同于地图固定信源池。</p>
{''.join(tier_cards)}

<h2 class="section">💼 招聘与实习来源标签</h2>
<p>招聘栏目不使用新闻 A/B/C 等级，而按投递可靠性显示“官方来源”“高校/就业平台”“主流招聘平台”“二手线索”。无论来源标签如何，申请前都应打开原文确认岗位仍在招收，并以原公告的截止时间和投递方式为准。</p>

<h2 class="section">🧪 发布门槛</h2>
<ol>
  <li>搜索引擎只负责发现候选，最终链接必须指向登记来源。</li>
  <li>涉及政策、考古年代、文物数量、归还争议和招聘截止日期，优先使用A级原文。</li>
  <li>B级来源只作专业补充；找不到可核验原文时宁可不发，不为凑数收录。</li>
  <li>每个事件按 canonical URL、标题和实体去重；只有实质新进展才重复出现。</li>
  <li>事实摘要和编辑判断分开，无法确认的内容标记“待核”，不把推测写成定论。</li>
  <li>地图先完成固定池全量巡检，再生成日报；没有进入日报的合格固定池内容仍保留在监测库。</li>
</ol>

<h2 class="section">🗺️ 地图事项重要性分档</h2>
<p>地图的“事项级别”不是模型自由评分，而是由标题和标签命中规则触发：<strong>重大</strong>包括国家级政策、世界遗产、重大考古、一级文物或文物安全；<strong>重要</strong>包括一般考古、文物返还追索或重要保护工程；<strong>关注</strong>包括数字化、科技保护、重要展览或开馆；讲座、报名、征集和常规活动归为<strong>一般</strong>。它只说明本页样本中的关注优先级，不等于事件的社会价值排名。</p>

<h2 class="section">📊 当前档案统计</h2>
<div class="audit-grid">
  <div class="audit-cell"><strong>{stats['total']}</strong>来源链接</div>
  <div class="audit-cell"><strong>{stats['A']}</strong>A级来源</div>
  <div class="audit-cell"><strong>{stats['B']}</strong>B级来源</div>
  <div class="audit-cell"><strong>{stats['C']}</strong>待复核</div>
</div>
<p class="source-note">C级来源只在历史档案中展示为待复核，不代表本站推荐或认可。</p>
<ul>{legacy_html}</ul>

<h2 class="section">🤖 AI 编撰边界</h2>
<p>本站由原生 Codex 自动生成页面，但 AI 不是事实来源，也不替代原文核验。重要信息请点击来源链接回到发布机构或专业媒体原文；发现错误可在项目仓库提交 issue。</p>

<footer><p><a href="index.html">返回首页</a> ｜ <a href="about.html">关于本站</a></p></footer>
</main>
</body>
</html>'''


def build_dedup_index(daily_reports, days=30):
    """生成近 days 天日报标题索引(新→旧),供 auto_task 日报去重比对(防重复机制,2026-08-21)。
    只含 日期+id+标题,紧凑格式,单次 read_file 可全读。仅本地使用(.gitignore 排除,不进 public 站点)。
    """
    sorted_r = sorted(daily_reports, key=lambda r: r['date'], reverse=True)[:days]
    out = []
    for r in sorted_r:
        items = [{'id': it['id'], 'title': it['title']} for it in r['domestic'] + r['international']]
        out.append({'date': r['date'], 'items': items})
    path = os.path.join(SITE_DIR, 'dedup-index.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)  # 紧凑单行,控制体积保证单次 read_file 全读
    n = sum(len(x['items']) for x in out)
    print(f'Dedup index: {path} ({len(out)} 天, {n} 条标题,供 auto_task 去重)')
    return path


# ───────────────── 主流程 ─────────────────

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)

    md_files = glob.glob(os.path.join(MD_DIR, '*.md'))
    if not md_files:
        print('No markdown files found in', MD_DIR)
        return

    daily_reports = []
    weekly_reports = []
    monthly_reports = []

    for md_path in sorted(md_files):
        fname = os.path.basename(md_path)
        print(f'Building: {fname}')

        # Read first line to detect type (avoids filename encoding issues on Windows)
        with open(md_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()

        # Determine type by title content
        if '周报' in first_line:
            data = parse_digest(md_path, 'weekly')
            if not data['ref_date']:
                print('  SKIP: could not parse weekly date')
                continue
            from automation.periodic_reports import load_periodic_data
            override = load_periodic_data(SITE_DIR, data)
            if override:
                data = override
            weekly_reports.append(data)
            print(f'  -> parsed weekly-{data["ref_date"]}.html')

        elif '月报' in first_line:
            data = parse_digest(md_path, 'monthly')
            if not data['ref_date']:
                print('  SKIP: could not parse monthly date')
                continue
            from automation.periodic_reports import load_periodic_data
            override = load_periodic_data(SITE_DIR, data)
            if override:
                data = override
            monthly_reports.append(data)
            print(f'  -> parsed monthly-{data["ref_date"]}.html')

        else:
            # Daily report - parse first, build HTML later (need prev/next)
            data = parse_md(md_path)
            if not data['date']:
                print(f'  SKIP: could not parse date')
                continue
            print(f'  -> parsed {data["date"]}')
            daily_reports.append(data)

    # Digests are rendered after all daily reports are parsed so legacy
    # summaries can recover matching original sources from the full archive.
    for data in weekly_reports:
        html = build_digest_html(data, daily_reports)
        html_path = os.path.join(REPORTS_DIR, f'weekly-{data["ref_date"]}.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
    for data in monthly_reports:
        html = build_digest_html(data, daily_reports)
        html_path = os.path.join(REPORTS_DIR, f'monthly-{data["ref_date"]}.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

    # Build a unified search index. It covers editorial archives and the two
    # practical job boards, not only daily reports.
    search_data = []
    for r in daily_reports:
        items = []
        for item in r['domestic'] + r['international']:
            items.append({
                'id': item.get('id', ''),
                'number': item.get('number', ''),
                'title': item['title'],
                'body': item['body'][:200] if item['body'] else '',
                'commentary': item['commentary'],
                'tags': item.get('tags', []),
                'sources': [{'name': s.get('name', ''), 'url': s.get('url', '')} for s in item.get('sources', [])],
            })
        search_data.append({
            'type': 'daily',
            'path': f"reports/{r['date']}.html",
            'title': r['title'],
            'date': r['date'],
            'weekday': r['weekday'],
            'domestic_count': r['domestic_count'],
            'international_count': r['international_count'],
            'items': items
        })
    for r in weekly_reports + monthly_reports:
        digest_text = ' '.join([r.get('title', ''), r.get('overview', '')])
        digest_text += ' ' + ' '.join(i.get('title', '') + ' ' + i.get('body', '') + ' ' + i.get('progress', '') for i in r.get('items', []))
        digest_text += ' ' + ' '.join(s.get('title', '') + ' ' + ' '.join(s.get('raw_lines', [])) for s in r.get('rich_sections', []))
        if r.get('layout') == 'periodic-v2':
            periodic_rows = []
            for section in r.get('sections', []):
                periodic_rows.append(section.get('title', '') + ' ' + section.get('summary', ''))
                periodic_rows.extend(
                    row.get('title', '') + ' ' + row.get('summary', '') + ' ' + row.get('whyImportant', '')
                    for row in section.get('items', [])
                )
            periodic_rows.extend(
                row.get('title', '') + ' ' + row.get('summary', '') + ' ' + row.get('whyImportant', '')
                for row in r.get('highlights', [])
            )
            digest_text += ' ' + ' '.join(periodic_rows)
        prefix = 'weekly' if r['type'] == 'weekly' else 'monthly'
        search_data.append({
            'type': r['type'],
            'path': f"reports/{prefix}-{r['ref_date']}.html",
            'title': r['title'],
            'date': r['ref_date'],
            'text': digest_text,
            'items': r.get('items', []),
        })

    # The map corpus is independent from the 4–8 editorial daily selections.
    monitoring_corpus = load_monitoring_corpus()
    heat_data, heat_audit = build_heatmap_data(monitoring_corpus)
    heat_path = os.path.join(SITE_DIR, 'heatmap-data.json')
    with open(heat_path, 'w', encoding='utf-8') as f:
        json.dump(heat_data, f, ensure_ascii=False, indent=2)
    st = heat_data['stats']
    print(f'Heatmap data V3: {heat_path} | 固定池 {st["totalMonitoredRecords"]} 条,纳入地域 {st["includedProvincialRecords"]} 条/{st["provincialEvents"]} 个事件,巡检尝试 {st["coverageDays"]} 天/完整 {st["completeCoverageDays"]} 天')
    _audit_print(heat_audit)
    heat_html = build_heatmap_html()
    heat_html_path = os.path.join(SITE_DIR, 'heatmap.html')
    with open(heat_html_path, 'w', encoding='utf-8') as f:
        f.write(heat_html)
    print(f'Heatmap page: {heat_html_path}')

    # Dedup index for auto_task daily anti-repetition (近30天标题,本地使用)
    build_dedup_index(daily_reports)

    # Build daily report HTML with prev/next navigation
    sorted_daily = sorted(daily_reports, key=lambda r: r['date'])
    for i, r in enumerate(sorted_daily):
        prev_r = sorted_daily[i - 1] if i > 0 else None
        next_r = sorted_daily[i + 1] if i < len(sorted_daily) - 1 else None
        html = build_report_html(r, prev_report=prev_r, next_report=next_r)
        html_path = os.path.join(REPORTS_DIR, f"{r['date']}.html")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
    print(f'Daily reports: {len(sorted_daily)} pages built')

    # Parse recruitment data
    recruitment_data = None
    if os.path.exists(JOBS_MD):
        recruitment_data = parse_jobs(JOBS_MD)
        if recruitment_data and recruitment_data.get('sections'):
            rec_html = build_jobs_html(recruitment_data)
            rec_path = os.path.join(SITE_DIR, 'jobs.html')
            with open(rec_path, 'w', encoding='utf-8') as f:
                f.write(rec_html)
            total = sum(len(s['items']) for s in recruitment_data['sections'])
            print(f'Jobs: {rec_path} ({total} jobs)')
        else:
            print('Jobs: no listings found in', JOBS_MD)
    else:
        print('Jobs: no source file at', JOBS_MD)

    # Parse internship data
    intern_data = None
    if os.path.exists(INTERN_MD):
        intern_data = parse_jobs(INTERN_MD)
        if intern_data and intern_data.get('sections'):
            intern_html = build_jobs_html(intern_data, page_type='intern')
            intern_path = os.path.join(SITE_DIR, 'intern.html')
            with open(intern_path, 'w', encoding='utf-8') as f:
                f.write(intern_html)
            total_intern = sum(len(s['items']) for s in intern_data['sections'])
            print(f'Intern: {intern_path} ({total_intern} internships)')
        else:
            print('Intern: no listings found in', INTERN_MD)
    else:
        print('Intern: no source file at', INTERN_MD)

    def append_job_search_record(data, kind, path):
        if not data:
            return
        parts = [data.get('summary', '')]
        for section in data.get('sections', []):
            parts.append(section.get('category', ''))
            for item in section.get('items', []):
                parts.extend([item.get('institution', ''), item.get('position', ''),
                              item.get('education', ''), item.get('location', ''),
                              item.get('deadline', ''), item.get('note', ''),
                              item.get('link_text', '')])
        search_data.append({
            'type': kind,
            'path': path,
            'title': '文博实习招聘' if kind == 'intern' else '文博招聘信息',
            'date': data.get('update_date', ''),
            'text': ' '.join(parts),
            'items': [],
        })

    append_job_search_record(recruitment_data, 'jobs', 'jobs.html')
    append_job_search_record(intern_data, 'intern', 'intern.html')
    idx_path = os.path.join(SITE_DIR, 'search-index.json')
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(search_data, f, ensure_ascii=False, indent=2)
    print(f'Search index: {idx_path} ({len(search_data)} searchable pages)')

    search_html = build_search_html()
    search_path = os.path.join(SITE_DIR, 'search.html')
    with open(search_path, 'w', encoding='utf-8') as f:
        f.write(search_html)
    print(f'Search page: {search_path}')

    # Build index with all sections
    index_html = build_index(daily_reports, weekly_reports, monthly_reports, recruitment_data, intern_data)
    index_path = os.path.join(SITE_DIR, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_html)
    print(f'Index: {index_path} ({len(daily_reports)} 日报 + {len(weekly_reports)} 周报 + {len(monthly_reports)} 月报 + {"招聘" if recruitment_data else "无招聘"} + {"实习" if intern_data else "无实习"})')

    # Build about page
    about_html = build_about_html()
    about_path = os.path.join(SITE_DIR, 'about.html')
    with open(about_path, 'w', encoding='utf-8') as f:
        f.write(about_html)
    print(f'About: {about_path}')

    sources_html = build_sources_html(daily_reports, heat_data)
    sources_path = os.path.join(SITE_DIR, 'sources.html')
    with open(sources_path, 'w', encoding='utf-8') as f:
        f.write(sources_html)
    print(f'Sources: {sources_path}')

    # Build robots.txt
    robots_txt = 'User-agent: *\nAllow: /\n\nSitemap: https://zhangheng666.top/sitemap.xml\n'
    with open(os.path.join(SITE_DIR, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(robots_txt)
    print('robots.txt: written')

    # Build sitemap.xml
    sitemap_xml = build_sitemap(daily_reports, weekly_reports, monthly_reports)
    sitemap_path = os.path.join(SITE_DIR, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write(sitemap_xml)
    print(f'Sitemap: {sitemap_path} ({len(daily_reports)} daily + {len(weekly_reports)} weekly + {len(monthly_reports)} monthly)')

    # Ordinary builds are intentionally side-effect-free for data collection.
    # The formal daily job runs --incremental explicitly before this page-only
    # rebuild; --build-only remains available for manual page rebuilds.
    try:
        import digital_trend
        digital_trend.main(['--build-only'])
    except Exception as e:
        print(f'Digital trends: SKIP ({e})')

    # Build the independent dashboard after the data artifacts are ready.
    try:
        import build_command_center
        build_command_center.main()
    except Exception as e:
        print(f'Command center: SKIP ({e})')

    print('\nDone! Run push to deploy.')


if __name__ == '__main__':
    main()

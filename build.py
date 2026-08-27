#!/usr/bin/env python3
"""
Build HTML reports from Markdown files and rebuild index.html.
Handles daily reports (日报), weekly digests (周报), and monthly digests (月报).
Usage: python build.py
"""
import os, re, glob, json, sys
from urllib.parse import quote
from datetime import date as _date, datetime, timedelta, timezone

from automation.governance import (
    SOURCE_GROUPS, canonical_url, source_info, source_link_html,
    source_registry_rows, source_stats,
)

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
    '陕西历史博物馆':'陕西','南京博物院':'江苏','河南博物院':'河南','湖北省博物馆':'湖北','浙江省博物馆':'浙江',
    '浙博':'浙江',   # 2026-08-21 加:浙江省博物馆简称(标题层)。修"太平年·天下同宁"大展标题含浙博、正文列出国博/陕历博/南博等出借方→误归北京+浙江双省。标题含"浙博"=主办馆在浙,标题层直接命中,正文出借方列表不再参与;事件地=浙江,出借方≠事件地。
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
# 顺序有讲究:扫描按此顺序,标签词命中第一个大类即停("国际展览"→展览 而非 国际交流)。
THEMES = {
    '考古':   ('考古', '考古发现', '考古学', '田野考古', '公共考古', '科技考古', '考古科技',
              '考古遗址', '旧石器时代', '古文字', '简牍', '水下考古', '考古新发现', '发掘', '考古展'),
    '博物馆': ('博物馆', '博物馆伦理', '博物馆建设', '博物馆日', '馆藏', '文博', '博物馆学会'),
    '展览':   ('展览', '特展', '临展', '巡展', '文物展', '艺术展', '国际展览', '大展'),
    '文物保护': ('文物保护', '文物安全', '文物修复', '修复', '保护技术', '科技保护', '古建修缮', '壁画保护', '预防性保护'),
    '文化遗产': ('文化遗产', '文化遗产保护', '世界遗产', '世遗', '非遗', '非物质文化遗产', '工业遗产',
              '海洋文化遗产', '农业遗产', '历史街区', '文明探源', '中华文明探源', '探源工程', '遗产大会'),
    '数字化': ('数字化', '数字文博', '数字科技', '数字展示', '虚拟展览', '科技', 'AI', '人工智能', '元宇宙', '大数据'),
    '文物追索': ('文物追索', '文物归还', '文物返还', '文物回归', '流失文物', '追缴', '返还'),
    '国际交流': ('国际', '国际合作', '国际交流', '国际文化交流', '国际传播', '文化外交',
              '对外交流', '文明互鉴', '文明桥梁', '海外', '出国', 'UNESCO'),
    '政策行业': ('政策', '行业动态', '国家文物局', '立法', '规划', '标准', '人才', '教育', '出版',
              '学术', '方法论', '文创', '产业', '文旅', '报告', '会议', '论坛'),
}

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
    th = _scan(title)
    if th:
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


def theme_of(tags):
    """把标签归一到 THEMES 大主题类(去重,保序)。

    按 THEMES 定义顺序扫描,每个标签词命中第一个大类即归属;
    地名/遗址(浙江/三星堆)/未命中任何大类的标签直接忽略(它们用于省份归类,不用于主题)。
    """
    themes = []
    for t in tags or []:
        for name, words in THEMES.items():
            if any(w in t for w in words):
                if name not in themes:
                    themes.append(name)
                break
    return themes


def build_heatmap_data(daily_reports):
    """从全部日报解析结果生成热点地图数据。

    只遍历 domestic 段;国际段不进。无省份归属的国内新闻不展示(用户确认)。
    热力公式: item_weight = 1 + 标题🔥数; decayed = weight * DECAY^days;
    多省归属时 share = decayed / len(provinces) 均分给各省。
    返回 (heatmap_data_dict, audit_lines)。
    """
    audit = []
    # 按日期归并,asOf = 最新日报日期(可复现,不依赖系统时间)
    dates = sorted({r['date'] for r in daily_reports})
    as_of = dates[-1] if dates else ''
    as_of_dt = None
    from datetime import date as _date
    if as_of:
        y, m, d = map(int, as_of.split('-'))
        as_of_dt = _date(y, m, d)

    # province short name -> {heat, count, items}
    prov_agg = {p: {'heat': 0.0, 'count': 0, 'items': []} for p in PROVINCES}

    for r in daily_reports:
        rdate = r['date']
        days = (as_of_dt - _date(*map(int, rdate.split('-')))).days if as_of_dt else 0
        for item in r['domestic']:
            att = attribute_item(item)
            provs = att['provinces']
            weight = 1 + item['title'].count('🔥')
            decayed = weight * (DECAY ** days)
            if not provs:
                # 无省份归属(全国性/对外交流/未识别)→ 不展示
                audit.append(('national' if att['tier'] in ('national', 'outreach') else 'unassigned',
                              rdate, item['id'], item['title'], '-', att['tier']))
                continue
            share = round(decayed / len(provs), 2)
            entry = {
                'date': rdate,
                'id': item['id'],
                'title': item['title'],
                'weight': weight,
                'pcount': len(provs),   # 前端时间窗口重算需按省份数均分
                'share': share,
                'url': f"reports/{rdate}.html#{item['id']}",
                'tags': item.get('tags', []),   # 原始标签(主题筛选用)
                'themes': theme_of(item.get('tags', [])),  # 归一化主题大类(省份摘要统计)
            }
            for p in provs:
                if p in prov_agg:
                    prov_agg[p]['heat'] = round(prov_agg[p]['heat'] + share, 2)
                    prov_agg[p]['count'] += 1
                    prov_agg[p]['items'].append(entry)
            audit.append(('prov' if len(provs) <= 1 else 'multi',
                          rdate, item['id'], item['title'], '/'.join(provs), att['tier']))

    # 排序:province 按 heat 降序;items 按 date 降序(同一省多日期)
    prov_list = []
    for p, agg in prov_agg.items():
        if agg['items']:
            agg['items'].sort(key=lambda e: e['date'], reverse=True)
            prov_list.append({'name': p, 'heat': agg['heat'], 'count': agg['count'],
                              'items': agg['items']})
    prov_list.sort(key=lambda x: x['heat'], reverse=True)

    # 归省条目数取唯一(多省条目出现在多省 items 列表,不能直接求和)
    unique_items = set()
    for x in prov_list:
        for it in x['items']:
            unique_items.add((it['date'], it['id']))

    stats = {
        'totalDomestic': sum(len(r['domestic']) for r in daily_reports),
        'provincialItems': len(unique_items),
        'internationalExcluded': sum(len(r['international']) for r in daily_reports),
        'maxHeat': round(prov_list[0]['heat'], 2) if prov_list else 0.0,
    }

    data = {
        'generated': as_of or '',
        'asOf': as_of,
        'start': dates[0] if dates else '',   # 最早日报日期(前端时间窗口用)
        'decay': DECAY,
        'stats': stats,
        'provinces': prov_list,
    }
    return data, audit


def _audit_print(audit):
    """打印归属审核日志,便于人工抽检。"""
    prov_n = sum(1 for a in audit if a[0] == 'prov')
    multi_n = sum(1 for a in audit if a[0] == 'multi')
    national_n = sum(1 for a in audit if a[0] == 'national')
    unassigned_n = sum(1 for a in audit if a[0] == 'unassigned')
    print(f'[HEATMAP] 归省 {prov_n} 条 | 多省均分 {multi_n} 条 | 全国性/对外 {national_n} 条 | 未识别 {unassigned_n} 条')
    print('[HEATMAP] WARN 抽检重点(正文/多省/未识别):')
    for kind, rdate, iid, title, provs, tier in audit:
        if tier in ('site', 'body', 'unassigned') or kind == 'multi':
            print(f'  [{tier}] {rdate} #{iid} {title[:36]} → {provs}')


def build_heatmap_html():
    """生成热点地图详情页 heatmap.html(ECharts 5 + 本地 china.json,内联 CSS/JS)。

    数据在运行时从 heatmap-data.json 加载(渐进增强:地图组件/数据任一加载失败
    都保留 Top10 快速入口)。暗色模式用 matchMedia 监听,切换时重建图表。
    """
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script>if(location.protocol==='http:' && !/^(localhost|127[.]0[.]0[.]1)$/.test(location.hostname))location.replace('https://'+location.host+location.pathname+location.search)</script>
<title>文博热点地图 | 每日文博资讯</title>
<meta name="description" content="中国文博热点地图 — 全国文物博物馆、考古、文化遗产热点省份热度可视化">
<link rel="canonical" href="https://zhangheng666.top/heatmap.html">
<meta property="og:title" content="文博热点地图 | 每日文博资讯">
<meta property="og:description" content="全国文物博物馆、考古、文化遗产热点省份热度可视化">
<style>
  :root {
    --bg: #f6f5f1; --card: #ffffff; --text: #2b2b2b;
    --muted: #8a867c; --border: #e5e2d9; --accent: #8a5a2b; --tag-bg: #f0ece2;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#17161a; --card:#22222a; --text:#ecebe6; --muted:#9a97a8; --border:#33323c; --accent:#c9a06a; --tag-bg:#2c2c36; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
  }
  .wrap { max-width: 720px; margin: 0 auto; padding: 0 18px 40px; }
  header { padding: 24px 0 14px; }
  header h1 { font-size: 1.35em; }
  .back { display: inline-block; margin-bottom: 10px; font-size: .85em; color: var(--accent); text-decoration: none; }
  .back:hover { text-decoration: underline; }
  #map { width: 100%; height: 55vh; min-height: 320px; background: transparent; }
  .meta { font-size: .78em; color: var(--muted); margin: 6px 0 14px; }
  .note { font-size: .78em; color: var(--muted); margin: 4px 0 14px; }
  h2.sec { font-size: 1em; margin: 20px 0 10px; }
  .win-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
  .win-tab {
    padding: 6px 14px; border-radius: 999px; font-size: .85em;
    background: var(--tag-bg); border: 1px solid var(--border);
    color: var(--text); cursor: pointer; transition: all .15s;
  }
  .win-tab:hover { background: var(--card); }
  .win-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    padding: 6px 12px; border-radius: 999px; font-size: .85em;
    background: var(--tag-bg); border: 1px solid var(--border);
    cursor: pointer; transition: background .15s, transform .1s;
  }
  .chip:hover { background: var(--card); transform: translateY(-1px); }
  .chip b { color: var(--accent); }
  .chip .heat { color: var(--muted); font-weight: 400; margin-left: 3px; }
  .detail {
    display: none; margin-top: 16px; padding: 16px;
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  }
  .detail.show { display: block; }
  .detail .d-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .detail .d-name { font-size: 1.2em; font-weight: 700; }
  .detail .d-heat { color: var(--accent); font-weight: 700; }
  .detail .d-count { color: var(--muted); font-size: .85em; }
  .detail .d-close { margin-left: auto; cursor: pointer; color: var(--muted); border: none; background: none; font-size: 1em; }
  .detail .d-themes { margin: 6px 0 2px; font-size: .8em; color: var(--muted); }
  .detail .d-themes .th {
    display: inline-block; background: var(--tag-bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 1px 10px; margin: 2px 4px 2px 0;
    color: var(--text); font-size: inherit; font-family: inherit; line-height: 1.7;
    cursor: pointer; transition: all .15s;
  }
  .detail .d-themes .th:hover { border-color: var(--accent); }
  .detail .d-themes .th.on { background: var(--accent); border-color: var(--accent); color: #fff; }
  .detail .d-items { margin-top: 12px; }
  .detail .d-items .it { padding: 9px 0; border-bottom: 1px dashed var(--border); }
  .detail .d-items .it:last-child { border-bottom: none; }
  .detail .d-items a { color: var(--accent); text-decoration: none; font-size: .9em; }
  .detail .d-items a:hover { text-decoration: underline; }
  .detail .d-items .it-date { display: block; font-size: .75em; color: var(--muted); margin-top: 2px; }
  .err { color: var(--muted); text-align: center; padding: 24px 0; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="back" href="./">← 返回首页</a>
    <h1>🗺️ 中国文博热点地图</h1>
    <p class="meta">按每日日报标题🔥加权、随时间衰减生成 · 点击省份或热力球查看当地全部报道</p>
  </header>
  <div id="map"><div class="err" id="map-fallback">地图加载中…</div></div>
  <p class="note">热力值 = 该省相关报道热度(🔥加权)随时间衰减后的累加 · 热力球越大越红热度越高，越小越浅热度越低 · 仅统计国内报道</p>
  <p class="note">🔥 = 一般关注 · 🔥🔥 = 较高关注 · 🔥🔥🔥 = 高关注 · 热度仅反映本站日报报道的相对关注度，不代表官方统计或社会整体关注度</p>

  <div class="win-tabs" id="wintabs">
    <button class="win-tab" data-days="7">近7天</button>
    <button class="win-tab active" data-days="30">近30天</button>
    <button class="win-tab" data-days="90">近90天</button>
  </div>

  <h2 class="sec">🔥 热点 Top 10</h2>
  <div class="chips" id="chips"></div>

  <div class="detail" id="detail">
    <div class="d-head">
      <span class="d-name" id="d-name"></span>
      <span class="d-heat" id="d-heat"></span>
      <span class="d-count" id="d-count"></span>
      <button class="d-close" id="d-close" aria-label="关闭">✕</button>
    </div>
    <div class="d-themes" id="d-themes"></div>
    <div class="d-items" id="d-items"></div>
  </div>
</div>

<script src="lib/echarts.min.js"></script>
<script>
// 简称 → geojson 全称(与 china.json 的 properties.name 一一对应)
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

var RAW = null;         // heatmap-data.json 全量数据
var VIEW = null;        // 当前时间窗口重算后的省份列表
var chart = null;
var CUR_WINDOW = { label: '近30天', days: 30 };   // 默认窗口(与 HTML 中 active 一致)
var CUR_THEME = null;   // 省份摘要的当前主题筛选(null=全部);切时间窗口时保留
var AS_OF_UTC = 0;
var AS_OF_STR = '';
var CENTROID = {};   // 简称 → [lng,lat] 省几何中心(取自 china.json properties.centroid)

// 时间窗口定义
var WINDOWS = [
  { key: '7d',  label: '近7天',   days: 7 },
  { key: '30d', label: '近30天',  days: 30 },
  { key: '90d', label: '近90天', days: 90 }
];

function parseUTC(s) {
  var a = s.split('-');
  return Date.UTC(+a[0], +a[1] - 1, +a[2]);
}

function isDark() { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }

function palette() {
  var dark = isDark();
  return {
    // 热力球色带(低→高: 浅→深红,深浅两种主题均适配;低端也保证与底色地图可区分)
    ballColors: dark
      ? ['#5c5148', '#8a5f33', '#c07a2c', '#e0483a', '#ff5f5f']
      : ['#e8ddd0', '#f2b28c', '#e8782e', '#d23a1f', '#a01313'],
    mapFill: dark ? '#26262f' : '#eae7df',      // 底色地图统一中性色,不随热力变色
    mapBorder: dark ? 'rgba(255,255,255,.14)' : 'rgba(255,255,255,.7)',
    ballBorder: dark ? 'rgba(255,255,255,.45)' : 'rgba(255,255,255,.85)', // 球描边,贴地色时也能被识别
    ballLabel: dark ? '#d5d2d8' : '#5a544c',
    tooltipBg: dark ? '#22222a' : '#ffffff',
    tooltipText: dark ? '#eee' : '#333',
    labelText: dark ? '#999' : '#777'
  };
}

// 按时间窗口重算省份热力(与 build.py 同公式: weight × DECAY^天数 / 省份数)
function computeWindow(days) {
  var byName = {};
  RAW.provinces.forEach(function(p){
    var heat = 0, count = 0, items = [];
    p.items.forEach(function(it){
      var since = (AS_OF_UTC - parseUTC(it.date)) / 86400000;
      if (days !== null && since >= days) return;   // 窗口外报道跳过
      heat += it.weight * Math.pow(0.93, since) / it.pcount;
      count += 1;
      items.push(it);
    });
    if (count > 0) byName[p.name] = { name: p.name, heat: heat, count: count, items: items };
  });
  var list = [];
  for (var k in byName) list.push(byName[k]);
  list.sort(function(a, b){ return b.heat - a.heat; });
  return list;
}

function findProvince(name) {
  var v = VIEW || [];
  for (var i = 0; i < v.length; i++) if (v[i].name === name) return v[i];
  return null;
}

function showDetail(shortName) {
  var prov = findProvince(shortName);
  var det = document.getElementById('detail');
  if (!prov) { det.classList.remove('show'); return; }
  document.getElementById('d-name').textContent = prov.name;
  document.getElementById('d-heat').textContent = '热度 ' + prov.heat.toFixed(2);
  // 主题 chips:统计该省当前窗口报道的归一化主题大类频次,点击可筛选
  var thCount = {};
  prov.items.forEach(function(it){
    (it.themes || []).forEach(function(t){ thCount[t] = (thCount[t] || 0) + 1; });
  });
  var themesBox = document.getElementById('d-themes');
  var thHtml = '<button class="th' + (CUR_THEME === null ? ' on' : '') + '" data-t="__all__">全部</button>';
  for (var t in thCount) {
    if (!Object.prototype.hasOwnProperty.call(thCount, t)) continue;
    thHtml += '<button class="th' + (CUR_THEME === t ? ' on' : '') + '" data-t="' + t + '">' + t + ' ×' + thCount[t] + '</button>';
  }
  themesBox.innerHTML = thHtml ? '主要主题：' + thHtml : '';
  themesBox.querySelectorAll('.th').forEach(function(btn){
    btn.addEventListener('click', function(){
      var t = btn.getAttribute('data-t');
      CUR_THEME = (t === '__all__' || t === CUR_THEME) ? null : t;  // 再点同主题=取消筛选
      showDetail(shortName);   // 重开,刷新 chips 激活态与列表
    });
  });
  // 按当前主题筛选(数据已由 build.py 归一化,纯前端过滤,无需重分类)
  var filtered = CUR_THEME
    ? prov.items.filter(function(it){ return (it.themes || []).indexOf(CUR_THEME) !== -1; })
    : prov.items;
  document.getElementById('d-count').textContent = CUR_THEME
    ? filtered.length + ' / ' + prov.count + ' 条报道 · ' + CUR_THEME
    : prov.count + ' 条报道';
  // 高🔥新闻置顶(weight 降序,同权按日期新→旧)
  var sorted = filtered.slice().sort(function(a, b){
    if (b.weight !== a.weight) return b.weight - a.weight;
    return b.date < a.date ? -1 : (b.date > a.date ? 1 : 0);
  });
  var box = document.getElementById('d-items');
  box.innerHTML = '';
  sorted.forEach(function(it){
    var div = document.createElement('div');
    div.className = 'it';
    var a = document.createElement('a');
    a.href = it.url; a.textContent = it.title;
    var d = document.createElement('span');
    d.className = 'it-date'; d.textContent = it.date;
    div.appendChild(a); div.appendChild(d);
    box.appendChild(div);
  });
  det.classList.add('show');
  det.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

function renderTop10() {
  var box = document.getElementById('chips');
  box.innerHTML = '';
  var top = (VIEW || []).slice(0, 10);
  if (!top.length) {
    box.innerHTML = '<div class="err">该时间段暂无热点数据，换个时间范围试试。</div>';
    return;
  }
  top.forEach(function(p){
    var chip = document.createElement('button');
    chip.className = 'chip';
    chip.innerHTML = '<b>' + p.name + '</b> <span class="heat">' + p.heat.toFixed(1) + '</span>';
    chip.onclick = function(){ showDetail(p.name); };
    box.appendChild(chip);
  });
}

function renderMap() {
  if (!window.echarts || !window.ChinaGeo || !VIEW) {
    document.getElementById('map-fallback').innerHTML = '地图组件加载失败，可用上方省份快速入口查看热点。';
    return;
  }
  var p = palette();
  var el = document.getElementById('map');
  if (chart) chart.dispose();
  chart = echarts.init(el);
  var maxHeat = VIEW.length ? VIEW[0].heat : 0;
  var vmMax = Math.max(1, Math.ceil(maxHeat * 1.05));
  var labelMin = maxHeat * 0.15;   // 热度≥最大值15%的省常显名称,防几十个标签互相遮挡
  // 球直径与 visualMap 的 symbolSize:[5,38] 同一线性插值 → 决定省名放球内还是球旁
  var rOf = function(v){ return 5 + (v / vmMax) * 33; };
  var LABEL_INSIDE_R = 26;   // symbolSize=球直径:直径≥26px(半径13,装得下2字10px省名)时省名装球内,否则小字标球旁
  // 热力球数据:位置=各省几何中心(centroid),value=[lng, lat, heat]
  var ballData = [];
  VIEW.forEach(function(pr){
    var c = CENTROID[pr.name];
    if (!c) return;
    var v = Math.round(pr.heat * 100) / 100;
    ballData.push({
      name: pr.name, value: [c[0], c[1], v],
      // 大球:省名白字装进球内(深色描边+暗影保证在各种球色上都可读);小球放不下:小字标在球右侧,画面更干净
      label: rOf(v) >= LABEL_INSIDE_R
        ? { position: 'inside', color: '#fff', fontWeight: 700, fontSize: 10,
            textBorderColor: 'rgba(0,0,0,.35)', textBorderWidth: 1,
            textShadowColor: 'rgba(0,0,0,.5)', textShadowBlur: 2 }
        : { position: 'right', distance: 4, color: p.ballLabel, fontSize: 9,
            fontWeight: 400, opacity: .85 }
    });
  });
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item', backgroundColor: p.tooltipBg, borderColor: 'rgba(0,0,0,.1)',
      textStyle: { color: p.tooltipText, fontSize: 13 },
      formatter: function(params){
        var short = GEO2SHORT[params.name] || params.name;
        var d = findProvince(short);
        if (!d) return '<b>' + params.name + '</b><br/>该时间段暂无数据';
        return '<b>' + d.name + '</b><br/>热度：' + d.heat.toFixed(2) + '<br/>报道：' + d.count + ' 条';
      }
    },
    geo: {
      // 关键:为 scatter 提供 'geo' 坐标系。ECharts 的 map 系列不提供可被其他系列引用的坐标系,
      // 无 geo 组件时 scatter 拿不到坐标→点不绘制(2026-08-21 修"看不到球"根因)。
      // 本组件透明+silent,只作坐标系统,视觉/悬停/点击全部交给 map 系列。
      map: 'china', roam: false,
      silent: true,
      label: { show: false },
      emphasis: { label: { show: false }, itemStyle: { areaColor: 'rgba(0,0,0,0)' } },
      itemStyle: { areaColor: 'rgba(0,0,0,0)', borderColor: 'rgba(0,0,0,0)' },
      zlevel: 0
    },
    series: [
      {
        // 底色地图:统一中性色,热力信息全部交给热力球(小面积省市不会被色块掩盖)
        type: 'map', map: 'china', roam: false, selectedMode: false,
        label: { show: false },
        emphasis: {
          // 划过省份不再高亮色块、不再弹大号省名(热力已由球的大小/颜色表达,2026-08-21 用户要求)
          label: { show: false },
          itemStyle: { areaColor: p.mapFill }
        },
        itemStyle: { borderColor: p.mapBorder, borderWidth: 0.6, areaColor: p.mapFill },
        data: []
      },
      {
        // 热力球:大小与颜色均由 heat 值映射(visualMap seriesIndex=[1] 只作用本系列)
        name: '热点', type: 'scatter', coordinateSystem: 'geo', zlevel: 2,
        symbol: 'circle', data: ballData,
        label: {
          // 位置/字号/颜色由每条数据自带的 label 覆盖:大球省名在球内、小球小字在球旁(2026-08-21 用户要求)
          show: true,
          formatter: function(p){ return p.value[2] >= labelMin ? p.name : ''; }
        },
        labelLayout: { hideOverlap: true },
        itemStyle: { borderColor: p.ballBorder, borderWidth: 1, shadowBlur: 8, shadowColor: 'rgba(0,0,0,.25)' },
        emphasis: {
          label: { show: true, color: p.ballLabel, fontWeight: 700, fontSize: 13 },
          itemStyle: { borderColor: '#fff', borderWidth: 1.5, shadowBlur: 14, shadowColor: 'rgba(0,0,0,.4)' }
        }
      }
    ],
    visualMap: {
      min: 0, max: vmMax,
      left: 12, bottom: 12, calculable: false, text: ['高', '低'],
      seriesIndex: [1], dimension: 2,
      inRange: { color: p.ballColors, symbolSize: [5, 38] },
      textStyle: { color: p.labelText }
    }
  });
  chart.off('click');
  chart.on('click', function(params){
    if (!params || !params.name) return;
    showDetail(GEO2SHORT[params.name] || params.name);
  });
}

function updateMeta() {
  var m = document.querySelector('.meta');
  if (m && AS_OF_STR) m.innerHTML = '按每日日报标题🔥加权、随时间衰减生成 · ' + CUR_WINDOW.label + ' · 数据截至 ' + AS_OF_STR;
}

function applyWindow(w) {
  if (!RAW) return;
  CUR_WINDOW = w;
  VIEW = computeWindow(w.days);
  document.querySelectorAll('.win-tab').forEach(function(btn){
    var v = btn.getAttribute('data-days');
    btn.classList.toggle('active', String(w.days) === v);
  });
  renderTop10();
  renderMap();
  updateMeta();
  // 详情开着时刷新到新窗口
  var det = document.getElementById('detail');
  if (det.classList.contains('show')) {
    showDetail(document.getElementById('d-name').textContent);
  }
}

// 初始化时间范围切换
document.querySelectorAll('.win-tab').forEach(function(btn){
  btn.addEventListener('click', function(){
    var v = btn.getAttribute('data-days');
    applyWindow({ label: btn.textContent, days: parseInt(v, 10) });
  });
});

// 暗色模式切换时重建图表
if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(){ renderMap(); });
}

// 加载 geojson → 注册地图
fetch('lib/china.json').then(function(r){
  return r.ok ? r.json() : Promise.reject();
}).then(function(geo){
  geo.features = geo.features.filter(function(f){ return f.properties && f.properties.name; }); // 剔除空名"十段线"单元
  window.ChinaGeo = geo;
  CENTROID = {};
  geo.features.forEach(function(f){
    var props = f.properties;
    var short = GEO2SHORT[props.name];
    if (!short || !(props.centroid || props.center)) return;
    CENTROID[short] = props.centroid || props.center;   // DataV geojson 自带省几何中心,热力球定位用
  });
  echarts.registerMap('china', geo);
  if (RAW) renderMap();
}).catch(function(){
  document.getElementById('map-fallback').innerHTML = '地图数据加载失败，可用上方省份快速入口查看热点。';
});

// 加载热力数据 → 按默认窗口初始化
fetch('heatmap-data.json').then(function(r){
  return r.ok ? r.json() : Promise.reject();
}).then(function(d){
  RAW = d;
  AS_OF_STR = d.asOf;
  AS_OF_UTC = d.asOf ? parseUTC(d.asOf) : 0;
  VIEW = computeWindow(CUR_WINDOW.days);
  renderTop10();
  document.getElementById('map-fallback').style.display = 'none';
  if (window.ChinaGeo) renderMap();
  updateMeta();
}).catch(function(){
  document.getElementById('map-fallback').innerHTML = '热力数据加载失败，请稍后刷新页面重试。';
});

document.getElementById('d-close').addEventListener('click', function(){
  document.getElementById('detail').classList.remove('show');
});
</script>
</body>
</html>'''


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

        # Section headers
        if line.startswith('## 🇨🇳 国内要闻'):
            current_section = 'domestic'
            i += 1
            continue
        elif line.startswith('## 🌍 国际要闻'):
            current_section = 'international'
            i += 1
            continue
        elif line.startswith('## 📊 今日趋势总结'):
            current_section = 'trends'
            i += 1
            continue
        elif line.startswith('## 📑 目录'):
            current_section = 'toc'
            i += 1
            continue
        elif line.startswith('## ') or line.startswith('# '):
            current_section = None
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
        src_match = re.findall(r'📎\s*\[(.+?)\]\((.+?)\)', line)
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
        # after the trends table). current_item is NOT reset on section change, so
        # only attach to it inside 国内/国际 sections; otherwise a trailing
        # blockquote would overwrite the last item's commentary.
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
                    tags_html += f' <a class="{cls}" href="../index.html?q={quote(tag)}">#{tag}</a>'

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
    international_html = render_items(data['international'], '🌍 国际要闻')

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
<meta name="description" content="{data['date']} 每日文博资讯，共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）。{data['toc_items'][0]['title'][:60] if data['toc_items'] else ''}">
<meta name="keywords" content="文博,考古,博物馆,文化遗产,文物,每日文博资讯,{data['date']}">
<link rel="canonical" href="https://zhangheng666.top/reports/{data['date']}.html">
<meta property="og:title" content="每日文博资讯 | {data['date']}">
<meta property="og:description" content="{data['date']} 每日文博资讯，共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）">
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
  <p class="meta">{data['date']} · {data['weekday']} ｜ 共 {total} 条（国内 {data['domestic_count']} + 国际 {data['international_count']}）</p>
  <p style="margin-top:4px;font-size:.85em"><a href="../index.html">← 返回目录</a></p>
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
        src_match = re.findall(r'📎\s*\[(.+?)\]\((.+?)\)', line)
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
                link_info = source_info(item['link_url'])
                link_badge = f' <span class="source-note">{link_info["tier"]}级来源</span>'
            else:
                link_badge = ''

            items_html += f'''
        <div class="job-item{row_class}">
          <div class="job-header">
            <span class="job-number">#{item['number']}</span>
            <span class="job-title">{item['institution']} — {item['position']}</span>
            {status_badge}
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
  <p class="meta">{data['update_date']} 更新 ｜ 共 {total} 个{'实习岗位' if is_intern else '岗位'} ｜ 可申请 {active_count} ｜ 已截止 {closed_count}</p>
  <p style="margin-top:4px;font-size:.85em"><a href="index.html">← 返回首页</a></p>
</header>

{summary_html}

<div class="stats-bar">
  <div class="stat-item">📋 总岗位数：<strong>{total}</strong></div>
  <div class="stat-item">🟢 可申请：<strong>{active_count}</strong></div>
  <div class="stat-item">⏰ 3天内截止：<strong>{urgent_count}</strong></div>
  <div class="stat-item">🔴 已截止：<strong>{closed_count}</strong></div>
  <div class="stat-item">🧭 待核截止：<strong>{check_count}</strong></div>
  <div class="stat-item">🔄 每两天更新一次</div>
</div>

{sections_html}

<hr>
<p style="font-size:.82em; color: var(--muted);">⚠️ 申请前请务必核对官方原文。本页保留已截止条目作为档案，但不代表仍可申请；“待核截止”表示公告未给出标准日期或需人工确认。收录范围：省级及以上博物馆、考古院所、设有考古/文博专业的高校。</p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ 招聘栏目 · 每两日更新 ｜ <a href="sources.html">信源与方法</a> ｜ <a href="about.html">关于本站</a></p>
</footer>

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


def related_digest_sources(title, daily_reports):
    """Recover evidence for legacy weekly/monthly summaries from daily items.

    New digest Markdown should carry 📎 links itself. This fallback only links
    an aggregate item when its title clearly matches a daily item title.
    """
    if not title or not daily_reports:
        return []
    target = _compact_title(title)
    if len(target) < 8:
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
            if shared:
                for source in item.get('sources', []):
                    matches.append(source)
                if matches:
                    return matches[:2]
    return []


def build_digest_html(data, daily_reports=None):
    """Generate HTML for a weekly or monthly digest."""
    dtype = data['type']
    emoji = '📰' if dtype == 'weekly' else '📊'

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
        items_html = '<h2 class="section">🔟 七月十大文博新闻</h2>\n\n'
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
            items_html += f'<tr><td class="rank">{rank}</td><td class="news-title">{md_inline(item["title"])}</td><td class="date">{date_str}</td><td class="sig">{md_inline(sig_str)}</td></tr>\n'
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
        for line in (data.get('rich_sections') or [{}])[0].get('raw_lines', []):
            match = re.match(r'###\s+(.+)', line)
            if match:
                evidence_targets.append({'title': match.group(1).strip(), 'sources': []})
    evidence_rows = []
    missing_evidence = 0
    for item in evidence_targets:
        sources = item.get('sources') or related_digest_sources(item.get('title', ''), daily_reports or [])
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
            rich_html += f'<h2 class="section">{sec["title"]}</h2>\n\n'
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
  .search-wrap {
    position: relative; margin-bottom: 20px;
  }
  .search-wrap input {
    width: 100%; padding: 12px 40px 12px 16px;
    font-size: .95em; border: 1px solid var(--border);
    border-radius: 24px; background: var(--card); color: var(--text);
    outline: none; transition: border-color .2s;
    -webkit-appearance: none;
  }
  .search-wrap input:focus { border-color: var(--accent); }
  .search-wrap input::placeholder { color: var(--muted); opacity: .7; }
  .search-wrap .clear {
    position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
    background: none; border: none; color: var(--muted); font-size: 1.2em;
    cursor: pointer; display: none; line-height: 1; padding: 4px;
  }
  .highlight { background: #f0c040; border-radius: 2px; padding: 0 1px; }
  .no-results { text-align: center; color: var(--muted); padding: 36px 0; display: none; }
  .result-count { font-size: .8em; color: var(--muted); text-align: center; margin-bottom: 12px; display: none; }
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
  /* Heatmap entry card */
  .heatmap-card {
    display: block; margin: 4px 0 18px; padding: 16px 18px; border-radius: 12px;
    text-decoration: none; color: #fff; position: relative;
    background: linear-gradient(135deg, #e8590c, #c92a2a);
    box-shadow: 0 3px 12px rgba(201, 42, 42, .18);
    transition: transform .15s, box-shadow .15s;
  }
  .heatmap-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(201, 42, 42, .28); }
  .heatmap-card .hm-title { font-size: 1.08em; font-weight: 700; }
  .heatmap-card .hm-sub { font-size: .8em; opacity: .9; margin-top: 3px; }
  .heatmap-card .hm-arrow { position: absolute; right: 16px; top: 50%; transform: translateY(-50%); font-size: 1.3em; opacity: .85; }
  .governance-card { background: linear-gradient(135deg, #315b63, #1d3e49); box-shadow: 0 3px 12px rgba(29,62,73,.18); }
  .quick-nav { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: -4px 0 18px; }
  .quick-nav a { display: inline-block; padding: 5px 11px; border: 1px solid var(--border); border-radius: 999px; background: var(--card); color: var(--text); text-decoration: none; font-size: .8em; transition: border-color .15s, color .15s, background .15s; }
  .quick-nav a:hover { border-color: var(--accent); color: var(--accent); background: var(--tag-bg); }
  .quick-nav a.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .home-note { color: var(--muted); font-size: .84em; margin: -4px 0 18px; text-align: center; }
  @media (max-width: 520px) {
    body { padding: 12px; }
    header { padding-top: 24px; }
    header h1 { font-size: 1.4em; }
    .quick-nav { justify-content: flex-start; }
    a.day-card { padding: 15px 16px; }
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
    "target": "https://zhangheng666.top/?q={{search_term_string}}",
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
  <a href="heatmap.html">热点地图</a>
  <a href="digital-trends.html">数字趋势</a>
  <a href="jobs.html">招聘</a>
  <a href="sources.html">来源规则</a>
</nav>

<p class="home-note">每天几分钟，读懂文博行业今天真正发生了什么。</p>

<div class="search-wrap">
  <input type="search" id="search" placeholder="🔍 搜索新闻…" autocomplete="off" aria-label="搜索新闻">
  <button class="clear" id="clear" aria-label="清除">✕</button>
</div>
<div class="result-count" id="result-count"></div>
<div class="no-results" id="no-results">😕 没有找到匹配的结果</div>

<a class="heatmap-card" href="heatmap.html">
  <div class="hm-title">🗺️ 中国文博热点地图</div>
  <div class="hm-sub">点击省份查看当地全部报道 · 热力随每日日报自动更新</div>
  <span class="hm-arrow">→</span>
</a>

<a class="heatmap-card" href="digital-trends.html">
  <div class="hm-title">📈 文博数字化趋势</div>
  <div class="hm-sub">国家文物局数字化相关新闻趋势 · 2021至今 · 缩放看月/周/天粒度</div>
  <span class="hm-arrow">→</span>
</a>

<a class="heatmap-card governance-card" href="sources.html">
  <div class="hm-title">🧭 信源与方法</div>
  <div class="hm-sub">A级官方来源 · B级专业补充 · 历史档案审计与发布门槛</div>
  <span class="hm-arrow">→</span>
</a>

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
  <p>由 <a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> 自动生成 ｜ 每日早 7:13（北京时间）更新 ｜ <a href="sources.html">信源与方法</a> ｜ <a href="about.html">关于本站</a></p>
</footer>

</body>
</html>'''
    # Inject JS (toggles + search)
    html = html.replace('</body>', '''<script>
function toggleSection(header) {
  header.classList.toggle('collapsed');
  const body = header.nextElementSibling;
  if (body && body.classList.contains('section-body')) {
    body.classList.toggle('hidden');
  }
}
function toggleOlder(btn) {
  const olderDiv = btn.previousElementSibling;
  if (olderDiv && olderDiv.classList.contains('older-cards')) {
    const isHidden = olderDiv.style.display === 'none';
    olderDiv.style.display = isHidden ? '' : 'none';
    if (isHidden) {
      btn.textContent = btn.getAttribute('data-collapse-text') || '收起 ▲';
    } else {
      btn.textContent = btn.getAttribute('data-expand-text') || btn.textContent;
    }
  }
}
(async function(){
  const searchInput = document.getElementById('search');
  const clearBtn = document.getElementById('clear');
  const noResults = document.getElementById('no-results');
  const resultCount = document.getElementById('result-count');
  const cards = document.querySelectorAll('.day-card');

  let searchData = null;
  try {
    const resp = await fetch('search-index.json');
    if (resp.ok) searchData = await resp.json();
  } catch(e) {}

  function doSearch(q) {
    q = q.trim().toLowerCase();
    let visible = 0;

    if (!q) {
      cards.forEach(c => c.classList.remove('hidden'));
      noResults.style.display = 'none';
      resultCount.style.display = 'none';
      clearBtn.style.display = 'none';
      cards.forEach(c => {
        const prev = c.querySelector('.match-preview');
        if (prev) prev.remove();
      });
      return;
    }

    clearBtn.style.display = 'block';
    const queryWords = q.split(/\\s+/).filter(Boolean);

    cards.forEach((card) => {
      const href = card.getAttribute('href');
      const cardText = card.textContent.toLowerCase();
      const path = (href || '').replace(/^\\.\\//, '');
      const record = searchData && searchData.find(r => r.path === path || (r.type === 'daily' && href && href.includes(r.date)));
      let matched = false;
      let previewText = '';
      const searchable = [cardText, record && record.title, record && record.text]
        .concat(record && record.items ? record.items.map(item =>
          [item.title, item.body, item.commentary, (item.tags || []).join(' '), (item.sources || []).join(' ')].join(' ')) : [])
        .filter(Boolean).join(' ').toLowerCase();

      for (const w of queryWords) {
        if (searchable.includes(w)) {
          matched = true;
          const idx = searchable.indexOf(w);
          const start = Math.max(0, idx - 30);
          const end = Math.min(searchable.length, idx + w.length + 50);
          let snippet = searchable.substring(start, end);
          if (start > 0) snippet = '…' + snippet;
          if (end < searchable.length) snippet = snippet + '…';
          const re = new RegExp('(' + w.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');
          previewText = snippet.replace(re, '<mark class="highlight">$1</mark>');
          break;
        }
      }

      if (matched) {
        card.classList.remove('hidden');
        visible++;
        let prev = card.querySelector('.match-preview');
        if (previewText) {
          if (!prev) {
            prev = document.createElement('div');
            prev.className = 'match-preview';
            card.appendChild(prev);
          }
          prev.innerHTML = previewText;
        } else {
          if (prev) prev.remove();
        }
      } else {
        card.classList.add('hidden');
        const prev = card.querySelector('.match-preview');
        if (prev) prev.remove();
      }
    });

    noResults.style.display = visible === 0 ? 'block' : 'none';
    resultCount.style.display = 'block';
    resultCount.textContent = `找到 ${visible} 个相关栏目`;
  }

  searchInput.addEventListener('input', function(){
    doSearch(this.value);
  });

  clearBtn.addEventListener('click', function(){
    searchInput.value = '';
    doSearch('');
    searchInput.focus();
  });

  const params = new URLSearchParams(location.search);
  const q = params.get('q');
  if (q) {
    searchInput.value = q;
    doSearch(q);
  }
})();
</script>
</body>''')
    return html


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
<p>「每日文博资讯」是一个聚焦<strong>文物、博物馆、考古、文化遗产</strong>领域的每日资讯站点，每天精选约 6–10 条国内外要闻，附带专业点评与趋势总结。内容由 AI 自动采集、筛选并编撰，宁缺毋滥，不以凑数为目标。</p>

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
<p>流程：定向检索登记来源 → 核对原文日期、数量和事件状态 → 按实质增量和行业价值筛选 → 与近 30 天内容去重 → 分开生成事实摘要和编辑判断 → 构建页面并执行质量门禁。日报按“国内要闻 / 国际要闻”组织，标签归一到九类主题，供搜索和趋势地图使用。历史内容不会被静默删除；若旧稿含未登记来源，页面会明确标为历史档案。若发现错误，欢迎在 GitHub 仓库提 issue 反馈。</p>

<h2 class="section">🔒 隐私</h2>
<p>本站为纯静态网站：<strong>不收集任何个人信息、不使用 Cookie、不接入任何统计或广告脚本</strong>。你只是阅读，我们只是展示。</p>

<footer>
  <p><a href="https://github.com/Zhangheng0610-nb/wenbo-daily" target="_blank">每日文博资讯</a> ｜ <a href="index.html">返回首页</a></p>
</footer>
</main>
</body>
</html>'''
    return html


def build_sources_html(daily_reports):
    """Generate a reader-facing source registry and archive audit page."""
    stats = source_stats(daily_reports)
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
  @media (max-width: 520px) {{ .audit-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
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

<h2 class="section">📚 信源分级</h2>
{''.join(tier_cards)}

<h2 class="section">🧪 发布门槛</h2>
<ol>
  <li>搜索引擎只负责发现候选，最终链接必须指向登记来源。</li>
  <li>涉及政策、考古年代、文物数量、归还争议和招聘截止日期，优先使用A级原文。</li>
  <li>B级来源只作专业补充；找不到可核验原文时宁可不发，不为凑数收录。</li>
  <li>每个事件按 canonical URL、标题和实体去重；只有实质新进展才重复出现。</li>
  <li>事实摘要和编辑判断分开，无法确认的内容标记“待核”，不把推测写成定论。</li>
</ol>

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
            weekly_reports.append(data)
            print(f'  -> parsed weekly-{data["ref_date"]}.html')

        elif '月报' in first_line:
            data = parse_digest(md_path, 'monthly')
            if not data['ref_date']:
                print('  SKIP: could not parse monthly date')
                continue
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
                'title': item['title'],
                'body': item['body'][:200] if item['body'] else '',
                'commentary': item['commentary'],
                'tags': item.get('tags', []),
                'sources': [s.get('name', '') for s in item.get('sources', [])],
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
        prefix = 'weekly' if r['type'] == 'weekly' else 'monthly'
        search_data.append({
            'type': r['type'],
            'path': f"reports/{prefix}-{r['ref_date']}.html",
            'title': r['title'],
            'date': r['ref_date'],
            'text': digest_text,
            'items': r.get('items', []),
        })

    # Build heatmap data + page (仅国内,国际段排除;资源缺失仅 WARN 不中断)
    heat_data, heat_audit = build_heatmap_data(daily_reports)
    heat_path = os.path.join(SITE_DIR, 'heatmap-data.json')
    with open(heat_path, 'w', encoding='utf-8') as f:
        json.dump(heat_data, f, ensure_ascii=False, indent=2)
    st = heat_data['stats']
    print(f'Heatmap data: {heat_path} | 国内 {st["totalDomestic"]} 条,归省 {st["provincialItems"]} 条,国际排除 {st["internationalExcluded"]} 条,最高热度 {st["maxHeat"]}')
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

    sources_html = build_sources_html(daily_reports)
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

    # Build digital trends page (数字化趋势;当日已有数据则只重建页面,不重新抓取)
    try:
        import digital_trend
        digital_trend.main()
    except Exception as e:
        print(f'Digital trends: SKIP ({e})')

    print('\nDone! Run push to deploy.')


if __name__ == '__main__':
    main()

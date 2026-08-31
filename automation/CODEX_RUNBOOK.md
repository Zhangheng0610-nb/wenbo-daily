# 每日文博资讯：Codex 原生运行手册

本仓库由 Codex 自动化直接运行。不要调用 `auto_task.py`、`auto_task_mac.py`，不要读取 Claude 配置，不要使用 Anthropic/DeepSeek 兼容接口，也不要创建或启用 Windows Task Scheduler、macOS launchd 任务。

## 运行目标

在北京时间当天完成必要栏目，并把可验证结果提交到本仓库的 `main` 分支：

- 每天：先生成 `content/监测/YYYY-MM-DD.json`，逐一登记固定信源池的巡检结果和全部合格候选。
- 每天：生成 `content/日报/YYYY-MM-DD.md`。
- 偶数日：更新 `content/招聘/jobs.md` 和 `content/招聘/intern.md`。
- 周日：生成当周周报。
- 每月 1 日：汇总上月月报，不要把当月第一天误写成完整月报。

固定信源巡检是地图的数据任务，日报是编辑精选任务，两者不能混为一谈。招聘、周报、月报只在对应日期执行，不应互相重复搜索或重复报道。

## 内容与信源

搜索引擎、行业雷达和未核验公众号只用于发现候选，不是信源本身。日报候选写入 `content/候选/YYYY-MM-DD.json`；最终链接必须来自可核验的 A/B 级证据。`content/监测/` 仍只服务地图固定六源，不能塞入日报候选。

日报链路明确分为两层：`DISCOVERY SOURCE` 用于扩大召回，不代表最终证据资格；`EVIDENCE SOURCE` 支持事实并展示给读者。每个候选都要在候选账本中记录发现渠道、证据来源、去重结果和最终决定。

### 行业地图固定信源池

地图只使用 `automation/governance.py` 中 `MAP_SOURCE_PANEL` 定义的 6 个固定来源：

1. 国家文物局：`ncha.gov.cn`；主管部门政策、文物新闻、行业信息和每周各地动态。
2. 中国文物报：`zhongguowenwubao.com`；全国文博行业专业报数字版。
3. 中国考古网：`kaogu.cssn.cn` / `kaogu.cn`；中国社会科学院考古研究所专业平台。
4. 中国博物馆协会：`chinamuseum.org.cn`；协会资讯、行业资讯和各地展览。
5. 新华网文博：`news.cn` / `xinhuanet.com`；文博栏目及重大文化报道。
6. 央视网文博：`cctv.com` / `cctv.cn`；文博专题、央博与重大文化报道。

每天必须逐源检查，不得只搜索最后会进入日报的 4—8 条。正式当天巡检写入 `mode: operational`；历史回溯脚本 `python automation/backfill_monitoring.py --end YYYY-MM-DD --days 1 --write` 只写入 `mode: archive-backfill`，不得把回溯覆盖度当作正式运行健康度。该程序对固定国内来源强制直连，并在国家文物局、中国文物报、中国考古网发生 HTTPS 握手异常时回退到官方 HTTP 原站。再补充当天新发布且属于文物、博物馆、考古、文化遗产、保护修复、文博数字化或行业政策范围的内容，随后才从中做日报精选。地方政府、博物馆官网和其他 A/B 级媒体可用于日报发现和交叉核验，但不能写入地图监测库，也不能直接改变地区排名。

正式巡检的 `coverage[].checkedAt` 必须由实际运行时生成（北京时间，保留秒），不得填写目标日期的固定整点。若历史文件或补跑过程没有可靠的逐源运行时刻，使用 `checkedAt: null`、`checkedAtStatus: "unknown"` 和说明字段，不得用提交时间冒充检查时间；回溯文件中的日期内时间只表示重建记录，不代表当日真实运行。

`coverage` 必须恰好包含 6 个来源：完整检查且有新内容写 `success`，完整检查且无新内容写 `no_update`，只能检查部分栏目写 `partial`，入口故障且无法可靠替代检查写 `failed`。即使没有新内容也不能省略来源，不能把“搜索没看到”伪装成完整检查。每条监测记录必须包含固定池原文、唯一发生省份或明确的全国/国际范围、主题、地理置信度和 `selectedForDaily`。

`content/监测/baseline.json` 只是从旧日报迁移的固定信源历史样本，覆盖率不可审计；不得改写为“完整历史数据”。

### 日报通用信源

- 国内 A 级：国家文物局 `ncha.gov.cn`、新华社 `news.cn`/`xinhuanet.com`、央视 `cctv.com`、中国文物报 `chinawenbao.com.cn`、中国博物馆协会 `chinamuseum.org.cn`、中国考古网/社科院考古 `kaogu.cn`/`kaogu.cssn.cn`。
- 国内补充：人民日报、光明网、中国新闻网、央广网；澎湃只作少量补充，地方媒体只有在直接报道机构公告且能被官方信息交叉核验时才可使用。
- 国际 A 级：UNESCO、世界遗产中心、ICOM、ICCROM。
- 国际补充：AP、Reuters、BBC、RTVE（西班牙国家公共电视台）、EFE（西班牙通讯社）、Archaeology Magazine、The Art Newspaper。
- 展览一手来源：指定博物馆官网及 `.museum` / `.museum.cn` 官方域名。

未知公众号、搜狗微信跳转、百度百科/知道、百家号、搜狐号、头条号、网易、搜索引擎跳转链接和不明聚合站均不得作为最终来源。经核验的政府部门、博物馆、考古院所、文保机构、行业协会和高校专业机构官方公众号原创文章，可登记为机构一手证据；必须有账号身份、机构归属、官网反向确认和原创关系记录，不能仅凭 `mp.weixin.qq.com` 放行。找不到 A/B 级证据就舍弃或标为待核验。

日报发现层至少覆盖中央专业来源、地方文物主管部门、国家级/省级/重点博物馆、重要考古院所和文保机构；文博圈、博物馆圈、博物馆头条承担行业雷达和线索发现，不自动升为 A 级。国际发现每日检查 UNESCO、世界遗产中心、ICOM、ICCROM、ICOMOS 及重要博物馆、大学和考古机构；没有合格国际新闻可以不发，但必须在候选账本留下检查记录。招聘单独使用“文博人才”作为招聘雷达，不升级为日报来源。

### 招聘与实习的独立规则

招聘/实习不是日报和行业地图，采用“真实性优先”的单独准入标准，不要求每条都达到日报的 A/B 级新闻标准：

1. 优先搜索博物馆、考古机构、高校、政府人社部门和企业官网；同时扩大到正规招聘平台、学校就业网和专业招聘站，不只盯着固定权威信源。
2. A/B/C 级链接均可收录，但必须是岗位详情或直接投递入口，链接可打开，岗位名称、机构、地点、要求、截止日期/持续招募状态和投递方式至少能核对出主要信息。只有搜索结果页、失效页、纯转载而无投递方式的页面不能收录。
3. C 级招聘来源只代表“招聘线索来源”，不等于本站认可其新闻可信度；必须能回到真实机构或明确投递邮箱/平台，并在页面上提醒“申请前核对原文”。C 级规则只适用于招聘/实习，不适用于日报和行业地图。
4. 每次招聘更新先复查旧岗位：已过截止时间的标为已截止或移出可申请列表；当日、次日和 3 天内截止的岗位置顶，并在标题或截止字段写出具体日期和时间，不能只写“尽快”。
5. 扩大检索地域和岗位类型：全国博物馆、考古队/研究所、高校文博岗位、文物保护修复、展览与公共教育、数字文博、文化遗产项目及相关企业均可纳入；按真实性、仍可投递和信息完整度排序，不按来源等级机械排除。
6. 同一岗位合并重复信息，优先保留官方投递入口，同时可附招聘平台链接用于补充；找不到有效投递方式就不收录。

### 周报 2.0 / 月报 1.0 周期报告

周报和月报共用 `automation/periodic_reports.py` 的周期数据模型与页面组件，但只消费已经生成的日报，不重新采集新闻，也不改变日报、地图或数字趋势口径。周报在周日运行：

```text
python automation/generate_periodic_reports.py --weekly YYYY-MM-DD
```

每月 1 日先确认上月每一天的日报都存在，再生成正式月报；脚本会在月份不完整时拒绝正式输出：

```text
python automation/generate_periodic_reports.py --monthly YYYY-MM
```

月末数据尚未齐全时，只能使用明确标记为本地预览的命令，预览不进入正式月报档案：

```text
python automation/generate_periodic_reports.py --monthly-preview YYYY-MM
```

周期报告的事件量、主题分布和时间节奏只统计实际存在的日报。候选账本从 2026-08-29 才建立，因此在历史周期不展示候选发现量或采用率 KPI。正式月报的时间范围严格使用上月 1 日至月末，不把当月 1 日日报混入上月。发布前运行：

```text
python automation/validate_periodic_reports.py --type weekly --key YYYY-MM-DD
python automation/validate_periodic_reports.py --type monthly --key YYYY-MM
```

周/月报可以回链到日报条目和原始来源；报告中的综合判断属于本站样本内观察，至少需要两个独立事实支点，不能把单纯展览规模或传播热度写成行业趋势。

周期报告采用“确定性数据层 + editorial layer”两层流程。Python 只计算周期事件量、覆盖日、范围、主题、节奏、比较基础数字、日报链接和证据；Codex 必须读取本周期数据和代表性日报，先生成 `content/报告/weekly-YYYY-MM-DD-editorial.json` 或 `content/报告/monthly-YYYY-MM-editorial.json`，再运行周期报告生成器。editorial layer 至少提供一句话、重点事项及逐条 `itemKey` 理由、主题板块观察、数字文博观察、比较说明和已公布的下期节点。每个引用必须属于本周期日报；趋势性判断至少绑定两个独立事件。正式周/月报缺少 editorial layer 时必须失败，不能退回固定模板。月末数据不完整时只能使用 `editorialStatus: preview` 的月报预览，正式月报必须使用完整自然月数据。

日报筛选规则：

1. 只选近 7 天内发布或有明确新进展的内容；展览和活动必须核对当前状态。
2. 一个事件只保留一条主报道，必要时附一个不同层级的交叉来源；每条新闻至少带一个原始来源链接。
3. 同一域名默认最多 2 条，用于避免单一来源占满版面；同一权威机构当天确有多个彼此独立且专业价值明显不同的事件时可超过 2 条，必须在候选账本记录编辑理由。
4. 报名通知、常规培训/研学、一般讲座、日常志愿招募和纯预热通稿通常不进入最终日报；重要考古新认识、重大阶段性成果、高专业价值学术会议和行业制度性会议不得被这些标签机械排除，先进入候选账本再判断。
5. 先读取 `site/dedup-index.json`（若存在），对 URL 去掉追踪参数后，再与近 30 天标题和事件实体去重；只有质变级新进展才重报。
6. 日报条数只是结果，不是准入条件；典型情况下可从约 6–12 个合格候选中精选，新闻不足时少发，不得用低质量内容凑数。候选账本必须区分“只发现了几条”和“发现很多、筛选后留下几条”。未入选日报的合格固定池内容仍保留在监测库。标签只能使用既定九类主题，并可附地点标签。
7. 事实摘要、编辑判断和不确定性分开写；“或”“据称”“尚待确认”不得在标题中被改写成确定事实。

## 工作流程

1. 先确认仓库根目录：它应同时包含 `build.py`、`content/`、`reports/` 和 `automation/`。
2. 读取当天已有监测文件和日报、近 30 天去重索引及必要的上一期栏目。
3. 先完成固定池巡检。先运行 `python automation/backfill_monitoring.py --end YYYY-MM-DD --days 1 --write`；再逐一核对登记入口，入口列表不完整时，以 `site:登记域名 文物/博物馆/考古/文化遗产 + 日期` 定向检索补齐。核对原文发布日期和当天新增项，把全部合格候选写入 `content/监测/YYYY-MM-DD.json`。不要另写临时爬虫。
4. 再做日报搜索：先按发现层广泛建立候选账本，再回溯 A/B 级证据，最后按专业价值精选。不得先选日报再反填监测库。
   现在必须执行独立的 broad discovery 审计：

   ```text
   python automation/daily_discovery.py --date YYYY-MM-DD --window-days 7 --write
   ```

   该命令只写 `content/发现/YYYY-MM-DD.json`，不写入 `content/监测/`，也不改变地图数据。它主动扫描国家文物局文物新闻/政策入口、新华网、中国新闻网、UNESCO 和 Archaeology Magazine 等可重复入口，并默认真实执行 `daily_discovery.py` 中的国内/国际 query family（Bing News RSS + Google News RSS）；每条查询的 `actualQuery`、`executedAt`、成功/失败、返回数和窗口内接纳数都会写入同日 discovery audit。`--no-query-search` 仅供测试使用。发现来源只负责扩大召回，证据来源必须另行核验。
   候选账本必须引用 `discoveryAuditPath`。每条候选保留 `discoveredVia`、`discoveryQuery`、`duplicateStatus`、`duplicateOf`、`duplicateReason` 和 `newDevelopment`（未知时使用 `possible_duplicate` / `needs_verification`，不得静默删除）。
5. 所有事实、日期、数量、地点和来源链接必须由原文支持；同一事件的不同来源作为证据合并，不重复列为新闻。去重顺序是：广泛发现 → 当天事件聚类 → 近 7—14 天历史事件核对 → evidence 核验 → editorial selection。当天同一事件只保留 canonical event；历史转载记录保留在 discovery audit 中并写明 `duplicateOf`；有明确新增事实的记录标记 `new_development`，不能因标题相似被误杀。
6. 按日期判断是否执行招聘、周报、月报；不要把所有栏目都重复搜一遍。
7. 正式每日任务先运行 `python digital_trend.py --incremental`，扫描国家文物局「文物新闻」近期分页，更新 `digital-data.json`，并写入 `content/数字趋势监测/YYYY-MM-DD.json`；确认扫描成功后再运行 `python build.py` 重建静态页面。普通 `python build.py` 只做页面构建（内部使用 `--build-only`），不联网采集、不更新数字趋势数据或覆盖记录。
8. 运行 `python automation/validate_project.py --date YYYY-MM-DD`；该检查会强制要求当日 6 源覆盖登记和固定池域名匹配。历史档案可用 `--all` 检查，`--strict-all` 仅用于专项清理。
9. 检查 `git status`、`git diff --check`、`heatmap-data.json`、`sources.html`、`search-index.json` 和生成文件；确认没有未预期的改动。
10. 提交并推送：

   ```text
   git add .
   git commit -m "Daily report YYYY-MM-DD"
   git push origin main
   git push gitee main
   ```

   若没有内容变化，不能伪造提交；但必须报告构建和推送状态。两个远端都成功后才算完成。

## 成功标准

当日监测 JSON 恰好登记 6 个固定来源，日报 Markdown、对应 `reports/YYYY-MM-DD.html`、地图数据、搜索索引和网站首页均存在且非空；来源与监测库校验通过；构建退出码为 0；Git 工作树干净；`origin/main` 和 `gitee/main` 都等于本地 HEAD。任何一项失败都必须报告失败原因，不得宣称成功。`partial` 或 `failed` 可以如实发布，但必须在任务结果中说明，网站覆盖率会自动降级；不得伪造 `success`。

## 迁移原则

本目录是可迁移仓库，不保存密钥。GitHub/Gitee 的登录凭据由新电脑上的 Git/SSH 配置提供；Codex 自动化只保存任务指令，不把 token 写进仓库。换电脑时克隆本仓库、在 Codex 中把自动化重新绑定到新电脑上的本地 checkout，并按 `PORTABILITY.md` 检查即可。

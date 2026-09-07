# 每日文博资讯

面向文博学生和从业者的资讯、行业观察与招聘服务。线上站点：https://zhangheng666.top/

## 本地构建与检查

需要 Python 3.11+、Node.js（仅用于测试），海外招聘时区需要系统 IANA 时区数据库。主构建无第三方 Python 依赖，不发起信息抓取。

```sh
python3 build.py
python3 -m unittest discover -s automation -p 'test_*.py'
python3 automation/validate_project.py --all
python3 automation/validate_product.py
```

构建错误会使命令失败；不得把失败时残留的旧页面视为新产物。GitHub Actions 在提交和 PR 时执行同样的检查，不触发采集，也不自动发布。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `content/日报`、`content/招聘` | 编辑源文件，修改后重新构建 |
| `content/发现`、`content/候选`、`content/复核` | 发现、证据和编辑决策账本 |
| `content/监测` | 固定六源地图样本，不能代表全国真实活动总量 |
| `automation/daily_discovery.py` | 资讯发现与事件处理 |
| `automation/recruitment_discovery.py` | 独立招聘发现与核验 |
| `automation/recruitment_dates.py` | 报名区间、截止时刻和时区 |
| `automation/governance.py` | 来源分类和发布规则 |
| `build.py` | 解析与生成主站页面 |
| `automation/product.py`、`assets/product.*` | 共享导航、主题、岗位筛选、数据时效说明及 RSS |
| `build_command_center.py`、`build_digital_page.py` | 行业观察与趋势页面 |
| `reports/`、根目录 HTML/JSON、`feed.xml` | 发布产物，不直接手改 |

完整发布应运行 `build.py`，以确保独立页面构建器的产物也接入共享导航和主题。单独运行趋势或驾驶舱构建器仅适合中间调试。

## 运营与证据边界

每日采集与编辑流程见 [运行手册](automation/CODEX_RUNBOOK.md)。项目沿用现有 Codex 自动化，不增加付费 API 或第二套定时任务。采集、编辑、构建、发布分别承担不同职责，构建成功不证明采集完整或内容已核验。

- 首页最近发布日期与固定信源覆盖取自已保存的日报、正式监测记录；覆盖统计不证明网站之外的信息已全部收录。
- 招聘“可申请”仅表示报名时间窗口未结束，不证明岗位尚有名额、用户符合资格或投递入口当天可用。
- 无明确时间或海外时区不明的岗位保留为“状态待核验”；有明确报名区间时区分“尚未开始”。
- RSS 地址为 `/feed.xml`，包含最近 30 期日报，不虚构精确发布时间。
- 部署前需要全部检查通过并完成浏览器验收；提交分支不会自动替代生产主分支。

本轮发现、修改和未完成事项见 [优化审计](automation/PRODUCT_AUDIT.md)。

### 本地开发与产品验收

```bash
npm ci
python build.py
npm run dev -- --port 4173
```

开发预览不会强制跳转线上域名。静态发布仍由 Python 构建，Vite 仅用于本地开发。

- 首页的近期内容来自已发布日报与对应编辑事件账本，不会另行抓取或自动补写新闻。
- 招聘与实习归入“机会”；搜索支持直达具体岗位，截止档案仍可检索。
- 收藏仅存当前浏览器，无账号、无跨设备同步；历史核查提示位于对应条目前。
- 持续优化记录见 `automation/PRODUCT_ROUND2.md`，其中列明实测与未完成事项。

离线重现本轮去重挑战集和全量发现回放：

```bash
python automation/replay_dedup_audit.py audit/live-discovery-2026-09-06.json --output audit/dedup-replay-summary.json
python -m unittest discover -s automation -p 'test_*.py'
python automation/validate_project.py --all
python automation/validate_product.py
```

需要新的实时质量审计时，运行 `python automation/measure_discovery.py YYYY-MM-DD`。该命令会联网但不改生产日报或监测账本；来源连接失败必须保留，不可用搜索引擎响应成功代替来源覆盖。

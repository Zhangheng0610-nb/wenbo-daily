# 每日文博资讯：Codex 原生运行手册

本仓库由 Codex 自动化直接运行。不要调用 `auto_task.py`、`auto_task_mac.py`，不要读取 Claude 配置，不要使用 Anthropic/DeepSeek 兼容接口，也不要创建或启用 Windows Task Scheduler、macOS launchd 任务。

## 运行目标

在北京时间当天完成必要栏目，并把可验证结果提交到本仓库的 `main` 分支：

- 每天：生成 `content/日报/YYYY-MM-DD.md`。
- 偶数日：更新 `content/招聘/jobs.md` 和 `content/招聘/intern.md`。
- 周日：生成当周周报。
- 每月 1 日：汇总上月月报，不要把当月第一天误写成完整月报。

日报是主任务；招聘、周报、月报只在对应日期执行。它们不应互相重复搜索或重复报道。

## 内容与信源

搜索引擎只用于发现候选，不是信源本身。最终链接必须来自 `automation/governance.py` 登记的 A/B 级来源；C 级只能作为线索，绝不能写入新稿。

- 国内 A 级：国家文物局 `ncha.gov.cn`、新华社 `news.cn`/`xinhuanet.com`、央视 `cctv.com`、中国文物报 `chinawenbao.com.cn`、中国博物馆协会 `chinamuseum.org.cn`、中国考古网/社科院考古 `kaogu.cn`/`kaogu.cssn.cn`。
- 国内补充：人民日报、光明网、中国新闻网、央广网；澎湃只作少量补充，地方媒体只有在直接报道机构公告且能被官方信息交叉核验时才可使用。
- 国际 A 级：UNESCO、世界遗产中心、ICOM、ICCROM。
- 国际补充：AP、Reuters、BBC、Archaeology Magazine、The Art Newspaper。
- 展览一手来源：指定博物馆官网及 `.museum` / `.museum.cn` 官方域名。

公众号、搜狗微信跳转、百度百科/知道、百家号、搜狐号、头条号、网易、搜索引擎跳转链接和不明聚合站均不得作为最终来源。找不到 A/B 级原文就舍弃，不要为了凑数收录。

日报筛选规则：

1. 只选近 7 天内发布或有明确新进展的内容；展览和活动必须核对当前状态。
2. 一个事件只保留一条主报道，必要时附一个不同层级的交叉来源；每条新闻至少带一个原始来源链接。
3. 同一域名每天最多 2 条；国内内容以博物馆、展览、文创、数字化、运营和行业动态为核心。
4. 普通考古发掘、培训/研学通知、一般讲座、日常志愿招募、纯预热通稿和“热度不减”续报不收。
5. 先读取 `site/dedup-index.json`（若存在），对 URL 去掉追踪参数后，再与近 30 天标题和事件实体去重；只有质变级新进展才重报。
6. 日报精选约 4–8 条，宁少勿杂；新闻不足时允许少发，不得用低质量内容凑数。标签只能使用既定九类主题，并可附地点标签。
7. 事实摘要、编辑判断和不确定性分开写；“或”“据称”“尚待确认”不得在标题中被改写成确定事实。

## 工作流程

1. 先确认仓库根目录：它应同时包含 `build.py`、`content/`、`reports/` 和 `automation/`。
2. 读取当天已有日报、近 30 天去重索引和必要的上一期栏目。
3. 用 Codex 的原生网页搜索工具做 5 个左右国内定向搜索和 3 个左右国际定向搜索；最多补搜 2–4 次。不要抓网页 HTML，不要写临时爬虫。
4. 先整理已确认候选，再写入 Markdown。所有事实、日期、数量和来源链接必须能由搜索结果支持。
5. 按日期判断是否执行招聘、周报、月报；不要把所有栏目都重复搜一遍。
6. 运行 `python build.py`。
7. 运行 `python automation/validate_project.py --date YYYY-MM-DD`；历史档案可用 `--all` 检查，`--strict-all` 仅用于专项清理。
8. 检查 `git status`、`git diff --check`、`sources.html`、`search-index.json` 和生成文件；确认没有未预期的改动。
9. 提交并推送：

   ```text
   git add .
   git commit -m "Daily report YYYY-MM-DD"
   git push origin main
   git push gitee main
   ```

   若没有内容变化，不能伪造提交；但必须报告构建和推送状态。两个远端都成功后才算完成。

## 成功标准

日报 Markdown、对应 `reports/YYYY-MM-DD.html`、搜索索引和网站首页均存在且非空；来源校验通过；构建退出码为 0；Git 工作树干净；`origin/main` 和 `gitee/main` 都等于本地 HEAD。任何一项失败都必须报告失败原因，不得宣称成功。

## 迁移原则

本目录是可迁移仓库，不保存密钥。GitHub/Gitee 的登录凭据由新电脑上的 Git/SSH 配置提供；Codex 自动化只保存任务指令，不把 token 写进仓库。换电脑时克隆本仓库、在 Codex 中把自动化重新绑定到新电脑上的本地 checkout，并按 `PORTABILITY.md` 检查即可。

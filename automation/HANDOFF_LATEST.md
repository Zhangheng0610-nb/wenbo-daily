# 截至第二十一轮的完整接续

只导入 wenbo-complete-round21.bundle，包含完整历史和第十六轮界面改版。分支 improve/product-reliability。用户目前电脑不在身边，拿到包后再本地接续即可。

1. 保护本地修改，fetch origin，在独立分支安全合并最新 main 和 bundle；保留最新日报、招聘、历史台账，不 force push。
2. 阅读 PRODUCT_ROUND21.md、PRODUCT_ROUND20.md、PRODUCT_ROUND19.md、PRODUCT_ROUND18.md、PRODUCT_ROUND17.md、PRODUCT_ROUND16.md、CODEX_RUNBOOK.md。用户已明确本轮招聘/实习优先，不再沿用“招聘暂缓”的旧交接要求。
3. 运行 `python -m unittest discover -s automation -p 'test_*.py'`、`python build.py`、`python automation/validate_project.py --date 2026-09-08`、`python automation/validate_product.py`、`git diff --check`。另外校验本地最新日报日期。Windows 原始发现哈希沿用 lf-normalized-v1。
4. 先预览桌面/手机首页、日报、招聘、实习，暂不 push，待用户确认前轮外观。浅色黑白灰主色、深色深蓝，允许少量合适的提示色。不要恢复绿色主题。
5. 本轮原文核查关闭9条旧公告、确认2条重复，待核队列从32条降至21条，没有新增已验证发布岗位。先保留 review-decisions.json 的持久处理记录；合并时逐条保留双方结论，不覆写本地最新数据。先读 content/招聘/review-queue.json 和 audit/round17-recruitment-replay.json，核对是否已被本地主线收录，避免重复。
6. 云端旧新闻搜索144次实测132次解析成功，但大量无关；新普通网页搜索8次样本也返回无关内容，已新增相关性失败判定。因此不要把成功响应视为覆盖成功。先运行 `python automation/recruitment_discovery.py --date YYYY-MM-DD --full-sweep --plan-only --output audit/recruitment-plan.json`；使用现有 Codex 网页搜索补查并按导入格式记录，再用 --input-results 回放，不要求用户购买新 API。
7. 详情材料里的邮箱、日期片段、附件只是核验辅助，不能自动升为 verified 或默认仍在招。未读取岗位表不得声称拆分完毕。微信公众号无法访问时保留缺口并查公开转载或原单位，不能假报已巡检。
8. 沿用现有日常任务执行新版运行手册：每日招聘发现、队列核验，有合格新增即发布；每周全国补查。脚本本身未创建任何新调度任务，需要核对本地原有任务是否读取最新手册。

第十六轮独立提交 7e44309，可单独调整或回退界面；数据采集改造保留。下一步目标是对外部真实有效岗位做漏报对账并完成入库，不用原始搜索数量冒充产品价值。

日报新增用户硬性口径：纯学术探讨、考释、常规发掘报告、长期技术研究介绍不选入。先读 PRODUCT_ROUND19.md。合并远端最新9月9/10日报后，按 round19-daily-scope-replay.json 校正四个被用户指出的条目及候选决策，同步正文、目录、数量、生成产物，保留原始发现数据与修订记录；有真实已核验新闻才补，不凑数。运行最新两天项目校验，不关闭新规则来让旧错误通过。上一包 round18 无须单独导入。

Round20新增前瞻发布要求：9月11日起 selected 候选含 industryAction 与原文段落快照引用。先读手册末节和真实回归示例，不把旧雷诺阿事件重复发布。生成候选时完成字段，不能跳过校验。动作证明仅在内部，不新增前台解释文字。

Round21首页去掉黑色主新闻版面：白底主新闻、灰阶层次、统一字体；深色模式同用深蓝卡片。请预览390px与1440px宽度、浅色和深色四个状态，特别确认主卡片不再反白、没有横向溢出、标题层级与正文密度合适。样式已更新内容哈希。此轮为独立UI提交，可单独回退。

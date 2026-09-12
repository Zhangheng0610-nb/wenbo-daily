# Round24 独立增量接续

用户已部署之前各轮，这次只导入 `wenbo-round24-incremental.bundle`。

- 必需基线：`14ebaca22f4679d7c25575bdf97d9b5186962839`
- 包内分支：`improve/product-reliability`
- 阅读：`automation/PRODUCT_ROUND24.md`
- 不要重复导入旧完整包，不 force push。

## 本地 Codex 操作

1. 检查本地工作树，保护未提交修改；fetch origin。用 `git cat-file -t 14ebaca22f4679d7c25575bdf97d9b5186962839` 确认已有基线。缺基线先从正常远端取回，不能跳过 bundle 校验。
2. `git bundle verify <包路径>`；`git fetch <包路径> improve/product-reliability:review/round24-import`。若该分支已存在，先检查是否已整合，不覆盖未知本地分支。
3. 从最新 `origin/main` 建立独立整合分支，再合并 `review/round24-import`。保留最新日报、招聘和原始发现账本。本轮更改 9 月 12 日三条候选决策及派生复核；如果主线又复核过同一事件，逐条对账，避免覆盖更晚证据。
4. 运行全量测试、`python build.py`、最新日期的项目校验、`python automation/validate_product.py` 和 `git diff --check`。另运行 `python automation/validate_candidates.py --date 2026-09-12` 核查历史修订。当前云端结果为 330 测试通过、构建与 88 页产品校验通过。
5. 构建后的页面从合并内容生成，不采用云端旧页面覆盖最新日报。CSS 没有本轮视觉改动；跨平台原始字节哈希可能变化，另核对真实样式内容。日期推进也可能自然更新招聘截止标签。
6. 推送遵从用户当前会话授权；本包已包含代码和复核证据，不包含线上部署。使用普通合并/推送流程，禁止强制推送。

## 必须保留的边界

- 原始发现与原复核输入未修改；Round24 是独立历史编辑修订，候选仍发布 7 条，另 2 条待核。
- `originalCitationLinks` 的链接是待核引用，不是自动验证通过。不得批量改 `articleVerified` 或绕过 `industryAction` / 原文证据门槛。
- `PRODUCT_ROUND24.md` 和 audit 文件写明原始报道时间；不要按二次报道日期重新发布旧事件。
- 页面仍遵从黑白灰浅色、深蓝深色，不恢复绿色或黑底主新闻。
- 下一轮优先完整采集到入选的真实转化测量；全站优化尚未完成。

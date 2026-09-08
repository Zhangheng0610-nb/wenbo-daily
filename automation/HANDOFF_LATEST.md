# 截至第十六轮的完整接续

使用 wenbo-complete-round16.bundle，一份包含完整历史。目标分支 improve/product-reliability。不要依次导入旧包。

1. 保护本地未提交修改，fetch origin，在独立整合分支合并 bundle 和最新主线；保留双方每日数据，不覆盖远端新日报，不 force push。
2. 阅读 PRODUCT_ROUND11.md 至 PRODUCT_ROUND16.md、CONTENT_STYLE.md、CODEX_RUNBOOK.md。前轮若已合并，按祖先关系整合新增提交，不重复从头审计。
3. 执行 python -m unittest discover -s automation -p 'test_*.py'；python build.py；python automation/validate_project.py --date 2026-09-08；python automation/validate_product.py；git diff --check。如日报已推进，再检查最新日期。
4. 先本地预览，暂不 push，等用户确认外观。最新偏好：浅色黑白灰主色、深色深蓝，少量适配的提示/重点色可以使用，不能恢复绿色主题。请展示桌面和手机首页、日报的浅色及深色截图。
5. 新版识别：首页“文博日报”大标题、整期全部新闻卡片、第一条深色主卡；日报桌面左侧目录。检查 CSS 请求含 ?v= 内容哈希并正常加载，避免旧缓存。测试全部标题跳转、目录锚点、筛选、查看更多、收藏、键盘访问、手机横向溢出。另检查搜索日期范围/排序/空关键词浏览，以及档案按月份筛选折叠历史。270 项自动化测试通过，浏览器视觉验收仍待本地完成。
6. Round15 界面提交 cf8fc6739f2e2c78842fe97a484222c87cd2344e，Round16 为后续独立提交。用户不喜欢时可单独调整或撤回这两轮界面，保留 Round14 及以前的数据改进，不 reset 或强推主线。
7. Windows 哈希验证仍使用 lf-normalized-v1，不回写原始发现账本。正常早间运行继续验证信源、抓取和事件去重，不把 UI 校验通过当作全自动运营已经达标。

持续目标：日报每日 6–9 条高价值国内外新闻是满意状态，3–5 只是底线，10+ 不封顶，不凑数。下一轮重点是旧事件/新报道的日期判定和真实供给验收。

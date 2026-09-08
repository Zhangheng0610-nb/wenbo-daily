# 本地 Codex 接续说明

导入 wenbo-complete-round11.bundle 中的 improve/product-reliability 分支。包包含完整历史，无前置包要求，基于已推送的 origin/main 16a9b85。

1. 保护本地修改，git fetch origin。在独立整合分支安全合并最新 origin/main 与 bundle 分支；不得 force push 或覆盖其他未提交修改。
2. 阅读 PRODUCT_ROUND11.md。沿用现有早间任务，不新建重复自动化；招聘暂缓。
3. 执行 python -m unittest discover -s automation -p 'test_*.py'、python build.py、python automation/validate_project.py --date 2026-09-08、python automation/validate_product.py、git diff --check。若日期数据已推进，另验最新日报。
4. 复核哈希显式使用 lf-normalized-v1，避免 Windows 换行转换后再手工改回 raw 哈希；不得修改原发现账本来通过验证。
5. 本地浏览器验收桌面和手机宽度驾驶舱：图表和筛选可用、顶部显示真实检查状态、采集记录链接可读。云端未完成视觉验收。
6. 用户已授权正常 push；验证后合并并推送 main。若分支保护要求 PR，走正常 PR 路径。部署后检查新 collection-status.js 和 observations 是否随站点发布。

真实抓取对比：9 月 1 日中国文物报由默认版面 8 篇变为完整版面 32 篇。此数据属于历史诊断，不是当日日报新增。下一轮继续实际采集覆盖、国际新闻漏报及稳定 6–9 条目标，不要把本轮视为全面优化完成。

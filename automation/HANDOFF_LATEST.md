# 累积第十一至十三轮的本地接续

用户电脑暂不在身边，第十一轮尚未交给本地推送。使用 wenbo-complete-round13.bundle 一份即可，无需叠加第十一轮或其他旧包。完整历史分支：improve/product-reliability，包含已推送 origin/main 16a9b85 及后续三轮。

1. 保护本地修改，fetch origin；在独立整合分支安全合并 bundle 与最新 main。不得 force push。
2. 阅读 PRODUCT_ROUND11.md、PRODUCT_ROUND12.md、PRODUCT_ROUND13.md、CONTENT_STYLE.md 和 CODEX_RUNBOOK.md，不从头审计，不转向招聘。
3. 运行 python -m unittest discover -s automation -p 'test_*.py'；python build.py；python automation/validate_project.py --date 2026-09-08；python automation/validate_product.py；git diff --check。若日报日期已推进，另验最新日期。
4. Windows 复核哈希沿用显式 lf-normalized-v1，不手动改回 CRLF raw 哈希，不修改原始发现文件。
5. 本地浏览器验收桌面/手机驾驶舱、采集记录概览卡、图表筛选和跳转。云端仅完成构建/静态/逻辑验证，视觉验收尚未完成。
6. 用户把本包交给你后，按已授权的安全整合和正常 push 流程上线；分支保护走正常 PR，不强推。部署检查新脚本 collection-status.js、健康 observations 和概览卡。
7. 下一次正常早间任务验证报纸全部版面、真实补收雷达、ICOM/ICCROM 适配器进入既有候选流程；新增列表线索不是原文核验通过，不得全部自动入选。

目标保持：每日 6–9 条高价值国内外文博新闻是满意状态，3–5 仅底线，不凑数。同一来源或摘编页面可以包含不同事件，不按信源配额压稿。记录实际失败和漏报，不因测试通过就宣称全自动运营已达标。

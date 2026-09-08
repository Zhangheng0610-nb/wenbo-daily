# 给本地 Codex 的接续推送指令

用户已授权导入、合并、验证并推送。请打开网站本地仓库，使用用户下载的 wenbo-round7-9.bundle。

1. 检查本地改动并保护，fetch 最新 origin/main。
2. git bundle verify 校验文件；通过 git fetch 从包内的 improve/product-reliability 分支导入到新的本地整合分支，保留提交历史。不要重复应用 patch。
3. 包包含第七、八轮和本轮发布校验修复，并已合并 9 月 8 日远端 6169806。若远端有更新，安全合并，禁止强制覆盖或 force push。
4. 阅读 PRODUCT_ROUND9.md。本轮 9 月 8 日日报是对同一 19 事件池的正式受控复核，4 条修订为 7 条；保留 content/复核/2026-09-08-editorial-replay.json 和候选账本指向。原始 content/发现/2026-09-08.json 不应改变。
5. 运行完整自动化测试、python build.py、python automation/validate_project.py --date 2026-09-08、python automation/validate_product.py。Windows 下使用 UTF-8 模式（例如 PYTHONUTF8=1），不要因编码报错删改内容。
6. 验证通过正常 push 到 origin/main；如分支保护要求 PR，则推送整合分支并创建 PR。无需再次确认是否 push。
7. 检查实际部署结果，确认线上 9 月 8 日为 7 条，并能看到深圳、绍兴和刚果三条、原始四条仍在。不要只看 HTTP 200。核对首页、RSS、搜索与日报条目一致。

本次先上线这些成果，不重新开始全面优化。不要再为了同一官方摘编 URL 删除独立事件：发布校验已验证不同条目 ID 和原文证据；缺失这些字段时应恢复可追溯证据，而不是绕过检查。

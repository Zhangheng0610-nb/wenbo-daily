# Windows → macOS 迁移说明

## 仓库内容

完整运行所需的日报、招聘、构建器、Codex 运行手册和网站都在本仓库中：

- `content/日报/`：日报、周报、月报源文件
- `content/监测/`：行业关注地图的固定信源监测库、迁移基线和每日覆盖记录
- `content/招聘/`：招聘和实习源文件
- `build.py`：跨平台网站构建器
- `automation/`：Codex 运行手册和可移植校验器
- `reports/`、`index.html` 等：发布到 GitHub Pages/Gitee Pages 的静态产物

仓库不包含 API token、SSH 私钥或 Claude 设置。不要把这些文件复制进仓库或提交。

## 新电脑步骤

1. 安装 Git、Python 3.11 或更新版本，并在 GitHub/Gitee 配置自己的 SSH key 或凭据。
2. 克隆仓库：

   ```bash
   git clone git@github.com:Zhangheng0610-nb/wenbo-daily.git
   cd wenbo-daily
   ```

3. 检查 Python 和 Git：

   ```bash
   python3 --version
   git remote -v
   python3 automation/validate_project.py --all
   python3 build.py
   ```

   Windows 可将 `python3` 换成 `python`。本项目的主构建器只使用 Python 标准库，不依赖固定的 Windows 路径。

4. 在 Codex 中新建或更新“每日文博资讯自动更新”自动化：
   - 目标设为新电脑上的这个仓库目录；
   - 模型使用当前可用的原生 Codex 模型；
   - 任务内容指向 `automation/CODEX_RUNBOOK.md`；
   - 不安装 Windows 任务计划程序，不安装 macOS launchd 副本。

5. 手动执行一次日报任务，确认网站构建、GitHub 推送和 Gitee 推送均成功，再等待下一次自动运行。

## 注意事项

- Codex 的本地自动化绑定的是本地主机和本地 checkout，不会因为 Git 仓库被克隆到另一台电脑而自动迁移；换电脑后需要在 Codex 中重新绑定一次，旧电脑上的任务可以暂停保留。
- GitHub/Gitee 的账号权限、SSH key、代理和网络环境属于新电脑配置，不应写入项目代码。
- `auto_task.py` 和 `auto_task_mac.py` 是旧版 Claude 兼容层，仅为回退保留；正常运营不要运行它们。

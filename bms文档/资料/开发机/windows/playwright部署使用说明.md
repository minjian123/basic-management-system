# playwright 部署使用说明

> mjpc 开发机 Windows 侧 Playwright（`playwright-cli` 与 CodeBuddy Playwright MCP）使用口径 · 2026-10-16 本机采集

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › playwright 部署使用说明　|　[同级：google-chrome部署使用说明 →](google-chrome部署使用说明.md)　[CodeBuddy部署使用说明 →](CodeBuddy部署使用说明.md)　[开发机部署使用说明总览 →](开发机部署使用说明总览.md)　[linux 侧同名文档 →](../linux/playwright部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** Windows 侧（Windows 11 专业版）**Playwright** 的使用口径：CLI 从哪来、为什么**不装 ms-playwright 浏览器内核**、浏览器真机验证主走 CodeBuddy 的 **Playwright MCP**、`playwright-cli` 兜底用法与产物清理、排障入口。

定位说明：本机 Playwright 用于**开发态真实浏览器核验**（开发态核对页、宿主页面的渲染 / 样式 / 交互实测，作为 jsdom 用例之外的补充证据）；**CI 侧 E2E 归平台《main 流水线》**（Playwright E2E job，服务容器内起后端与前端产物），两者相互独立。linux 侧同名文档《[playwright部署使用说明](../linux/playwright部署使用说明.md)》记录镜像装内核与「CDN 被拦」的历史结论；Windows 侧**有意不装内核**，只走系统 Chrome。

> **取值说明**：路径按 Windows 写法；凭据类信息不在本文记录。

## 2. 环境概览 <a id="env"></a>

| 项 | 取值 |
| --- | --- |
| CLI | **`@playwright/cli` 0.1.22**（npm 全局安装；命令 `playwright-cli`） |
| CLI 落点 | `%LOCALAPPDATA%\Author Software\nvm\.nodejs\playwright-cli.exe`（nvm 的 shim 目录） |
| Node / npm | Node **v24.20.0**（nvm 管理，实体在 `…\nvm\installs\v24.20.0\`）；npm 11.19.0（全局包：`@playwright/cli`、`pnpm`、`corepack`、`npm`） |
| 内核目录 | `%LOCALAPPDATA%\ms-playwright\`（**实测仅有 `cli-update-check.json`，未装任何浏览器内核**） |
| 浏览器来源 | **系统 Google Chrome**（`--browser=chrome`，见《[google-chrome部署使用说明](google-chrome部署使用说明.md)》）；`msedge` / `firefox` 可选 |
| 主通道 | CodeBuddy 的 **Playwright MCP**（登记于 `%USERPROFILE%\.codebuddy\mcp.json`，见[第 4 节](#mcp)） |
| 会话产物 | 当前工作目录的 `.playwright-cli\`（`page-*.yml` 等）；截图建议落工作区 `tmp\`（已 gitignore） |

## 3. 浏览器内核口径：不装 ms-playwright <a id="kernel"></a>

本机**有意不下载** Playwright 自带浏览器内核（`%LOCALAPPDATA%\ms-playwright` 为空，见[第 6 节](#verify)）：

- 真机验证一律走**系统 Chrome**（`--browser=chrome`）——省磁盘、内核版本由管理员可控的 Chrome 自动更新承担；
- 与之对应，**不要跑** `playwright-cli install-browser`（既无需求，也会引入约数百 MB 的内核与版本跟随问题）；
- 与 linux 侧结论一致（那边是镜像版本滞后导致自带 Chromium 装不上，最终同样改走系统 Chrome）。

## 4. 主通道：CodeBuddy Playwright MCP <a id="mcp"></a>

浏览器真机验证的**主通道**是 CodeBuddy 里的 Playwright MCP（工具名前缀 `mcp__playwright__*`）。用户级登记 `%USERPROFILE%\.codebuddy\mcp.json` 实测内容：

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@0.0.83", "--browser", "chrome", "--isolated"],
      "env": { "npm_config_registry": "https://registry.npmmirror.com" }
    }
  }
}
```

`--browser chrome` 复用系统 Chrome、`--isolated` 用隔离会话（不写用户 profile）；`npx` 走 npmmirror 镜像。登记或改配置后须**重启 IDE** 才会出现在工具的可见列表里。

导航 / 点击 / 填表 / 截图 / 读控制台的走查口径（含读页面结构用 `browser_snapshot` / `browser_find`、截图落工作区 `tmp\`、预期控制台噪声）见同目录《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》，与 linux 侧《[CodeBuddy部署使用说明](../linux/CodeBuddy部署使用说明.md)》「浏览器真机验证」节同源。

## 5. 兜底：playwright-cli 使用 <a id="usage"></a>

长会话首选 MCP（又快又省）；`playwright-cli` 只在 1~2 步的极短会话或只看单次输出时使用：

```powershell
cd D:\Develop\bizs                                                              # 产物落当前目录的 .playwright-cli\
playwright-cli open --browser=chrome http://localhost:5173/login-check.html     # 打开（默认无头）
playwright-cli goto http://localhost:5173/login                                 # 同一会话内跳转
playwright-cli snapshot                                                         # 页面结构快照
playwright-cli screenshot --filename=tmp\shot.png                               # 截图
playwright-cli eval "() => document.querySelectorAll('[data-check]').length"    # 取页面数据（结果在 ### Result 段）
playwright-cli console                                                          # 页面控制台（排 JS 异常首选）
playwright-cli close-all                                                        # 关闭全部会话
```

口径与注意：

- `--browser` 取值限 **`chrome` / `firefox` / `webkit` / `msedge`**；**不接受 `chromium`**（自带 Chromium 走缺省通道，本机未装）；
- 默认**无头**；需要看界面加 `--headed`；`--idle-timeout` 缺省为无头 1 小时、有头不超时（`open --help` 实测口径）；
- 快照 / 日志等默认写当前目录的 `.playwright-cli\`（含 `page-*.yml`）——**用完清理**，不要留在仓库工作区；截图放工作区 `tmp\`（不入库）；
- 后端未起时页面会出现预期噪声：`/favicon.ico` 404 与 `/api/...` 502，不属页面缺陷（与 linux 口径一致）。

## 6. 验证 <a id="verify"></a>

```powershell
playwright-cli --version                            # 0.1.22
where.exe playwright-cli                            # …\nvm\.nodejs\playwright-cli.exe
Get-ChildItem "$env:LOCALAPPDATA\ms-playwright"     # 仅 cli-update-check.json（未装内核，属预期）

# 真机自检（实测通过：系统 Chrome、无头）
cd D:\Develop\bizs
playwright-cli open --browser=chrome about:blank    # → ### Browser `default` opened with pid …
playwright-cli list                                 # → browser-type: chrome / headed: false
playwright-cli close
```

## 7. 常见问题 <a id="troubleshoot"></a>

| 现象 | 处理 |
| --- | --- |
| `--browser=chromium` 报错 | 该取值不受支持；改用 `--browser=chrome`（系统 Chrome，首选）或 `--browser=msedge` |
| `%LOCALAPPDATA%\ms-playwright` 为空 / 只有 `cli-update-check.json` | **正常**：本机有意不装内核（见[第 3 节](#kernel)），不要跑 `install-browser` |
| 命令找不到 `playwright-cli` | 它在 nvm 的 `.nodejs` shim 目录（随 npm 全局安装）；**新开终端**后再试，`where.exe playwright-cli` 核实 |
| 会话残留 / 浏览器没关掉 | `playwright-cli close-all`；僵尸进程用 `kill-all`；工作区里的 `.playwright-cli\` 目录可直接删除 |
| 页面 404 / 502 噪声 | `/favicon.ico` 404、后端未起时 `/api/...` 502 属预期（见[第 5 节](#usage)） |

## 8. 关联文档 <a id="related"></a>

- 《[google-chrome部署使用说明](google-chrome部署使用说明.md)》：系统 Chrome（Playwright 首选内核）的安装、更新与 CDP 自检
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：浏览器真机验证主通道（Playwright MCP）的登记与走查口径
- 《[VSCode部署使用说明](VSCode部署使用说明.md)》：浏览器断点的平台覆盖（另一条浏览器链路）
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc Windows 侧开发设施汇总
- 《[playwright部署使用说明](../linux/playwright部署使用说明.md)》：linux 侧同名文档（镜像装内核与系统 Chrome 口径的由来）
- 《[前端开发规范](../../../规范/前端开发规范.md)》：前端门禁与开发态核对页口径
- 平台《main 流水线》：CI 侧 Playwright E2E job（与本文的本地核验用途区分）

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc（Windows 侧）本机核实结果

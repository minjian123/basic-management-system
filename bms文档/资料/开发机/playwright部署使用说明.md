# playwright 部署使用说明

> mjpc 开发机 Playwright CLI（真实浏览器核验）与浏览器内核安装口径 · 2026-10-03

[文档首页](../../文档首页.md) › 资料 › 开发机 › playwright 部署使用说明　|　[同级：google-chrome部署使用说明 →](google-chrome部署使用说明.md)　[开发机部署使用说明总览 →](开发机部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** 上 **Playwright CLI** 的部署与使用：CLI 从哪来、内核怎么装（**官方 CDN 被拦 → 走国内镜像**）、为什么 Playwright 自带的 Chromium 一直装不上、以及改用**系统 Chrome**（`--browser=chrome`）后的最终口径；另含常用命令与排障。

定位说明：本机 Playwright 用于**开发态真实浏览器核验**（开发态核对页、宿主页面的渲染 / 样式 / 交互实测，作为 jsdom 用例之外的补充证据）。**CI 侧 E2E 归《[main 流水线](../../项目/00_准备期/任务/02_仓库与CI/02_仓库与CI_04_main流水线/02_仓库与CI_04_main流水线.md)》**（Playwright E2E job，服务容器内起后端与前端产物），两者相互独立。

> **取值说明**：路径统一用 `~` 表示（开发用户 `minjian`）；凭据类信息不在本文记录。

## 2. 环境概览 <a id="env"></a>

| 项 | 取值 |
| --- | --- |
| CLI | **`@playwright/cli@0.1.22`**（全局 npm 安装；二进制 `playwright-cli`，随 nvm 的 Node v24.20.0） |
| 内置 playwright-core | 1.64.0-alpha-1790635538000（内核需求版本由它决定） |
| 内核目录 | `~/.cache/ms-playwright/` |
| 已装内核 | **firefox-1553**、ffmpeg-1011（2026-10-03 现状） |
| 缺的内核 | **chromium-1247 / chromium-headless-shell-1247**（原因见[第 4 节](#mirror)）；不再尝试 |
| 浏览器来源口径 | **系统 Google Chrome**（`--browser=chrome`，见《[google-chrome部署使用说明](google-chrome部署使用说明.md)》），Playwright Firefox 作兜底 |
| 内核下载源 | 国内镜像 `https://registry.npmmirror.com/-/binary/playwright`（环境变量 `PLAYWRIGHT_DOWNLOAD_HOST`） |

## 3. 内核安装（国内镜像） <a id="deploy"></a>

### 3.1 官方 CDN 不可用的表现 <a id="cdn-blocked"></a>

Playwright 官方内核走 `https://cdn.playwright.dev/dbazure/download/playwright`（重定向到 `playwright.download.prss.microsoft.com`）。本机网络下该域被**网关拦截**：

```bash
curl -sL -o /dev/null -w "%{http_code}\n" \
  https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1247/chromium-linux.zip
# → 400，响应体为网关错误页（ GatewayExceptionResponse ）
```

于是 `playwright-cli install-browser ...` 长时间无进展（表现为「卡住」）。

### 3.2 镜像安装 <a id="mirror"></a>

```bash
export PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright
playwright-cli install-browser firefox        # 装 Firefox（本机 1553，与 CLI 需求一致）
playwright-cli install-browser --list         # 查看已装内核与版本
```

镜像 URL 拼接口径为 `${PLAYWRIGHT_DOWNLOAD_HOST}/${downloadPath}`，其中 `downloadPath` 形如 `builds/<内核名>/<版本>/<内核名>-linux.zip`（可按浏览器分别覆盖：`PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST` / `PLAYWRIGHT_FIREFOX_DOWNLOAD_HOST` / `PLAYWRIGHT_WEBKIT_DOWNLOAD_HOST`）。

**镜像与本机 CLI 的版本对照（2026-10-03 实测）**：

| 内核 | CLI 需求 | 镜像最高 | 结论 |
| --- | --- | --- | --- |
| chromium | 1247 | **1243** | ✗ 装不上（差 4 个版本） |
| chromium-headless-shell | 1247 | **1155** | ✗ 更旧，同样不可用 |
| **firefox** | 1553 | **1553** | ✓ 已装 |
| **webkit** | 2368 | **2368** | ✓ 可装（本机未装，Linux 下系统依赖较重） |
| ffmpeg / winldd | 1011 / 1007 | 1011 / 1007 | ✓ 已装 ffmpeg |

> **不要用的两个「镜像」**：`https://cdn.npmmirror.com/binaries/playwright/...`（根与文件均 404）、`https://mirrors.huaweicloud.com/playwright/...`（返回 HTML 兜底页，HTTP 200 是**假 200**，`content-type: text/html` 且 `content-length` 对不上，判断时必须看响应头而不是状态码）。

### 3.3 结论：走系统 Chrome <a id="use-chrome"></a>

Chromium 系内核经镜像补齐**不可行**（版本永远滞后于 CLI），因此本机定稿为：

- **Playwright 首选 `--browser=chrome`**（系统 Google Chrome 154，走 chrome 通道，无需下载内核）；
- **兜底 `--browser=firefox`**（Playwright 自带内核 1553，已装）；
- **不再尝试** `install-browser chromium`（含 `--no-shell`）。

## 4. 使用 <a id="usage"></a>

```bash
cd ~/develop/bizs                        # 快照/日志落工作目录下的 .playwright-cli/

playwright-cli open --browser=chrome http://localhost:5173/login-check.html   # 打开（默认无头）
playwright-cli goto http://localhost:5173/login                               # 同一会话内跳转
playwright-cli snapshot                                                       # 页面结构快照（落文件）
playwright-cli screenshot --filename=/tmp/x.png                               # 截图
playwright-cli eval "() => document.querySelectorAll('[data-check]').length"  # 取页面数据（结果在 ### Result 段）
playwright-cli console                                                        # 页面控制台（排 JS 异常首选）
playwright-cli close                                                          # 关闭会话
```

口径与注意：

- `--browser` 取值限 **`chrome` / `firefox` / `webkit` / `msedge`**；**不接受 `chromium`**（自带 Chromium 走缺省通道，本机未装）；
- `eval` 的返回值打印在 `### Result` 段，取值时按该段截取；返回复杂对象建议 `JSON.stringify` 后返回字符串；
- 快照/日志/视频默认写当前目录的 `.playwright-cli/`（含 `page-*.yml`、`console-*.log`）——**用完清理**，不要留在仓库工作区；
- `--idle-timeout` 缺省为无头 1 小时、有头不超时；需要常驻会话时可显式设置；
- 开发态核对页在**后端未起**时会出现预期噪声：`/favicon.ico` 404 与 `/api/.../captcha/scenes/login/policy` 502，不属页面缺陷。

## 5. 常见问题 <a id="troubleshoot"></a>

| 现象 | 处理 |
| --- | --- |
| `install-browser` 长时间无输出 / 卡住 | 官方 CDN 被拦（见[3.1](#cdn-blocked)）；设 `PLAYWRIGHT_DOWNLOAD_HOST` 走镜像，或按[3.3](#use-chrome)改用系统 Chrome |
| 镜像上 404 | 先看镜像版本表（[3.2](#mirror)）：Chromium 系长期滞后；确认 URL 拼接为 `builds/<内核>/<版本>/...` |
| 某「镜像」返回 200 但装不上 | 假 200（HTML 兜底页）：核对 `content-type` / `content-length`，别只看状态码 |
| `--browser=chromium` 报错 | 该取值不受支持；改用 `--browser=chrome`（系统 Chrome）或 `--browser=firefox` |
| `browser 'default' is not open` | 先 `open` 建立会话再 `goto` / `eval` / `click` |
| 会话残留占用 | `playwright-cli close`（或 `close-all`）；强制清理用 `kill-all` |
| 页面样式/接口异常但非本次改动 | 走 `console` 与 `network` 定位；无后端时的 404/502 见[第 4 节](#usage)末条 |

## 6. 关联文档 <a id="related"></a>

- 《[google-chrome部署使用说明](google-chrome部署使用说明.md)》：系统 Chrome（Playwright 首选内核）的安装与验证
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：IDE 内 `playwright-cli` 插件、运行与调试启动项
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发设施汇总
- 《[main 流水线](../../项目/00_准备期/任务/02_仓库与CI/02_仓库与CI_04_main流水线/02_仓库与CI_04_main流水线.md)》：CI 侧 Playwright E2E job（与本文的本地核验用途区分）
- 《[前端开发规范](../../规范/前端开发规范.md)》：前端门禁与核对页口径

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-10-03 mjpc 内核安装与口径定稿

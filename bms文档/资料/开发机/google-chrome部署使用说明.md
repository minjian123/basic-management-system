# google-chrome 部署使用说明

> mjpc 开发机 Google Chrome（系统浏览器：IDE 浏览器断点与 Playwright 的首选内核）部署与使用 · 2026-10-03

[文档首页](../../文档首页.md) › 资料 › 开发机 › google-chrome 部署使用说明　|　[同级：playwright部署使用说明 →](playwright部署使用说明.md)　[CodeBuddy部署使用说明 →](CodeBuddy部署使用说明.md)　[开发机部署使用说明总览 →](开发机部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS，x86_64）上 **Google Chrome** 的部署与使用口径：为什么装它、与系统 Chromium / Playwright 自带 Chromium 的分工、安装与验证步骤、排障入口。

配套文档：

- 《[playwright部署使用说明](playwright部署使用说明.md)》：Playwright CLI 与内核安装（本机为何装不上 Playwright 自带 Chromium，以及为何改用系统 Chrome 走 `--browser=chrome`）
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》「运行与调试启动项」节：IDE 内如何用本浏览器打断点
- 《[goat-gauge部署使用说明](goat-gauge部署使用说明.md)》：早先的 snap Chromium 会话捕获用法（另一条旧路径，与本文不冲突）

> **取值说明**：路径统一用 `~` 表示（开发用户 `minjian`）；凭据类信息不在本文记录。

## 2. 背景与结论 <a id="background"></a>

本机存在**三类** Chromium 系浏览器，用途与可调试性不同，先分清再选：

| 类别 | 来源 | 版本 | 本机取舍 |
| --- | --- | --- | --- |
| Playwright 自带 Chromium | `playwright install chromium` 下载（官方 CDN） | 需 **1247** | **装不上**：官方 CDN 被本网络网关拦、国内镜像只同步到 1243 → 放弃（见[playwright部署使用说明](playwright部署使用说明.md)） |
| 系统 Chromium（snap） | `apt`/snap 发行包（`/snap/bin/chromium`） | 153.x | **保留作备用**（IDE 浏览器断点把 `runtimeExecutable` 换成 `chromium` 即用） |
| **系统 Google Chrome** | Google 官方 `.deb`（本机本次安装） | **154.0.8037.97** | **首选**：IDE 浏览器断点 + Playwright `--browser=chrome` 都用它 |

**结论**：Chrome 作为本机唯一的「首选浏览器内核」；snap Chromium 不卸载、留作备用；Playwright 自带的 Chromium 不再尝试。

## 3. 技术环境 <a id="environment"></a>

| 项 | 取值 |
| --- | --- |
| 版本 | **Google Chrome 154.0.8037.97**（deb 包 `google-chrome-stable` 154.0.8037.97-1，amd64） |
| 可执行文件 | `/usr/bin/google-chrome`（同 `google-chrome-stable`，另注册为 `x-www-browser` / `gnome-www-browser` 备选） |
| 安装形态 | **apt 安装官方 `.deb`**；同时登记 Google 官方源 `/etc/apt/sources.list.d/google-chrome.sources` → **随 `apt upgrade` 更新**（与 CodeBuddy「手工 deb 无源」不同） |
| 用户数据目录 | `~/.config/google-chrome/`（自动化/调试另用独立 `--user-data-dir`，不污染日常配置） |
| 与 snap Chromium 关系 | 两者并存、互不影响（不同可执行文件与 profile），按启动项切换 |
| 主要用途 | ① IDE（js-debug）浏览器断点；② Playwright `--browser=chrome` 真实浏览器核验 |

## 4. 安装 <a id="deploy"></a>

### 4.1 下载与安装 <a id="install"></a>

```bash
# 1) 下载官方 deb（dl.google.com 本机可达，约 142 MB）
curl -L -o /tmp/google-chrome-stable.deb \
  https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 2) apt 安装（本地路径形式；自动解依赖并登记 Google 源）
sudo apt-get install -y /tmp/google-chrome-stable.deb

# 3) 清理
rm -f /tmp/google-chrome-stable.deb
```

> 免密 sudo 可用（本机口径见《[开发机部署使用说明总览](开发机部署使用说明总览.md)》）；如 `apt` 报依赖缺失，`sudo apt-get -f install` 补齐。

### 4.2 验证 <a id="verify"></a>

```bash
google-chrome --version                 # Google Chrome 154.0.8037.97
dpkg -l google-chrome-stable | tail -1  # ii  google-chrome-stable 154.0.8037.97-1 amd64
command -v google-chrome                # /usr/bin/google-chrome
```

**远程调试可用性自检**（IDE 浏览器断点与 Playwright 均依赖 CDP，必须先验证能带调试端口起来）：

```bash
(google-chrome --headless=new --no-first-run --disable-gpu \
  --remote-debugging-port=9231 --user-data-dir=/tmp/chrome-probe about:blank &)
sleep 6
curl -s http://127.0.0.1:9231/json/version | head -c 160   # 应返回 Browser/Protocol-Version
pkill -f "chrome-probe"; rm -rf /tmp/chrome-probe
```

本机 2026-10-03 实测返回 `"Browser": "Chrome/154.0.8037.97"`、`Protocol-Version 1.3`。

## 5. 使用 <a id="usage"></a>

### 5.1 IDE 浏览器断点 <a id="usage-ide"></a>

调试启动项（`bizs/.vscode/launch.json` 与 `bms/.vscode/launch.json` 各一份，见《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》「运行与调试启动项」节）里：

```jsonc
{ "type": "chrome", "runtimeExecutable": "google-chrome", ... }   // 首选
{ "type": "chrome", "runtimeExecutable": "chromium", ... }        // 备用（snap Chromium）
```

可用的断点能力：页面 JS、Vue 组件源码（`webRoot` 指向 `bms/frontend/apps/desktop/src`，sourcemap 由 Vite 提供）。

### 5.2 Playwright <a id="usage-playwright"></a>

```bash
cd ~/develop/bizs
playwright-cli open --browser=chrome http://localhost:5173/login-check.html
playwright-cli eval "() => document.querySelectorAll('[data-check]').length"
playwright-cli close
```

口径：**首选 `--browser=chrome`**（系统 Chrome），兜底 `--browser=firefox`（已装 Playwright Firefox 1553）。`--browser` 取值限 `chrome` / `firefox` / `webkit` / `msedge`，**不接受 `chromium`**（Playwright 自带 Chromium 走缺省通道，本机未装）。

### 5.3 与 Chromium 的区别（速查） <a id="usage-diff"></a>

| 维度 | Chromium | Google Chrome |
| --- | --- | --- |
| 性质 | 上游开源项目（BSD 类） | 基于 Chromium 的**闭源商业发行版**（含 Google 专有件） |
| 更新 | 无自动更新（随发行版/snap） | 内置更新器；本机经 apt 源更新 |
| Google 账号同步 / Widevine DRM / H.264·AAC 许可版 | 一般不带 | 内置 |
| 内核与协议 | 同为 Blink + V8，同实现 **CDP** | 同左（因此自动化工具两者都能驱动） |
| 本机用途 | 备用浏览器内核 | 首选（IDE 断点 + Playwright） |

## 6. 常见问题 <a id="troubleshoot"></a>

| 现象 | 处理 |
| --- | --- |
| `google-chrome` 不在 PATH | 确认已装：`dpkg -l google-chrome-stable`；未装按[第 4 节](#deploy)安装 |
| 启动报 `SingletonLock` / `ProcessSingleton` | 已有一个实例占用同一 `--user-data-dir`；自动化务必给独立 profile（`--user-data-dir=$(mktemp -d)`），或先关掉其它实例 |
| 调试端口连不上 | 确认带 `--remote-debugging-port=<端口>` 且 profile 独立；`curl http://127.0.0.1:<端口>/json/version` 自检 |
| 想改用 snap Chromium 调试 | 把启动项 `runtimeExecutable` 换成 `chromium`（`/snap/bin/chromium`）；snap 版同样支持自定义 `--user-data-dir` 与调试端口（实测通过） |
| 需要无头截图/取页 | `google-chrome --headless=new --screenshot=/tmp/x.png <url>`，或直接用 Playwright（[5.2](#usage-playwright)） |
| 页面报 `/api/...` 502 | 属后端未起（网关缺位），与浏览器无关；本机联调链路见《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》与阶段五发布口径 |

## 7. 关联文档 <a id="related"></a>

- 《[playwright部署使用说明](playwright部署使用说明.md)》：Playwright CLI 与内核安装（含国内镜像）
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：IDE 安装配置、扩展管理、运行与调试启动项
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发设施汇总（浏览器在其中的定位）
- 《[goat-gauge部署使用说明](goat-gauge部署使用说明.md)》：snap Chromium 会话捕获（旧路径参照）
- 《[文档生成规范](../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-10-03 mjpc 安装与验证结果

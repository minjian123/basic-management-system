# opencode 部署使用说明

> mjpc 开发机 opencode desktop（非 snap、.deb 方式）部署与验证实录 · 2026-08-29

[文档首页](../../文档首页.md) › 资料 › 开发机 › opencode 部署使用说明　|　[同级参照：中文输入法部署使用说明 →](中文输入法部署使用说明.md)　[Steamcommunity_302部署使用说明 →](Steamcommunity_302部署使用说明.md)　[防火墙部署使用说明 →](防火墙部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS，GNOME，Wayland，NVIDIA RTX 4090）上 **opencode desktop**（OpenCode 桌面图形端）从 snap 版改用 **.deb 版**的完整过程：为何弃用 snap、如何手工下载安装、启动遇到 GPU 崩溃的环境特例及 `--disable-gpu` 规避方案、验证结果与排障方法，作为日后重装、迁移或再遇同类问题的参照。

方案经过确认（2026-08-29）：弃用 snap，改用官方 .deb 版；针对本机 NVIDIA/Wayland 下的 GPU 崩溃，默认以 `--disable-gpu` 启动。

## 2. 背景与结论 <a id="background"></a>

### 2.1 现象 <a id="symptom"></a>

配置完[中文输入法（Fcitx5 + kimpanel 候选窗跟随光标）](中文输入法部署使用说明.md)之后，opencode desktop 出现「启动不了」的现象：

- 点击桌面图标**毫无反应**，或窗口一闪而过；
- 反复点击启动，每次都无窗口产出，就像「点了没作用」。

### 2.2 排查过程 <a id="diagnose"></a>

排查中发现两件事，需要分清层次：

1. **进程与后台服务是活的**：主进程、渲染进程、网络/Node 服务都在，`127.0.0.1:<port>` 的后台服务也能返回「服务已就绪」（HTTP 401 即说明服务已起）。但窗口没有真正绘制出来。
2. **GPU 进程在无限崩溃**：启动日志反复出现——

```text
ERROR:content/browser/gpu/gpu_process_host.cc:998
GPU process exited unexpectedly: exit_code=139

ERROR:ui/ozone/platform/wayland/gpu/wayland_surface_factory.cc:252
'--ozone-platform=wayland' is not compatible with Vulkan.
Consider switching to '--ozone-platform=x11' or disabling Vulkan

ERROR:media/gpu/vaapi/vaapi_wrapper.cc:1658
vaInitialize failed: unknown libva error
```

`exit_code=139`（SIGSEGV）说明 GPU 进程在**原生 Wayland + Vulkan** 下初始化即段错误崩溃，且不停重试，最终把主进程也拖垮，导致窗口永远画不出来。

### 2.3 结论 <a id="conclusion"></a>

**根本原因不是 snap 版的问题，也和「输入法跟随光标」的配置无关**，而是本机 **NVIDIA 显卡（RTX 4090、驱动 595.84）与 Electron 应用的 Vulkan/Wayland 初始化不兼容**。

- 这个崩溃在 **snap 版**和 **.deb 版**上**都能复现**，证明与打包方式无关；
- 用 `--ozone-platform=x11` 回退 XWayland**仍然崩溃**（试图切 X11 后 GPU 进程依然 SIGSEGV），说明问题不在 Wayland 本身，而在 GPU 进程初始化；
- 用 `--disable-gpu`（彻底禁用 GPU 进程，走软件渲染）后**不再崩溃**，主进程稳定、服务就绪、窗口正常。

> **关键**：本结论与《[中文输入法部署使用说明](中文输入法部署使用说明.md)》第 7.4 节中"不要用 `ELECTRON_OZONE_PLATFORM_HINT=x11` 回退"的提醒是两条不同的线——那条针对的是**输入法候选窗**，本条针对的是**窗口能否渲染**。用 `--disable-gpu` 解决渲染问题，不会影响 kimpanel 候选窗跟随光标。

### 2.4 为什么弃用 snap <a id="why-not-snap"></a>

- 想要一个更贴近官方、不经过 snap 封装的安装方式，便于自行控制启动参数；
- snap 版为 classic + components 结构，桌面端在其中，且不继承宿主自定义环境变量（对输入法、GPU 等排障不友好）；
- 官方 GitHub Releases 直接发布独立的 `opencode-desktop-linux-amd64.deb`，链路上更直接。

## 3. 技术环境 <a id="environment"></a>

| 项 | 取值 |
| --- | --- |
| 系统 | Ubuntu 26.04.1 LTS（resolute），x86_64 |
| 桌面 | GNOME（`XDG_SESSION_TYPE=wayland`） |
| 显卡 | NVIDIA GeForce RTX 4090（AD102），驱动 595.84 |
| opencode（.deb 版） | 1.18.25 |
| 安装路径 | `/opt/OpenCode/ai.opencode.desktop` |
| 启动器 | `ai.opencode.desktop`（`/usr/bin/ai.opencode.desktop`，指向 `/opt/OpenCode/ai.opencode.desktop`） |
| 配置数据目录 | `~/.config/ai.opencode.desktop/` |
| 数据（会话/项目）目录 | `~/.local/share/opencode/` |

版本说明：本次安装的 .deb 版为 **1.18.25**；此前 snap 版为 1.18.21，属更新版。

### 3.1 依赖（按实际包名） <a id="deps"></a>

`.deb` 包声明的依赖在 Ubuntu 26.04 下的实际包名（t64 后缀属 Ubuntu 24.04+ 的 t64 迁移约定）：

| 声明依赖 | 实际包名（Ubuntu 26.04） |
| --- | --- |
| libgtk-3-0 | libgtk-3-0t64 |
| libatspi2.0-0 | libatspi2.0-0t64 |
| libnotify4 | libnotify4 |
| libnss3 | libnss3 |
| libxss1 | libxss1 |
| libxtst6 | libxtst6 |
| xdg-utils | xdg-utils |
| libuuid1 | libuuid1 |
| libsecret-1-0 | libsecret-1-0 |

## 4. 部署步骤 <a id="deploy"></a>

以下全部在开发机本地执行，安装类命令需 sudo。下载优先走国内加速镜像（GitHub 经 `ghfast.top` 加速，见 4.2）。

### 4.1 卸载 snap 版 <a id="remove-snap"></a>

```bash
sudo snap remove opencode
```

说明：

- 该命令**只删除 `/snap/opencode` 下的程序本体**，**不会**删除你的配置与数据（`~/.config/opencode`、`~/.config/ai.opencode.desktop`、`~/.local/share/opencode` 等），重新装好后登录态与项目都在；
- 卸载后 `/snap/bin/opencode`、`/snap/bin/opencode.desktop` 链接一并移除。

验证卸载完成：

```bash
snap list | grep -i opencode      # 无输出即已移除
ls /snap/bin/opencode* 2>/dev/null || echo "已无 /snap/bin 链接"
```

### 4.2 获取 .deb 安装包 <a id="get-deb"></a>

确定最新版号后，从 GitHub Releases 下载。本机 `github.com` 直连下载很慢，经 **`ghfast.top`** 加速前缀可大幅提速（下游下载类命令统一走该加速的方式）。

```bash
# 1) 用 GitHub API 查最新桌面版资产（github.com 直连 API 不走镜像）
curl -s https://api.github.com/repos/anomalyco/opencode/releases/latest \
  | grep -oE '"tag_name": *"[^"]*"'

# 2) 经 ghfast.top 加速下载 .deb（替换下方 vX.Y.Z 为查到的版本号）
curl -fL -o /tmp/opencode-desktop-linux-amd64.deb \
  "https://ghfast.top/https://github.com/anomalyco/opencode/releases/download/v1.18.25/opencode-desktop-linux-amd64.deb"
```

> 说明：`anomalyco/opencode` 是 opencode 当前的 GitHub 组织仓库。若下载用镜像前缀，`--retry 5 --retry-delay 3` 可增强稳定性；直连慢时优先镜像。

### 4.3 用 apt 安装 .deb <a id="install-deb"></a>

用 `apt-get install` 安装本地 .deb，让 apt 自动补齐依赖（会比直接 `dpkg -i` 省事，依赖来自已配置的国内源）。

```bash
sudo apt-get update
sudo apt-get install -y /tmp/opencode-desktop-linux-amd64.deb
```

- 安装完成后注册启动器 `/usr/bin/ai.opencode.desktop`（指向 `/opt/OpenCode/ai.opencode.desktop`）；
- 桌面应用菜单里出现 **OpenCode** 条目，图标为 `ai.opencode.desktop`；
- 依赖（libxss1 等）由 apt 一起装好，虽见 `debconf` 提示但自动转 Noninteractive 完成，可忽略。

验证安装：

```bash
dpkg -s opencode | grep -E 'Status|Version'   # install ok installed / 1.18.25
ls -l /usr/bin/ai.opencode.desktop             # 指向 /opt/OpenCode/ai.opencode.desktop
```

### 4.4 针对 GPU 崩溃：让启动自动带 --disable-gpu <a id="disable-gpu-default"></a>

**这是本项目环境的关键定制**。deb 版默认启动命令不带任何开关，直接双击仍会复现 2.2 节所述的 GPU 崩溃（窗口闪退/无窗口）。办法是在**用户级**覆盖桌面项，让启动自动带上 `--disable-gpu`，从而不碰系统文件、不影响其他用户。

在 `~/.local/share/applications/` 下创建与系统同名的 `.desktop` 覆盖文件（GNOME 优先读取用户级目录）。两个文件都做（系统里有两个桌面项，见 5.1）：

**`~/.local/share/applications/ai.opencode.desktop.desktop`**

```text
[Desktop Entry]
Name=OpenCode
Exec=/opt/OpenCode/ai.opencode.desktop --disable-gpu %U
Terminal=false
Type=Application
Icon=ai.opencode.desktop
StartupWMClass=ai.opencode.desktop
MimeType=x-scheme-handler/opencode;
Categories=Development;
```

**`~/.local/share/applications/opencode-desktop.desktop`**（系统里这个条目是 `NoDisplay=true`，同样覆盖）

```text
[Desktop Entry]
Name=OpenCode
Exec=/opt/OpenCode/ai.opencode.desktop --disable-gpu %U
Terminal=false
Type=Application
Icon=ai.opencode.desktop
StartupWMClass=ai.opencode.desktop
NoDisplay=true
Comment=Open source AI coding agent
Categories=Development;
```

权限设为 644 并刷新桌面数据库：

```bash
chmod 644 ~/.local/share/applications/ai.opencode.desktop.desktop \
          ~/.local/share/applications/opencode-desktop.desktop
update-desktop-database ~/.local/share/applications
```

> 命令行手启动时，手动带 `--disable-gpu` 即可，效果与桌面双击一致：
> ```bash
> /opt/OpenCode/ai.opencode.desktop --disable-gpu
> ```

## 5. 部署产物与配置 <a id="artifacts"></a>

### 5.1 安装后的文件 <a id="files"></a>

| 路径 | 作用 |
| --- | --- |
| `/opt/OpenCode/` | 桌面端主程序目录（`ai.opencode.desktop`、resources/app.asar、locales 等） |
| `/usr/bin/ai.opencode.desktop` | 启动器符号链接（→ `/etc/alternatives/ai.opencode.desktop` → `/opt/OpenCode/ai.opencode.desktop`） |
| `/usr/share/applications/ai.opencode.desktop.desktop` | 系统桌面项（不带 --disable-gpu，勿直接用于本机） |
| `/usr/share/applications/opencode-desktop.desktop` | 系统第二桌面项（NoDisplay=true，不带 --disable-gpu） |
| `~/.local/share/applications/ai.opencode.desktop.desktop` | **用户级覆盖**：带 `--disable-gpu`（本机生效项） |
| `~/.local/share/applications/opencode-desktop.desktop` | **用户级覆盖**：带 `--disable-gpu`（本机生效项） |
| `~/.config/ai.opencode.desktop/` | 桌面端配置数据（窗口状态、会话、日志子目录 logs/ 等） |
| `~/.local/share/opencode/` | opencode 应用数据（会话、快照、git 等） |

> **要点**：本机真正做到「双击即带 `--disable-gpu`」靠的是 `~/.local/share/applications/` 下的**用户级覆盖**；系统目录里的桌面项仍是无开关的。若日后系统更新重装了 `desktop` 包把用户级覆盖覆盖掉（一般不会），需检查 4.4 节两个文件是否仍在。

## 6. 使用说明 <a id="usage"></a>

- **启动**：桌面/应用菜单点 **OpenCode**；或命令行 `/opt/OpenCode/ai.opencode.desktop --disable-gpu`。
- **正常姿态**：主进程 + 渲染进程 + 网络/Node/音频服务齐全，后台服务 `127.0.0.1:<port>` 返回就绪。日志目录 `~/.config/ai.opencode.desktop/logs/<时间戳>/` 出现且 `main.log` 含 `server ready` 即正常。
- **升级**：新版本会在 `main.log` 出现 "Checking for update" 与 "up-to-date / not available"，官方自动更新走项目自更新通道（`auto updater configured`）。

## 7. 常见问题与故障排查 <a id="troubleshoot"></a>

### 7.1 启动后无窗口 / 闪退 <a id="no-window"></a>

优先排 GPU 崩溃（本机的头号原因）。查看启动日志：

```bash
# 最近一次会话日志
D=$(ls -td ~/.config/ai.opencode.desktop/logs/*/ | head -1); echo "$D"
cat "$D/main.log"         # 是否 app starting → server ready
cat "$D/utility.log"      # 是否 GPU 崩溃
grep -iE 'exit_code=139|GPU process exited|not compatible with Vulkan' "$D"utility.log
```

- 若有 `exit_code=139` / `not compatible with Vulkan`：确认用 `--disable-gpu` 启动（见 4.4/6）。若仍存在，说明用户级覆盖未生效，检查 4.4 节文件。
- 若 `main.log` 停在 `app starting` 而无 `server ready`：多为后台服务未就绪或较早退出，可尝试手动命令行启动看错误。

### 7.2 需要排除 GPU 崩溃影响时 <a id="check-gpu"></a>

```bash
# 主进程是否带 --disable-gpu
ps -eo cmd | grep '/opt/OpenCode/ai.opencode.desktop' | grep -v grep | head

# 是否存在 GPU 崩溃转储（pending 目录有新 .dmp 说明近期崩过）
ls -lt ~/.config/ai.opencode.desktop/Crashpad/pending/*.dmp 2>/dev/null | head
```

### 7.3 环境变量回退 X11 的误区 <a id="ox11-misconception"></a>

不要用 `ELECTRON_OZONE_PLATFORM_HINT=x11` 来解决窗口不出问题——本机实测**设成 X11 后端仍会崩溃**（GPU 进程照样 SIGSEGV），且该变量对 snap 版无效。正解是 `--disable-gpu`。详见 2.3 节。

### 7.4 想恢复 snap 版 <a id="revert-snap"></a>

```bash
sudo snap install opencode       # 恢复 snap 版
# 移除用户级覆盖（让双击回到 snap 默认）：
rm ~/.local/share/applications/ai.opencode.desktop.desktop \
   ~/.local/share/applications/opencode-desktop.desktop
```

## 8. 关联文档 <a id="related"></a>

- 《[中文输入法部署使用说明](中文输入法部署使用说明.md)》：mjpc 的 Fcitx5 + kimpanel 输入法部署，其 7.4 节「候选窗跟随」与本文 2.3 节的「渲染」是两条不同的线，勿混用
- 《[Steamcommunity_302部署使用说明](Steamcommunity_302部署使用说明.md)》：mjpc 上的 Steam 社区加速反代部署与运维
- 《[防火墙部署使用说明](防火墙部署使用说明.md)》：mjpc 开发机 ufw 防火墙规则
- 《[文档生成规范](../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定
- 《[本地资源](../../用户文档/本地资源.md)》：mjpc 相关机器信息取值（已 gitignore）

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-08-29 mjpc 实际安装、排障与验证结果 · 更新日期：2026-08-29

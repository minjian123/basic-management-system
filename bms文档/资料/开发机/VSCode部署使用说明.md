# VS Code 部署使用说明

> mjpc 开发机 Visual Studio Code（官方 deb 版）部署、配置与排障实录 · 2026-10-12 安装（stable 1.141.0）· 同日排查并修复「源代码管理面板看不到仓库」

[文档首页](../../文档首页.md) › 资料 › 开发机 › VS Code 部署使用说明　|　[同级：开发机部署使用说明总览](开发机部署使用说明总览.md)　[CodeBuddy部署使用说明 →](CodeBuddy部署使用说明.md)　[opencode部署使用说明 →](opencode部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS，GNOME，Wayland，NVIDIA RTX 4090）上 **Visual Studio Code 官方版**的部署与使用：安装来源与版本、用户数据目录、扩展沿用、工作区打开口径，以及**「源代码管理面板看不到仓库」的成因与修复**（见[第 6 节](#scm)，这是本机重复出现过的问题）。

本文档与《[开发机部署使用说明总览](开发机部署使用说明总览.md)》「开发设施清单」节配套；VS Code 与 [CodeBuddy](CodeBuddy部署使用说明.md)、[opencode](opencode部署使用说明.md) 同为基于 Electron 的编辑器/IDE，三者**共用同款用户数据布局但各用各的目录**，互不干扰（见[第 4 节](#dirs)）。

> **取值说明**：本机路径统一用 `~` 表示（开发机开发用户为 `minjian`）；账号、令牌等凭据不在本文记录，以本机登录态与《[本地资源](../../用户文档/本地资源.md)》（已 gitignore）为准。

## 2. 环境概览 <a id="env"></a>

| 项           | 取值                                                                                     |
| ------------ | ---------------------------------------------------------------------------------------- |
| 系统 / 桌面  | Ubuntu 26.04.1 LTS（x86_64）；GNOME（`XDG_SESSION_TYPE=wayland`）                          |
| 应用         | Visual Studio Code 官方版（`applicationName = code`）                                     |
| 版本         | **1.141.0**（stable；commit `2a59476c`；deb 包版本 `1.141.0-1791276758`）                   |
| Electron     | 43.7.7（由进程启动参数核实）                                                              |
| 安装形态     | **微软官方 apt 源**（`/etc/apt/sources.list.d/vscode.sources`）→ 随 `apt upgrade` 自动跟进   |
| 应用目录     | `/usr/share/code/`（二进制 `/usr/share/code/bin/code`）                                    |
| 启动器       | `/usr/share/applications/com.microsoft.VSCode.desktop` → `Exec=/usr/share/code/code %F`     |
| CLI          | `/usr/bin/code`（符号链接 → `/usr/share/code/bin/code`），支持 `--list-extensions` 等       |

> 本机 **无 GPU/Wayland 崩溃**：VS Code 日志中未见 GPU 进程段错误（与 [opencode](opencode部署使用说明.md) 在本机 NVIDIA + Wayland 下的 GPU 崩溃不是一类问题），因此**无需** `--disable-gpu`。日志中 `'--ozone-platform=wayland' is not compatible with Vulkan` 一条为无害提示（自动回退渲染路径），不影响使用。

## 3. 安装与升级 <a id="install"></a>

### 3.1 安装形态与 apt 源 <a id="install-form"></a>

VS Code 官方版通过**微软 apt 源**安装（区别于 Ubuntu 自带的 snap 版 `code`），因此 `apt upgrade` 会自动更新：

```bash
# 1) 导入微软签名密钥（指纹 BC52 8686 B50D 79E3 39D3 721C EB3E 94AD BE12 29CF）
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
  | gpg --dearmor | sudo tee /usr/share/keyrings/microsoft.gpg > /dev/null

# 2) 登记 apt 源（deb822 格式）
sudo tee /etc/apt/sources.list.d/vscode.sources > /dev/null <<'EOF'
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: amd64
Signed-By: /usr/share/keyrings/microsoft.gpg
EOF

# 3) 安装
sudo apt-get update
sudo apt-get install -y code
```

> **国内网络实测（2026-10-12）**：`packages.microsoft.com` 源索引本身很快（几十 KB），但其**包站直连仅约 320 KB/s**（249 MB 的 deb 要约 13 分钟）；而官方 Azure CDN 直链 `vscode.download.prss.microsoft.com` **实测约 39 MB/s（6 秒下完）**。因此首次安装建议按 3.2 从 CDN 直链取 deb，源仍保留用于后续自动升级。**未使用第三方镜像**——官方源在本机可达，无需经 ghfast.top 等代理。

### 3.2 首次安装（CDN 直链 + apt 本地装包） <a id="install-first"></a>

```bash
# 1) 取 stable 最新 deb 的直链（跟随官方重定向拿真实 URL）
curl -sI "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64" | grep -i '^location'

# 2) 下载（把 <真实URL> 换成上一步的 location）
curl -fL --retry 3 -o /tmp/code.deb "<真实URL>"

# 3) 校验：下载文件的 sha256 应与官方源 Packages 声明一致
sha256sum /tmp/code.deb
curl -s https://packages.microsoft.com/repos/code/dists/stable/main/binary-amd64/Packages \
  | grep -A20 '^Package: code$' | grep -E '^(Version|SHA256):'

# 4) 用 apt 装本地 deb（自动补齐依赖，如 socat）
sudo apt-get install -y /tmp/code.deb
```

> 本机实测：下载文件 SHA256 `d0ff4f77…6277` 与官方源声明**逐字节一致**后才安装；依赖由 Ubuntu 26.04 的 t64 包 `Provides` 旧包名满足（`libatk1.0-0`/`libatspi2.0-0`/`libcups2`/`libcurl4`/`libglib2.0-0` 等），`ldd /usr/share/code/code` 无缺失库。

### 3.3 与 snap 版的关系（重要） <a id="install-snap"></a>

Ubuntu 软件商店/`snap install code` 装的是 **snap 版**，与本文的官方 deb 版是**两个不同的包**，但**共用同一个用户数据目录** `~/.config/Code`（snap 版日志中同样为 `user-data-dir=/home/minjian/.config/Code`）。

由此带来一条**关键结论**：**从 snap 版换成 deb 版时，设置、扩展、工作区状态全部原样沿用**——既省去重装扩展，也意味着 **snap 版遗留的状态问题（如[第 6 节](#scm)的 SCM 面板故障）会一并带到新装版本上**，看起来像「新装的就有毛病」。

```bash
# 确认当前装的是哪一种
dpkg -l code | tail -1            # deb 版
snap list code 2>/dev/null        # snap 版（无输出即未装）
code --version                    # 两者都可执行
```

卸载：deb 版 `sudo apt-get remove code`，snap 版 `sudo snap remove code`；两者**均不会**删除 `~/.config/Code` 与 `~/.vscode`，用户数据保留。

## 4. 用户数据目录 <a id="dirs"></a>

VS Code 的用户数据分两处（体积为 2026-10-12 本机快照，仅作量级参考）：

| 目录                | 体积   | 内容                                                                                              | 说明                                          |
| ------------------- | ------ | ------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `~/.config/Code/`   | 396 MB | `User/settings.json`（**IDE 设置**）、`User/workspaceStorage/<hash>/state.vscdb`（**工作区状态**，[第 6 节](#scm)修复对象）、`logs/<时间戳>/`、`History/`、`Backups/` | 与 CodeBuddy 同布局，但**目录名不同、互不影响** |
| `~/.vscode/`        | 321 MB | `extensions/`（已装扩展 + `extensions.json`）、`argv.json`（持久启动参数，含 `locale`）              | 扩展宿主目录                                  |
| `~/.vscode-shared/` | 32 KB  | `sharedStorage/state.vscdb`                                                                        | 跨 profile 共享状态                           |

> **与 CodeBuddy 的区别**：CodeBuddy 的用户数据目录是 `~/.config/CodeBuddy CN/`、扩展目录是 `~/.codebuddycn/`，两者**完全独立**。因此同一台机器上 VS Code 与 CodeBuddy 可以并存且各装各的扩展；但**同一工作区在两边的 SCM 状态也各自独立**——一边出问题不代表另一边有问题，反之亦然（这正是[第 6 节](#scm)的定位突破口）。

`argv.json` 关键项：`locale`（本机 `zh-cn`，中文界面）、`enable-crash-reporter`、`disable-hardware-acceleration`（本机未启用）。

## 5. 扩展与工作区 <a id="extensions"></a>

### 5.1 扩展沿用与 CLI 管理 <a id="ext-install"></a>

换装方式（snap ↔ deb）时扩展**自动沿用**，无需重装。用应用自带 CLI 管理：

```bash
code --list-extensions --show-versions     # 列出已装扩展
code --install-extension <发布者.扩展名>    # 安装
code --uninstall-extension <发布者.扩展名>  # 卸载
```

本机已装（2026-10-12，换装后全部正常识别）：

| 扩展                                    | 用途                     |
| --------------------------------------- | ------------------------ |
| `ms-python.python` / `debugpy` / `pylance` / `vscode-python-envs` | Python 后端开发与类型检查 |
| `vue.volar`                             | Vue 前端开发             |
| `ms-ceintl.vscode-language-pack-zh-hans` | 中文语言包               |
| `cweijan.vscode-office`                 | Office 文档预览          |
| `donjayamanne.githistory`               | Git 历史                 |
| `fengze233.dsh-vscode-panel`            | DSH 面板                 |

### 5.2 打开工作区 <a id="workspace"></a>

工作区以 `*.code-workspace` 多根打开（「工作区配置 / BMS 基座 / 产品」多根并置）：

```bash
code ~/develop/bizs/bizs.code-workspace
```

> **工作区打开口径**：本工作区既可用 `.code-workspace` 打开，也可直接打开**裸目录** `~/develop/bizs`。两者会生成**不同的 `workspaceStorage` hash 目录**，因此**各自的 SCM 状态独立**（[第 6 节](#scm)的修复需按实际打开方式定位对应 hash）。本机历史上以裸目录打开为主。

## 6. 源代码管理面板看不到仓库（2026-10-12 排查与修复） <a id="scm"></a>

### 6.1 现象 <a id="scm-symptom"></a>

多仓库工作区（`bizs`：根 + `bms` / `biz` / `mdm` / `test` 共 5 个仓库）里，**源代码管理面板不显示当前文件变化**：面板顶部的仓库选择器停在某个**没有变更的仓库**（本机为 `test`），而有几十条变更的 `bms` 完全不出现；「更改」「仓库」「图表」等视图也可能整块消失。

### 6.2 排查与根因 <a id="scm-rootcause"></a>

**先确认 git 本身没问题**（避免误判为仓库损坏）：

```bash
cd ~/develop/bizs
for d in . bms biz mdm test; do
  printf '%-6s 变更 %2s 条 | %s\n' "$d" \
    "$(git -C "$d" status --short | wc -l)" "$(git -C "$d" status -sb | head -1)"
done
```

本机结果：`bms` 79 条变更、其余为 0——**变更确实存在，是面板没显示它**。再看 Git 扩展日志（`~/.config/Code/logs/<会话>/window1/exthost/vscode.git/Git.log`）确认扫描正常：

```text
[Model][doInitialScan] Initial repository scan completed - repositories (5), closed repositories (0) ...
[Model][openRepository] Opened repository (path): /home/minjian/develop/bizs/bms
```

**根因：IDE 的「工作区状态」里「哪些仓库可见」被改窄了。** 权威存储在 `~/.config/Code/User/workspaceStorage/<hash>/state.vscdb`（SQLite；`<hash>` 目录按同目录 `workspace.json` 的 `folder` 字段定位），关键键如下：

| 键                             | 说明                                                                       |
| ------------------------------ | -------------------------------------------------------------------------- |
| `scm:view:visibleRepositories` | **故障就在这个键**：`visible` 只含部分下标（本次为 `[4]`），有变更的仓库被排除 |
| `workbench.scm.views.state`    | `isHidden: true` 是**正常默认值**，非故障（详见下方「易误判」）              |

`visible` 存的是 `all` 数组的**下标**（不是仓库名）：`all` 顺序为 `[bizs, biz, bms, mdm, test]`，故 `[4]` 正指向**空仓库 test**。

> **易误判（本次踩过）**：`workbench.scm.views.state` 里三个视图的 `isHidden` 在**正常工作的**工作区同样是 `true`（实测 CodeBuddy 的 `bms_other` / `cws` / `Claw` 三项全为 true，面板照常显示变更）——它是默认值，**不能拿来判故障**。判据只有一条：`visible` 是否覆盖 `all`。

> **定位突破口（可复用）**：同一工作区在 **CodeBuddy** 里是正常的（`visible: [0,1,2,3,4]`）。**同一工作区、同一份仓库、两个 IDE 表现不同 ⇒ 排除 git 与工作区本身，锁定为 IDE 侧状态**。排查手法：无 `sqlite3` 命令时用 `python3 -c` + 标准库 `sqlite3` 读 `ItemTable`（先 `SELECT key FROM ItemTable` 过滤 `scm`/`git` 相关键）。

### 6.3 修复 <a id="scm-fix"></a>

用仓库内脚本 `bms/scripts/tools/ide/fix_scm_state.py`（参数化，VS Code / CodeBuddy 通用）：

```bash
cd ~/develop/bizs/bms

# 只看现状（只读，可随时跑，无需退出 IDE）
python3 scripts/tools/ide/fix_scm_state.py --ide vscode --check

# 执行修复（必须先完全退出 VS Code，含所有窗口）
python3 scripts/tools/ide/fix_scm_state.py --ide vscode
```

脚本行为：定位 `state.vscdb` → 自动备份为 `state.vscdb.bak-<时间戳>` → 把 `visible` 改为全部下标（**只改这一处**，`isHidden` 属正常默认值不动）→ **回读校验**并打印结果。**检测到目标 IDE 仍在运行时会直接中止**（运行期间改库会被退出时的内存回写覆盖，白改）。工作区若从未保存过仓库可见性记录（键不存在），脚本报「不适用」并直接退出，不判失败。

修复后重新打开 IDE，面板即显示全部 5 个仓库。实测 `--check` 输出（修复前）：

```text
视图 isHidden：workbench.scm.repositories, workbench.scm, workbench.scm.history（此项为正常默认值，不参与判故障）
仓库总数  ：5，可见下标：[4]
  ✗ [0] /home/minjian/develop/bizs
  ✗ [1] /home/minjian/develop/bizs/biz
  ✗ [2] /home/minjian/develop/bizs/bms
  ✗ [3] /home/minjian/develop/bizs/mdm
  ✓ [4] /home/minjian/develop/bizs/test
```

**备选手段**（不想改数据库时）：命令面板 →「视图: 重置视图位置」；或在面板顶部仓库选择器里手动勾回全部仓库。

### 6.4 预防 <a id="scm-prevent"></a>

用户设置加 `"scm.alwaysShowRepositories": true`（官方描述：让仓库始终在源代码管理视图中可见；本机已加）：

```jsonc
// ~/.config/Code/User/settings.json
"scm.alwaysShowRepositories": true
```

> 该设置**只降低复发概率，不能完全防止**——仓库可见性仍可能被改窄。复发时重跑[6.3](#scm-fix)的脚本即可；若是**视图本身**被误隐藏（面板里整块消失），用命令面板「视图: 重置视图位置」。
>
> **另一处易混淆点**：本工作区根 `.gitignore` 为「`/*` 全忽略 + 白名单」，根仓库本就**只跟踪工作区配置文件**（`AGENTS.md`、`README.md`、`.vscode/`、`*.code-workspace` 等）。因此在面板里选中**根仓库**时「看不到变化」往往是正常的；`bms` / `biz` / `mdm` / `test` 的变更需各自可见才会展示。

## 7. 常见问题 <a id="troubleshoot"></a>

| 现象 | 处理 |
| --- | --- |
| 源代码管理面板只显示一个仓库 / 不显示文件变化 | 见[第 6 节](#scm)：先跑 `--check` 确认，再完全退出后跑修复脚本 |
| 面板里选中根仓库「没有变化」 | 多为正常：根 `.gitignore` 为全忽略 + 白名单，只跟踪配置文件；切到 `bms` 等子仓库查看 |
| 装了官方版后界面/扩展与之前完全一样 | 正常：snap 版与 deb 版**共用 `~/.config/Code`**，设置与扩展原样沿用（见[3.3](#install-snap)） |
| 安装 deb 时提示依赖缺失 | 用 `sudo apt-get install -y /path/to/code.deb`（而非 `dpkg -i`）让 apt 自动补齐；Ubuntu 26.04 的 t64 包已 `Provides` 旧包名 |
| `code` 不在 PATH | 确认已装 `dpkg -l code`；deb 版会建 `/usr/bin/code` 符号链接 |
| 启动报 `SingletonLock` / 已有实例 | 同一 `--user-data-dir` 已被占用；关掉其它窗口，或给自动化场景独立 `--user-data-dir` |
| 日志里 `--ozone-platform=wayland is not compatible with Vulkan` | 无害提示（自动回退渲染路径），不影响使用；如确有渲染异常再考虑 `--disable-gpu` |

## 8. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发设施汇总（VS Code 在其中的定位）
- 《[CodeBuddy部署使用说明](CodeBuddy部署使用说明.md)》：同为 Electron 编辑器；其「源代码管理」面板曾出现同一问题，排查口径可互为参照
- 《[opencode部署使用说明](opencode部署使用说明.md)》：本机另一 AI 编码工具的部署与 NVIDIA/Wayland 排障
- 《[git部署使用说明](git部署使用说明.md)》：git 全局配置与凭据管理
- 《[文档生成规范](../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-10-12 mjpc 安装（stable 1.141.0）与 SCM 面板修复结果

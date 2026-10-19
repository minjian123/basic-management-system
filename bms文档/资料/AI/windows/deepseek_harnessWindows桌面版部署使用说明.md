# deepseek_harness Windows 桌面版部署使用说明

> mjpc（Windows 11 侧）· DeepSeek Harness 桌面版 `0.2.1-rc.2`（Electron 44.7.0）· 插件市场与 Our Free Model 的安装与更新

[文档首页](../../../文档首页.md) › 资料 › [AI](../) › [windows](./) › deepseek_harness Windows 桌面版部署使用说明

## 1. 目的与适用范围 <a id="purpose"></a>

本文档记录 DSH **桌面版（Electron 客户端）**在 **mjpc 的 Windows 侧**的部署形态、插件机制与更新方法。

mjpc 是同机双系统：Ubuntu 侧跑的是**源码版** dsh（`node apps/cli/lib/bin.js web`），Windows 侧跑的是**桌面版**
（安装包形态，独立进程与独立 profile）。两者**插件目录、插件管理机制、更新方式全不相同**，不可混用命令。

| 项 | 桌面版（本文档） | 源码版 |
| --- | --- | --- |
| 典型机器 | mjpc Windows 侧 | mjpc Ubuntu 侧、mjw |
| 部署文档 | 本文档 | 《[deepseek_harness部署使用说明](../linux/deepseek_harness部署使用说明.md)》（Linux/mjpc）、[deepseek_harnessWindows部署使用说明](../../开发服务器/windows/deepseek_harnessWindows部署使用说明.md)（mjw） |
| 安装方式 | 安装包（`DeepSeek Harness.exe`） | `git clone` + `pnpm install` + `pnpm run build` |
| profile 目录 | `~/.dsh/profiles/desktop/` | `~/.dsh/profiles/web/` |
| 插件管理 | 应用内 in-process 插件管理器（设置 → 插件） | `dsh plugin --profile web add <pkg>`（转发 pnpm） |
| 命令行 | **不提供** `dsh` 命令 | `node apps/cli/lib/bin.js` |
| 访问地址 | 应用自动起 Web 服务（随机端口，仅 `127.0.0.1`） | `http://127.0.0.1:3080` |

> 本文档的取值（安装路径、端口、进程号）均取自 mjpc Windows 侧实测；机器通用信息见《[本地资源](../../../用户文档/本地资源.md)》。

## 2. 安装与版本 <a id="install"></a>

### 2.1 安装形态 <a id="install-layout"></a>

桌面版为 Electron 应用，按用户级安装（无需管理员）：

```text
C:\Users\<用户>\AppData\Local\Programs\DeepSeek Harness\
├── DeepSeek Harness.exe          # 主可执行文件（Electron）
├── version                       # Electron 版本（本机 44.7.0）
├── Uninstall DeepSeek Harness.exe
└── resources\
    ├── app.asar                  # 应用主体（约 174 MB）
    ├── app.asar.unpacked\        # 原生模块（node-pty / sherpa-onnx / libreoffice-kit 等）
    ├── runtime\                  # 内置运行时
    │   ├── versions.json         # node 24.21.0 / pnpm 11.28.5
    │   ├── bin\                  # 内置 node
    │   ├── cli\                  # dsh 命令包装（未加入 PATH）
    │   └── primary-runtime\      # node / pnpm / python 三套依赖
    └── app-update.yml            # 自动更新源（nightly 通道）
```

应用整体约 **1.0 GB**（含内置 node、pnpm、Python 及其库）。版本信息有两层，不要混：

| 项 | 取值 | 来源 |
| --- | --- | --- |
| Electron 版本 | 44.7.0 | 安装目录 `version` 文件 |
| 应用版本 | 0.2.1-rc.2 | `app.asar` 内根 `package.json` 的 `name: @deepseek-ai/dsh-desktop` |
| 内置运行时 | node 24.21.0 / pnpm 11.28.5 / Python 3.12.14 | `resources\runtime\versions.json` |

### 2.2 与源码版的关键差异 <a id="install-diff"></a>

- **不提供 `dsh` 命令行**：`resources\cli\` 下有命令包装，但**未加入 PATH**，`~\.dsh\bin\` 也不存在。因此源码版文档里的
  `dsh plugin ...` 在 Windows 侧**无法直接执行**，这是排障时最容易走错的一步。
- **profile 固定为 `desktop`**：环境变量 `DSH_PROFILE=desktop`，profile 目录 `C:\Users\<用户>\.dsh\profiles\desktop\`。
  桌面端独占该 profile（`dsh` CLI 对 `--profile desktop` 有硬性拒绝，仅安装器自身可管理）。
- **Web 服务由应用托管**：主进程派生一个 `dsh-desktop-host` 子进程跑 Web 服务，端口**随机**（本机实测 `127.0.0.1:60910`），
  仅监听 `127.0.0.1`。浏览器访问由应用内的 WebView 承载，一般不单独开浏览器。

## 3. 数据目录 <a id="dirs"></a>

桌面版有两套数据目录，**不要混淆**：

```text
C:\Users\<用户>\AppData\Roaming\@deepseek-ai\dsh-desktop\   # Electron 层（56 MB）
├── logs\                          # 启动崩溃日志（crash-*-web-boot.log 等）
├── Local Storage\ / IndexedDB\    # 渲染进程存储
├── Preferences                    # 窗口与外观偏好
└── .updaterId                     # 自动更新标识

C:\Users\<用户>\.dsh\                # DSH_HOME（DSH 自身数据）
├── profiles\desktop\              # 桌面版 profile（插件装在这里）
│   ├── package.json               # 依赖清单 + dsh.profile.bundles 图层顺序
│   ├── pnpm-lock.yaml             # 锁文件（必须与 package.json 同步）
│   ├── pnpm-workspace.yaml        # 发布新鲜度白名单 allowBuilds 等
│   ├── cordis.patch.yml           # 用户补丁层（模型、端口、插件配置）
│   ├── node_modules\              # 插件实际安装位置
│   ├── vendor\dsh-our-free-model\ # Our Free Model 以本地链接方式装入
│   └── .plugin-manager\logs\      # 每次安装/更新的 pnpm 日志
├── .credentials.yaml              # API Key（write-only）
├── sessions\ / storages\          # 会话与存储
├── logs\                          # 启动诊断（startup-*.log）
├── dsh-market\                    # 插件市场的构建标识
└── our-free-model\                # Our Free Model 数据（设置、目录缓存、备份）
```

> 桌面版**没有** `~/.dsh/settings.yaml`（源码版有）；模型与 provider 配置改由 `profiles\desktop\cordis.patch.yml` 承载。

## 4. 插件机制 <a id="plugins"></a>

### 4.1 插件如何生效 <a id="plugins-load"></a>

插件分**两半**：Node 侧（`main` 入口）与浏览器侧（`dsh.client` 声明的 `client.js`）。装载顺序由
`profiles\desktop\package.json` 的 `dsh.profile.bundles` 数组决定，数组即图层栈，后项覆盖前项。

```text
profiles\desktop\package.json
├── dependencies            # 装了什么包（版本在此钉死）
└── dsh.profile.bundles     # 按序装载哪些包（顺序即优先级）
```

因此**手工改插件必须同时动三处**，缺一处就会不一致：

| 文件 | 作用 | 漏改的后果 |
| --- | --- | --- |
| `package.json` 的 `dependencies` | 声明版本 | pnpm 装不到目标版本 |
| `package.json` 的 `dsh.profile.bundles` | 声明装载 | 装了但不生效（无报错） |
| `pnpm-lock.yaml` | 锁死实际版本与哈希 | 下次安装被回退 |

### 4.2 插件市场 dshmarket <a id="plugins-market"></a>

`dshmarket` 在应用内提供可视化插件市场（设置 → 插件市场，侧边栏亦可入口），可浏览、搜索、一键安装社区插件。

| 项 | 值 |
| --- | --- |
| 包名 / 版本 | `dshmarket`，当前 1.66.42 |
| 仓库 | <https://github.com/dsh-market/dsh-market>（MIT） |
| 落位 | `profiles\desktop\node_modules\dshmarket`，`bundles` 中登记为 `dshmarket`，patch 插入 `id: dsh-market` |
| 区域设置 | `.dsh-market\state.json`：`region: china`（国内走腾讯云镜像 `mirrors.cloud.tencent.com/npm`） |
| 运行日志 | `.dsh-market\log.ndjson`（每次安装/更新一行，含 exit code 与失败原因） |
| 数据目录 | `.dsh-market\`（区域、分组、禁用列表、兼容性探测缓存） |

**市场能更新别的插件，但更新不了自己**——这是本项目实际踩到的坑，机制见 4.2.1。

#### 4.2.1 市场自更新失败的根因 <a id="plugins-market-selfupdate"></a>

在市场的插件列表里对 `dshmarket` 自己点「更新」，**必然失败**，日志形如：

```text
dshmarket -> dshmarket@1.66.42 exit=1 err=… 市场不能在自己的请求里先卸载自己 …
```

原因（上游 issue `#900`）：桌面端的更新是「先卸载旧版 → 再安装新版」两步。卸载会把市场自己从运行中的插件组合里摘掉，
而负责执行「安装新版」的代码**正是市场自己**——它已经被卸载，补装那一步永远不会执行。所以这不是网络、版本或权限问题，
是设计上的自引用死结。

**处置：更新市场不要从市场界面点，改用 4.3 的手工流程。** 该缺陷截至 1.66.42 仍未修复（`lib/official-desktop.js` 中
`market-self-update` 拒绝逻辑仍在），升级市场本身之后仍会遇到同样的限制。

> 若市场界面提示「有 agent 正在运行，拒绝更新」：那是另一层保护——替换插件文件前禁止有会话在跑。等会话结束再操作，
> 或按 4.3 手工更新（手工流程不受此限制，但要自己承担文件被替换的风险）。

### 4.3 手工更新插件的流程 <a id="plugins-manual"></a>

适用于**市场自己更新失败**、或需要在会话进行中更新、或桌面端设置页也失败的情况。

#### 4.3.1 前置：备份 <a id="plugins-manual-backup"></a>

```powershell
$prof = "$env:USERPROFILE\.dsh\profiles\desktop"
$bak  = "$prof\.update-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $bak -Force | Out-Null
Copy-Item "$prof\package.json","$prof\pnpm-lock.yaml","$prof\pnpm-workspace.yaml" $bak
```

#### 4.3.2 改版本并安装 <a id="plugins-manual-install"></a>

以把市场从 1.66.37 升到 1.66.42 为例：

```powershell
$prof = "$env:USERPROFILE\.dsh\profiles\desktop"
$node = "C:\Users\$env:USERNAME\AppData\Local\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
$pnpm = "C:\Users\$env:USERNAME\AppData\Local\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\pnpm\dist\pnpm.mjs"

# 1) 改 package.json 的 dependencies 版本号（用编辑器或脚本，这里用脚本示例）
$pj = Get-Content "$prof\package.json" -Raw | ConvertFrom-Json
$pj.dependencies.dshmarket = "1.66.42"
$pj | ConvertTo-Json -Depth 10 | Set-Content "$prof\package.json" -Encoding UTF8

# 2) 用桌面版自带的 pnpm 安装（必须用它，不要用全局 pnpm）
Push-Location $prof
& $node $pnpm install --no-frozen-lockfile
Write-Host "EXIT=$LASTEXITCODE"
Pop-Location

# 3) 核对落盘版本
(Get-Content "$prof\node_modules\dshmarket\package.json" -Raw | ConvertFrom-Json).version
```

关键点：

- **必须用桌面版内置的 pnpm**（`resources\runtime\primary-runtime\dependencies\`），它带着 profile 期望的 pnpm 版本（11.28.5）
  与依赖存储目录。用全局 pnpm 容易把 `node_modules` 布局改坏。
- `--no-frozen-lockfile` 让 pnpm 按新的 `package.json` 重算并更新锁文件；装完可再用
  `install --frozen-lockfile --lockfile-only --dry-run` 验证锁文件已同步（输出 `is up to date` 即一致）。
- `dsh.profile.bundles` **不用改**——包的登记名没变，只改版本。
- 安装耗时通常几秒到十几秒；若报 `ECONNRESET` 多为镜像抖动，重试即可。

#### 4.3.3 发布新鲜度门槛 <a id="plugins-manual-freshness"></a>

桌面版 profile 的 `pnpm-workspace.yaml` 设了 `minimumReleaseAge: 1440`（分钟），即**发布不满 24 小时的新版本装不上**，
表现为 pnpm 静默回退到旧版本。要装一个刚发布的版本，需把该版本加进白名单：

```yaml
# ~/.dsh/profiles/desktop/pnpm-workspace.yaml
minimumReleaseAgeExclude:
  - dshmarket@1.66.23 || 1.66.28 || 1.66.35 || 1.66.36 || 1.66.37 || 1.66.42
```

> 同一个包名只能写一条规则，多个版本用 `||` 串联——写多条会被 pnpm 静默忽略。

#### 4.3.4 回滚 <a id="plugins-manual-rollback"></a>

```powershell
$prof = "$env:USERPROFILE\.dsh\profiles\desktop"
$bak  = "$prof\.update-backup-<时间戳>"      # 换成实际备份目录

Copy-Item "$bak\package.json","$bak\pnpm-lock.yaml","$bak\pnpm-workspace.yaml" $prof -Force
# 然后完全退出 DSH，重跑：
$node = "C:\Users\$env:USERNAME\AppData\Local\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\node\bin\node.exe"
$pnpm = "C:\Users\$env:USERNAME\AppData\Local\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\pnpm\dist\pnpm.mjs"
Push-Location $prof; & $node $pnpm install --frozen-lockfile; Pop-Location
```

### 4.4 Our Free Model（dsh-our-free-model） <a id="plugins-ofm"></a>

在 DSH 内直连免密免费模型（DeepSeek V4.1 Flash、Kimi K3 等），无需登录、注册或填 API Key；2.0 起另接入
CodeArts、CodeBuddy、WorkBuddy、Qoder、TRAE、Cline 等账号渠道，并提供 Token 用量看板与 OpenAI 兼容的本地转发端口。

| 项 | 值 |
| --- | --- |
| 包名 / 版本 | `dsh-our-free-model`，当前 2.5.4 |
| 仓库 | <https://github.com/Ebony-Vinyl/dsh-our-free-model>（MIT） |
| 安装形态 | **本地链接**：`profiles\desktop\vendor\dsh-our-free-model`，`dependencies` 记 `link:vendor/dsh-our-free-model` |
| 界面入口 | 设置页分区「Our Free Model」（`settings.section` id `our-free-model`），含「插件升级」小节 |
| 数据目录 | `~\.dsh\our-free-model\`：`settings.json`（开关与偏好）、`updates.json`（升级历史）、`rollback\`（备份） |
| 升级入口 | 设置页 → Our Free Model →「插件升级」→「检查更新」/「恢复备份」 |

#### 4.4.1 与插件市场的更新方式完全不同 <a id="plugins-ofm-update"></a>

Our Free Model **不走 pnpm、不走插件市场**，而是自己从 GitHub 拉取签名清单后逐文件替换：

```mermaid
flowchart LR
  A["设置页点「检查更新」"] --> B["拉取 feed/manifest.json<br/>（raw.githubusercontent / jsdelivr / ghfast 多源）"]
  B --> C{"Ed25519 签名<br/>校验通过?"}
  C -->|否| X["拒绝升级<br/>（防伪造清单）"]
  C -->|是| D["下载文件到 staging 目录"]
  D --> E["逐文件 SHA-256 校验"]
  E -->|不符| X
  E -->|通过| F["备份当前版本到 rollback/"]
  F --> G["替换安装目录文件"]
  G --> H["热重载插件（无需重装 DSH）"]
```

要点：

- **不需要动 `package.json` 与锁文件**，也不要用 pnpm 去装它——它是以 `link:` 方式挂进 profile 的本地目录，
  pnpm 管不到它的内部文件。
- 升级**失败可回滚**：设置页「恢复备份」按钮，对应 `~\.dsh\our-free-model\rollback\` 里的上一版文件。
- 升级历史记在 `updates.json`，每次含 `from`/`to`/`ok`/`error`；排障先看这个文件。
- 常见失败：`staging failed: … The operation was aborted due to timeout` 是下载超时（本机实测过一次，重试即成功）；
  `size X != manifest Y` 是清单与文件不匹配（上游发布瞬间抓到了半成品，等几分钟重试）。

#### 4.4.2 版本口径 <a id="plugins-ofm-version"></a>

`settings.json` 里有三个版本字段，排查时按此判断：

| 字段 | 含义 |
| --- | --- |
| `installedVersion` | 磁盘上已安装的版本 |
| `updateNotifiedFor` | 已提示过的新版本（不代表已安装） |
| `catalogSyncedAt` | 模型清单上次同步时间（与插件版本无关） |

## 5. 启动、停止与排障 <a id="run"></a>

### 5.1 进程模型 <a id="run-process"></a>

桌面版为多进程（Electron 常规结构），实测约 6 个进程：

| 进程类型 | 作用 |
| --- | --- |
| `main`（主进程） | 窗口、托盘、自动更新 |
| `main`（`--expose-internals` + `dsh-desktop-host`） | **承载 DSH Web 服务**，参数含 profile 路径与内置 pnpm 路径 |
| `renderer` | 界面渲染 |
| `gpu-process` / `utility`（NetworkService） | 图形与网络 |

停止 DSH 要**完全退出**（含托盘图标），不能只关窗口——主进程仍在时插件文件被占用，更新会失败。

### 5.2 插件更新后为什么需要重启 <a id="run-restart"></a>

插件在 profile **启动时**合成装载。手工替换 `node_modules` 里的文件后，正在运行的进程仍持有旧代码：

- 界面上的版本号可能仍显示旧值；
- 新装的插件半身（client.js）不会自动挂载。

**完全退出并重新打开**后才会以新代码装载。市场的「热更新」（`hot=true`）只对市场自己经手的安装生效，手工更新不触发。

### 5.3 排障 <a id="faq"></a>

| 现象 | 根因 / 处理 |
| --- | --- |
| 市场里点更新 `dshmarket` 一直失败，报「不能在自己的请求里先卸载自己」 | 自引用死结（4.2.1），改用手工流程（4.3）。 |
| 市场提示「有 agent 正在运行，拒绝更新」 | 替换插件文件前禁止有会话在跑；等会话结束，或按 4.3 手工更新。 |
| `dsh` 命令在 Windows 侧找不到 | 桌面版不提供命令行（2.2），用内置 pnpm 直连 profile 目录。 |
| 手工更新后版本号没变 / 插件没生效 | 未完全退出 DSH（5.2）；或只改了 `package.json` 没重装；或漏改 `dsh.profile.bundles`。 |
| 装的是刚发布的新版本，pnpm 却回退了旧版 | 24 小时发布新鲜度门槛（4.3.3），加进 `minimumReleaseAgeExclude` 白名单。 |
| 桌面版启动报 `web boot: N entries did not activate` | 有插件的 client 半身加载失败（本机 2026-10-18 实测：`@linxin666/dsh-remote-web-ui`、`dsh-context`、`dsh-better-sidebar` 三个）。看 `AppData\Roaming\@deepseek-ai\dsh-desktop\logs\crash-*-web-boot.log` 定位具体插件，多为插件版本与当前宿主不兼容，按 4.3 回滚或改版本。 |
| Our Free Model 升级报 `staging failed: … aborted due to timeout` | 下载超时（4.4.1），重试；持续失败看 `~\.dsh\our-free-model\updates.json` 的 `error` 字段。 |
| 想确认某次安装到底跑了什么 | 看 `profiles\desktop\.plugin-manager\logs\operation-*\pnpm.log`（每次一个目录，含完整 pnpm 输出与退出码）。 |

## 6. 关联文档 <a id="related"></a>

- 《[deepseek_harness部署使用说明](../linux/deepseek_harness部署使用说明.md)》：Linux/mjpc 源码版（安装主体、CLI 命令、模型接入等通用内容）
- 《[deepseek_harnessWindows部署使用说明](../../开发服务器/windows/deepseek_harnessWindows部署使用说明.md)》：mjw 源码版（`pnpm dsh web`、访问边界、计划任务执行法）
- 《[LM Studio模型服务使用说明](LM Studio模型服务使用说明.md)》：mjw 本地模型服务
- 《[llamacpp部署使用说明](../linux/llamacpp部署使用说明.md)》：mjpc 本地 llama.cpp 推理服务
- 《[本地资源](../../../用户文档/本地资源.md)》：机器硬件与账号（已 gitignore，不入库）
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档遵循的规范

> 依《文档生成规范》编写 · 桌面版实测基于 DSH 0.2.1-rc.2（Electron 44.7.0）

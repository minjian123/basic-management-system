# git 部署使用说明

> mjpc 开发机 Windows 侧 git 安装、全局配置与仓库使用实录 · 2026-10-16

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › git 部署使用说明　|　[同级：开发机部署使用说明总览 →](开发机部署使用说明总览.md)　[pnpm 部署使用说明 →](pnpm部署使用说明.md)　[uv 部署使用说明 →](uv部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** 的 **Windows 11 侧**（与 Ubuntu 26.04.1 LTS 双系统同机）git 的安装形态、全局配置、本项目仓库（内网 GitLab）接入与 Git Bash 使用注意，作为 Windows 侧重装或迁移后的配置参照。它是《[开发机部署使用说明总览](开发机部署使用说明总览.md)》的 Windows 侧分册；Ubuntu 侧对应文档见《[git 部署使用说明](../linux/git部署使用说明.md)》。

**取值说明**：`<GitLab 主机>` 等占位符与真实凭据的具体值见《[本地资源](../../../用户文档/本地资源.md)》，不在文档中记录。git 协作规则（分支模型、提交信息、MR 流程）见《[Git协作规范](../../../规范/Git协作规范.md)》，本文档只描述 Windows 侧本机 git 的部署与使用。

## 2. 版本与路径（速查） <a id="versions"></a>

| 组件 | 版本 | 路径 |
| --- | --- | --- |
| git（Git for Windows） | 2.56.0.windows.2 | `C:\Program Files\Git\cmd\git.exe` |
| Git Bash | GNU bash 5.3.15(2)-release | `C:\Program Files\Git\bin\bash.exe` |
| 全局配置 | — | `C:\Users\minjian\.gitconfig` |
| 系统级 gitconfig | — | `C:\Program Files\Git\etc\gitconfig`（注册凭据助手为 GCM） |
| 凭据助手 | Git Credential Manager 2.9.1 | Windows 凭据管理器（`cmdkey /list` 可见 `git:http://<GitLab 主机>:8080` 条目） |

来源：Git for Windows 官方安装器（默认组件含 Git Bash 与 Git Credential Manager），装在默认路径 `C:\Program Files\Git`；重装后按本文档核对版本与配置即可恢复。

## 3. 环境前提与安装 <a id="prereq"></a>

Windows 侧两项系统级前提（本机均为 1，已开启）：

| 前提 | 状态 | 作用 |
| --- | --- | --- |
| 开发者模式（`AllowDevelopmentWithoutDevLicense`） | 1 | 允许普通用户创建符号链接（依赖外置用 junction，另见 [pnpm 部署使用说明](pnpm部署使用说明.md)） |
| 长路径（`LongPathsEnabled`） | 1 | 路径超 260 字符上限仍可用（深层 node_modules 必需；git 侧另开 `core.longpaths`，见[第 4 节](#global-config)） |

核对命令（PowerShell）：

```powershell
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock').AllowDevelopmentWithoutDevLicense   # 1
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem').LongPathsEnabled                                # 1
```

git 本身为「开箱即装」型工具：官方安装器默认路径安装后，`C:\Program Files\Git\cmd` 已入系统 PATH（cmd / PowerShell / Git Bash 均可直接 `git`）。若需重装，按官方安装器默认选项安装，装后核对：

```bat
git --version    rem git version 2.56.0.windows.2
where.exe git    rem C:\Program Files\Git\cmd\git.exe
```

> 本机**未装** Docker（容器服务在开发服务器 mjbk 上），git 仅作本地版本控制使用。

## 4. 全局配置 <a id="global-config"></a>

全局配置写入 `C:\Users\minjian\.gitconfig`（本机实测内容，主机名以占位符表示）：

```ini
[user]
	name = minjian
	email = minjian_1@qq.com
[credential "http://<GitLab 主机>:8080"]
	provider = generic
[core]
	autocrlf = false
	longpaths = true
```

| 配置项 | 值 | 作用 |
| --- | --- | --- |
| `user.name` / `user.email` | `minjian` / `minjian_1@qq.com` | 提交作者身份，所有仓库共用（与 Linux 侧同口径，本项目仓库无仓库级覆盖） |
| `core.autocrlf` | `false` | 行尾不做自动转换，配合仓库 `.gitattributes` 避免 CRLF 污染工作区 |
| `core.longpaths` | `true` | 允许长路径（与系统长路径开关配套） |
| `credential.http://<GitLab 主机>:8080.provider` | `generic` | 把该主机的凭据提供者固定为 generic（普通账号认证口径） |

- **凭据助手来自系统级配置**：`C:\Program Files\Git\etc\gitconfig` 内有 `credential.helper = manager`（Git for Windows 自带 Git Credential Manager，见[第 7 节](#credentials)）；Windows 侧不采用 Linux 侧的 `store` 明文凭据文件口径。
- **行尾统一策略**：各仓库根已加 `.gitattributes`——文本文件 `* text=auto eol=lf` 按 LF 检出（Windows / Linux 双端一致），`*.bat` / `*.cmd` / `*.ps1` 按 CRLF 检出（cmd / PowerShell 兼容）。`core.autocrlf=false` 与 `.gitattributes` 两道合下，工作区不再出现 CRLF 与 LF 互染的全文件差异。

核对命令：

```bash
git config --global --list --show-origin   # 带来源文件，确认全局还是仓库级
git config --show-origin core.autocrlf     # 用户级应为 false（系统级缺省为 true，被用户级覆盖）
```

提交信息遵循《[Git协作规范](../../../规范/Git协作规范.md)》「提交信息」节格式：`type(scope): 中文描述`，如 `docs(开发机): 新增 windows 侧部署文档`。

## 5. 验证 <a id="verify"></a>

可直接复制的核对命令：

```bash
git --version                                 # git version 2.56.0.windows.2
where.exe git                                 # C:\Program Files\Git\cmd\git.exe
git config --global --list --show-origin      # 核对第 4 节各项配置
"C:\Program Files\Git\bin\bash.exe" --version # GNU bash, version 5.3.15(2)-release
git -C D:\Develop\bizs\bms status -sb         # ## main...origin/main（GitLab 可达时）
```

## 6. 本项目仓库接入（内网 GitLab） <a id="bms-repo"></a>

本项目仓库按工作区模型克隆在 `D:\Develop\bizs\`（工作区根，其内平级并置 `bms\` 与产品仓库克隆，经各自远端同步，见平台《平台可扩展性规划》）。`bms\` 的远端配置（实测，地址中不含凭据）：

| 远端 | 地址 | 角色 |
| --- | --- | --- |
| `origin`（唯一） | `http://<GitLab 主机>:8080/bms/bms.git` | 开发、MR、CI（日常推送目标） |

- 地址为内网 HTTP，`8080` 为 mjbk 上 GitLab 容器的 HTTP 监听口（见《[GitLab部署使用说明](../../开发服务器/linux/GitLab部署使用说明.md)》）；主机取值见《[本地资源](../../../用户文档/本地资源.md)》。
- **首次认证**：clone / pull / push 时由 Git Credential Manager 弹窗登录 GitLab 账号，认证成功后凭据存入 Windows 凭据管理器（见[第 7 节](#credentials)）。
- 分支 `main` 跟踪 `origin/main`；当前为单人直推 main 模式（《Git协作规范》「目的与适用范围」节「当前阶段简化执行」）。

新机器接入（重装后重建）示例：

```bat
rem <GitLab 主机> 替换为《本地资源》中的取值
git clone http://<GitLab 主机>:8080/bms/bms.git
cd bms
git status -sb          rem 应显示 ## main...origin/main
```

## 7. 凭据管理（GCM） <a id="credentials"></a>

Windows 侧凭据由 **Git Credential Manager**（GCM 2.9.1，随 Git for Windows 提供；系统级 gitconfig 注册 `credential.helper=manager`）管理：

1. 首次访问需要认证的远端时弹窗登录（GitLab 账号）；
2. 凭据以 Windows 凭据条目形式保存（`cmdkey /list` 可见 `LegacyGeneric:target=git:http://<GitLab 主机>:8080`）；
3. 之后同一地址免密访问。

```bat
cmdkey /list                 rem 查看已存凭据（含 git:http://<GitLab 主机>:8080）
git ls-remote origin HEAD    rem 验证凭据可用（能列出远端提交即通过）
```

安全注意：

- 凭据条目对 Windows 当前用户可用，仅适合单人开发机（本机现状）；不要复制条目内容进文档、提交记录或聊天。
- GitLab 侧访问令牌 / 密码变更后，先在凭据管理器里删除 `git:http://<GitLab 主机>:8080` 条目，下次操作重新弹窗登录。

## 8. Git Bash 与脚本执行 <a id="git-bash"></a>

Git Bash（5.3.15）随 Git for Windows 安装，是 `.sh` 脚本与 POSIX 命令在 Windows 的落脚点；仓库脚本现统一「Python 单一实现 + `.sh` / `.bat` 薄包装」（见 [pnpm 部署使用说明](pnpm部署使用说明.md)「依赖外置」节），Git Bash 是可用的 `.sh` 执行环境。实测注意（2026-10-16）：

- **`bash` 在 PATH 上可能解析到 WindowsApps 的 0 字节 WSL 存根**：`where.exe bash` 首条为 `C:\Users\minjian\AppData\Local\Microsoft\WindowsApps\bash.exe`（Store 别名，非 Git Bash；本机 System32 下已无 WSL 版 `bash.exe`，`bash` 仅此一处存根）。需要强制用 Git Bash 时写完整路径 `C:\Program Files\Git\bin\bash.exe`，或把 WindowsApps 目录在 PATH 中后置。
- **Git Bash 内工具面**（实测 `command -v`）：`awk` / `kill` / `ps` / `nohup` / `timeout` / `curl` 有；`ss` / `pgrep` / `lsof` 缺——Linux 侧脚本若用到这三个命令，在 Git Bash 里不可直接迁移。
- **跑脚本前确保 PATH 含用户级目录**：node / pnpm / python / uv 都在用户级 PATH（见 [pnpm 部署使用说明](pnpm部署使用说明.md)、[uv 部署使用说明](uv部署使用说明.md)）；从旧会话或未刷新 PATH 的进程启动 Git Bash 时这些命令可能缺失（实测会让 `python3` 落到 WindowsApps 存根）。可在 Git Bash 会话内临时补齐（实测可用）：

```bash
export PATH="/c/Users/minjian/AppData/Local/Author Software/nvm/.nodejs:$PATH"
export PATH="/c/Users/minjian/AppData/Local/Programs/Python/Python314:/c/Users/minjian/AppData/Local/Programs/Python/Python314/Scripts:$PATH"
python3 --version    # Python 3.14.4（不再是 Store 存根）
node -v && pnpm -v   # v24.20.0 / 11.7.0
```

## 9. 日常操作 <a id="usage"></a>

常用命令（cmd / PowerShell / Git Bash 通用）：

```bash
# 查看状态与差异
git status -sb
git diff                 # 工作区改动
git log --oneline -10    # 最近提交

# 提交（提交信息格式见《Git协作规范》「提交信息」节）
git add <文件>
git commit -m "docs(开发机): 新增 windows 侧部署文档"

# 推送 / 拉取
git push origin main
git pull origin main
git fetch origin         # 只拉不合并，先看再合
```

**`git pull origin main` 语义**：先 `git fetch origin` 把远端 main 下载到本地 `origin/main`，再把它合并到**当前分支**（在 main 上执行即更新本地 main）。本项目仓库远端分支是 `main`；GitHub 系仓库（deepseek-harness、ComfyUI、llama.cpp）默认分支是 `master`——分支名要对上仓库，不确定时 `git branch -r` 先看，或省略分支名直接 `git pull` 按跟踪配置拉取。

使用前提：**开发服务器 mjbk 开机且 GitLab 可达**（远程命令都要连 `http://<GitLab 主机>:8080`，见[第 10.3 节](#server-down)）；本地没有会被合并覆盖的未提交改动；执行后看提示——`Already up to date.` 表示远端无新提交，`Fast-forward` 表示本地指针前移。

- 一个提交只做一件事，禁止「顺便改」混入无关改动。
- 提交信息中文描述，scope 用模块名（user、wf、docs、deps 等），无明确模块可省略。

## 10. 常见问题 <a id="troubleshoot"></a>

### 10.1 `bash` 解析到 WindowsApps 存根（0 字节） <a id="bash-stub"></a>

`where.exe bash` 首条为 WindowsApps 下的 0 字节 Store 别名（WSL 入口），并非 Git Bash。处理：用完整路径 `C:\Program Files\Git\bin\bash.exe` 调用；或把 WindowsApps 目录在 PATH 中后置（见[第 8 节](#git-bash)）。

### 10.2 报「Filename too long」（长路径） <a id="longpath"></a>

深层 node_modules / 依赖仓路径超 260 字符上限时报 `Filename too long`。两道开关缺一不可：系统 `LongPathsEnabled=1`（[第 3 节](#prereq)）与 `git config --global core.longpaths true`（[第 4 节](#global-config)），本机均已开启。

### 10.3 远程操作报「Could not connect to server」（连不上 GitLab） <a id="server-down"></a>

`git pull` / `git push` / `git fetch` / `git clone` 报 `Failed to connect to <GitLab 主机> port 8080 ... Could not connect to server`，通常是**开发服务器 mjbk 关机**（或断网、GitLab 容器未启动）。排查：

```bash
ping <GitLab 主机>          # 不通 = 机器关机/断网（取值见《本地资源》）
curl -s -o /dev/null -w "%{http_code}\n" http://<GitLab 主机>:8080/users/sign_in   # 应返回 200/302
```

mjbk 关机则先远程唤醒（WOL，脚本在 `bms\scripts\tools\wol\`，用法见《[开发服务器电源控制使用说明](../../开发服务器/linux/开发服务器电源控制使用说明.md)》）；开机后 GitLab 容器随 docker 自动恢复，重试即可。

### 10.4 认证失败（401 / 403） <a id="auth-fail"></a>

多为凭据过期或 GitLab 令牌被改：按[第 7 节](#credentials)删除 Windows 凭据管理器中的 `git:http://<GitLab 主机>:8080` 条目，重新操作触发 GCM 弹窗登录；GitLab 侧密码重置后先在浏览器登录 `http://<GitLab 主机>:8080` 重新生成访问令牌。

## 11. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发机设施总览（Windows 侧总纲）
- 《[git 部署使用说明](../linux/git部署使用说明.md)》：Ubuntu 侧对应文档（安装、全局配置、仓库接入与 GitHub 镜像加速）
- 《[pnpm 部署使用说明](pnpm部署使用说明.md)》：前端依赖管理（Node / nvm、pnpm 与依赖外置）
- 《[uv 部署使用说明](uv部署使用说明.md)》：后端 Python 依赖与 .venv 外置
- 《[Git协作规范](../../../规范/Git协作规范.md)》：分支模型、提交信息、MR 流程与版本管理（git 的使用规则）
- 《[GitLab部署使用说明](../../开发服务器/linux/GitLab部署使用说明.md)》：mjbk 上 GitLab CE + runner 的服务器侧部署
- 《[开发服务器电源控制使用说明](../../开发服务器/linux/开发服务器电源控制使用说明.md)》：mjbk 远程唤醒（WOL）与远程关机脚本用法
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档遵循的格式规范
- 《[本地资源](../../../用户文档/本地资源.md)》：`<GitLab 主机>` 等取值（已 gitignore，不入库）

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc Windows 侧本机核实结果（git 2.56.0.windows.2、`~\.gitconfig`、GCM 2.9.1、Git Bash 5.3.15）

# git 部署使用说明

> mjpc 开发机 git 安装、全局配置与仓库使用实录 · 2026-08-31

[文档首页](../../文档首页.md) › 资料 › 开发机 › git 部署使用说明　|　[同级参照：开发机部署使用说明总览 →](开发机部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc**（Ubuntu 26.04.1 LTS）上 git 的安装方式、全局配置、BMS 仓库（内网 GitLab）接入与日常操作，作为重装系统或迁移后的配置参照。它是《[开发机部署使用说明总览](开发机部署使用说明总览.md)》第 3 节「开发工具链 git」一行的详细说明；GitLab 服务器侧的部署见《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》。

**取值说明**：`<mjbk-IP>`、`<访问令牌>` 等占位符与真实凭据的具体值见《[本地资源](../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`，不在文档中记录。git 协作规则（分支模型、提交信息、MR 流程）见《[Git协作规范](../../规范/Git协作规范.md)》，本文档只描述本机 git 的部署与使用。

## 2. 环境与安装 <a id="install"></a>

| 项 | 取值 |
| --- | --- |
| 机器 | mjpc（开发机，Ubuntu 26.04.1 LTS，x86_64） |
| 版本 | git 2.53.0（包版本 `1:2.53.0-1ubuntu1`） |
| 位置 | `/usr/bin/git` |
| 来源 | Ubuntu 系统源（apt），开箱即用，无独立安装过程 |

git 随系统源安装，属「开箱即用」型工具。若日后需重装或升级：

```bash
sudo apt-get update
sudo apt-get install -y git
git --version   # 核对版本
```

> 开发机**未装** Docker（容器服务在开发服务器 mjbk 上），git 仅作本地版本控制使用，不涉及容器内 git。

## 3. 全局配置 <a id="global-config"></a>

全局配置写入 `~/.gitconfig`（本机实测内容，2026-08-31）：

```ini
[credential]
	helper = store
[user]
	name = minjian
	email = minjian_1@qq.com
[url "https://ghfast.top/https://github.com/"]
	insteadOf = https://github.com/
```

| 配置项 | 值 | 作用 |
| --- | --- | --- |
| `credential.helper` | `store` | 凭据保存到 `~/.git-credentials`，首次认证后免密（见[第 6 节](#credentials)） |
| `user.name` / `user.email` | `minjian` / `minjian_1@qq.com` | 提交作者身份，所有仓库共用（BMS 仓库无仓库级覆盖） |
| `url.<镜像>.insteadOf` | `https://ghfast.top/https://github.com/` → `https://github.com/` | GitHub 仓库访问自动走加速镜像（见[第 7 节](#github-mirror)） |

核对命令：

```bash
git config --global --list
git config --list --show-origin   # 带来源文件查看，确认是全局还是仓库级
```

提交信息遵循《[Git协作规范](../../规范/Git协作规范.md)》第 4 节格式：`type(scope): 中文描述`，如 `docs(开发机): 新增 git 部署使用说明`。

## 4. BMS 仓库接入（内网 GitLab） <a id="bms-repo"></a>

BMS 仓库 `~/develop/bms/` 的远端配置（`git remote -v` 实测）：

| 远端 | 地址 | 角色 |
| --- | --- | --- |
| `origin`（唯一） | `http://<mjbk-IP>:8080/bms/bms.git` | 开发、MR、CI、Registry（日常推送目标） |

- 地址为内网 HTTP，`8080` 端口即 mjbk 上 GitLab 容器 `bms-gitlab` 的 HTTP 监听口（见《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》第 2 节）。
- 当前 URL 中**内嵌了访问凭据**（`http://root:<访问令牌>@<mjbk-IP>:8080/...`，实测如此），clone/push 无需再输入密码。令牌属敏感信息，仅存于本机，不入文档、不入提交。
- 分支 `main` 跟踪 `origin/main`；当前为单人直推 main 模式（《Git协作规范》第 1 节「当前阶段简化执行」），feature 分支 → MR 门禁流程暂缓。

> **口径说明**：《Git协作规范》第 2 节约定远端命名为 `gitlab`，本机 BMS 仓库实际配置的远端名为 `origin`（初始 clone 默认名）。日常命令按本机实际以 `origin` 执行；两者指向同一地址，无功能差异。

新机器接入（重装后重建）示例：

```bash
# 占位符替换为真实值：<mjbk-IP> 见《本地资源》，<访问令牌> 为 GitLab root 的 PAT
git clone http://root:<访问令牌>@<mjbk-IP>:8080/bms/bms.git
cd bms
git status -sb          # 应显示 main...origin/main
```

仓库迁移与 GitHub 归档的来龙去脉见《[GitLab迁移使用说明](../工具/GitLab迁移使用说明.md)》。

## 5. 日常操作 <a id="usage"></a>

以 BMS 仓库为例，常用命令速查：

```bash
# 查看状态与差异
git status -sb
git diff                 # 工作区改动
git log --oneline -10    # 最近提交

# 提交（提交信息格式见《Git协作规范》第 4 节）
git add <文件>
git commit -m "docs(开发机): 新增 git 部署使用说明"

# 推送 / 拉取
git push origin main
git pull origin main
git fetch origin         # 只拉不合并，先看再合

# 分支（日常单人直推 main；多人协作时按《Git协作规范》第 3/5 节走分支 + MR）
git checkout -b feature/xxx origin/main   # 从最新 main 切功能分支
git branch -d feature/xxx                 # 合入后删本地分支
```

**`git pull origin main` 是什么**：它是「拉取 + 合并」的简写，等价于先 `git fetch origin`（把远端 main 的最新提交下载到本地 `origin/main`），再把 `origin/main` **合并到当前分支**。注意合并目标是**当前所在分支**——在 main 上执行就是更新本地 main；若在别的分支上执行，会把远端 main 合并进那个分支（日常不这么做）。

> **分支名要对上仓库**：`origin main` 里的 `main` 是**远端分支名**，写错就报 `无法找到远程引用 main`。BMS 仓库的默认分支是 `main`，但 GitHub 系仓库（deepseek-harness、ComfyUI、llama.cpp）的默认分支是 **master**，这些仓库里应写 `git pull origin master`。不确定时先看远端有哪些分支：`git branch -r`（或 `git remote show origin`）。也可以省略分支名直接 `git pull`——git 会按当前分支的跟踪配置自动拉对应分支，最省心。

**使用前提**：

1. 开发服务器 **mjbk 开机且 GitLab 可达**——所有远程命令（pull/push/fetch/clone）都要连 `http://<mjbk-IP>:8080`，服务器关机时直接报 `Failed to connect ... Could not connect to server`（见[第 8.1 节](#server-down)）。
2. **本地没有未提交的冲突改动**——若远端新提交碰了你工作区改过的文件，会报 `Your local changes would be overwritten by merge`，先 `git stash` 或提交再拉。
3. 执行后看提示：`Already up to date.` 表示本地已包含远端全部提交（远端没新东西，或本地已领先）；`Fast-forward` 表示远端有更新、本地指针直接前移；报冲突则按[第 8.6 节](#conflict)处理。

> 单人直推模式下，「先拉再推」的意义：push 前先 pull 确认远端没有他人新提交，避免 push 被拒（`rejected`）或推完才发现分叉。若服务器不可达，pull/push 都无法执行，先处理[第 8.1 节](#server-down)再回来操作。

- **一个提交只做一件事**，禁止「顺便改」混入无关改动。
- **提交信息中文描述**，scope 用模块名（user、wf、docs、deps 等），无明确模块可省略。

## 6. 凭据管理 <a id="credentials"></a>

全局 `credential.helper = store`（见[第 3 节](#global-config)）的工作机制：

1. 首次访问需要认证的远端（如内嵌凭据失效、改为无凭据地址）时，git 提示输入用户名/密码；
2. 认证成功后凭据**明文**保存到 `~/.git-credentials`（本机权限 `600`，仅当前用户可读写）；
3. 之后同一地址免密访问。

```bash
ls -l ~/.git-credentials    # 应为 -rw-------（600）
git credential fill         # 查看 git 会为某地址使用哪组凭据（交互式，勿在共享屏幕执行）
```

安全注意：

- `store` 是明文存储，仅适合**单人开发机**；本机已满足（`~/.git-credentials` 权限 600）。
- 令牌写入远端 URL（BMS 现状）或 `~/.git-credentials` 后即存在于磁盘明文，**不要**把含令牌的地址复制进文档、提交记录或聊天。
- 更换 GitLab 访问令牌时，同步更新两处：

```bash
# 1) 远端 URL 中的令牌
git remote set-url origin "http://root:<新令牌>@<mjbk-IP>:8080/bms/bms.git"
# 2) 或凭据文件中的条目（按需编辑 ~/.git-credentials 后 chmod 600）
```

- 备选方案：改用 SSH 克隆（`ssh://git@<mjbk-IP>:2222/...`，GitLab SSH 端口 2222），密钥认证免明文令牌；当前未采用。

## 7. GitHub 镜像加速 <a id="github-mirror"></a>

全局配置的 `insteadOf` 重写规则（见[第 3 节](#global-config)）让**所有**指向 `https://github.com/` 的 git 操作自动改写为 `https://ghfast.top/https://github.com/`，走加速镜像，解决 GitHub 直连慢/超时问题。本机 `~/develop/` 下的 GitHub 系仓库（deepseek-harness、ComfyUI、llama.cpp）均因此免配置直接 clone/pull。

```bash
# 实际等效命令（origin 地址已含 ghfast.top 前缀，git remote -v 可见）
git remote -v

# 单次绕过镜像（如镜像故障时直连官方）
git -c url.https://github.com/.insteadOf= clone https://github.com/ggml-org/llama.cpp
```

> 该重写是**全局**规则：新建任何 GitHub 仓库 clone 都会自动生效。若镜像失效导致 clone/pull 报错，见[第 8.1 节](#mirror-down)。

## 8. 常见问题与故障排查 <a id="troubleshoot"></a>

### 8.1 远程操作报「Could not connect to server」（连不上 GitLab） <a id="server-down"></a>

`git pull` / `git push` / `git fetch` / `git clone` 等**一切远程命令**报 `Failed to connect to <mjbk-IP> port 8080 ... Could not connect to server`，说明连不上 GitLab 服务器，而非 git 命令用法问题。最常见原因是**开发服务器 mjbk 关机**（或断网、GitLab 容器未启动）。本机实测复现（2026-08-31）：mjbk 关机时 ping 100% 丢包、8080 与 SSH 22 端口均不通。

排查与处理：

```bash
# 1) 确认 mjbk 是否可达（ping 不通 = 机器关机/断网）
ping -c 2 192.168.0.107
# 2) 确认 GitLab HTTP 是否就绪（应返回 200/302）
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.0.107:8080/users/sign_in

# 3) 机器关机则远程唤醒（等待 SSH 就绪，见《开发服务器电源控制使用说明》）
cd ~/develop/bms
python scripts/tools/wol/wake_mjbk.py

# 4) mjbk 开机后 GitLab 容器随 docker 自动恢复（常驻服务），curl 通过后重试
git pull origin main
```

> 若 ping 通但 8080 不通：GitLab 容器没起来，SSH 登录 mjbk 后 `docker ps` 查 `bms-gitlab` 状态，参照《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》第 3 节重启。

### 8.2 GitHub 仓库 clone/pull 超时或报错 <a id="mirror-down"></a>

镜像 `ghfast.top` 不稳定时，GitHub 系仓库操作会失败。排查与绕行：

```bash
# 1) 确认失败地址确实被重写（应看到 ghfast.top 前缀）
git config --get-all url.https://ghfast.top/https://github.com/.insteadof

# 2) 单次绕过镜像直连官方
git -c url.https://github.com/.insteadOf= pull origin master

# 3) 长期切换：直接改远端地址，或临时注释 ~/.gitconfig 中的 [url] 段
```

### 8.3 push/clone 报认证失败（401 / 403） <a id="auth-fail"></a>

多为 GitLab 访问令牌失效或被改。处理：按[第 6 节](#credentials)更新远端 URL 中的令牌（或 `~/.git-credentials` 条目）；若 GitLab 侧 root 密码重置，先在浏览器登录 `http://<mjbk-IP>:8080` 重新生成 PAT。

### 8.4 提交时报「Author identity unknown」 <a id="no-identity"></a>

`user.name` / `user.email` 未设置。全局配置缺失时补写：

```bash
git config --global user.name "minjian"
git config --global user.email "minjian_1@qq.com"
```

### 8.5 误把令牌写进提交或文档 <a id="leak"></a>

内嵌凭据的地址只存在于本机 `.git/config` 与 `~/.git-credentials`（均已 gitignore 或非跟踪文件），正常提交不会入库。若发现含令牌的 URL 出现在 diff 中：立即换新令牌（旧令牌作废），再用 `git filter-repo` 或 `git rebase -i` 改写历史（见《[GitLab迁移使用说明](../工具/GitLab迁移使用说明.md)》相关章节）。

### 8.6 pull 冲突 <a id="conflict"></a>

本地与远端同一文件各有修改时 `git pull` 报冲突。处理：`git status` 看冲突文件 → 手动保留正确内容 → `git add` 后 `git commit`（合并提交）或 `git pull --rebase` 保持线性（重放本地提交到远端之后）。

### 8.7 pull 报「无法找到远程引用 main」 <a id="no-branch"></a>

`fatal: couldn't find remote ref main`（中文：无法找到远程引用 main）表示**远端没有叫 `main` 的分支**，多半是分支名写错或照搬了别的仓库的命令。排查：

```bash
git branch -r          # 看远端有哪些分支（如 origin/master、origin/main）
git pull               # 省略分支名，按当前分支的跟踪配置自动拉取
```

BMS 仓库远端分支是 `main`；GitHub 系仓库（deepseek-harness、ComfyUI、llama.cpp）是 `master`。deepseek-harness 下应执行 `git pull origin master`（见[第 5 节](#usage)的说明框）。已实测复现（2026-08-31）：`git pull origin main` 报该错，改 `git pull origin master` 正常。

## 9. 关联文档 <a id="related"></a>

- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发机设施总览（本文档所属目录的总纲）
- 《[Git协作规范](../../规范/Git协作规范.md)》：分支模型、提交信息、MR 流程与版本管理（git 的使用规则）
- 《[GitLab部署使用说明](../开发服务器/GitLab部署使用说明.md)》：mjbk 上 GitLab CE + runner 的服务器侧部署
- 《[GitLab迁移使用说明](../工具/GitLab迁移使用说明.md)》：仓库迁移至 GitLab、GitHub 归档同步与日常流程
- 《[开发服务器电源控制使用说明](../工具/开发服务器电源控制使用说明.md)》：mjbk 远程唤醒（WOL）与远程关机脚本用法（8.1 节排障的前置步骤）
- 《[文档生成规范](../../规范/文档生成规范.md)》：本文档遵循的格式规范
- 《[本地资源](../../用户文档/本地资源.md)》：`<mjbk-IP>` 等取值（已 gitignore，不入库）

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-08-31 mjpc 本机核实结果（git 2.53.0、`~/.gitconfig`、BMS 远端配置） · 更新日期：2026-08-31（补 8.1 服务器不可达排障与 8.7 分支名排障——均实测复现：mjbk 关机时 `git pull` 报 Could not connect to server；deepseek-harness 下 `git pull origin main` 报找不到 main 分支，改 master 正常）

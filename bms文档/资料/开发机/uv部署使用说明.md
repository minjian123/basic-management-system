# uv 部署使用说明

> mjpc 开发机 uv（后端 Python 包管理 + .venv 外置）部署与使用 · 2026-09-24

[文档首页](../../文档首页.md) › 资料 › 开发机 › uv 部署使用说明　|　[同级：pnpm 部署使用说明 →](pnpm部署使用说明.md)　[git 部署使用说明 →](git部署使用说明.md)　[开发机部署使用说明总览 →](开发机部署使用说明总览.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** 上 uv 的部署与使用：后端 Python 依赖由 **uv 单一管理**（`backend/pyproject.toml` 声明 + `backend/uv.lock` 单一锁文件），且**虚拟环境 .venv 物理外置到依赖仓**（项目仓库树内不落 `.venv`），与前端依赖外置（见[pnpm 部署使用说明](pnpm部署使用说明.md)）同口径。

适用范围：开发机本地后端开发与测试；CI 侧后端镜像/服务子流水线另走 `UV_PROJECT_ENVIRONMENT`（镜像内锁库），与本地互不干扰。

## 2. 背景与结论 <a id="background"></a>

- 后端多服务、共享库（`backend/libs/*`、`backend/services/*`）复用同一依赖集，`pyproject.toml` + `uv.lock` 单一锁文件承担全部声明；
- 项目内 `.venv` 会随测试/运行被轻易重建，且体积大（数百 MB），留在仓库树里同样污染检索与目录结构；
- 结论：**同分区外置**——`.venv` 外置到本地依赖仓 `$DEPS_DIR/backend-venv`，仓库内不落 `.venv`（`.gitignore` 本来已忽略 .venv）；`UV_PROJECT_ENVIRONMENT` 持久到 `~/.bashrc`，任何新的 uv 调用都自动落外置环境。

## 3. 技术环境 <a id="environment"></a>

| 项 | 取值 |
| --- | --- |
| uv | **0.12.7**（pip 安装，`~/.local/bin/uv`，`~/.local/lib/python3.14/site-packages`） |
| python（系统） | 3.14.4（`/usr/bin/python3`；uv 自身可下载任意锁定版本解释器） |
| 后端依赖声明 | `bms/backend/pyproject.toml`（uv 工程） |
| 单一锁文件 | `bms/backend/uv.lock`（**必须提交**） |
| 本地依赖仓 | `bms/deploy/.env` 的 `DEPS_DIR`（默认 `$HOME/dev-deps/bms`） |
| 虚拟环境外置路径 | `$DEPS_DIR/backend-venv`（即 `$HOME/dev-deps/bms/backend-venv`） |
| 外置持久化 | `~/.bashrc` 内 `export UV_PROJECT_ENVIRONMENT="$HOME/dev-deps/bms/backend-venv"` |
| PYPI 镜像 | 清华 TUNA（`UV_DEFAULT_INDEX` / `PIP_INDEX_URL`；CI variables 同款） |

## 4. 部署 <a id="deploy"></a>

### 4.1 安装 uv <a id="install"></a>

本机为 pip 安装（落 `~/.local/bin`）：

```bash
python3 -m pip install --user uv --index-url https://pypi.tuna.tsinghua.edu.cn/simple
uv --version     # uv 0.12.7
which uv         # ~/.local/bin/uv
```

> 也可用官方独立安装脚本（默认同样装 `~/.local/bin/uv`）；升级即重装相同位置。

### 4.2 虚拟环境外置（关键定制） <a id="venv-external"></a>

`.venv` 外置两个落点：`~/.bashrc` 持久化（默认生效） + `deploy/.env` 的 `DEPS_DIR`（脚本读取）。

```bash
# ~/.bashrc（已就位，勿重复追加）：
export UV_PROJECT_ENVIRONMENT="$HOME/dev-deps/bms/backend-venv"
```

生效方式：

- 新开终端自动生效（登录/交互 shell 读 ~/.bashrc）；
- 当前会话：`export UV_PROJECT_ENVIRONMENT="$HOME/dev-deps/bms/backend-venv"`（或重开终端）。

外置环境已随本次迁移创建（`$HOME/dev-deps/bms/backend-venv`）。重建口径：仓库内**永不**手动 `uv sync` 前不删外置仓——需要全新环境时（见[第 7.2 节](#rebuild)）删外置仓对应目录再 sync。

## 5. 使用 <a id="usage"></a>

命令一律在 `bms/backend/` 下执行（uv 自动识别工程）：

| 用途 | 命令 |
| --- | --- |
| 按锁文件同步（推荐） | `uv sync --frozen` |
| 更新锁（改了 pyproject 后） | `uv sync`（或 `uv lock` 后 `uv sync --frozen`） |
| 跑命令（自动用工程环境） | `uv run python -m ops.xxx` |
| 跑测试 | `uv run pytest services/platform/tests --sqlite` |
| 查看环境位置 | `uv run python -c "import sys; print(sys.prefix)"` |

> 装了外置后 `uv sync --frozen` 全量命中（秒级，仅解析 0.0x 秒）；外置仓与仓库同分区，`mv`（rename）行为保留硬链接，无复制损耗。

后端完整重装（前端一并，见 deps 脚本）：

```bash
sh bms/scripts/tools/deps/重装依赖.sh --backend-only   # 后端：还原(无此项)→ uv sync --frozen（落外置）
sh bms/scripts/tools/deps/重装依赖.sh                   # 前后端一起重装
```

## 6. CI 侧口径（后端） <a id="ci"></a>

CI 后端镜像与 job 已有独立外置约定，**与本地不冲突**：

- 后端基础镜像（`deploy/ci/Dockerfile.backend`）在镜像内以 `UV_PROJECT_ENVIRONMENT=/opt/bms-venv` + `UV_NO_SYNC=1` 锁库；
- 服务子流水线（`deploy/ci/templates/backend-service.yml`）与各后端 job 在构建产物内同步 env，不依赖本地 `~/.bashrc`；
- 本地外置只影响开发机 shell：仓库与 CI 配置均不含本地绝对路径，`DEPS_DIR` 仅存在于 `deploy/.env`（gitignore）与 `~/.bashrc`（本机）——见《[开发机部署使用说明总览](开发机部署使用说明总览.md)》。

## 7. 常见问题 <a id="troubleshoot"></a>

### 7.1 项目内又出现了 .venv <a id="venv-again"></a>

任何未带外置变量的 uv 调用（如某些脚本/工具以子进程裸跑 uv）都会按默认路径重建项目内 .venv。处置：

```bash
rm -rf bms/backend/.venv          # 仓库内不留（.gitignore 已忽略，不影响 git）
# 确认外置环境存在 & .bashrc 已 export；重开终端后 uv 自动落外置
```

### 7.2 外置环境损坏需重建 <a id="rebuild"></a>

```bash
rm -rf "$HOME/dev-deps/bms/backend-venv"     # 全新开头（同分区、秒级）
cd bms/backend && uv sync --frozen            # 重新构建外置环境
```

> 只能删外置仓里的 backend-venv；仓库内 `.venv` 若有残留先按第 7.1 节清掉，避免出现两份环境混淆。

### 7.3 改依赖后 frozen 失败 <a id="frozen-sync"></a>

`pyproject.toml` 与 `uv.lock` 不一致：先 `uv sync`（更新锁）或 `uv lock`，再回 `uv sync --frozen`。

## 8. 关联文档 <a id="related"></a>

- 《[pnpm 部署使用说明](pnpm部署使用说明.md)》：前端依赖管理（workspace + 依赖外置），与本文同走本地依赖仓与 deps 脚本
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发设施汇总（python/uv 在其中的定位）
- 《[后端开发规范](../../规范/后端开发规范.md)》：后端分层与依赖方向、服务边界（pyproject.toml 工作区成员口径）
- 《[git 部署使用说明](git部署使用说明.md)》：开发机 git 与仓库接入（uv.lock 提交要求见 Git 协作规范）
- 《[文档生成规范](../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定

> 依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 记录 2026-09-24 mjpc 后端 .venv 外置落地状态
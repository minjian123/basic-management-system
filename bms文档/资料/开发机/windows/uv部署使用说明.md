# uv 部署使用说明

> mjpc 开发机 Windows 侧 uv（后端 Python 包管理 + .venv 外置）部署与使用 · 2026-10-16

[文档首页](../../../文档首页.md) › 资料 › 开发机 › windows › uv 部署使用说明　|　[同级：开发机部署使用说明总览 →](开发机部署使用说明总览.md)　[git 部署使用说明 →](git部署使用说明.md)　[pnpm 部署使用说明 →](pnpm部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

记录开发机 **mjpc** 的 **Windows 11 侧**（与 Ubuntu 26.04.1 LTS 双系统同机）上 uv 的部署与使用：后端 Python 依赖由 **uv 单一管理**（`backend\pyproject.toml` 声明 + `backend\uv.lock` 单一锁文件），**虚拟环境 `.venv` 物理外置到依赖仓**（Windows 侧为 junction，项目仓库树内不落实体），与前端依赖外置（见 [pnpm 部署使用说明](pnpm部署使用说明.md)）同套脚本、同一依赖仓。Ubuntu 侧对应文档见《[uv 部署使用说明](../linux/uv部署使用说明.md)》。

适用范围：开发机本地后端开发与测试；CI 侧后端镜像/服务子流水线另走 `UV_PROJECT_ENVIRONMENT`（镜像内锁库），与本地互不干扰（见[第 7 节](#ci)）。

## 2. 版本与路径（速查） <a id="versions"></a>

| 组件 | 版本 | 路径 |
| --- | --- | --- |
| Python（官方安装器） | 3.14.4 | `C:\Users\minjian\AppData\Local\Programs\Python\Python314`（已加入用户 PATH，含 `python3` 垫片） |
| py launcher | — | `C:\Users\minjian\AppData\Local\Programs\Python\Launcher\py.exe`（`py -0p` 实测默认 3.14） |
| pip | 26.0.1 | 随 Python；TUNA 源（`%APPDATA%\pip\pip.ini`） |
| uv | **0.12.7** | `...\Python314\Scripts\uv.exe`（pip 安装，同目录另有 uvx / uvw） |
| uv 配置 | — | `%APPDATA%\uv\uv.toml`（TUNA 索引，内容见[第 3.3 节](#install-uv)） |
| uv 缓存 | — | `%LOCALAPPDATA%\uv\cache`（实测 `uv cache dir`） |
| 后端依赖声明 | — | `D:\Develop\bizs\bms\backend\pyproject.toml`（uv 工程） |
| 单一锁文件 | — | `D:\Develop\bizs\bms\backend\uv.lock`（**必须提交**） |
| 本地依赖仓 | — | `D:\dev-deps\bms`（DEPS_DIR，与 pnpm 共用，见 [pnpm 部署使用说明](pnpm部署使用说明.md)「依赖外置」节） |
| 虚拟环境外置 | — | `backend\.venv` 为 **junction** → `D:\dev-deps\bms\backend-venv` |
| PYPI 镜像 | 清华 TUNA | pip.ini / uv.toml（CI variables 同款） |

## 3. 安装与配置过程 <a id="install"></a>

### 3.1 Python（官方安装器） <a id="python"></a>

Python 由**官方安装器**装入用户目录 `%LOCALAPPDATA%\Programs\Python\Python314`（3.14.4），含 `python3` 垫片（仓库脚本统一「Python 单一实现」，`python3 xxx.py` 双平台同口径即依赖此垫片），随装 py launcher；安装时加入用户 PATH，`python3` / `python` / `py` 均可直接调用。核对：

```bat
python3 --version    rem Python 3.14.4
where.exe python3    rem C:\Users\minjian\AppData\Local\Programs\Python\Python314\python3.exe
py --version         rem Python 3.14.4
py -0p               rem 列出已装解释器（默认 3.14）
```

> uv 自身也能管理解释器（`uv python list` 会列出可下载版本，本机已识别上述 3.14.4）；本机当前使用用户级 Python 3.14.4。

### 3.2 pip 源 <a id="pip"></a>

`%APPDATA%\pip\pip.ini` 已配置清华 TUNA（本机实测内容）：

```ini
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3.3 安装 uv 与 uv 配置 <a id="install-uv"></a>

uv 经 pip 装入与 Python 同层的用户目录 `Scripts\`：

```bat
python3 -m pip install uv     rem pip.ini 已指向 TUNA，无需再写 --index-url
uv --version                  rem uv 0.12.7 (61291a8ca 2026-08-27 x86_64-pc-windows-msvc)
where.exe uv                  rem C:\Users\minjian\AppData\Local\Programs\Python\Python314\Scripts\uv.exe
```

`%APPDATA%\uv\uv.toml`（本机实测内容，TUNA 为默认索引）：

```toml
[[index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
```

> 升级 uv 即重跑同一条安装命令（`python3 -m pip install --upgrade uv`）。

## 4. 虚拟环境外置（关键定制） <a id="venv-external"></a>

`.venv` 实体在本地依赖仓，仓内原位为 junction：

```text
D:\Develop\bizs\bms\backend\.venv  --(junction)-->  D:\dev-deps\bms\backend-venv
```

外置与还原由 `bms\scripts\tools\deps\` 三入口脚本统一处理（与前端 node_modules 同一套脚本、同一依赖仓；脚本入口与 `DEPS_DIR` 口径详见 [pnpm 部署使用说明](pnpm部署使用说明.md)「依赖外置」节）：

```bat
rem 在 bms 仓根执行；本机依赖仓须先显式指定（DEPS_DIR 未持久化）
set DEPS_DIR=D:\dev-deps\bms
scripts\tools\deps\外置依赖.bat                 rem 搬移 + 建 junction（含后端 .venv）
scripts\tools\deps\重装依赖.bat --backend-only  rem 还原 → backend\ 下 uv sync --frozen → 再外置
```

**为什么不用 `UV_PROJECT_ENVIRONMENT`**：该变量只对导出它的进程及子进程生效，且全局导出会**跨仓串环境**（Linux 侧 2026-10-14 实测：在 mdm 目录下 `uv run` 把 mdm 的包装进了 bms 共享环境），Windows 侧同口径不用；junction 链接链路每仓自持、不随环境变量漂移。实测（2026-10-16）：

- 外置态下 `uv sync --frozen` **保留 junction**（输出 `Checked 101 packages in 4ms`，秒级完成）；
- `uv run python -c "import sys; print(sys.prefix)"` 输出 `D:\Develop\bizs\bms\backend\.venv`（字面路径，不穿透 junction）。

> 前提：基座工程根定位不穿透链接（`bms_core.core.paths.resolve_backend_root`）——外置后包体虽在依赖仓，仍能经 `backend\.venv\...` 这一字面层级上溯到仓库内工程根；若穿透解析会向上搜不到 `alembic.ini` / `config.toml` 而报 `ConfigError`。

## 5. 使用 <a id="usage"></a>

命令一律在 `bms\backend\` 下执行（uv 自动识别工程）：

| 用途 | 命令 |
| --- | --- |
| 按锁文件同步（推荐） | `uv sync --frozen` |
| 更新锁（改了 pyproject 后） | `uv sync`（或 `uv lock` 后 `uv sync --frozen`） |
| 跑命令（自动用工程环境） | `uv run python -m ops.xxx` |
| 跑测试 | `uv run pytest services/platform/tests --sqlite` |
| 查看环境位置 | `uv run python -c "import sys; print(sys.prefix)"` |

> 外置态（`.venv` 为 junction）下 `uv sync --frozen` 保留链接、日常直接可用（实测）；仅当需要重建环境时才走还原 / 重装（见[第 8.4 节](#rebuild)）。

后端完整重装（前端一并，见 deps 脚本）：

```bat
set DEPS_DIR=D:\dev-deps\bms
scripts\tools\deps\重装依赖.bat --backend-only   rem 后端：还原 → backend\ 下 uv sync --frozen → 再外置
scripts\tools\deps\重装依赖.bat                  rem 前后端一起重装
```

## 6. 验证 <a id="verify"></a>

可直接复制的核对命令（Python / uv 已在用户级 PATH）：

```bat
uv --version                  rem uv 0.12.7 (61291a8ca 2026-08-27 x86_64-pc-windows-msvc)
cd D:\Develop\bizs\bms\backend
uv sync --frozen              rem Checked 101 packages in 4ms（命中即秒级）
uv run python -V              rem Python 3.14.4
uv run python -c "import sys; print(sys.prefix)"   rem D:\Develop\bizs\bms\backend\.venv
```

链接态核对（PowerShell；应为 Junction，Target 指向 `D:\dev-deps\bms\backend-venv`）：

```powershell
Get-Item D:\Develop\bizs\bms\backend\.venv | Select-Object FullName, LinkType, Target
```

## 7. CI 侧口径（后端） <a id="ci"></a>

CI 后端镜像与 job 已有独立外置约定，**与本地不冲突**：

- 后端基础镜像（`deploy/ci/Dockerfile.backend`）在镜像内以 `UV_PROJECT_ENVIRONMENT=/opt/bms-venv` + `UV_NO_SYNC=1` 锁库；
- 服务子流水线（`deploy/ci/templates/backend-service.yml`）与各后端 job 在构建产物内同步 env，不依赖本地环境变量；
- 本地外置只影响开发机目录布局：仓库与 CI 配置均不含本地绝对路径，`DEPS_DIR` 仅存在于 `deploy\.env`（gitignore）与脚本缺省值。

## 8. 常见问题 <a id="troubleshoot"></a>

### 8.1 项目内又出现了 .venv 实体 <a id="venv-again"></a>

junction 被删除或被重建覆盖（例如手工删掉 junction 后直接 `uv venv` / `uv sync`）时，仓内会重新出现真实环境目录——**两份环境并存且内容可以不一致，误用会得到难以排查的行为差异**，须尽快收回外置态：

```bat
set DEPS_DIR=D:\dev-deps\bms
scripts\tools\deps\外置依赖.bat      rem 依赖仓已有环境即以依赖仓为准，删除仓内残留并重建 junction
```

```powershell
Get-Item backend\.venv | Select-Object LinkType, Target   # 确认是 Junction
```

### 8.2 `python3` 解析到 WindowsApps 存根 <a id="python3-stub"></a>

Windows 自带 Store 版 `python3` 别名（`C:\Users\minjian\AppData\Local\Microsoft\WindowsApps\python3.exe`，执行时报「Python was not found…install from the Microsoft Store」）。本机用户 PATH 中 Python314 目录在先、正常解析；若被存根抢占（多见于 PATH 未刷新的旧会话或顺序被改），核对与处理：

```bat
where.exe python3            rem 首条应为 ...\Programs\Python\Python314\python3.exe
```

换新终端；仍在旧会话里则按 [git 部署使用说明](git部署使用说明.md)「Git Bash 与脚本执行」节的 PATH 补齐方式处理。**不要**用 Store 存根跑仓库脚本（`python3 xxx.py` 会直接失败）。

### 8.3 改依赖后 frozen 失败 <a id="frozen-sync"></a>

`pyproject.toml` 与 `uv.lock` 不一致：先 `uv sync`（更新锁）或 `uv lock`，再回 `uv sync --frozen`；CI 只认锁文件，本地一致后才能推送。

### 8.4 外置环境损坏需重建 <a id="rebuild"></a>

```bat
set DEPS_DIR=D:\dev-deps\bms
scripts\tools\deps\还原依赖.bat            rem 环境搬回 backend\.venv（真实目录）
rmdir /s /q backend\.venv                  rem 全新开头
cd backend && uv sync --frozen && cd ..    rem 在 backend\ 下按锁文件重建
scripts\tools\deps\外置依赖.bat            rem 再外置
rem 或一步到位：scripts\tools\deps\重装依赖.bat --backend-only
```

> 环境实体只应存在于依赖仓或在还原态临时回到 `backend\`；任何时候都**只保留一份**。

## 9. 关联文档 <a id="related"></a>

- 《[pnpm 部署使用说明](pnpm部署使用说明.md)》：前端依赖管理（workspace + 依赖外置），与本文同走本地依赖仓与 deps 脚本
- 《[开发机部署使用说明总览](开发机部署使用说明总览.md)》：mjpc 开发设施汇总（Windows 侧总纲）
- 《[uv 部署使用说明](../linux/uv部署使用说明.md)》：Ubuntu 侧对应文档（外置演进背景与重建口径）
- 《[后端开发规范](../../../规范/后端开发规范.md)》：后端分层与依赖方向、服务边界（pyproject.toml 工作区成员口径）
- 《[git 部署使用说明](git部署使用说明.md)》：开发机 git 与仓库接入（uv.lock 提交要求见 Git 协作规范）
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档的组织、格式与图形约定

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 记录 2026-10-16 mjpc Windows 侧 uv 部署落地状态（Python 3.14.4 / uv 0.12.7 / backend-venv junction 外置）

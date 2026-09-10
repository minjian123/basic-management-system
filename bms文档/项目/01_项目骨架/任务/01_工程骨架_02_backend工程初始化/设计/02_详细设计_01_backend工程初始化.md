# backend 工程初始化详细设计

> BMS · 阶段一 / 02 任务 · 任务级详细设计（可落地、可逐项验收）

[文档首页](../../../../../文档首页.md) › [02 任务文档](../01_工程骨架_02_backend工程初始化.md) › 01 详细设计　|　[← 01 工程骨架](../../01_工程骨架.md)

## 1. 概述 <a id="overview"></a>

本文档是任务 [02 backend 工程初始化](../01_工程骨架_02_backend工程初始化.md) 的**详细设计**，粒度到「按序落地、逐条验收」，是任务级执行设计，位于 `bms文档/设计/` 全局粗设计之下一级。两者不一致时，以本文档为 02 的执行依据；所有不一致点已逐项对齐并记录于 [第 12 节](#align)。

上游依据（可追溯）：

- 《[项目规划说明](../../../../../规划/项目规划说明.md)》§2.1 技术选型、§17 环境与配置
- 《[架构设计 · 总体架构](../../../../../设计/架构设计/03_架构设计_总体架构.md)》§5 monorepo 布局、§6 技术栈
- 《[后端开发规范](../../../../../规范/后端开发规范.md)》§2 目录与分层职责、§3 Python 编码规范、§10 测试写法
- 《[命名规范](../../../../../规范/命名规范.md)》§6 Python 命名、《[需求文档规范](../../../../../规范/需求文档规范.md)》
- 需求 [01-2](../../../需求/01_需求_工程骨架.md#r01-2)

与前后任务的关系：01（仓库根骨架）已交付三工程最小占位（pyproject 仅 `fastapi`/`uvicorn`、`app/main.py` 含 `/healthz`、`uv.lock`）；02 在其上补齐 **backend 工程初始化**（全量依赖与工具配置、工厂基线与根路由、配置/迁移占位、测试基线）；03 建 `app/` 分层目录与职责 docstring；06 做依赖锁定复核与 Python 3.14 兼容验证。职责边界见 [第 8 节](#boundary)。

## 2. 现状与差距 <a id="gap"></a>

01 交付后的 backend 现状与 02 目标：

| 项 | 现状（01 交付） | 02 目标 | 动作 |
| --- | --- | --- | --- |
| `pyproject.toml` | 仅 `fastapi` / `uvicorn`，无 dev 组与工具配置 | 全量运行时依赖 + `[dependency-groups]` dev + ruff / pyright / pytest 配置 | 修改 |
| `.python-version` | `3.14` | 保持（回退口径见 06） | — |
| `app/__init__.py` | `__version__ = "0.1.0"` | 保持 | — |
| `app/main.py` | 最小工厂 + `/healthz`（title「BMS 后端」） | 工厂基线（title「BMS 基础管理系统」、根路由 `GET /`、注册位预留）+ `/healthz` 保持 | 修改 |
| `config.toml` | 缺失 | 占位文件（分区与键清单由 02-1 填充） | 新建 |
| `alembic.ini` | 缺失 | 占位文件（迁移配置由 03-6 填充） | 新建 |
| `tests/` | 缺失 | `conftest.py`（ASGITransport 客户端夹具）+ 根路由/健康检查冒烟用例 | 新建 |
| `README.md` | 四章节（01 简化版） | 目录结构补 `config.toml` / `alembic.ini` / `tests/`；「依赖与版本」节待 01-06 | 更新 |
| `uv.lock` | 20 包（01 版） | 重新锁定（全量依赖） | 更新 |

## 3. 目标目录与交付物清单 <a id="tree"></a>

02 落地后的 `backend/` 结构：

```text
backend/
├── .python-version       # 固定 Python 3.14（保持）
├── pyproject.toml        # 元数据 + 全量依赖 + dev 组 + 工具配置（修改）
├── uv.lock               # 依赖锁定（重新生成）
├── config.toml           # 配置占位（02-1 填充）
├── alembic.ini           # 迁移配置占位（03-6 填充）
├── README.md             # 工程说明（更新）
├── app/
│   ├── __init__.py       # 暴露 __version__（保持）
│   └── main.py           # 应用工厂 create_app() + 根路由 + /healthz（修改）
└── tests/
    ├── conftest.py       # httpx ASGITransport 客户端夹具（新增）
    └── test_main.py      # 根路由 / 健康检查冒烟用例（新增）
```

交付物清单（02 新建 / 修改的文件）：

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `pyproject.toml` | 修改 | 全量依赖、dev 组、ruff / pyright / pytest 配置 |
| `app/main.py` | 修改 | 工厂基线（title / 版本 / 根路由 / 注册位） |
| `config.toml` | 新建 | 配置占位（仅注释头） |
| `alembic.ini` | 新建 | 迁移配置占位（仅注释头） |
| `tests/conftest.py` | 新建 | 异步客户端夹具 |
| `tests/test_main.py` | 新建 | 根路由与 `/healthz` 冒烟 |
| `README.md` | 修改 | 目录结构与依赖说明对齐 |
| `uv.lock` | 修改 | 重新锁定 |

> 无空目录、无 `.gitkeep`；`app/` 分层目录（core/api/…）与 `tests/` 同构子目录归 03。

## 4. pyproject.toml 设计 <a id="pyproject"></a>

```toml
[project]
name = "bms-backend"
version = "0.1.0"
description = "BMS 后端服务（阶段一项目骨架）"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.9",
    "pydantic-settings>=2.5",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "aiosqlite>=0.20",
    "aiomysql>=0.2",
    "psycopg[binary]>=3.2",
    "dmPython",
    "structlog>=24.1",
    "redis>=5.0",
    "python-multipart>=0.0.9",
    "httpx>=0.27",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "pyright>=1.1.380",
]

[tool.ruff]
line-length = 120
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF"]
# 中文标点为文档与注释的有意用法，关闭歧义字符检查
ignore = ["RUF001", "RUF002", "RUF003"]

[tool.pyright]
typeCheckingMode = "strict"
pythonVersion = "3.14"
include = ["app", "tests"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
markers = [
    "kiwi_id: Kiwi TCMS 用例编号（如 @pytest.mark.kiwi_id(1)）",
]
```

口径：

- **不声明 `[build-system]`**：应用不作为包发布，uv 以虚拟工程管理（`uv sync` 只装依赖、不安装本项目）。
- **版本下限取当前稳定线**，实际版本以 `uv.lock` 锁定为准；`dmPython` 不写下限（达梦官方轮子版本线特殊，交 06 锁定与验证）。
- dev 组按需求 01-2 固定清单；`httpx` 同时是运行时依赖（外部调用）与测试依赖，重复声明无副作用。
- `target-version = "py314"`、`pythonVersion = "3.14"` 与 `.python-version` 一致；06 若回退 3.13，三处同步调整。
- `pythonpath = ["."]`：虚拟工程未安装为包，供 `tests/` 能 `import app`；`markers` 登记 `kiwi_id`，避免未注册标记告警。
- ruff 关闭 `RUF001`–`RUF003`：中文标点（，。（）「」）为文档与注释的有意用法（实施期发现 21 处误报）。

## 5. 配置与迁移占位设计 <a id="placeholders"></a>

**`config.toml`**（仅注释头，不写实际键，避免与 02-1 冲突）：

```toml
# BMS 后端配置（阶段一占位）
# 分区与键清单由任务 02-1（配置管理）填充：app / server / log / database / redis / minio / security / cors
# 环境分层：BMS_ENV = dev | test | prod；密钥类配置只走环境变量，不入本文件
```

**`alembic.ini`**（仅注释头，完整内容由 03-6 交付）：

```ini
# Alembic 迁移配置（阶段一占位）
# 完整内容由任务 03-6（批量迁移与租户库初始化）交付：script_location、
# 三套方言 URL 读取方式（config.toml + 环境变量）、日志配置
```

## 6. 应用工厂与端点设计 <a id="factory"></a>

`app/main.py`（02 目标形态）：

```python
"""BMS 后端入口：应用工厂 create_app()，提供根路由与 /healthz 存活检查。"""

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    """创建 FastAPI 应用。

    注册位按序预留：中间件 → 异常处理器 → 路由（02 域实现，01-03 起迁移到 app/api/）。

    Returns:
        FastAPI: 已注册基线配置与端点的应用实例。
    """
    app = FastAPI(title="BMS 基础管理系统", version=__version__)

    # TODO(01-03): 路由迁移至 app/api/router.py 统一 include
    # TODO(02-01/02-02): lifespan 内加载配置与日志
    # TODO(02-03): 注册统一异常处理器（BizError / RequestValidationError / 未捕获异常）

    @app.get("/")
    def root() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        """应用信息（统一响应结构占位，02-3 起换用 ApiResponse）。

        Returns:
            dict: {code, message, data:{name, version}}。
        """
        return {
            "code": 0,
            "message": "ok",
            "data": {"name": "BMS 基础管理系统", "version": __version__},
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        """存活检查端点。

        Returns:
            dict: 服务状态，固定返回 {"status": "ok"}。
        """
        return {"status": "ok"}

    return app
```

口径：

- 根路由响应为 **dict 字面量**（统一响应模型 `ApiResponse`/`PageResponse` 归 02-3，届时替换）。
- `/healthz` 保持 01 的行为与路径；`/readyz` 与契约细化归 02-4。
- `/docs`、`/openapi.json` 由 FastAPI 默认提供；接口 docstring 按《后端开发规范》§3.1 进入 OpenAPI。
- 工厂内**不引入**尚未存在的模块（config / logging / exceptions），保证 02 完成时 `uvicorn` 可直接启动。

## 7. 测试基线设计 <a id="tests"></a>

`tests/conftest.py`：

```python
"""pytest 公共夹具：ASGI 内存客户端（免启服务器）。"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端夹具（每个用例独立应用实例）。"""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

`tests/test_main.py`：

```python
"""应用工厂冒烟：根路由与应用信息、/healthz 存活。"""

import pytest
from httpx import AsyncClient


@pytest.mark.kiwi_id(1)
async def test_root_returns_app_info(client: AsyncClient) -> None:
    """GET / 返回统一响应结构与应用名/版本。"""
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["name"] == "BMS 基础管理系统"
    assert body["data"]["version"]


@pytest.mark.kiwi_id(2)
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz 返回 {"status":"ok"}。"""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

口径：命名与覆盖遵循《后端开发规范》§10；测试库统一 SQLite（本任务无库依赖）；`asyncio_mode = "auto"`、`pythonpath` 与 `kiwi_id` 标记由 `[tool.pytest.ini_options]` 提供。**自动化用例先登记 Kiwi TCMS 再写代码**（本任务 Case 1 根路由、Case 2 `/healthz`），测试代码以 `@pytest.mark.kiwi_id(编号)` 标注关联。

## 8. 职责边界（02 vs 01 / 03 / 06 / 02 域） <a id="boundary"></a>

| 事项 | 归属 | 说明 |
| --- | --- | --- |
| 全量依赖与工具配置、config/alembic 占位、工厂基线、根路由、测试基线 | **02（本文档）** | 本任务交付 |
| `app/` 分层目录（core/api/models/schemas/services/repositories/db/tasks/ws/i18n）与职责 docstring、`alembic/` 目录、`tests/` 同构扩展 | 03 | 在 02 占位之上细化 |
| 配置加载（pydantic-settings / lifespan）、`BMS_` 覆盖与校验 | 02-1 | 填充 `config.toml` |
| structlog 日志体系与请求日志中间件 | 02-2 | 工厂注册位接入 |
| 统一响应模型 `ApiResponse`/`PageResponse`、异常体系与错误码 | 02-3 | 替换根路由 dict 占位 |
| `/healthz` `/readyz` 契约与依赖检查项 | 02-4 | 细化健康检查 |
| 全量依赖锁定复核、Python 3.14 兼容矩阵（含达梦实测）与回退口径 | 06 | 复核 02 的 `uv.lock` |

> 原则：02 只做「工程初始化 + 最小可运行 + 冒烟测试」，不引入业务与 02 域实现；占位文件可被后续任务直接扩展，不返工。

## 9. 实施步骤 <a id="steps"></a>

按序执行，每步附验证点：

1. **更新 `pyproject.toml`**：按 §4 写入依赖与工具配置 → `uv lock`（阿里云 PyPI 镜像）→ 检查解析成功。
2. **安装依赖**：`uv sync` → 全量依赖安装成功（若 `dmPython`/`aiomysql` 在 3.14 下不可得，按 06 回退口径处置，见 §11）。
3. **占位文件**：写入 `config.toml`、`alembic.ini`（§5）。
4. **应用工厂**：`app/main.py` 改为 §6 形态（title、根路由、注册位注释）。
5. **测试基线（Kiwi 先行）**：先在 Kiwi TCMS 登记用例并取得用例 ID（本任务 Case 1 根路由、Case 2 `/healthz`）→ 新增 `tests/conftest.py`、`tests/test_main.py` 并以 `@pytest.mark.kiwi_id` 标注（§7）；确认 `pytest` 配置生效。
6. **更新 README**：目录结构补 `config.toml` / `alembic.ini` / `tests/`；其余四章节保持。
7. **验证**：`uv run ruff check .`、`uv run pyright`、`uv run pytest`、`uv run uvicorn app.main:create_app --factory --port 8000` + `curl /`、`/healthz`、`/docs`、`/openapi.json`（均 200）。
8. **提交**：经用户明确指令后再 `git commit`（遵循工作区根《AGENTS.md》提交纪律）。

## 10. 验收映射 <a id="accept-map"></a>

任务文档「完成标准」逐条映射到本设计与验证方法：

| 完成标准 | 设计落点 | 验证方法 |
| --- | --- | --- |
| `uv sync` 通过 | §4 | 在 `backend/` 执行 `uv sync` |
| 启动无报错，`/docs`、`/openapi.json`、`/` 三端点 200 | §6 | `uvicorn` 启动后逐端点 `curl` |
| `uv run ruff check .` 与 `uv run pyright` 无错误 | §4 | 两条命令零输出退出 |
| `uv run pytest` 通过（含 1 条根路由冒烟用例） | §7 | `uv run pytest` 全绿（2 条用例） |

## 11. 风险与开放项 <a id="risk"></a>

| 风险 / 开放项 | 说明 | 处置 |
| --- | --- | --- |
| `dmPython` / `aiomysql` 在 Python 3.14 下可用性未知 | 全量依赖一次加入，解析或安装可能失败 | 交 06 按既定口径整体回退 3.13（`.python-version`、`requires-python`、README 徽标同步改并重新锁定）；实施反馈：`dmPython` 2.5.38 已在 3.14 安装成功，连接实测留 06 |
| pyright strict 首次启用告警量 | 严格模式对最小代码面（app/tests）可能暴露注解缺失 | 本任务先保证 `app`/`tests` 零错误；规则集后续任务不得放宽 |
| ruff 规则集范围 | `select` 基线 E/F/W/I/B/UP/SIM/RUF | 后续收紧在设计修订中统一，不在 02 反复调整 |
| pytest-asyncio 与 pytest 版本协同 | 异步夹具依赖两者兼容 | 以 `uv.lock` 锁定，`asyncio_mode = "auto"` |
| uv / npm 下载慢 | 国内网络 | uv 走阿里云 PyPI 镜像，命令注明 |

## 12. 对齐记录 <a id="align"></a>

02 与全局设计对照后的定稿口径：

| # | 事项 | 定稿口径 | 落点 |
| --- | --- | --- | --- |
| 1 | 运行时依赖范围 | **全量一次加入**（含 `dmPython` / `aiomysql`），兼容性问题交 06 回退口径 | §4、§11 |
| 2 | 统一响应模型 | 根路由先用 **dict 字面量**，`ApiResponse`/`PageResponse` 归 02-3 | §6 |
| 3 | 健康检查归属 | `/healthz` **保持内联**于 `main.py`；`app/api/` 分层与 `health.py` 迁移归 01-03、契约细化归 02-4 | §6、§8 |
| 4 | 配置与迁移占位 | 仅注释头，不写实际键/节，避免与 02-1、03-6 冲突 | §5 |
| 5 | 工具配置基线 | ruff（line-length 120、py314、规则集 E/F/W/I/B/UP/SIM/RUF，忽略 RUF001–003 中文标点）+ pyright strict + pytest（asyncio auto、pythonpath、kiwi_id 标记） | §4 |
| 6 | 用例登记时机 | 自动化用例**先登记 Kiwi TCMS 再写代码**（Case 1/2），测试代码以 `@pytest.mark.kiwi_id` 标注 | §7、§9 |
| 7 | 工具配置实施补充 | ruff 忽略 RUF001–003（中文标点误报 21 处）；pytest 补 `pythonpath = ["."]`；pyright 对装饰器注册的路由函数局部忽略 `reportUnusedFunction` | §4、§6 |

> 本文档依《文档生成规范》编写

# 02 backend 工程初始化实施记录

> 项目骨架 · 01 工程骨架 · 子任务 02 · 实施记录（实做内容、问题与处置、验证与遗留）

[文档首页](../../../../../../文档首页.md) › [02 任务文档](../01_工程骨架_02_backend工程初始化.md) › 01 实施记录　|　[← 01 工程骨架](../../01_工程骨架.md)　[详细设计 →](../设计/02_详细设计_01_backend工程初始化.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [02 backend 工程初始化](../01_工程骨架_02_backend工程初始化.md) |
| 对应需求 | [01-2](../../../../需求/01_需求_工程骨架.md#r01-2) |
| 详细设计 | [02 详细设计_01](../设计/02_详细设计_01_backend工程初始化.md) |
| 实施日期 | 2026-09-10 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；依赖镜像：阿里云 PyPI；Kiwi TCMS（mjbk:8060） |
| 提交 | —（随本批提交，见仓库 git log） |
| 结论 | backend 工程初始化完成：全量依赖锁定、工厂基线与根路由、配置/迁移占位、测试基线与 Kiwi 用例登记；验证全部通过 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[Kiwi 用例登记] --> B[pyproject 依赖与工具配置]
    B --> C[uv lock / sync]
    C --> D[config.toml / alembic.ini 占位]
    D --> E[应用工厂与根路由]
    E --> F[测试基线 kiwi_id 标注]
    F --> G[验证与提交]
```

| 步骤 | 内容 | 结果 |
| --- | --- | --- |
| 1 | Kiwi TCMS 登记用例（先登记再写代码） | Case 1（根路由）、Case 2（`/healthz`） |
| 2 | `pyproject.toml`：全量依赖 + dev 组 + ruff / pyright / pytest 配置 | 完成 |
| 3 | `uv lock` / `uv sync` | 通过（含 `dmPython 2.5.38`） |
| 4 | `config.toml`、`alembic.ini` 占位 | 完成 |
| 5 | `app/main.py`：title、根路由、注册位预留 | 完成 |
| 6 | `tests/conftest.py` + `tests/test_main.py`（kiwi_id 标注） | `pytest` 2 通过 |
| 7 | 验证（ruff / pyright / 四端点） | 全部通过 |

## 3. 实施过程 <a id="process"></a>

### 3.1 Kiwi TCMS 用例登记（先登记再写代码）

通过 SSH 进入 mjbk，在 `bms-kiwi` 容器内以 `manage.py shell` 登记（Kiwi 为空库，先建产品与分类）：

- 分类：`BMS 平台`；产品：`BMS 基础管理系统`；用例分类：`平台骨架`（产品 id 1 / 分类 id 2）
- **Case 1**：根路由返回应用名与版本（GET /），优先级 P2
- **Case 2**：健康检查 /healthz 存活（GET /healthz），优先级 P2

### 3.2 pyproject 与依赖锁定

按设计 §4 写入全量运行时依赖（含 `aiomysql`、`dmPython`）、dev 组与工具配置，并补实施项（`pythonpath`、`kiwi_id` 标记、ruff 中文标点忽略）：

```bash
cd backend
uv lock   # 阿里云 PyPI 镜像
uv sync
```

关键锁定版本：`fastapi 0.141.1`、`uvicorn 0.52.4`、`pydantic 2.13.5`、`pydantic-settings 2.15.0`、`sqlalchemy 2.0.52`、`alembic 1.19.2`、`aiosqlite 0.22.1`、`aiomysql 0.3.2`、`psycopg 3.3.5`、**`dmPython 2.5.38`**、`structlog 26.1.0`、`redis 8.1.0`、`httpx 0.28.1`；dev：`pytest 9.1.1`、`pytest-asyncio 1.4.0`、`pytest-cov 7.1.0`、`ruff 0.16.6`、`pyright 1.1.411`。

### 3.3 占位文件

`config.toml`、`alembic.ini` 按设计 §5 仅写注释头（分别由 02-1、03-6 填充），不写实际键/节。

### 3.4 应用工厂与根路由

`app/main.py` 改为设计 §6 形态：title「BMS 基础管理系统」、根路由 `GET /` 返回 `{code, message, data:{name, version}}`、`/healthz` 保持；中间件/异常处理器/lifespan 以 TODO 预留注册位。

### 3.5 测试基线

`tests/conftest.py`（ASGITransport 客户端夹具）+ `tests/test_main.py`（2 条冒烟用例，分别标注 `@pytest.mark.kiwi_id(1)` / `(2)`）。

```bash
uv run pytest -q   # 2 passed
```

### 3.6 验证与提交

`uv run ruff check .`、`uv run pyright`、`uv run uvicorn app.main:create_app --factory --port 8000` + 四端点 `curl`，见 [§5 验证结果](#verify)；随后形成本批提交（等用户指令）。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | `pytest` 加载 `conftest.py` 报 `ModuleNotFoundError: No module named 'app'` | 虚拟工程未安装为包，pytest 默认只把 `tests/` 加入 `sys.path` | `[tool.pytest.ini_options]` 增加 `pythonpath = ["."]` | 设计 §4（实施补充） |
| 2 | `ruff check` 报 21 处（RUF002 ×19、RUF003 ×2） | 歧义字符规则把中文标点（，。（）「」）判为误报 | `[tool.ruff.lint]` 增加 `ignore = ["RUF001", "RUF002", "RUF003"]` | 设计 §4（实施补充） |
| 3 | `pyright`（strict）报 2 处 `reportUnusedFunction` | 装饰器注册的路由函数不被 pyright 视为“已使用” | 两个路由函数行尾加 `# pyright: ignore[reportUnusedFunction]` | 设计 §6（实施补充） |
| 4 | `dmPython` 能否在 Python 3.14 安装 | 达梦官方驱动版本线特殊（设计风险项） | 实测 `dmPython 2.5.38` 安装成功；连接实测留 01-06 | 设计 §11（实施反馈） |
| 5 | Kiwi 无产品/分类，`TestCase` 直建报 `case_status_id cannot be null` | 空库未建产品与分类；TestCase 需状态字段 | 先建分类/产品/用例分类，`case_status=CONFIRMED` 后创建成功 | 本记录 §3.1 |

## 5. 验证结果 <a id="verify"></a>

| 验证点（任务完成标准） | 方法 | 结果 |
| --- | --- | --- |
| `uv sync` 通过 | 在 `backend/` 执行 | 通过（全量依赖，含 `dmPython`） |
| 启动无报错、四端点可用 | `uvicorn` 启动 + `curl` | 通过（`/`、`/healthz`、`/docs`、`/openapi.json` 均 200） |
| `GET /` 契约 | `curl` 响应体 | 通过（`{"code":0,"message":"ok","data":{"name":"BMS 基础管理系统","version":"0.1.0"}}`） |
| `uv run ruff check .` | 命令 | 通过（All checks passed） |
| `uv run pyright` | 命令 | 通过（0 errors, 0 warnings） |
| `uv run pytest` | 命令 | 通过（2 passed，含根路由冒烟） |
| Kiwi 用例关联 | 平台登记 + 代码 `kiwi_id` 标注 | 通过（Case 1/2 登记，用例代码一一对应） |

## 6. 偏差与遗留 <a id="deviations"></a>

- 设计 §4/§6/§7/§9/§11 已按实施反馈回写（`pythonpath`、ruff 中文标点忽略、`kiwi_id` 标记、路由函数局部忽略、Kiwi 先行、dmPython 安装反馈）。
- Allure 报告与测试结果导入 Kiwi TCMS（执行归档链路）属阶段末 05-4，本任务只完成用例登记与本地 pytest 执行。
- `dmPython` 达梦连接实测（`SELECT 1`）与兼容矩阵留 01-06；若连接不兼容再按回退口径处置。
- 前端（frontend / frontend-mobile）测试基线归 01-04 / 01-05 实施。
- 根 README 的 backend 目录树已同步为 02 完成态。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》第 5 节实施文档结构组织

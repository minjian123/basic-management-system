# 02 backend 工程初始化测试记录

> 项目骨架 · 01 工程骨架 · 子任务 02 · 测试记录（用例、执行结果、问题与覆盖率）

[文档首页](../../../../../文档首页.md) › [02 任务文档](../01_工程骨架_02_backend工程初始化.md) › 01 测试记录　|　[← 01 工程骨架](../../01_工程骨架.md)　[详细设计 →](../设计/02_详细设计_01_backend工程初始化.md)　[实施记录 →](../实施/02_实施_01_backend工程初始化.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [02 backend 工程初始化](../01_工程骨架_02_backend工程初始化.md) |
| 对应需求 | [01-2](../../../需求/01_需求_工程骨架.md#r01-2) |
| 详细设计 | [02 详细设计_01](../设计/02_详细设计_01_backend工程初始化.md) |
| 实施记录 | [02 实施记录](../实施/02_实施_01_backend工程初始化.md) |
| 测试日期 | 2026-09-10 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；本地服务端口 8000；Kiwi TCMS（mjbk:8060） |
| Kiwi 用例 | Case 1（根路由）、Case 2（`/healthz`）；产品「BMS 基础管理系统」/ 用例分类「平台骨架」 |
| 结论 | 自动化用例 2/2 通过；接口冒烟 4/4 返回 200；覆盖率 100%（12 语句） |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：本任务「工程初始化 + 最小可运行」——应用工厂基线、根路由、`/healthz` 存活与基线端点可用性。不含：`/readyz` 依赖检查（02-4）、租户拓扑与模块注册（03/04 域）、前端工程（01-04/05）。

**用例清单**（先登记 Kiwi TCMS、后写自动化代码）：

| Kiwi ID | 用例 | 类型 | 自动化文件 | 优先级 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 根路由返回应用名与版本（GET /） | 接口冒烟 | `backend/tests/test_main.py::test_root_returns_app_info` | P2 | 通过 |
| 2 | 健康检查 /healthz 存活（GET /healthz） | 接口冒烟 | `backend/tests/test_main.py::test_healthz_returns_ok` | P2 | 通过 |

接口级冒烟验证（联调补充，不在 Kiwi 自动化范围）：服务启动后逐端点 `curl`（`/`、`/healthz`、`/docs`、`/openapi.json`）。

## 3. 执行记录与结果 <a id="run"></a>

**自动化用例**：

```bash
cd backend
uv run pytest -q
# 2 passed in 0.02s
```

**服务与端点冒烟**：

```bash
uv run uvicorn app.main:create_app --factory --port 8000
```

| 端点 | 期望 | 实测 |
| --- | --- | --- |
| `GET /` | 200 + `{code:0,message:"ok",data:{name,version}}` | 200，`{"code":0,"message":"ok","data":{"name":"BMS 基础管理系统","version":"0.1.0"}}` |
| `GET /healthz` | 200 + `{"status":"ok"}` | 200，`{"status":"ok"}` |
| `GET /docs` | 200 | 200 |
| `GET /openapi.json` | 200 | 200 |

**质量门禁（辅助）**：`uv run ruff check .` 通过；`uv run pyright` 0 errors（详见实施记录）。

**结果汇总**：用例通过率 2/2（100%）；接口冒烟 4/4；Kiwi 用例登记与代码 `kiwi_id` 标注一一对应。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | `pytest` 报 `ModuleNotFoundError: No module named 'app'` | 虚拟工程未安装为包，pytest 只把 `tests/` 加入 `sys.path` | pytest 配置补 `pythonpath = ["."]` | 设计 §4（实施补充） |
| 2 | `ruff` 报 21 处（RUF002 ×19、RUF003 ×2） | 歧义字符规则误报中文标点 | ruff 忽略 `RUF001`–`RUF003` | 设计 §4（实施补充） |
| 3 | `pyright`（strict）报 2 处 `reportUnusedFunction` | 装饰器注册的路由函数不被视为「已使用」 | 路由函数行尾局部忽略注释 | 设计 §6（实施补充） |
| 4 | Kiwi 直建用例报 `case_status_id cannot be null` | 空库未建产品/分类，TestCase 需状态字段 | 先建分类/产品/用例分类，`CONFIRMED` 状态创建成功 | 实施记录 §3.1 |
| 5 | `dmPython` 兼容性 | 达梦官方驱动版本线特殊 | 安装已在 3.14 通过（2.5.38）；**连接实测（SELECT 1）留 01-06** | 实施记录 §6 |

## 5. 覆盖率 <a id="coverage"></a>

```bash
uv run pytest --cov=app --cov-report=term-missing -q
```

| 模块 | 语句 | 未覆盖 | 覆盖率 |
| --- | --- | --- | --- |
| `app/__init__.py` | 1 | 0 | 100% |
| `app/main.py` | 11 | 0 | 100% |
| **合计** | **12** | **0** | **100%** |

口径：本任务为任务级覆盖率快照；覆盖率门禁（核心 ≥ 80% / 整体 ≥ 70%）随 05-1 接入 CI，`pytest-cov` 机制已就位。

## 6. 偏差与遗留 <a id="deviations"></a>

- Allure 报告生成与测试结果导入 Kiwi TCMS（执行归档链路）属阶段末 05-4；本任务只完成用例登记与本地执行。
- `dmPython` 达梦连接实测与 Python 3.14 兼容矩阵留 01-06。
- `/readyz`、租户拓扑、模块注册等深层用例归 02-4、03、04 域；前端（frontend / frontend-mobile）测试基线归 01-04/05。
- 覆盖率暂未接流水线门禁（随 05-1）。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》第 6 节测试文档结构组织

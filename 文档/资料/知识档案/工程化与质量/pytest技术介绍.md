# pytest 技术介绍

> 后端测试框架（pytest + httpx + pytest-cov）· BMS 质量门禁核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [工程化与质量](../技术栈知识档案总览.md#eng) › pytest 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**pytest** 是 Python 生态使用最广的测试框架，靠"assert 原生断言 + fixture 复用 + 参数化"三个特性
把测试写得像自然语言；**httpx** 是现代 HTTP 客户端，其 ASGITransport 能
不启动服务器直接调用 FastAPI 应用；**pytest-cov** 统计测试覆盖率。
三者组合是 BMS 后端测试的标准三件套。

- **定位**：BMS 后端全部单元测试与接口测试的唯一框架。
- **版本**：pytest 8.x 系列（持续迭代）；httpx 0.2x 系列；pytest-cov 5.x 系列。
- **许可**：pytest MIT、httpx BSD-3-Clause、pytest-cov MIT，均为 OSI 认证开源。
- **语言**：Python。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 测试函数 | 文件名 `test_*.py`、函数名 `test_*` 即被自动收集为用例；断言直接用 `assert`，失败自动输出上下文 |
| fixture | 可复用的准备/清理逻辑（数据库会话、登录 token、临时文件），按需注入测试函数，自动管理生命周期 |
| 参数化（parametrize） | `@pytest.mark.parametrize` 一组数据跑多次用例，覆盖边界值不再复制粘贴 |
| ASGITransport | httpx 的传输层：`httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` 直接调用 FastAPI 应用，全程不起真实端口 |
| pytest-cov | 基于 coverage 统计"被测代码行 / 总行"的覆盖率，输出到终端与报告文件 |
| 覆盖率门禁 | `--cov-fail-under=70` 低于阈值直接失败，CI 强制不达标不放行 |
| pyproject.toml 配置 | `[tool.pytest.ini_options]` 段集中配置：testpaths、markers、插件启用；cov 配置同段 |
| conftest.py | 目录级共享 fixture 与钩子的文件，根级 conftest 放全局 fixture |
| 标记（marker） | `@pytest.mark.asyncio` 等给用例打标签：异步用例、慢用例分组执行 |
| 插件体系 | pytest-asyncio（异步用例）、allure-pytest（《[Allure](Allure技术介绍.md)》报告）、pytest-cov 均为插件形态，按需装载 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节指定的后端测试方案（选型依据见《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节）。
- FastAPI 接口测试用 httpx ASGITransport 免启服务器：测试快、无端口冲突，见《[FastAPI 技术介绍](../后端核心/FastAPI技术介绍.md)》。
- 测试库统一 SQLite 保证可移植：本地、CI、任何机器跑同一套测试零部署成本（见《[SQLite 技术介绍](../后端核心/SQLite与aiosqlite技术介绍.md)》）。
- pytest-cov 统计覆盖率并作 CI 门禁：核心模块（认证/RBAC/工作流/审计/收付款）行覆盖 ≥ 80%、整体 ≥ 70%，低于门槛流水线失败（见《[项目规划说明](../../../规划/项目规划说明.md#test-exit)》16.4 节）。
- CI 执行：MR 流水线后端 job 即 `uv sync` 后跑 pytest（见《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节），main 流水线另加 MySQL/PostgreSQL/达梦 DM8 三库方言集成测试。
- 本地命令（Windows PowerShell 与 Linux 通用）：

```bash
uv run pytest                          # 跑全部测试（SQLite 库）
uv run pytest tests/test_auth.py       # 只跑指定文件
uv run pytest -k "login"               # 按名称过滤用例
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=70   # 带覆盖率与门禁
```

- 结果双出口：Allure 生成可视化报告归档 CI 产物；执行结果经官方插件导入《[Kiwi TCMS](KiwiTCMS技术介绍.md)》用例库归档，用例在代码中以用例 ID 关联（见《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节）。

## 4. 选型对比 <a id="compare"></a>

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| **pytest（选中）** | 断言简洁、fixture/参数化强、插件生态全（异步/覆盖率/报告） | 大型项目需约定组织方式（BMS 已按模块分目录） | 生态与表达力最优，唯一选择 |
| unittest（标准库） | 零依赖、官方维护 | 类式样板代码多、无参数化、异步支持弱 | 能力不足，不采用 |
| nose2 / 其他 | — | 维护停滞、生态小 | 不采用 |
| 测试客户端直连（requests + 真实服务器） | 最贴近真实环境 | 慢、依赖端口与环境、CI 脆弱 | ASGITransport 已覆盖该场景，仅方言测试留真实库 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **异步用例需要插件**：FastAPI 接口多为 `async def`，用例用 `@pytest.mark.asyncio`（pytest-asyncio）或 anyio 插件，别用同步方式裸调异步函数。
- **SQLite 与生产库方言差异**：SQLite 通过不代表 MySQL/PostgreSQL 通过（函数、类型、事务行为不同），方言问题由 CI 三库集成测试兜底，本地以 SQLite 快跑为主。
- **测试库数据隔离**：每个用例/每次会话做干净的数据准备与清理（fixture + 事务回滚），防止用例间互相污染导致"单独跑过、一起跑挂"。
- **覆盖率数字别只看总量**：行覆盖高不等于逻辑覆盖全；核心分支（权限校验、工作流网关、异常分支）优先补用例，门禁只是底线。
- **ASGITransport 注意事项**：它直接调用应用，不经过真实网络层（无 uvicorn、无中间件网络行为差异），依赖 Host 头等场景需在 base_url 里显式设置。
- **CI 与本地一致性**：依赖版本由 uv.lock 锁定；pytest 版本漂移会导致"本地绿、CI 红"，统一 `uv sync` 解决。
- **用例与《[Kiwi TCMS](KiwiTCMS技术介绍.md)》关联**：自动化用例务必标注用例 ID（对应平台登记），保证需求可追溯、无孤儿用例（见《[项目规划说明](../../../规划/项目规划说明.md#test-regression)》16.3 节）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| pytest 官方文档 | https://docs.pytest.org/ | 完整教程：fixture、参数化、插件开发 |
| pytest 最佳实践 | https://docs.pytest.org/en/stable/explanation/goodpractices.html | 官方推荐的工程组织方式（对应 pyproject.toml 配置） |
| httpx 官方文档 | https://www.python-httpx.org/ | 客户端与 ASGITransport 用法 |
| pytest-cov（GitHub） | https://github.com/pytest-dev/pytest-cov | 覆盖率插件：参数、报告格式与门禁 |
| pytest-asyncio（GitHub） | https://github.com/pytest-dev/pytest-asyncio | 异步用例插件 |
| FastAPI 测试教程 | https://fastapi.tiangolo.com/tutorial/testing/ | 官方测试指南，ASGITransport 标准用法 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节 | 测试策略与测试流程（用例管理、回归、准出标准） |
| 《[测试规范](../../../规范/测试规范.md)》 | 测试分类、用例组织与执行约定 |
| 《[FastAPI 技术介绍](../后端核心/FastAPI技术介绍.md)》 | 被测对象：接口测试方式（httpx ASGITransport） |
| 《[Allure 技术介绍](Allure技术介绍.md)》 | 测试结果生成可视化报告 |
| 《[Kiwi TCMS 技术介绍](KiwiTCMS技术介绍.md)》 | 用例唯一库，执行结果导入归档 |
| 《[uv 技术介绍](uv技术介绍.md)》 | 统一以 `uv run pytest` 执行 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
# BaseRepository 异步与 BaseModel 落库实施记录

> 后端基座与服务化地基 · 01 后端基座真实实现 · 03 BaseRepository 异步与 BaseModel 落库 · 实施记录

[文档首页](../../../../../../文档首页.md) › [03 BaseRepository 异步与 BaseModel 落库](../01_后端基座真实实现_03_BaseRepository 异步与 BaseModel 落库.md) › 01 实施　|　[详细设计](../设计/01_详细设计_03_BaseRepository 异步与 BaseModel 落库.md) · [测试记录](../测试/01_测试_03_BaseRepository 异步与 BaseModel 落库.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 BaseRepository 异步与 BaseModel 落库](../01_后端基座真实实现_03_BaseRepository 异步与 BaseModel 落库.md) |
| 对应需求 | [01-3](../../../../需求/01_需求_后端基座真实实现.md#r01-3) |
| 详细设计 | [01_详细设计_03_BaseRepository 异步与 BaseModel 落库](../设计/01_详细设计_03_BaseRepository 异步与 BaseModel 落库.md) |
| 实施日期 | 2026-09-22 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu，Python 3.14 / uv）；SQLite 真库（临时库），四方言 DDL 离线编译（含达梦 `dmSQLAlchemy`） |
| 提交 | 3547f173（详细设计）+ 7ae9eb1b（feat：代码与用例）+ 本条 docs 提交 |
| 结论 | 完成 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A["Kiwi 用例登记（1050）"] --> B["BaseDbRepository 真实实现"]
    B --> C["BaseModel / 四库映射 / 索引命名"]
    C --> D["session_scope + dict/listing 迁移"]
    D --> E["sys_module 种子脚本"]
    E --> F["用例 + 门禁 + 开发库实测"]
    F --> G["登记回写 + 实施/测试记录 + 提交"]
```

结果小结：`BaseDbRepository` 由占位填为真实异步实现——会话构造注入与 `model` 类属性、作用域条件 11 操作符 SQL 翻译、CRUD 与 `SELECT EXISTS` 存在性、页码 `LIMIT/OFFSET` 与偏移游标分页、基础 ORDER BY（默认 `id` 升序）、写入严格白名单、租户 `create` 注入与 `update` 禁改、`delete` 默认软删 + `soft_delete` / `hard_delete` 出口（硬删穿透软删过滤）、乐观锁冲突转 409；`BaseModel` 在异步会话下雪花 ID / 审计 / 软删 / 乐观锁验证通过；四库类型映射与 `(唯一字段, deleted_at)` 复合唯一经 DDL 断言 + SQLite NULL 语义验证；索引命名统一 `idx_{表}_{列}`；统一会话入口 `session_scope` 落地并迁移 dict / listing 6 处 `_session`；`sys_module` 平台域种子幂等落库。`ruff` / `pyright` / 全量 `pytest` 全绿（812 passed / 覆盖率 95%，本任务模块 100%）。

## 3. 实施过程 <a id="process"></a>

1. **Kiwi 用例登记**：先登记本任务策展用例并回读编号 **1050**（登记输入与结果落测试仓 `scripts/kiwi/cases/`、`exports/`，台账已回填）。
2. **仓储契约与中间层**：`BaseScopedRepository` 新增 `soft_delete` / `hard_delete` 派生默认（委托 `delete`，DB 实现覆写）；`_scope_conditions(include_soft_delete=...)` 参数支持物理删除穿透软删过滤。
3. **DB 实现**：`BaseDbRepository` 改真实实现并退出 `BaseStub`——构造注入 `AsyncSession`、`model` 类属性、`_column` / `_scope_where` / `_select` 基础语句、11 操作符翻译（非法条件 `ConfigError`）、CRUD / `exists` / `count`、`list_page` / `list_cursor`、`_apply_sort` 基础 ORDER BY、`_write_values`（白名单 + 租户写入口径）、`_guard_version` 包 `flush` 转 409。仓储只 `flush` 不 `commit`。
4. **模型与映射**：`Base.metadata` 设 ix 命名约定（`idx_{表}_{列}`）；`BaseModel` docstring 四库映射表按实测回写（布尔实为 SQLite BOOLEAN / MySQL BOOL / PG BOOLEAN / 达梦 SMALLINT；补 String / Text / JSON 与多值口径）。
5. **会话入口**：`db/session.py` 新增 `session_scope`（租户上下文 / 显式库键 + 读写角色 + 可注入会话工厂）；dict（providers / query / service / sql×2）与 listing（store）共 6 处 `_session` 迁入并清理重复 `async_sessionmaker`。
6. **种子脚本**：`ops/seed_module.py` 幂等建 `sys_module` 表 + `PLATFORM_MODULES` 四行（复用 `ops.seed_tenant.resolve_url`）；开发平台库执行实测（新增 4 行，重复执行 0 行）。
7. **用例**：新增 `tests/repositories/test_db_repository.py`、`tests/models/test_type_mapping.py`、`tests/db/test_session_scope.py`、`tests/ops/test_module_ops.py`；适配 `tests/repositories/test_base_repository.py`（DB 占位断言改真实语义 + 继承链退出 `BaseStub` + 软删硬删别名）；统一标注 Kiwi `1050`（21 处）。
8. **门禁**：`ruff check` / `ruff format --check` / `pyright` 全绿；全量 `pytest` 812 passed / 8 skipped、覆盖率 95%（本任务新增 / 修改模块 100%）。
9. **登记回写**：《后端基类清单》§2 / §5 / §6 / §8；《后端开发规范》「SQL 与数据访问规范」（仓储写入与会话入口口径）；《架构设计 · 数据架构》「数据规范」（布尔 / 多值存储口径）；《数据库设计 · sys_module》状态与迁移注记；计划与任务 / 父任务状态。
10. **开发库实测**：`uv run python -m ops.seed_module`（4 行 / 重复 0 行）；开发平台库索引名核实 `idx_sys_module_deleted_at`；`ops.check_modules` 通过。

关键命令：

```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -q --cov=app --cov-branch
uv run python -m ops.seed_module
uv run python -m ops.check_modules
python3 scripts/tools/base-check/check-backend-base.py   # 仓库根
python3 scripts/tools/base-check/check-base.py
python3 scripts/tools/base-check/check-links.py
```

## 4. 问题与处置 <a id="issues"></a>

| 问题 / 现象 | 原因 | 处置与落点 |
| --- | --- | --- |
| `hard_delete` 初稿无法清理已软删行 | `get()` 带软删过滤，回收站物理清理场景被挡 | 设计回写（4.3 行 + 穿透段）：`_scope_conditions(include_soft_delete=False)` 仅去掉软删条件、保留租户与数据范围；用例覆盖 |
| pyright 报 `ClassVar` 不能含类型变量 | `model: ClassVar[type[ModelT]]` 不合类型规范 | 改 `ClassVar[type[BaseModel]]`，`_select` / `create` 两处显式 `cast` 回泛型 |
| 乐观锁用例首版未抛冲突 | 用例未持有二次载入实体的强引用，identity map 弱引用回收后复载拿到新版本 | 用例持有 `stale` 变量（同会话旧版本）复现冲突；仓储语义不变 |
| PostgreSQL 探针主键渲染为 `BIGSERIAL` | 探针表整型主键默认自增（`BaseModel` 雪花 ID 有 Python 默认值不受影响） | 探针列 `autoincrement=False`，与雪花 ID 禁用数据库自增口径一致 |
| `__table__` 在 pyright 下判为 `FromClause` | 无 SQLAlchemy 类型插件 | 用例显式 `cast("Table", ...)` 后取 `create` / `indexes` / `constraints` |
| 用例直用受保护钩子触发 pyright 告警 | `_apply_data_scope` / `_apply_tenant_scope` 为基类内部钩子 | 测试替身子类暴露包装方法（对齐既有测试风格） |

## 5. 验证结果 <a id="verify"></a>

| 完成标准 | 验证方法 | 实测结果 |
| --- | --- | --- |
| `BaseRepository` 异步 CRUD 与分页用例通过 | DB 仓储用例（CRUD / 作用域 11 操作符 / 软删硬删 / 租户 / 分页排序 / 存在性） | 通过 |
| `BaseModel` 雪花 ID / 软删除 / 审计 / 乐观锁用例通过 | 仓储异步链路用例（ID / 审计字段 / 软删恢复 / 并发旧版本 409）+ 既有 Kiwi 30 同步用例 | 通过 |
| 四库类型映射与复合唯一索引验证通过 | 四方言 DDL 编译断言 + SQLite 真库多 NULL 共存与同键复用 | 通过（三库真库实测归 01_05） |
| `sys_module` 落库且种子正确 | 种子脚本幂等用例 + 开发平台库执行 | 通过（4 行，重复执行 0 行） |
| `pytest` / `ruff` / `pyright` 全绿 | 门禁命令 | `ruff` / `pyright` 全绿；`pytest` 812 passed / 8 skipped，覆盖率 95%（门禁 ≥70%），本任务新增 / 修改模块 100% |

## 6. 偏差与遗留 <a id="deviations"></a>

- **归 01_04**：排序契约 DB 侧细化（四库 NULLS 口径、排序字段索引配合、分页限深 100 页、keyset 游标键）；Alembic 在线迁移与 SQLite 全量自动建表（`ops/seed_module.py` 建表分支届时退化）；`ops` 批量迁移。
- **归 01_05**：三库真库集成与达梦方言实测（复合唯一 NULL 语义、迁移 DDL、schema 前缀大小写、类型映射真库确认）；CI `verify/db` 档。
- **归 03_01 / 03_02**：`sys_module` 升格服务目录（服务维度与契约版本字段）与启动 / CI 接库唯一性校验。
- **归 RBAC 阶段**：数据范围 `read_predicate` 真实规则注入与 `allow_write` 写前校验。
- **开放项**：模块仓储的依赖注入工厂装配随首个业务模块接入；dict / listing 只迁移会话入口、未做仓储化。
- 消费方前置契约标注见偏差与遗留闭环提交（01_04 / 01_05 / 03_01）。

> 本文档依《文档生成规范》编写

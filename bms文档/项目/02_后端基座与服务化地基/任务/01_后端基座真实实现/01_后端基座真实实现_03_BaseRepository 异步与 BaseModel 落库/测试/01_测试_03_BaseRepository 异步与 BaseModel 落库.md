# BaseRepository 异步与 BaseModel 落库测试记录

> 后端基座与服务化地基 · 01 后端基座真实实现 · 03 BaseRepository 异步与 BaseModel 落库 · 测试记录

[文档首页](../../../../../../文档首页.md) › [03 BaseRepository 异步与 BaseModel 落库](../01_后端基座真实实现_03_BaseRepository 异步与 BaseModel 落库.md) › 01 测试　|　[详细设计](../设计/01_详细设计_03_BaseRepository 异步与 BaseModel 落库.md) · [实施记录](../实施/01_实施_03_BaseRepository 异步与 BaseModel 落库.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 BaseRepository 异步与 BaseModel 落库](../01_后端基座真实实现_03_BaseRepository 异步与 BaseModel 落库.md) |
| 对应需求 | [01-3](../../../../需求/01_需求_后端基座真实实现.md#r01-3) |
| 详细设计 | [01_详细设计_03_BaseRepository 异步与 BaseModel 落库](../设计/01_详细设计_03_BaseRepository 异步与 BaseModel 落库.md) |
| 实施记录 | [01 实施记录](../实施/01_实施_03_BaseRepository 异步与 BaseModel 落库.md) |
| 测试日期 | 2026-09-22 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14 / uv）；SQLite 真库（临时库）；四方言 DDL 离线编译（sqlite / mysql / postgresql / 达梦 `dmSQLAlchemy`，不建连） |
| Kiwi 用例 | 1050 |
| 结论 | 通过 |

## 2. 测试范围与用例 <a id="scope"></a>

| Kiwi | 用例 | 类型 | 自动化文件 | 断言要点 |
| --- | --- | --- | --- | --- |
| 1050 | CRUD 与审计 | 单元 | `tests/repositories/test_db_repository.py::test_crud_roundtrip_and_audit` | 雪花 ID / 审计字段 / 版本初值；get / list / count / `SELECT EXISTS`；update 版本自增与缺失返回 None |
| 1050 | 写入白名单 | 单元 | `…::test_write_whitelist_rejects_unknown_and_internal_fields` | 未知键与 `id` / `created_by` / `version` / `deleted_at` 一律 `ConfigError` |
| 1050 | 作用域操作符翻译 | 单元 | `…::test_scope_operator_translation` | 11 操作符（eq/ne/in/like/gt/gte/lt/lte/between/is_null/is_not_null）与空 `in` 恒假 |
| 1050 | 条件非法快速失败 | 单元 | `…::test_scope_condition_errors` | 字段不存在 / 操作符不支持 / 值形态非法（`in` 非序列、`like` 非字符串、`between` 非二元） |
| 1050 | 软删恢复与唯一复用 | 单元 | `…::test_soft_delete_restore_and_unique_reuse` | 软删后不可见 / 存在性 False；复合唯一键释放复用；`restore` 后恢复可见 |
| 1050 | 删除出口 | 单元 | `…::test_delete_switch_and_hard_delete` | `delete` 默认软删 / 关闭软删物理删；`hard_delete` 穿透软删过滤清理残留；缺失返回 False |
| 1050 | 租户写读作用域 | 单元 | `…::test_tenant_write_and_read_scope` | `create` 注入与显式同值通过、异值拒绝；`update` 禁改租户；跨租户不可见 / 存在性 False |
| 1050 | 租户边界分支 | 单元 | `…::test_tenant_scope_edge_branches` | 上下文无主键不注入；`tenant_scoped` 声明与模型不符（读写）`ConfigError` |
| 1050 | 乐观锁冲突 | 单元 | `…::test_optimistic_lock_conflict` | 并发旧版本 flush → `ConcurrentConflictError`（409） |
| 1050 | 分页与排序 | 单元 | `…::test_pagination_and_sort` | `list_page` LIMIT/OFFSET（含排序参数）；`list_cursor` 偏移；默认 `id` 升序；未知排序字段忽略 |
| 1050 | 内存基线删除别名 | 单元 | `tests/repositories/test_base_repository.py::test_soft_and_hard_delete_aliases_delegate_to_delete` | 测试替身 `soft_delete` / `hard_delete` 默认委托 `delete`（硬删差异口径） |
| 1050 | 继承链退出桩 | 单元 | `…::test_inheritance_chain` | `BaseDbRepository` 仍属契约体系且不再继承 `BaseStub` |
| 1050 | 四库类型映射 | 单元 | `tests/models/test_type_mapping.py::test_four_dialect_type_mapping` | sqlite / mysql / postgresql / 达梦 DDL 的 BIGINT / DATETIME / VARCHAR / 布尔 / JSON 映射 |
| 1050 | 复合唯一索引 | 单元 | `…::test_soft_delete_composite_unique_in_ddl` | 四库 DDL 均含 `UNIQUE (唯一字段, deleted_at)` 四组 |
| 1050 | 索引命名 | 单元 | `…::test_index_naming_convention` | `index=True` 生成 `idx_{表}_{列}`；显式 `uq_*` 不变 |
| 1050 | SQLite NULL 唯一语义 | 单元 | `…::test_sqlite_soft_delete_unique_semantics` | 未删行（NULL deleted_at）共存、删除后同键复用、DDL 索引名对齐 |
| 1050 | 布尔落库 | 单元 | `…::test_boolean_storage_roundtrip` | 布尔字段 SQLite 按小整数 1/0 存储 |
| 1050 | 会话入口租户键与工厂 | 单元 | `tests/db/test_session_scope.py::test_session_scope_tenant_key_and_custom_factory` | 按租户上下文库键取引擎；自定义会话工厂生效 |
| 1050 | 会话入口回落与角色 | 单元 | `…::test_session_scope_demo_fallback_explicit_key_and_read_only` | 无上下文回落演示租户；显式库键优先；只读参数透传注册表 |
| 1050 | 种子 URL 与幂等 | 单元 | `tests/ops/test_module_ops.py::test_seed_module_resolve_url` / `…::test_seed_module_idempotent` | URL 解析优先序；首建 4 行、重复 0 行；键集合与清单一致 |
| 1050 | 种子 CLI | 单元 | `…::test_seed_module_cli` | dry-run 输出种子清单；正式执行输出新增行数 |
| 1050 | dict / listing 回归 | 单元 | `tests/dict/`、`tests/listing/`（既有用例） | 会话入口迁移后行为不变 |

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ uv run ruff check .                # All checks passed!
$ uv run ruff format --check .       # 391 files already formatted
$ uv run pyright                     # 0 errors, 0 warnings, 0 informations
$ uv run pytest -q                   # 812 passed, 8 skipped
$ uv run pytest --cov=app --cov-branch --cov-report=term   # TOTAL 95%
$ uv run python -m ops.seed_module   # 新增 4 行（幂等；重复执行输出 0）
$ uv run python -m ops.check_modules # 校验通过（4 项）
$ python3 scripts/tools/base-check/check-backend-base.py   # 通过
$ python3 scripts/tools/base-check/check-base.py           # 通过
$ python3 scripts/tools/base-check/check-links.py          # 断链 0 / 失效锚点 0
```

结果汇总：本任务新增 / 适配用例全绿（Kiwi 1050 标注 21 处）；全量 812 passed / 8 skipped（较 01_02 快照 787 / 8 净增 25 条通过）。DB 仓储 CRUD / 作用域翻译 / 软删硬删 / 租户写读口径 / 乐观锁 / 分页排序、四库类型映射与复合唯一、索引命名、统一会话入口与 `sys_module` 种子用例均通过；开发平台库种子实测幂等（重复执行 0 行）；三库真库用例因未配置 `BMS_TEST_DB_URL` 跳过（归 01_05）。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 原因 | 处置与落点 |
| --- | --- | --- |
| 乐观锁断言首版未触发 | identity map 弱引用回收后复载拿到新版本 | 用例持有旧版本实体强引用复现冲突（见实施记录 §4） |
| PostgreSQL 探针主键渲染 `BIGSERIAL` | 整型主键默认自增（非 `BaseModel` 口径） | 探针列 `autoincrement=False`，断言对齐雪花 ID 口径 |
| 测试表对象类型判为 `FromClause` | 无 SQLAlchemy 类型插件 | 用例显式 `cast("Table", ...)` 后访问表能力 |
| 受保护钩子用例直用告警 | 基类内部钩子 | 测试替身暴露包装方法（`apply_scope` / `tenant_payload`） |

## 5. 覆盖率 <a id="coverage"></a>

`uv run pytest --cov=app --cov-branch --cov-report=term`：**TOTAL 8937 语句，覆盖率 95%**（门禁阈值 70%，达标；任务级快照）。本任务新增 / 修改模块：`repositories/base_db_repository.py` 100%、`repositories/base_scoped_repository.py` 100%、`db/session.py` 100%、`models/base.py` 100%；dict / listing 迁移仅替换会话入口，覆盖率与既有基线持平（既有分支缺口非本任务引入）。

## 6. 偏差与遗留 <a id="deviations"></a>

- 排序契约 DB 侧细化（四库 NULLS / 限深 / 游标键）与 Alembic 迁移归 01_04；三库真库与达梦方言实测归 01_05；服务目录升格与接库校验归 03_01 / 03_02；数据范围写校验归 RBAC 阶段。
- 开放项：模块仓储依赖注入工厂随首个业务模块接入；dict / listing 仓储化另行评估。

> 本文档依《文档生成规范》编写

# Alembic 迁移与排序 DB 侧测试记录

> 后端基座与服务化地基 · 01 后端基座真实实现 · 04 Alembic 迁移与排序 DB 侧 · 测试记录

[文档首页](../../../../../../文档首页.md) › [04 Alembic 迁移与排序 DB 侧](../01_后端基座真实实现_04_Alembic 迁移与排序 DB 侧.md) › 01 测试　|　[详细设计](../设计/01_详细设计_04_Alembic 迁移与排序 DB 侧.md) · [实施记录](../实施/01_实施_04_Alembic 迁移与排序 DB 侧.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04 Alembic 迁移与排序 DB 侧](../01_后端基座真实实现_04_Alembic 迁移与排序 DB 侧.md) |
| 对应需求 | [01-4](../../../../需求/01_需求_后端基座真实实现.md#r01-4) |
| Kiwi 用例 | **1078**（1 条用例覆盖全部断言面；平台回读编号） |
| 测试日期 | 2026-09-22 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14 / uv，SQLite 真库）；mjbk 常驻三库（MySQL 8.0 / PostgreSQL 16 / 达梦 DM8）真库演练 |
| 执行入口 | `cd backend && uv run pytest -q --cov=app --cov-branch`；基座对账脚本见 §3.1 |

## 2. 测试范围与用例 <a id="scope"></a>

| 关注点 | 断言要点 | 自动化文件 |
| --- | --- | --- |
| 迁移链注册与元数据子集 | 三链注册（版本目录 / 表集 / 分支标签）；未知链名与未知表集抛 `ConfigError`；元数据子集只含链表；URL 解析优先序（`-x url=` > `BMS_MIGRATION_URL` > 配置；租户链 `-x db_key=` 经模板） | `tests/alembic/test_alembic_chains.py`、`test_alembic_env.py` |
| 迁移链完整性与零漂移 | 每链单 head、无断链、revision 跨链唯一、链首 `branch_labels`、空链（归档）语义；每条链迁移后与元数据子集 autogenerate 对比差异为空 + 未迁移表差异非空（反例） | `tests/alembic/test_alembic_chains.py`、`test_alembic_drift.py` |
| 版本读取与模式切换 | `current_revision` 未迁移 / 已迁移（异步与同步变体）；`apply_session_schema` 非达梦 / 空模式空操作、达梦 `SET SCHEMA`、不支持时回落 `ALTER SESSION SET CURRENT_SCHEMA`、切换后结束隐式事务；达梦走同步读取线程 | `tests/alembic/test_alembic_env.py` |
| SQLite 自动建表 | 开关开 + SQLite → 按链表集建表且幂等（二次执行 0 张新表）；开关关 / 非 SQLite → 跳过 | `tests/alembic/test_auto_create_tables.py` |
| 库级建删能力 | SQLite 建 / 查 / 删文件；MySQL、PostgreSQL、达梦的建库 / 建模式与删库 / 删模式语句、存在性检查与确认提示；已存在 / 不存在分支幂等；达梦经同步助手线程执行 | `tests/db/test_db_admin.py` |
| ops 批量迁移与新租户初始化 | 临时平台库 + 双租户：首跑全迁移、重跑「已是最新」跳过；单库失败不中断且汇总含失败项（退出码 1）；`--dry-run` 不建连；初始化三步（建库 → 迁移 → 幂等种子）与 `--skip-create-db` | `tests/ops/test_migration_ops.py` |
| 排序 NULL 口径 | 四方言 ORDER BY 编译含 `IS NULL` 排序键（不出现 `NULLS FIRST/LAST` 字面量）；SQLite 真库升 / 降序 NULL 均末位；混合类型兜底不抛错；内存基线与 DB 同口径 | `tests/repositories/test_ordering.py`、`test_db_repository.py`、`test_base_repository.py` |
| 排序字段索引配合 | 主键 / 表级索引 / 单列唯一约束视为已索引；缺索引字段抛 `ConfigError`；无 `__table__` 抛 `ConfigError` | `tests/repositories/test_ordering.py` |
| 分页限深 | `page = max_page` 通过、`max_page + 1` 校验失败（10001 口径）；`[pagination].max_page` 配置可调 | `tests/schemas/test_pagination.py` |
| keyset 游标 | 编解码往返与规格指纹校验；非法 base64 / JSON / 版本 / 规格不一致 / 类型不支持 / 载荷缺字段抛 `ParamError`；DB 与内存基线逐页取完与全量排序一致（升 / 降序、多键、含 NULL）；服务层 `next_cursor` / `has_more` | `tests/schemas/test_cursor.py`、`tests/repositories/test_ordering.py` / `test_db_repository.py`、`tests/services/test_base_service.py`、`tests/db/test_data_access.py` |
| 既有回归 | dict（含自有迁移）/ listing / 仓储 / 服务 / 会话入口用例全绿；既有阶段二批次用例无回归 | 全量 `pytest` + `tests/integration/test_tenant_routing_integration.py`、`tests/ops/test_tenant_ops.py` 适配项 |

## 3. 执行记录与结果 <a id="run"></a>

### 3.1 自动化与门禁

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 全量用例 | `uv run pytest -q` | **884 passed / 8 skipped**（1 条既有 aiosqlite GC 告警，非本任务引入） |
| 覆盖率 | `uv run pytest -q --cov=app --cov-branch --cov-report=term-missing` | 总体 **96%**；新增 / 改动模块 100%（见 §5） |
| 静态检查 | `uv run ruff check .` + `uv run ruff format --check .` + `uv run pyright` | 全通过（0 error / 0 warning） |
| 基座对账 | `python3 scripts/tools/base-check/check-backend-base.py`（含 `--self-test`） | 通过；自检 5 例（含新增「迁移链分链合规」「同链双 head」）全通过 |
| 文档对账 | `python3 scripts/tools/base-check/check-base.py`、`scripts/tools/base-check/check-links.py`、`scripts/tools/check-docs/check-status.py --stage 02_后端基座与服务化地基` | 全通过（阶段二硬规则 0 / 软提示 0） |

### 3.2 三库真库迁移演练（建库 → 迁移 → 校验 → 清理）

口径：一库一演练一清理；MySQL / PostgreSQL 用临时库 `bms_migrcheck`（平台链）与 `bms_migrcheck_tenant`（租户链），达梦用模式 `BMS_MIGRCHECK` / `BMS_MIGRCHECK_TENANT`；凭据取本地资源文档，不入库。

| 库 | 对象 | 建（`ops/db_admin create`） | 迁移（`ops/migrate_tenants`） | 校验（`alembic_version` / 表） | 清理（`ops/db_admin drop`） |
| --- | --- | --- | --- | --- | --- |
| MySQL 8 | `bms_migrcheck`（平台链） | 新建 | 未迁移 → `0001_sys_tenant_module` | `0001_sys_tenant_module`；表 4/4（含 `alembic_version`） | 已删除 |
| MySQL 8 | `bms_migrcheck_tenant`（租户链） | 新建 | 未迁移 → `0001_dict_query_scheme` | `0001_dict_query_scheme`；表 8/8 | 已删除 |
| PostgreSQL 16 | `bms_migrcheck`（平台链） | 新建 | 未迁移 → `0001_sys_tenant_module` | `0001_sys_tenant_module`；表 4/4 | 已删除 |
| PostgreSQL 16 | `bms_migrcheck_tenant`（租户链） | 新建 | 未迁移 → `0001_dict_query_scheme` | `0001_dict_query_scheme`；表 8/8 | 已删除 |
| 达梦 DM8 | 模式 `BMS_MIGRCHECK`（平台链） | 新建 | 未迁移 → `0001_sys_tenant_module` | `0001_sys_tenant_module`；表 4/4 | 已删除 |
| 达梦 DM8 | 模式 `BMS_MIGRCHECK_TENANT`（租户链） | 新建 | 未迁移 → `0001_dict_query_scheme` | `0001_dict_query_scheme`；表 8/8 | 已删除 |

结论：**6 次迁移执行全部通过**，演练后三库无残留对象（达梦模式清单复核仅剩既有 `BMS_DEV` 与系统模式）。

### 3.3 达梦实测结论（本任务新增，01_05 复评）

| 观测项 | 实测结论 |
| --- | --- |
| DDL 执行 | 需注册 Alembic DDL impl（`env.py::DMImpl`，`__dialect__ = "dm"`），否则 `MigrationContext` 直接 `KeyError: 'dm'` |
| 库级隔离 | 以**模式**为单位：`CREATE SCHEMA <名>` → 迁移前 `SET SCHEMA <名>`（会话级切换可用）→ 清理 `DROP SCHEMA <名> CASCADE` |
| 模式存在性 | `ALL_USERS` 不含 `CREATE SCHEMA` 建出的模式；应查 `SYS.SYSOBJECTS WHERE TYPE$ = 'SCH'` |
| 版本表回滚 | `SET SCHEMA` 打开的隐式事务若不结束，Alembic 视为外部事务而不再提交 → `alembic_version` 版本行为空（表已建）；切换后显式提交即正常 |
| 「表不存在」异常类 | 报 `DatabaseError`（区别于 PG / MySQL 的 `ProgrammingError`、SQLite 的 `OperationalError`） |
| 迁移连接 | 达梦无异步方言驱动 → 在线迁移走同步引擎分支（应用运行期仍走同步引擎，见《架构设计 · 数据访问与分片》） |

### 3.4 开发库重建与幂等复核

| 项 | 结果 |
| --- | --- |
| 平台库迁移 | `alembic -n alembic:platform upgrade head` → `0001_sys_tenant_module`，表 `sys_tenant` / `sys_module` / `sys_module_i18n` |
| 租户库迁移 | `alembic upgrade head`（缺省链）→ `0001_dict_query_scheme`，字典六表 + `sys_query_scheme` |
| 索引命名 | 两库索引全部为 `idx_*`（无 `ix_*` 残留，索引数 4 / 18） |
| 种子幂等 | `ops.seed_tenant` 2 行 / `ops.seed_module` 4 行 / `ops.seed_dict` 25 行，重复执行新增 0 行 |
| 批量迁移幂等 | `ops.migrate_tenants --target all` → 成功 1、跳过 3（含归档空链提示）、失败 0 |

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 处置 |
| --- | --- |
| 达梦迁移首轮失败（DDL impl 缺失 / 版本行为空 / 模式存在性误判） | 三项均已修正并复测通过（详见实施记录 §4 与本节 §3.3） |
| CLI 选链形态与 Alembic 读取顺序冲突 | 经确认改用命名配置段（决策 19），用例改按「配置段 → 链」断言 |
| 既有 `list_cursor` 偏移口径用例 | 按 keyset 语义重写（游标由响应回传、末页 `next_cursor` 为 None），`tests/db/test_data_access.py` / `test_base_repository.py` / `test_db_repository.py` / `test_base_service.py` 同步适配 |
| 既有租户运维用例（`tests/ops/test_tenant_ops.py`） | 批量迁移 / 初始化相关断言迁入 `tests/ops/test_migration_ops.py`（真实实现口径），原文件保留种子断言 |

## 5. 覆盖率 <a id="coverage"></a>

| 模块 | 语句 / 分支覆盖率 |
| --- | --- |
| `app/db/migration.py` | 100% |
| `app/db/admin.py` | 100% |
| `app/db/bootstrap.py` | 100% |
| `app/repositories/ordering.py` | 100% |
| `app/schemas/cursor.py` | 100% |
| `app/schemas/pagination.py` | 100% |
| `app/services/base_service.py` | 100% |
| `app/repositories/base_repository.py` / `base_memory_repository.py` / `base_db_repository.py` | 100% |
| 全量 `app/` | 96%（余量为既有模块） |

## 6. 偏差与遗留 <a id="deviations"></a>

- **偏差（已闭环）**：达梦模式切换与版本提交口径、DDL impl 注册三处为实施中实测发现并当场修正，结论已回写实施记录与本节 §3.3；CLI 选链形态变更（决策 19）与阶段二既有文档合规偏差修正（决策 20）见实施记录 §7。
- **遗留（归口）**：① 三库集成用例、CI `verify/db` 档激活与达梦方言细节复评（复合唯一 NULL 语义 / 类型映射真库确认 / DDL 差异）→ **01_05**；② `ops/test_db.py` 真库流程编排 → **01_05**；③ 骨架表迁移 → 所属阶段；④ 游标排序键类型范围（`Decimal` 等）按需扩展；⑤ 01_01「预存在 6 条用例失败」保持阶段收口归口（本任务未触碰）。

> 依《文档生成规范》编写 · 与《实施记录》配套

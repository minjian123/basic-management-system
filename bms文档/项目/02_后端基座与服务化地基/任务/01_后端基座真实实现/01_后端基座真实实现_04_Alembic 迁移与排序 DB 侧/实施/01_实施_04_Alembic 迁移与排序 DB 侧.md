# Alembic 迁移与排序 DB 侧实施记录

> 后端基座与服务化地基 · 01 后端基座真实实现 · 04 Alembic 迁移与排序 DB 侧 · 实施记录

[文档首页](../../../../../../文档首页.md) › [04 Alembic 迁移与排序 DB 侧](../01_后端基座真实实现_04_Alembic 迁移与排序 DB 侧.md) › 01 实施　|　[详细设计](../设计/01_详细设计_04_Alembic 迁移与排序 DB 侧.md) · [测试记录](../测试/01_测试_04_Alembic 迁移与排序 DB 侧.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04 Alembic 迁移与排序 DB 侧](../01_后端基座真实实现_04_Alembic 迁移与排序 DB 侧.md) |
| 对应需求 | [01-4](../../../../需求/01_需求_后端基座真实实现.md#r01-4) |
| 详细设计 | [01_详细设计_04_Alembic 迁移与排序 DB 侧](../设计/01_详细设计_04_Alembic 迁移与排序 DB 侧.md) |
| 实施日期 | 2026-09-22 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu，Python 3.14 / uv）；SQLite 开发与临时库；mjbk 常驻三库（MySQL 8 / PostgreSQL 16 / 达梦 DM8，容器 `bms-mysql` / `bms-postgres` / `bms-dm`） |
| 提交 | 70b958ca（详细设计）+ 9b5c598f（feat：代码与用例）+ 本条 docs 提交 |
| 结论 | 完成 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A["Kiwi 用例登记（1078）"] --> B["链注册 app/db/migration.py + alembic.ini 命名段"]
    B --> C["alembic/env.py 重构 + 迁移脚本（platform 新建 / tenant 迁址修订）"]
    C --> D["SQLite 自动建表 + 基座校验脚本适配"]
    D --> E["app/db/admin.py + ops（db_admin / migrate_tenants / init_tenant）"]
    E --> F["排序 NULL 末位 + 索引断言 + 限深 + keyset 游标"]
    F --> G["用例 + 门禁 + 零漂移校验 + 开发库重建"]
    G --> H["三库真库迁移演练"]
    H --> I["登记回写 + 实施/测试记录 + 提交"]
```

## 3. 实施过程 <a id="process"></a>

1. **Kiwi 用例登记（先登记后编码）**：登记 1 条用例覆盖全部断言面，平台回读编号 **1078**；登记输入 `scripts/kiwi/cases/2026-09-22_阶段二01-04_Alembic迁移与排序DB侧.json`（含回读 `case_id`），台账回写见 §7。
2. **迁移链注册** `app/db/migration.py`：登记三链（`platform` / `tenant` / `archive`）的版本目录、表集（平台三表 / 租户七表 / 归档空）、分支标签与连接串取法；`chain_metadata` 取元数据子集（`Table.to_metadata` + 命名约定）、`chain_url` 复用 `EngineFactory.resolve_url` / `resolved_url`（本任务公开化）、`current_revision` 读 `alembic_version`、`apply_session_schema` 切换达梦会话模式。
3. **`alembic` 环境与脚本**：`alembic.ini` 增命名配置段 `[alembic:platform]` / `[alembic:tenant]` / `[alembic:archive]`（各自 `version_locations`；缺省 `[alembic]` 段即租户链，既有裸命令零改动）；`env.py` 由配置段派生链并取元数据子集，在线分支按方言分流（达梦同步引擎、其余异步 + `run_sync`），支持 `-x url=` / `-x db_key=` / `-x schema=`，空链提示跳过；新增平台链迁移 `versions/platform/0001_sys_tenant_module.py`（`sys_tenant` / `sys_module` / `sys_module_i18n`），租户链迁移迁入 `versions/tenant/` 并补 `branch_labels`、12 处 `ix_*` 索引名修订为 `idx_*`，归档链建占位说明。
4. **SQLite 开发库自动建表** `app/db/bootstrap.py` + `main.lifespan` 接线：按 `[database].auto_create` 开关与 SQLite 方言判定，以迁移链表集执行 `create_all(checkfirst=True)`（幂等、不建骨架表），URL 去重后写入日志。
5. **运维脚本**：`app/db/admin.py` 库级建删能力（MySQL / PostgreSQL 建删库、SQLite 建删文件、达梦建删模式；幂等且不擅动既有对象）+ 薄 CLI `ops/db_admin.py`（create / drop / exists）；`ops/migrate_tenants.py` 真实批量迁移（枚举平台库 + `sys_tenant` 各租户 + 归档库，逐库经 Alembic 程序化接口迁移，`alembic_version` 已最新则跳过，失败不中断并汇总，存在失败退出码 1）；`ops/init_tenant.py` 建库 → 迁移 → 幂等种子三步。
6. **排序 DB 侧细化**：新增 `app/repositories/ordering.py`（`order_criteria` 生成「`列 IS NULL` + 列」排序键实现 NULL 恒末位并补主键兜底、`keyset_condition` 键集续查谓词、`sort_items` / `is_after_cursor` 内存镜像、`assert_sortable_fields_indexed` 索引断言工具）；`BaseDbRepository._apply_sort` / `list_cursor` 与 `BaseMemoryRepository` 接线；新增 `app/schemas/cursor.py`（keyset 游标载荷与 base64url JSON 编解码，规格指纹不一致或载荷非法抛 `ParamError`）；`BasePageQuery` 增加 `page ≤ [pagination].max_page` 限深（默认 100）；`BaseRepository` 增 `effective_sort` / `build_cursor` 契约，`BaseService.cursor_page` 据此生成 `next_cursor` / `has_more`。
7. **配置**：`config.toml` 增 `[pagination].max_page` 与 `[database].auto_create`（`config.prod.toml` 置 false）、`.env.example` 补 `BMS_PAGINATION__MAX_PAGE` / `BMS_DATABASE__AUTO_CREATE`。
8. **基座校验脚本适配**：`scripts/tools/base-check/check-backend-base.py` 迁移链校验改为「按链分目录：每链单 head / 无断链 / revision 跨链唯一 / 链首 `branch_labels` / `alembic.ini` 配置段齐备 / 禁止脚本置于版本根目录」，自检新增「迁移链分链合规」与「同链双 head」两例（拦截已验证）。
9. **开发库重建**：删除本地 SQLite 开发库（先备份至 `/tmp`）→ 平台链 `0001_sys_tenant_module` + 租户链 `0001_dict_query_scheme` 迁移 → `ops.seed_tenant`（2 行）/ `ops.seed_module`（4 行）/ `ops.seed_dict`（25 行）幂等重跑；复核 `alembic_version` 与索引名（无 `ix_*` 残留）。
10. **用例与门禁**：新增/适配 11 个用例文件（见测试记录），`pytest` / `ruff` / `pyright` 全绿；新增与改动模块覆盖率 100%。
11. **三库真库演练**：mjbk 三库按方言建库（达梦建模式）→ 迁移平台链与租户链 → 校验 `alembic_version` 与表清单 → 清理，6 次迁移执行全部通过（结论见测试记录 §3.2）。
12. **登记回写与记录**：见 §6 与测试记录；计划 §2 / §3、任务状态、Kiwi 台账、基类清单、规范与架构节点、数据表设计状态均已按实施结果回写。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 现象 | 处置 |
| --- | --- | --- |
| `-x target=` 无法切换版本目录 | Alembic 在 `env.py` 执行**之前**读取 `version_locations`，`env.py` 内动态设置无效；且三链 = 三 head，裸 `upgrade head` 直接报「Multiple head revisions」 | 经确认改用**命名配置段**选链（`alembic -n alembic:<链名>`；缺省 `[alembic]` = 租户链、既有命令与两个既有用例零改动），`env.py` 由 `config.config_ini_section` 派生链（决策 19，设计已回写） |
| 达梦无 Alembic DDL impl | `MigrationContext` 初始化 `KeyError: 'dm'`（Alembic 未内建 `dm` 方言实现） | `env.py` 注册 `DMImpl(DefaultImpl)`（`__dialect__ = "dm"`，DDL 沿用通用实现） |
| 达梦「表不存在」异常类型不同 | 未迁移时 `SELECT version_num FROM alembic_version` 抛 `DatabaseError`（非 PG / MySQL 的 `ProgrammingError`、SQLite 的 `OperationalError`），导致「是否已迁移」判断失败 | `current_revision` / `_read_revision` 将三类异常统一视为「未迁移」并注明各库差异 |
| 达梦版本行回滚 | 迁移后表已建、`alembic_version` **版本行为空**（Alembic 把 `SET SCHEMA` 打开的隐式事务视为外部事务而不再提交） | `apply_session_schema` 在切换模式后结束隐式事务（`connection.commit()`），复测版本行正常落库 |
| 达梦模式存在性检查 | `ALL_USERS` 只含用户、不含 `CREATE SCHEMA` 建出的模式 → `drop` 误判「不存在（跳过）」 | 改查系统对象表 `SYS.SYSOBJECTS WHERE TYPE$ = 'SCH' AND NAME = :name`（实测可行） |
| 阶段二既有文档合规偏差 | `check-status` 报 §2 表五列（规范要求六列 → 行全部漏读，连带 H6）、§1 缺工时台账行、01_01~01_03 任务状态写作「完成」（集合外取值） | 经确认本任务一并修正（§2 改六列 + 补「任务文件」列、§1 补「已完成 42h；剩余 214h；阶段合计 **256h**」、三个任务状态改「已完成」），阶段二硬规则归零（决策 20） |
| ruff 重写异常括号 | py314 目标下 ruff 自动修复把 `except (A, B):` 改为无括号形态（PEP 758） | 遵循自动修复结果（格式与门禁一致），代码形态以 `ruff format` 输出为准 |

## 5. 验证结果 <a id="verify"></a>

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 单元用例 | `uv run pytest -q` | 884 passed / 8 skipped（1 条告警为既有 aiosqlite GC 告警，非本任务引入） |
| 覆盖率 | `uv run pytest -q --cov=app --cov-branch` | 总体 96%；新增与改动模块（`db/migration` / `db/admin` / `db/bootstrap` / `repositories/ordering` / `schemas/cursor` / `schemas/pagination` / `services/base_service` / `repositories/base_*`）**100%** |
| 静态检查 | `uv run ruff check .` / `uv run ruff format --check .` / `uv run pyright` | 全通过（0 error / 0 warning） |
| 基座对账 | `python3 scripts/tools/base-check/check-backend-base.py`（含 `--self-test`） | 通过（迁移链按链口径检查 2 个 revision；自检 5 例全通过） |
| 文档对账 | `python3 scripts/tools/base-check/check-base.py` / `check-links.py` / `check-docs/check-status.py --stage 02_后端基座与服务化地基` | 全通过（阶段二硬规则 0、软提示 0） |
| 开发库 | 迁移 + 三个种子脚本（幂等复核） | 平台库 3 表 + 租户库 7 表落地；索引无 `ix_*` 残留；种子重跑新增 0 行 |
| 三库真库迁移演练 | 建库（达梦建模式）→ 迁移 → 校验 → 清理 | MySQL / PostgreSQL / 达梦 × 平台链 / 租户链 **6 次执行全部通过**（见测试记录 §3.2） |

## 6. 登记回写 <a id="registry"></a>

| 落点 | 内容 |
| --- | --- |
| 《后端基类清单》 | §5 `BaseRepository`（`effective_sort` / `build_cursor`）+ `BaseMemoryRepository` / `BaseDbRepository`（NULL 末位 / keyset / 限深）；§8 新增迁移链注册 `MigrationChain`、库级建删 `DatabaseTarget`、开发库自动建表、排序与游标公共实现、游标契约 `CursorPayload`、分页契约限深；§10 登记三个 frozen dataclass 继承链 |
| 《后端开发规范》 | 「SQL 与数据访问规范」补排序（白名单 + NULL 恒末位 + 主键兜底 + 禁 `NULLS FIRST/LAST` + 排序字段须建索引）、分页（限深 100 + keyset 游标）、结构变更与建表（迁移分链 / 自动建表 / 建库删库经基座能力） |
| 《数据库开发规范》 | 「迁移规范（Alembic）」补按数据源分链、命令口径（`-n alembic:<链名>` / `-x schema=`）、零漂移、建删库与批量迁移 / 新租户初始化入口、SQLite 开发库自动建表 |
| 《架构设计 · 数据架构》 | 「迁移策略」口径对齐：按数据源分链 + **一套方言无关脚本在三库执行**；SQLite 开发库按链表集自动建表 |
| 《架构设计 · 数据访问与分片》 | 「查询规范」补排序字段索引配合与四库 NULL 位次口径、分页限深可配置与 keyset 游标 |
| 《数据库设计 · 数据表设计》 | `sys_tenant` / `sys_module` / `sys_module_i18n` 状态 → 已落库（平台链 `0001`）；字典六表 + 查询方案表状态与迁移脚本位置（租户链）注记 |
| 计划 / 任务 | 计划 §1 工时台账（已完成 42h / 剩余 214h / 合计 256h）、§2 已完成表（六列 + 01_04 行）、§3 移除 01_04、甘特移除已完成节点；任务与父任务域总览状态两处一致（01_04 = 已完成 / 2026-09-22） |
| 任务基线口径修正 | 任务内容第 1 条「三套方言迁移」按《数据库开发规范》修正为「按数据源分链的方言无关迁移，三库执行」 |
| Kiwi TCMS | 用例 **1078**（正文含配置段选链与达梦实测口径，登记后更新） |

## 7. 偏差与遗留 <a id="deviations"></a>

- **偏差（已闭环）**：① CLI 选链形态由设计初稿的 `-x target=` 改为命名配置段 `-n alembic:<链名>`（技术约束所迫，设计 §4.2 / §5 / §6 / §9 / §10 已回写，决策 19）；② 任务基线「三套方言迁移」措辞按《数据库开发规范》修正；③ 阶段二既有计划 / 任务文档合规偏差（§2 六列缺失、§1 缺工时台账、状态取值）经确认在本任务一并修正，阶段二文档硬规则归零。
- **遗留（归口）**：① 达梦方言细节实测（复合唯一约束的 NULL 语义、迁移 DDL 差异、schema 前缀与大小写、类型映射真库确认）与三库集成用例、CI `verify/db` 档激活 → **01_05**；② `ops/test_db.py` 三库测试库流程真实编排 → **01_05**（复用本任务 `app/db/admin.py` 与迁移入口）；③ 每服务建库 `bms_{service}_{tenant}` 与多服务多库迁移编排、连接预算 → **06_01 / 06_02**；④ 骨架表（`sys_task` / `sys_notification` / `sys_icon` / `ai_chat_log` 等）迁移 → 所属阶段；⑤ 游标支持排序键类型范围（`Decimal` 等）按需扩展；⑥ 01_01 记录的「预存在 6 条用例失败另行归口」仍保持归口阶段收口（本任务未触碰）。

> 依《文档生成规范》编写 · 与《测试记录》配套

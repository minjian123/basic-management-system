# alembic — 迁移机制目录（按「服务 × 数据源」分链；当前无脚本）

> **现状（2026-10-18，06_05「建表方式切换与迁移脚本清空」）**：历史迁移脚本已**全部清空**（48 份），
> 目录结构与 `alembic.ini` 全 7 配置段**保留**；**迁移机制完整保留**（分链注册 / 配置段映射 / 版本目录 /
> 达梦方言补丁 / 库级编排），将来需要「既有库在线升级」时按新基线重建脚本。当前表结构由**幂等建表**
> 落地：启动期自动建表（`bms_core/db/bootstrap.py::ensure_service_schema`，四库方言）与运维 / CI
> 显式入口 `ops/init_schema.py`，两处共用 `chain_metadata(chain)` 表集派生点；**开发 / 演示库一律删库重建**。

链名形如 `{service}:{datasource}`，链名即 Alembic 配置段名（`alembic.ini`）；重建脚本后同一套脚本在
SQLite / MySQL / PostgreSQL / 达梦 DM8 四库执行（**禁写方言 SQL**，见《数据库开发规范》「迁移与建表口径」节）。
**版本目录**：`alembic/versions/{service}/{datasource}/`（现为空壳目录 + `.gitkeep`）。

链定义与**表集派生**的唯一来源是 `bms_core/db/migration.py`：表集 = 表归属登记
（`bms_core/services/table_registry.py::chain_tables(service, datasource)`，仅 `status = enabled`）
∩ 已有模型；**建表集合与迁移元数据子集同源**。

| 链 | 配置段 | 版本目录 | 库 | 表集（派生） |
| --- | --- | --- | --- | --- |
| `platform:tenant`（缺省链） | `[alembic]` | `versions/platform/tenant/` | `bms_platform_{tenant}` | 字典六表（`sys_dict_*`）+ `sys_query_scheme` / `sys_config` / `sys_user_extension` + 用户与账号锁定（`sys_user` / `sys_account_lock`）+ 角色域五表（`sys_role` / `sys_user_role` / `sys_role_permission` / `sys_role_field` / `sys_data_scope`）+ 发件箱三表 |
| `platform:platform` | `[alembic:platform:platform]` | `versions/platform/platform/` | `bms_platform` | 服务目录与产品注册（`sys_module` / `sys_module_i18n` / `sys_product`）+ `sys_table_ownership` + 菜单族元数据（`sys_menu` / `sys_menu_i18n` / `sys_form` / `sys_menu_form` / `sys_field` / `sys_field_i18n` / `sys_button` / `sys_business` / `sys_business_i18n` / `sys_action` / `sys_action_i18n`）+ 发件箱三表 |
| `tenant:platform` | `[alembic:tenant:platform]` | `versions/tenant/platform/` | `bms_tenant` | `sys_tenant` / `sys_tenant_database` / `sys_user_tenant` + 发件箱三表 |
| `tenant:tenant` | `[alembic:tenant:tenant]` | `versions/tenant/tenant/` | `bms_tenant_{tenant}` | 发件箱三表 |
| `identity:platform` | `[alembic:identity:platform]` | `versions/identity/platform/` | `bms_identity` | `sys_user_identity` + 发件箱三表 |
| `identity:tenant` | `[alembic:identity:tenant]` | `versions/identity/tenant/` | `bms_identity_{tenant}` | `sys_session` / `sys_identity_provider` / `sys_client` + 发件箱三表 |
| `txn:platform` | `[alembic:txn:platform]` | `versions/txn/platform/` | `bms_txn` | `txn_global` / `txn_global_branch` / `txn_global_recovery` + 发件箱三表 |
| `org`（已退役，2026-10-07） | — | — | — | 组织主数据归 mdm 产品服务（`org` 标识易主为 mdm 产品行，其库 / 链路由 mdm 仓库维护）；原 `bms_org_{tenant}` 库由运维清理 |
| 其余服务（file / notification / search / ai / report） | 首次迁移时补段 | `versions/{service}/{platform,tenant}/`（空壳目录 + `.gitkeep`） | `bms_{service}` / `bms_{service}_{tenant}` | 表集由 `chain_tables` 派生（当前为基础设施三表），表随该服务模型补齐自动进链 |

段名规则：`[alembic]` = 缺省链 `platform:tenant`；其余链 = `[alembic:{service}:{datasource}]`。
**配置段与版本目录全量保留（含空链）**：无脚本时 `has_revisions=False` → `head_revision()` 返回 `None`、
`alembic upgrade head` 打印「链 X 暂无迁移脚本（跳过）」并正常退出。

## 命令

当前**无脚本**：以下迁移命令输出「暂无迁移脚本（跳过）」并正常退出（机制保留、按新基线重建脚本后即生效）。

```bash
cd backend

# 缺省链 platform:tenant（向后兼容既有裸命令）：platform 服务 × 各租户的租户库
uv run alembic upgrade head

# platform 服务的平台服务库
uv run alembic -n alembic:platform:platform upgrade head

# 指定库键（运维通道，可跨服务；经 url_template 解析连接串）
uv run alembic -n alembic:tenant:platform -x db_key=platform_tenant upgrade head
```

扩展参数（`-x`）：

- `-x url=<连接串>`：显式覆盖连接串（优先于 `BMS_MIGRATION_URL` 与配置）；
- `-x db_key=<库键>`：按库键经 `url_template` 解析连接串（`platform` / `platform_{service}` /
  `tenant_{code}` / `tenant_{service}_{code}`；命令行给库键即视为**运维通道**，自动开跨服务豁免）；
- `-x schema=<模式名>`：达梦模式切换（迁移前 `SET SCHEMA`，仅达梦生效；用于三库演练与多模式环境）。

## 建表（现行路径）

```bash
cd backend

# 运维 / CI 显式建表入口（与批量迁移同构：服务 × 数据源 × 库；幂等、逐库统计）
uv run python -m ops.init_schema --dry-run                        # 清单预演（不建连）
uv run python -m ops.init_schema --service platform --target platform
uv run python -m ops.init_schema --target tenants --code demo --code acme

# 启动期自动建表：服务启动时按本服务分链表集幂等建表（[database].auto_create；四库方言）
```

- **单一来源**：两处均经 `chain_metadata(chain)` 取表集；**只补不建改**（`create_all(checkfirst=True)`，不做 ALTER）。
- **建库 / 删库**：走 `ops/db_admin.py`（`bms_core/db/admin.py` 能力）与 `ops/provision_tenant.py` / `ops/init_tenant.py`（建库 → 建表 → 幂等种子）。
- **库重建**：结构不符或分链形态变更时，开发 / 演示库一律**删库重建**（`mysqldump` 留档 → drop → 建库 → 建表 → 种子）。

## 约定

- **编号**（按新基线重建脚本时适用）：各链**独立编号**，均从 `0001` 起（`revision` 值形如 `0001_sys_module`，文件名同 revision id）；
  revision 编号**链内唯一**（跨链允许同名，各链版本目录独立）；
- **分支标签**：每链首个 revision 声明 `branch_labels=("<服务>:<数据源>",)`，其余 revision 不声明；
- **公共字段块**：对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），各链同源写法；
- **基础设施表**（发件箱三表）每服务自有：各服务每条链（`platform` / `tenant`）各含三表，脚本按服务同构；
- **种子与结构分离**：建表 / 迁移只建表不写种子，种子走 `ops/seed_*.py` 幂等脚本；
- **模型与表集一致**：建表表集与迁移元数据子集同源（`chain_metadata`）；当前无脚本，逐链零漂移比对随脚本重建恢复；
- **建库 / 删库**：不在建表 / 迁移内，走 `ops/db_admin.py`（`bms_core/db/admin.py` 能力）。

## 文档导航

- 上层 [backend 工程说明](../README.md) · 仓库根 [README](../../README.md)
- 《[数据库开发规范](../../bms文档/规范/数据库开发规范.md)》·《[命名规范](../../bms文档/规范/命名规范.md)》
- 《[数据库设计总览](../../bms文档/设计/数据库设计/01_数据库设计_总览.md)》

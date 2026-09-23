# alembic — 迁移脚本目录（按「服务 × 数据源」分链）

迁移脚本按**服务 × 数据源**分链维护，链名形如 `{service}:{datasource}`，链名即 Alembic 配置段名
（`alembic.ini`）；同一套脚本在 SQLite / MySQL / PostgreSQL / 达梦 DM8 四库执行（**禁写方言 SQL**，
见《数据库开发规范》「迁移与建表口径」节）。**版本目录**：`alembic/versions/{service}/{datasource}/`。

链定义与**表集派生**的唯一来源是 `bms_core/db/migration.py`：表集 = 表归属登记
（`bms_core/services/table_registry.py::chain_tables(service, datasource)`，仅 `status = enabled`）
∩ 已有模型。

| 链 | 配置段 | 版本目录 | 库 | 表集（派生） |
| --- | --- | --- | --- | --- |
| `platform:tenant`（缺省链） | `[alembic]` | `versions/platform/tenant/` | `bms_platform_{tenant}` | 字典六表 + `sys_query_scheme` + 发件箱三表 |
| `platform:platform` | `[alembic:platform:platform]` | `versions/platform/platform/` | `bms_platform` | `sys_module` / `sys_module_i18n` / `sys_table_ownership` + 发件箱三表 |
| `tenant:platform` | `[alembic:tenant:platform]` | `versions/tenant/platform/` | `bms_tenant` | `sys_tenant` + 发件箱三表 |
| `tenant:tenant` | `[alembic:tenant:tenant]` | `versions/tenant/tenant/` | `bms_tenant_{tenant}` | 发件箱三表 |
| 其余服务 | 首次迁移时补段 | `versions/{service}/{platform,tenant}/`（空目录） | `bms_{service}` / `bms_{service}_{tenant}` | 基础设施表脚本随该服务首个需要补（见计划「后续阶段待办」） |

段名规则：`[alembic]` = 缺省链 `platform:tenant`；其余链 = `[alembic:{service}:{datasource}]`。
**只登记有迁移脚本的链**；新增服务首次迁移时须补段，否则 `alembic_config` 快速失败并给出提示。

## 命令

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

## 约定

- **编号**：各链**独立编号**，均从 `0001` 起（`revision` 值形如 `0001_sys_module`，文件名同 revision id）；
  revision 编号**链内唯一**（跨链允许同名，各链版本目录独立）；
- **分支标签**：每链首个 revision 声明 `branch_labels=("<服务>:<数据源>",)`，其余 revision 不声明；
- **公共字段块**：对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），各链同源写法；
- **基础设施表**（发件箱三表）每服务自有：各服务每条链（`platform` / `tenant`）各含三表，脚本按服务同构；
- **种子与结构分离**：迁移只建表不写种子，种子走 `ops/seed_*.py` 幂等脚本；
- **零漂移**：迁移脚本须与模型元数据一致（`tests/alembic/test_alembic_drift.py` 逐链校验）；
- **建库 / 删库**：不在迁移脚本内，走 `ops/db_admin.py`（`bms_core/db/admin.py` 能力）；
- **库重建**：分链形态变更（链名 / 目录 / revision 归属调整）后，既有开发库 / CI 临时库 / 演练库
  须**重建**（`alembic_version` 存量取值在新链中不存在，迁移会报「找不到 revision」）。

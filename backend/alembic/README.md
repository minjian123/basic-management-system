# alembic — 迁移脚本目录（按数据源分链）

迁移脚本按**数据源分链**维护，链名即 Alembic 配置段名（`alembic.ini`）：同一套脚本在
SQLite / MySQL / PostgreSQL / 达梦 DM8 四库执行（**禁写方言 SQL**，见《数据库开发规范》「迁移与建表口径」节）。

| 链 | 配置段 | 版本目录 | 库 | 表集（唯一来源：`bms_core/db/migration.py`） |
| --- | --- | --- | --- | --- |
| `tenant`（缺省） | `[alembic]` / `[alembic:tenant]` | `versions/tenant/` | 租户库 `bms_tenant_{code}` | 字典六表 + `sys_query_scheme` |
| `platform` | `[alembic:platform]` | `versions/platform/` | 平台库 `bms_platform` | `sys_tenant` / `sys_module` / `sys_module_i18n` |
| `archive` | `[alembic:archive]` | `versions/archive/` | 归档库 `bms_archive` | 空（归档表随归档阶段落地） |

## 命令

```bash
cd backend

# 租户库（缺省链；向后兼容既有裸命令）
BMS_MIGRATION_URL="sqlite+aiosqlite:///./bms_tenant_demo.db" uv run alembic upgrade head

# 平台库
BMS_MIGRATION_URL="sqlite+aiosqlite:///./bms_platform.db" uv run alembic -n alembic:platform upgrade head

# 归档库（暂无脚本 → 提示「暂无迁移脚本（跳过）」）
uv run alembic -n alembic:archive upgrade head
```

扩展参数（`-x`）：

- `-x url=<连接串>`：显式覆盖连接串（优先于 `BMS_MIGRATION_URL` 与配置）；
- `-x db_key=tenant_{code}`：租户链按库键经 `url_template` 解析租户库连接串；
- `-x schema=<模式名>`：达梦模式切换（迁移前 `SET SCHEMA`，仅达梦生效；用于三库演练与多模式环境）。

## 约定

- **编号**：各链独立编号，均从 `0001` 起（`revision` 值形如 `0001_sys_tenant_module`，文件名同 revision id）；
- **分支标签**：每链首个 revision 声明 `branch_labels=("<链名>",)`；
- **公共字段块**：对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），与租户链 `0001` 同源写法；
- **种子与结构分离**：迁移只建表不写种子，种子走 `ops/seed_*.py` 幂等脚本；
- **零漂移**：迁移脚本须与模型元数据一致（`tests/alembic/test_alembic_drift.py` 逐链校验）；
- **建库 / 删库**：不在迁移脚本内，走 `ops/db_admin.py`（`bms_core/db/admin.py` 能力）。

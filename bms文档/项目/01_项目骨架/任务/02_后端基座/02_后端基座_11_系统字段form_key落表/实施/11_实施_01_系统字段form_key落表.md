# 11 实施记录 · 系统字段 `form_key` 落表（表文件 / 模型 / 迁移）

> 项目骨架 · 02 后端基座 · 子任务 11 · 实施记录 01

[文档首页](../../../../../../文档首页.md) › [02 后端基座](../../02_后端基座.md) › [11 系统字段 form_key 落表](../02_后端基座_11_系统字段form_key落表.md) › 实施　|　[← 详细设计](../设计/11_详细设计_01_系统字段form_key落表.md)

## 1. 信息 <a id="info"></a>

- 任务：`02_11` 系统字段 `form_key` 落表（表文件 / 模型 / 迁移）；对应需求 `02-57`。
- 详细设计：[11_详细设计_01_系统字段form_key落表](../设计/11_详细设计_01_系统字段form_key落表.md)（定稿口径见其「决策确认汇总」）。
- 交付日期：2026-10-11；Kiwi 用例 **2286**。
- 范围：**仅 bms 仓**（产品仓同步另立任务，见「偏差与遗留」）。

## 2. 过程与交付物 <a id="process"></a>

按《数据库开发规范》「变更传导」顺序实施：**表文件 → ORM 模型 → Alembic 迁移 → 基座校验**。

```
bms/backend/libs/bms_core/src/bms_core/registry/
├─ __init__.py               # 导出 FormRecord / FORM_CATALOG / FormRegistry / merge_form_records
└─ forms.py                  # 新增：form_key 构建期清单（12 条） + 跨表全局唯一校验
bms/backend/alembic/versions/
├─ platform/platform/0010_system_fields_form_key.py
├─ platform/tenant/0015_system_fields_form_key.py
├─ tenant/platform/0007_system_fields_form_key.py
├─ identity/tenant/0006_system_fields_form_key.py
└─ txn/platform/0003_system_fields_form_key.py
bms/backend/libs/bms_core/tests/registry/test_form_catalog.py     # 新增：清单定向用例（Kiwi 2286）
bms/scripts/tools/base-check/check-system-fields.py               # 新增：清单 ↔ 表文件 双向一致 + 跨表唯一
bms/bms文档/设计/数据库设计/数据表设计/*.md                          # 27 份补列 + 变更记录；新增 sys_icon.md
```

**表文件（27 份）**：字典表 11（`sys_module` / `sys_product` / `sys_business` / `sys_action` / `sys_role` / `sys_user` / `sys_config` / `sys_tenant` / `sys_identity_provider` / `sys_client` / `sys_task`）逐表补 `form_key` + `parent_id`（`sys_config` 另补 `name` / `status`），标识列 DB 名改 `code` 并登记「列名 ↔ ORM 属性 / 契约字段名」映射；明细表 16 补 `parent_id`。另**补建 `sys_icon.md`**（planned 字典表，随系统字段对齐补表文件 + 总览登记）。

**ORM 模型（11 个文件）**：`catalog.py` / `menu.py` / `role.py` / `user.py` / `system.py`（platform）、`tenant.py` / `tenant_database.py`（tenant）、`identity_provider.py` / `client.py`（identity）、`ledger.py`（txn）、`config/models.py`（bms_core）。

**关键实现口径**（与设计一致）：

- **标识列只改 DB 列名**：`mapped_column("code", String(...), ...)` 映射，ORM 属性与 API 契约字段名不动（`module_key` / `product_key` / `username` / `config_key` / `idp_key` / `client_id`）；
- **`form_key` 为每表常量**：模型 `default="<标识>"`、迁移 `server_default='<标识>'`（加列即回填存量行）；**核心用途＝多表联合取数判别列**；
- **唯一约束按 DB 列名解析**：`UniqueConstraint("code", "deleted_at", ...)`（列改名后原 `..._key_deleted_at` 更名 `..._code_deleted_at`）；
- **迁移四库兼容**：`batch_alter_table`（SQLite 重建表）；改名与约束变更**分块**执行（先改名、再删建约束）。

**基座校验**（设计交付边界第 10 项）：`check-system-fields.py`（清单 ↔ 表文件双向一致 + 跨表全局唯一 + 字典表文件含 `form_key` / `parent_id` 行；含 `--self-test` 反例）并入 `preflight --fast` 与 CI `base-integrity`；`ops/check_tables.py` 增「`FORM_CATALOG` ↔ 模型 `form_key` 列双向一致」断言。

## 3. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 标识列**是否连 ORM 属性 / 契约字段名一起改**（Python 引用 `client_id` 561 / `username` 881 / `idp_key` 266 / `product_key` 230 / `module_key` 134 / `config_key` 73 处，且含 OAuth 协议同名参数，盲目替换有误伤风险） | 逐项确认后定为**只改 DB 列名**（属性 / 契约名保持，`mapped_column("code", ...)` 映射），代码零波及 |
| 2 | `UniqueConstraint("module_key", ...)` 报 `ConstraintColumnNotFoundError`（约束按 DB 列名解析，列已改名 `code`） | 6 处唯一约束的第二列改写为 `"code"` |
| 3 | 边界校验 `check-service-boundaries` 报 `form_key` 清单模块「跨服务库访问」（libs 内字符串表名 token） | 该模块与 `services/table_registry.py` 同性质（按定义登记全部表名）→ 加引用扫描豁免（`_FORM_CATALOG_REGISTRY_RELATIVE`） |
| 4 | `sys_icon`（planned 字典表）无表文件，`check-system-fields` 报「清单表缺表文件」 | 补建 `sys_icon.md`（状态 `已设计`）并在总览「已设计数据表登记」登记 |
| 5 | `sys_icon.md` 相关节点链接指向未建表文件 `sys_icon_i18n.md` → 断链 | 改纯文本（表文件待补） |

## 4. 验证 <a id="verify"></a>

- `uv run pytest libs/bms_core/tests/registry/test_form_catalog.py libs/bms_core/tests/alembic/test_alembic_drift.py`：**17 passed**（含逐链迁移 ↔ 模型零漂移 8 链）。
- `uv run python -m ops.check_tables --offline`：通过（清单 53 项 + 模型表对账 + 脚本表集 + `form_key` 一致）。
- `uv run ruff check`（改动范围）：All checks passed；`uv run ruff format` 已应用。
- `uv run pyright`（改动范围）：0 errors, 0 warnings。
- `python3 scripts/tools/preflight/check-preflight.py --fast`：**全部通过**。
- 文档门禁：`check-base`（表文件 42 / 方言 3，登记一致）、`check-docs-scope`（0 违规）、`check-links`（本任务新增文档零断链）、`check-status --stage 01_项目骨架`（0 不合规）。

## 5. 覆盖率 <a id="coverage"></a>

- 新增模块 `bms_core/registry/forms.py` 用例覆盖：`FormRegistry.validate` 正常 / 重复 / 格式非法、`merge_form_records` 注入、按标识 / 表名查询（Kiwi 2286）。
- 迁移 ↔ 模型零漂移由既有 `test_alembic_drift` 逐链断言覆盖（含本任务 5 条新迁移）。

## 6. 偏差与遗留 <a id="open"></a>

- **产品仓同步（本任务范围外）**：`mdm`（`org_dept` / `org_post` / `org_role_dept` / `org_role_post` / `org_user_dept` / `org_user_post` 表文件）、`biz` / `cw`（暂无表文件）按本口径对齐——**另立产品仓任务**（工作区模型下各仓独立提交），本任务仅 bms 仓。
- **三库真库实测**：迁移在 SQLite（零漂移测试）与本地开发库实测通过；MySQL / PostgreSQL / 达梦 真库执行**待验**，随部署窗口回写方言特性文档。
- **`form_key` 常量列语义**：DB 层 `(form_key, deleted_at)` 复合唯一对同表多行无实际约束力（`form_key` 为每表常量，联合取数判别列即其用途）；跨表全局唯一由 `FormRegistry` 承担（设计 §12 已登记）。
- **`02_10` 待回填**：`FormRecord.data_source_key` 暂空，由任务 `02_10`（统一数据源注册）回填，供任务 `02_13` 解析 `form_key → data_source_key`。

> 本文档依《文档生成规范》编写

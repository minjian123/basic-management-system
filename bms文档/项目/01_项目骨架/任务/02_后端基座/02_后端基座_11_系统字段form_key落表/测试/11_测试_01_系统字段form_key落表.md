# 11 测试记录 · 系统字段 `form_key` 落表（表文件 / 模型 / 迁移）

> 项目骨架 · 02 后端基座 · 子任务 11 · 测试记录 01

[文档首页](../../../../../../文档首页.md) › [02 后端基座](../../02_后端基座.md) › [11 系统字段 form_key 落表](../02_后端基座_11_系统字段form_key落表.md) › 测试　|　[← 实施记录](../实施/11_实施_01_系统字段form_key落表.md)

## 1. 信息 <a id="info"></a>

- 任务：`02_11` 系统字段 `form_key` 落表；实施记录见[11_实施_01_系统字段form_key落表](../实施/11_实施_01_系统字段form_key落表.md)。
- 测试对象：`form_key` 构建期清单（`bms_core/registry/forms.py`）、5 条分链迁移、基座校验脚本。
- Kiwi 用例：**2286**（02 11 系统字段 form_key 落表）。
- 执行范围：**只跑受变更影响部分**（清单用例 + 逐链迁移零漂移 + 基座 / 边界门禁）；全量交 CI 按需触发。

## 2. 用例与结果 <a id="cases"></a>

| 用例 | 覆盖 | 结果 |
| --- | --- | --- |
| `libs/bms_core/tests/registry/test_form_catalog.py`（Kiwi 2286） | 清单自校验通过；`form_key` 跨表全局唯一 / 表名唯一；类型合法与按标识 / 表名查询；注入合并；反例（重复与格式非法） | 通过 |
| `libs/bms_core/tests/alembic/test_alembic_drift.py`（Kiwi 1078 / 2219） | 8 条有脚本链迁移后库结构 ↔ 链模型元数据零漂移（含本次 5 条新迁移：表 / 列 / 索引 / 唯一约束） | 通过（8 passed） |
| `ops.check_tables --offline` | 表归属清单自校验 + 模型表对账 + 脚本表集 + **`FORM_CATALOG` ↔ 模型 `form_key` 列双向一致** | 通过 |
| `check_system_fields.py`（+ `--self-test`） | 清单 ↔ 表文件双向一致、跨表唯一、字典表文件含 `form_key` / `parent_id` 行 | 通过（自检 4 用例） |

## 3. 门禁 <a id="gates"></a>

- `pytest`（定向）：17 passed。
- `ruff check` / `ruff format`：通过。
- `pyright`（改动范围）：0 errors。
- `preflight --fast`：**全部通过**（含 `check_base` / `check_backend_base` / `check_service_boundaries` / `check_system_fields` / `check_docs_scope` / 契约与 `api-types` 零漂移）。
- `check_links`：本任务新增 / 修改文档零断链（仓库既有 9 处历史断链与本次无关）。
- `check_status --stage 01_项目骨架`：0 硬规则不合规。

## 4. 原型对照结论 <a id="prototype"></a>

**不适用**：本任务为纯数据底座改动（表文件 / ORM 模型 / Alembic 迁移 / 基座校验脚本与构建期清单），不涉及任何界面源码（`frontend/**`、`*.vue`、`ui-ep`），无原型可比对；界面相关交付归任务 `02_13`（前端通用页面路由）。

## 5. 偏差与遗留 <a id="open"></a>

- **三库真库实测待验**：迁移在 SQLite 零漂移测试与开发库实测通过；MySQL / PostgreSQL / 达梦 真库执行随部署窗口回写方言特性文档。
- **产品仓同步**：mdm / biz / cw 表文件与模型按本口径对齐归产品仓独立任务（本任务范围外）。
- 其余同[实施记录](../实施/11_实施_01_系统字段form_key落表.md)「偏差与遗留」节。

> 本文档依《文档生成规范》编写

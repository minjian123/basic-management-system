# sys_business（业务码）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_business

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 08-菜单管理（业务码字典维护） |
| 上游依据 | 《[概要设计 · 菜单管理](../../概要设计/07_概要设计_菜单管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」「业务码 / 动作码 / 权限码清单」节、《[需求 07-5 菜单/表单/按钮/字段挂接与动态菜单接口](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》 |
| ORM 模型 | `bms_platform/models/menu.py::SysBusiness`（继承 `BaseModel`） |
| 状态 | 已落库（表文件与平台链迁移 `0007_menu_metadata` 就绪；真库随部署窗口） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_business_i18n](sys_business_i18n.md)、[sys_action](sys_action.md)、[sys_permission](sys_permission.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 业务码（小写单词，如 `user`、`role`、`menu`） |
| `name` | VARCHAR(128) | 否 | — | 名称（**按优先级兜底派生的快照**：系统默认语言 → 必填语言 → 首个有值语言；写侧只提交「locale → 文案」映射，多语言见 `sys_business_i18n`） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled`（停用代替删除） · **系统字段**：状态（通用可选） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | BIGINT | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_business_code_deleted_at` | 唯一 | `(code, deleted_at)` | 业务码唯一（软删除后可复用） |

- 无物理外键；业务码为跨库引用锚点（租户库经 code 逻辑外键引用），同平台库内被 `sys_form.business_id`、`sys_permission.business_id` 引用。
- **三词分治（2026-10-10）**：业务码为**纯资源维度**（权限码左半），不再同时承担「业务级权限」；业务级校验由入口授权独立判定、接口/数据访问走权限码。
- 业务码一经发布稳定不变（错误码 / 接口契约耦合）；**停用代替删除**。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（权限元数据）。
- **迁移**：随**平台链** Alembic 迁移落地（`alembic/versions/platform/platform/0007_menu_metadata.py`，建表 + 唯一约束）；命令 `alembic -n alembic:platform:platform upgrade head`；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库；随平台链 `0007_menu_metadata` 迁移落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

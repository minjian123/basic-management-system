# sys_button（表单按钮）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_button

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属部署单元 `platform`） |
| 覆盖模块 | 08-菜单管理（按钮 → 权限码 挂接链） |
| 上游依据 | 《[概要设计 · 菜单管理](../../概要设计/07_概要设计_菜单管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」节、《[需求 07-5](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》 |
| ORM 模型 | `bms_core/models/platform/menu.py::SysButton`（继承 `BaseModel`；基座共享模型，14_01 下沉） |
| 状态 | 已落库（表文件与平台链迁移 `0007_menu_metadata` 就绪；真库随部署窗口） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_form](sys_form.md)、[sys_permission](sys_permission.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_id` | BIGINT | 否 | `(form_id, permission_id, deleted_at)` 复合唯一；建索引 | 所属表单 ID（逻辑外键 → `sys_form.id`） · **系统字段**：主表 ID（明细归属） |
| `permission_id` | BIGINT | 否 | 同上；建索引 | 挂接权限码 ID（逻辑外键 → `sys_permission.id`，**1:1**） |
| `name` | VARCHAR(128) | 否 | — | 按钮名（界面可见文本；不入 i18n 附表） |
| `type` | VARCHAR(16) | 否 | 默认 `toolbar` | 按钮形态：`toolbar`（工具栏）/ `interface`（表单界面内） |
| `sort` | INT | 否 | 默认 `0` | 同表内排序（升序） · **系统字段**：行序（明细排序） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` · **系统字段**：状态（通用可选） |
| `parent_id` | BIGINT | 是 | — | 上级明细 ID（自引用同表 `id`；本表无层级，按明细系统字段口径保留） · **系统字段**：上级明细 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | BIGINT | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_button_form_permission_deleted_at` | 唯一 | `(form_id, permission_id, deleted_at)` | 同表单同权限码唯一定义（软删除后可复用） |
| `idx_sys_button_form_id` | 普通 | `form_id` | 按表单列示按钮 |
| `idx_sys_button_permission_id` | 普通 | `permission_id` | 按权限码反查按钮 |

- 无物理外键；`form_id` / `permission_id` 为逻辑外键，同库。
- **默认无任何按钮权限**：按钮不授予即不显隐（前端按权限码 `{业务码}:{动作码}` 过滤）。
- **三词分治（2026-10-10）**：按钮挂接对象由动作码改为**权限码**（`permission_id`）；权限码业务须与按钮所属表单业务一致（服务层校验）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（权限元数据）。
- **建表**：随 **`platform:platform` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库；随平台链 `0007_menu_metadata` 迁移落地） | minjian |
| 2026-10-10 | v2 | 三词分治：挂接对象 `action_id` → `permission_id`（唯一键与索引同步改） | minjian |
| 2026-10-11 | v3 | 系统字段对齐（02_11）：增 `parent_id`（上级明细 ID）；随 `platform:platform` 链 `0010_system_fields_form_key` | minjian |
| 2026-10-22 | v4 | ORM 模型落点迁基座共享 `bms_core/models/platform/menu.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套


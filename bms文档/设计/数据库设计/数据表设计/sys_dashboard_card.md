# sys_dashboard_card（工作台卡片注册表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_dashboard_card

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`，业务域 `dashboard`） |
| 覆盖模块 | 36-首页工作台（卡片注册表：内置功能卡 / 数据集图表卡） |
| 上游依据 | 《[概要设计 · 首页工作台](../../概要设计/35_概要设计_首页工作台.md)》§4、《[架构设计 · 首页工作台](../../架构设计/29_架构设计_子系统_首页工作台.md)》§3 / §6、《[需求 08-1](../../../项目/08_通用能力/需求/08_需求_工作台与表单定制.md#r08-1)》 |
| ORM 模型 | `bms_core/models/platform/dashboard.py::SysDashboardCard`（继承 `BaseModel`；基座共享模型） |
| 状态 | 待落库（本任务 11_01 建表） |
| 相关节点 | [36-首页工作台](../36_数据库设计_首页工作台.md) 节点、[sys_dashboard_card_i18n](sys_dashboard_card_i18n.md)、[sys_dashboard_template](sys_dashboard_template.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一；建索引 | 卡片标识（业务键，`^[a-z][a-z0-9_]{1,63}$`）；布局与模板只引用本列 |
| `name` | VARCHAR(128) | 否 | — | 卡片名默认文案（派生快照：系统默认语言 → 首个有值语言；多语言见附表） |
| `card_type` | VARCHAR(16) | 否 | 默认 `builtin` | 卡片类型：`builtin`（内置功能卡，租户只可停用）/ `dataset`（数据集图表卡，租户自建） |
| `render_key` | VARCHAR(64) | 否 | 默认空串 | 前端渲染器标识（builtin 卡必填，如 `todo` / `notice` / `stats`；dataset 卡为空） |
| `dataset_id` | VARCHAR(64) | 是 | — | 数据集标识（逻辑外键 → 报表中心数据集，跨服务；仅 dataset 卡） |
| `chart_type` | VARCHAR(32) | 是 | — | 图表类型（`line` / `bar` / `pie` 等，取后端 `CHART_TYPES` 白名单；仅 dataset 卡） |
| `chart_config` | TEXT | 是 | — | 可选图表样式覆盖 JSON 文本（图例 / 坐标轴 / 色板序号等）；非法配置读取时忽略并回退默认 |
| `data_endpoint` | VARCHAR(256) | 否 | 默认空串 | 卡片数据接口地址（空表示前端按渲染器自身逻辑取数或占位） |
| `default_width` | INT | 否 | 默认 4 | 默认网格宽（列，2~12） |
| `default_height` | INT | 否 | 默认 2 | 默认网格高（行，2~6） |
| `mobile_supported` | BOOLEAN | 否 | 默认 true | 是否参与移动端单列布局 |
| `sort` | INT | 否 | 默认 0 | 可选卡片清单与最小布局的排序（升序；种子按 10 递增） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled`（停用后解析期从所有布局剔除） · **系统字段**：状态（通用可选） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | DECIMAL(38,0) | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | DECIMAL(38,0) | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_dashboard_card_code_deleted_at` | 唯一 | `(code, deleted_at)` | 卡片标识唯一；软删除后可复用同码 |
| `idx_sys_dashboard_card_code` | 普通 | `code` | 解析与按码取卡 |

- 无物理外键；`dataset_id` 为跨服务逻辑外键（报表中心数据集），只做形态校验与端口判定，不建约束。
- `code` 是**业务键**：接口路径（`/dashboard/cards/{code}`）与 `layout_config` 内引用均用它，避免雪花 ID 漂移。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（租户库配置表）。
- **归档**：不归档（配置元数据；变更留痕走字段级审计）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；历史迁移脚本已清空，结构以模型为唯一事实源）；启动期自动建表、运维 / CI 经 `ops.init_schema`。
- **种子**：内置卡由 `bms_core.tenant.seed.dashboard` 幂等写入（`code` 存在即跳过，保留租户改过的 `status` 与名称）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-18 | v1 | 新建表结构（任务 11_01）：卡片注册表；补 `chart_config` / `data_endpoint` / `mobile_supported`（相对概要 35 §4 的增量） | minjian |

> 数据表设计 · 与《[数据库开发规范](../../../规范/数据库开发规范.md)》「数据表文件规范」节配套

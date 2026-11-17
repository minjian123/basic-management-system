# sys_help_category（帮助分类）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_help_category

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `help`（帮助中心） |
| 覆盖模块 | 17-帮助中心（分类树 / 装载按路径 upsert） |
| 上游依据 | [需求 09-2](../../../项目/08_通用能力/需求/09_需求_帮助中心.md#r09-2)、《[概要设计 · 帮助中心](../../概要设计/17_概要设计_帮助中心.md)》§4、《[帮助包规范](../../../规范/帮助包规范.md)》§4 |
| ORM 模型 | `bms_core.models.platform.help.py::SysHelpCategory`（继承 `BaseModel`） |
| 状态 | 已设计（随 08_03 进 platform 服务租户链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [sys_help_article](sys_help_article.md)（文章分类归属）、[17-帮助中心](../17_数据库设计_帮助中心.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 分类标识 |
| `parent_id` | DECIMAL(38,0) | 否 | 默认 0 | 上级分类 ID（逻辑外键 → `sys_help_category.id`；0 = 根） |
| `name` | VARCHAR(128) | 否 | — | 分类名（默认语言；帮助分类不设多语言附表） |
| `sort` | INT | 否 | 默认 0 | 同级排序（升序） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` 启用 / `disabled` 停用 |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

- **根节点**：`parent_id = 0` 表示根，不用 `NULL`——规避达梦「复合唯一中 NULL 视同相等」的已知方言差异，同时让 `(parent_id, name, deleted_at)` 唯一约束在四库同语义生效。
- **路径**：分类树不存路径列；包装载按「父级 → 子级」逐级以 `(parent_id, name)` 定位，读取侧按 `parent_id` 递归拼路径。
- **弱归属**：删除分类前须先迁移或级联下架其下文章（12_01 维护入口校验）；包装载只 upsert 分类，不改其下已有文章。
- **软删除**：删除写 `deleted_at`；列表 / 树 / 文章归属全部过滤。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_help_category_parent_name_deleted_at` | 唯一 | `(parent_id, name, deleted_at)` | 同父级下分类名唯一（软删除后释放） |
| `idx_sys_help_category_parent_sort` | 普通 | `(parent_id, sort)` | 分类树按父级与排序读取 |

- 公共 `deleted_at` 索引由元数据命名约定生成（`idx_sys_help_category_deleted_at`），不在本表重复列；业务索引 2 个 + 公共 1 个 = 3 个（≤5）。
- 无物理外键；`parent_id` 为自引用逻辑外键（同库）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一租户一库；分类量级小）。
- **归档**：不归档（分类为结构数据，随文章长期使用）。
- **建表**：进入 platform 服务**租户链**（`help:tenant`），由启动期建表 / `ops.init_schema` 幂等建表（表归属 `status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-17 | v1 | 新建（08_03 产品帮助包装载注册）：帮助分类树，根 `parent_id=0`、按路径 upsert | minjian |

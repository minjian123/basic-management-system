# 04 Alembic 迁移与排序 DB 侧

> 后端基座与服务化地基 · 01_后端基座真实实现 · 子任务 04

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 04 |
| 父任务 | [01_后端基座真实实现](../01_后端基座真实实现.md) |
| 对应需求 | [01-4](../../../需求/01_需求_后端基座真实实现.md#r01-4) |
| 工时（重估） | 10h |
| 依赖 | 01_01 |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-09-22 |

## 2. 任务内容 <a id="content"></a>

1. alembic/env.py 在线分支实现与按数据源分链的方言无关迁移（平台链 / 租户链 / 归档链；一套脚本三库执行）
2. ops 批量迁移（create / migrate / drop）幂等
3. 排序契约 DB 侧（白名单拼接 / 四库 NULLS 恒末位 / 排序字段索引配合 / 分页限深 / keyset 游标键）
4. 迁移演练：建库 → 迁移 → 校验 → 清理

## 3. 完成标准 <a id="accept"></a>

三库在线迁移执行通过；ops 批量迁移幂等；排序 DB 侧用例通过；pytest / ruff / pyright 全绿。

## 4. 参考文档 <a id="ref"></a>

- 《架构设计 · 数据架构》「迁移策略」节；《架构设计 · 数据访问与分片》「查询规范」节

> **前置契约（已交付）**：01_02 多租户数据拓扑（2026-09-22）已交付 `ops/seed_tenant.py`（幂等建 `sys_tenant` 表 + demo/acme 种子；**Alembic 迁移就位后退化为纯种子脚本，建表分支兼容保留**）、租户库键助手（`build_tenant_db_key` / `parse_tenant_db_key`）与租户库 `url_template` 解析。本任务落 Alembic 迁移 / SQLite 全量自动建表 / `ops` 批量迁移时**直接复用**键助手与配置口径（平台库迁移纳入 `sys_tenant`；租户库目标地址按库键派生）。
>
> **前置契约（已交付）**：01_03 BaseRepository 异步与 BaseModel 落库（2026-09-22）已交付 `BaseDbRepository` 真实 CRUD 与**基础 `_apply_sort`**（白名单字段 → ORDER BY、默认 `id` 升序、未知字段忽略）、`list_page` LIMIT/OFFSET 与 `list_cursor` 偏移口径、`sys_module` 表与平台域种子（`ops/seed_module.py` 幂等建表 + 四行，迁移就位后退化为纯种子）、索引命名 `idx_{表}_{列}`（`Base.metadata` 命名约定）与统一会话入口 `session_scope`。本任务落排序 DB 侧细化（四库 NULLS / 限深 / 游标键）与迁移编排时**直接复用**上述实现：排序细化改 `BaseDbRepository._apply_sort` 与分页入口，平台库迁移纳入 `sys_module` / `sys_tenant`，**不需改 01_03 的 CRUD / 作用域翻译与写入口径**。

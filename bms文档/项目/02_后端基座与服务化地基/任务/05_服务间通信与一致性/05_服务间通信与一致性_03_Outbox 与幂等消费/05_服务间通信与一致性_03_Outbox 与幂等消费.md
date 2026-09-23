# 03 Outbox 与幂等消费

> 后端基座与服务化地基 · 05_服务间通信与一致性 · 子任务 03

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 03 |
| 父任务 | [05_服务间通信与一致性](../05_服务间通信与一致性.md) |
| 对应需求 | [05-3](../../../需求/05_需求_服务间通信与一致性.md#r05-3) |
| 工时（重估） | 14h |
| 依赖 | 05_02、01_01 |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-09-23 |

## 2. 任务内容 <a id="content"></a>

1. sys_outbox 表与投递器（同库同事务写事件、轮询转发并标记）
2. 消费幂等（consumer + event_id 唯一，与副作用同事务）
3. 顺序投递与重放、死信看板
4. 业务幂等键（Redis SETNX + 唯一约束兜底）

## 3. 完成标准 <a id="accept"></a>

库↔事件原子用例通过（回滚不发事件）；投递器转发与标记正确；消费幂等去重与重放安全；pytest / ruff / pyright 全绿。

## 4. 参考文档 <a id="ref"></a>

- 《架构设计 · 事件总线》「生产一致性」「幂等与重试」节

> **前置契约（已交付 · 05_02，2026-09-23）**：数据所有权边界基座已就位——构建期硬校验 `check-service-boundaries.py` 规则 6/7（按服务目录表前缀归属拦「跨服务表声明 / 引用」，读侧例外白名单 `deploy/boundaries/data_ownership_exceptions.json`）；运行时守卫能力域 `bms_core/boundary/`（`BaseDataOwnershipGuard` / `TableOwnershipGuard`，插件键 `data_ownership_guard`，模式 `off`/`warn`/`enforce`，越界抛 `DataOwnershipError` 10008）；`sys_` 平台域共享前缀内建放行。本任务的 `sys_outbox` 表归属与消费幂等落库须符合该归属口径（`sys_` 共享前缀），越界由上述硬校验拦截。


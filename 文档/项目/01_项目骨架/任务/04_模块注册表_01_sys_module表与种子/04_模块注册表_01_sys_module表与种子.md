# 01 sys_module 表与种子

> 项目骨架 · 04 模块注册表 · 子任务 01

[文档首页](../../../../文档首页.md) › [04 模块注册表](../04_模块注册表.md) › 01 sys_module 表与种子　|　[← 父任务](../04_模块注册表.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01 |
| 父任务 | [04 模块注册表](../04_模块注册表.md) |
| 对应需求 | [04-1](../../需求/04_需求_模块注册表.md#r04-1) |
| 工时（重估） | 3h |
| 依赖 | 03_01（拓扑）、03_03（平台库迁移流水线） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. `sys_module` 表（平台库）：module_key VARCHAR(32)（(module_key, deleted_at) 复合唯一）、name VARCHAR(64)、table_prefix VARCHAR(16)（{简称}_ 形如 pur_）、errcode_segment SMALLINT（两位段号 10 起，平台域 0 占位）、event_domain VARCHAR(32)（小写，默认与 module_key 一致）、status SMALLINT（1 启用 / 0 规划中）+ 基类字段；三要素 (字段, deleted_at) 复合唯一索引
2. i18n 附表 `sys_module_i18n`（module_id + locale 联合主键 + name），中文名存主表、英文名入附表（en-US）
3. 初始种子：平台域 sys/wf/rpt/ai（启用）；业务规划态 purchase(pur_,10)/payment(pay_,11)/supplier(sup_,12)/sale(sale_,13)/warehouse(wh_,14)（status=0）——与《项目规划说明》23.4/23.5 逐行一致
4. 注册方式：运行时无写接口；新增模块 = Alembic 迁移 revision（建表 + 注册种子）原子落地、平台库单库执行；业务码与模块简称一致（sys_business 阶段三）

## 3. 完成标准 <a id="accept"></a>

与 sys_tenant 同迁移流水线落表（三库迁移通过）；种子查询返回 4 平台域 + 5 业务规划态共 9 行，prefix/段号/事件域与 23.4/23.5 逐行一致；sys_module_i18n 英文名可查；无任何写接口暴露。

## 4. 参考文档 <a id="ref"></a>

- 《架构设计 · 模块注册》第 2/3 节
- 《项目规划说明》23.3~23.5
- 《命名规范》第 7 节

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23

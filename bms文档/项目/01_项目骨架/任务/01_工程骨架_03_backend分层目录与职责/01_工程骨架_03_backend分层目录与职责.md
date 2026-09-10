# 03 backend 分层目录与职责

> 项目骨架 · 01 工程骨架 · 子任务 03

[文档首页](../../../../文档首页.md) › [01 工程骨架](../01_工程骨架.md) › 03 backend 分层目录与职责　|　[← 父任务](../01_工程骨架.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 03 |
| 父任务 | [01 工程骨架](../01_工程骨架.md) |
| 对应需求 | [01-3](../../需求/01_需求_工程骨架.md#r01-3) |
| 工时（重估） | 3h |
| 依赖 | 02（backend 工程就位） |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. `app/` 分层目录与首版文件：core（config/security/exceptions）、api（deps/router/health + 模块目录）、models（base）、schemas（common）、services、repositories、db（engine/session）、tasks/ws/i18n 占位；alembic/、tests/ 与 app 同构
2. 分层调用规则写入各层 `__init__.py` docstring：api 只做参数校验与路由分发、禁止操作模型；services 承载业务与事务边界、禁止拼 SQL；repositories 承载数据访问与路由、禁止业务规则；models/schemas 禁止业务逻辑
3. 路由注册约定：模块内 `APIRouter(prefix="/{资源}", tags=["{模块}"])`，`app/api/router.py` 统一 include；模块四件套缺一不可

## 3. 完成标准 <a id="accept"></a>

目录树与需求清单逐项一致；各层 docstring 写明职责与禁止项；示例模块 `demo`（占位 CRUD 空壳）按四件套 + 路由注册走通。

## 4. 参考文档 <a id="ref"></a>

- [03_详细设计_01_backend分层目录与职责](设计/03_详细设计_01_backend分层目录与职责.md)（本任务详细设计，已定稿）
- 《项目规划说明》第 4 节
- 《[架构设计 · 总体架构](../../../../设计/架构设计/03_架构设计_总体架构.md)》§5 monorepo 布局、§6 技术栈
- 《后端开发规范》第 2/4 节
- 《命名规范》第 3/6 节

> 本文档依《文档生成规范》编写

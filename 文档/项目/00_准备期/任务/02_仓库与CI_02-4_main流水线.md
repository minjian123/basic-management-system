# 02-4 main 流水线

> 准备期 · 02 仓库与CI · 子任务 02-4

[文档首页](../../../文档首页.md) › [02 仓库与CI](02_仓库与CI.md) › 02-4 main 流水线　|　[← 父任务](02_仓库与CI.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 02-4 |
| 父任务 | [02 仓库与CI](02_仓库与CI.md) |
| 对应需求 | [02-4](../需求/02_需求_仓库与CI.md#r02-4) |
| 禅道任务 | 待建（父任务 2） |
| 工时（重估） | 11h |
| 依赖 | 02-3、阶段一骨架 |
| 负责人 | minjian |
| 状态 | 未开始 |
| 完成日期 | — |

## 2. 任务内容 <a id="content"></a>

1. Playwright E2E（服务容器起后端（SQLite）与前端产物）
2. MySQL/PostgreSQL/达梦 DM8 三库方言集成测试：job 连 mjbk 常驻三库，建 `bms_test` 前缀测试库 → Alembic 迁移 → 集成测试 → 删库清理
3. 构建 `bms-backend`、`bms-frontend` 镜像并推 GitLab Registry（5050）
4. `swagger.json` 契约快照导出归档
5. 测试报告：Allure 报告归档（CI artifact），测试结果经官方插件导入 Kiwi TCMS 用例库

## 3. 完成标准 <a id="accept"></a>

main 流水线端到端通过；契约快照与 Allure 报告已归档。

## 4. 参考文档 <a id="ref"></a>

- 《开发部署规划》第 7 节、《测试规范》

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-21

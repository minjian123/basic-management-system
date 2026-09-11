# 04-2 前端公共组合式与工具基座

> 项目骨架 · 01 工程骨架 · 04 frontend 工程初始化 · 嵌套子任务 02

[文档首页](../../../../../../文档首页.md) › [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) › 02 前端公共组合式与工具基座　|　[← 父任务](../01_工程骨架_04_frontend工程初始化.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-4-2 |
| 父任务 | [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) |
| 对应需求 | [01-4](../../../../需求/01_需求_工程骨架.md#r01-4) |
| 工时（重估） | 6h |
| 依赖 | 04（frontend / frontend-mobile 工程初始化）、01-4-1（契约类型/BaseApi/createCrudStore） |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-09-10 |

## 2. 任务内容 <a id="content"></a>

1. `useRequest`（`src/utils/useRequest.ts`）：通用异步状态 `data/loading/error/run`，竞态保护（递增序号丢弃过期响应），可选 `onSuccess/onError`
2. `useListPage`（`src/utils/useListPage.ts`）：分页列表公共逻辑 `query/list/total/loading/error/search/reset/changePage`，基于 `useRequest` 与 `BasePageQuery` / `PageResponse`
3. `validators`（`src/utils/validators.ts`）：常用校验（手机号 / 邮箱 / 身份证 / URL / 密码强度）+ 规则工厂（required / pattern），框架无关（Element Plus / Vant 通用）
4. `useTabs`（`src/utils/useTabs.ts`）：模块级单例——`tabs/active`、`openTab/closeTab/activate`、白名单 `ALLOWED_PATHS`、`localStorage` 键 `bms_open_tabs` 持久化；`navigate` 回调留路由接入位（布局阶段）
5. `EntityStatus` 状态映射（`src/utils/status.ts`）：启用/停用常量 + `entityStatusI18nKey`；i18n 补 `common.enabled/disabled`
6. 测试基座 `tests/helpers/mount.ts`：`mountWithPlugins`（预挂 pinia / i18n，可选 router）；既有页面用例改用之
7. 双工程同款落地；Kiwi Case 23/24；实施 / 测试记录回写

## 3. 完成标准 <a id="accept"></a>

双端五类基座落地（useRequest / useListPage / validators / useTabs / EntityStatus）且 Vitest 全绿、覆盖率 100%；`npm run lint`、`vue-tsc -b`、`npm run build` 通过；测试统一走 `mountWithPlugins`；Kiwi Case 23/24 登记并关联；记录回写。

## 4. 参考文档 <a id="ref"></a>

- [02_详细设计_01_前端公共组合式与工具基座](设计/02_详细设计_01_前端公共组合式与工具基座.md)（本任务详细设计，已定稿）
- [01 实施记录](实施/02_实施_01_前端公共组合式与工具基座.md)（实做内容、问题与处置、验证与遗留）
- [01 测试记录](测试/02_测试_01_前端公共组合式与工具基座.md)（用例、执行结果、问题与覆盖率）
- [04-1 前端基础类](../01_工程骨架_04_frontend工程初始化_01_前端基础类/01_工程骨架_04_frontend工程初始化_01_前端基础类.md)（上游：契约类型与 BaseApi）
- [需求 01-4](../../../../需求/01_需求_工程骨架.md#r01-4)
- 《[前端开发规范](../../../../../../规范/前端开发规范.md)》第 5/7/11 节

> 本文档依《文档生成规范》编写

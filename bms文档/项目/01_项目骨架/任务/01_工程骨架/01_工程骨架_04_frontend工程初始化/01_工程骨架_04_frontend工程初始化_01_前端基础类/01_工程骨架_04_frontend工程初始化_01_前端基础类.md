# 04-1 前端基础类

> 项目骨架 · 01 工程骨架 · 04 frontend 工程初始化 · 嵌套子任务 01

[文档首页](../../../../../../文档首页.md) › [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) › 01 前端基础类　|　[← 父任务](../01_工程骨架_04_frontend工程初始化.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 01-4-1 |
| 父任务 | [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) |
| 对应需求 | [01-4](../../../../需求/01_需求_工程骨架.md#r01-4) |
| 工时（重估） | 6h |
| 依赖 | 04（frontend / frontend-mobile 工程初始化） |
| 负责人 | minjian |
| 状态 | 已完成 |
| 完成日期 | 2026-09-10 |

## 2. 任务内容 <a id="content"></a>

1. 契约公共类型（双工程 `src/api/types.ts`）：`BaseEntity`（`id` 为 **string**——雪花 BIGINT 超出 JS 安全整数，JSON 边界以字符串传输；`createdAt` / `updatedAt` 字符串时间）、`BasePageQuery`（page / size）
2. `BaseApi`（`src/api/base.ts`）：模块 API 类基类，统一封装 get / post / put / delete（拼 `basePath` + 复用 `request<T>()` 统一响应解析）
3. `createCrudStore`（`src/stores/base.ts`）：Pinia 通用 CRUD store 工厂（`list` / `total` / `loading` + `fetchList` / `fetchOne` / `create` / `update` / `remove`），以工厂实现「BaseStore」能力（Pinia 惯例为组合式函数，非类继承）
4. `stableStringify`（`src/utils/serialize.ts`）：稳定序列化——对象键排序、Set / Map 确定序、BigInt 转字符串、Date 转 ISO；用于对拍 / 存档 / 日志
5. 《前端开发规范》增补继承约定：契约类型基于公共类型、API 模块继承 `BaseApi`、列表 / 详情 store 用 `createCrudStore`、对外序列化用 `stableStringify`
6. 跨端 ID 口径登记：后端 02-3 出参 `str(id)` / 入参 `int(id)`（数据库 BIGINT 与 JOIN 不变）；03-2 字段口径注明 API 以字符串输出
7. 测试：双端各登记 Kiwi 用例（Case 21 / 22），Vitest 覆盖四类基础件

## 3. 完成标准 <a id="accept"></a>

双工程四类基础件落地（契约类型 / BaseApi / createCrudStore / stableStringify），Vitest 用例全绿；`npm run lint`、`vue-tsc -b`、`npm run build` 通过；《前端开发规范》含继承约定；ID 字符串口径登记进 02-3 / 03-2；Kiwi Case 21 / 22 登记并关联；实施 / 测试记录回写。

## 4. 参考文档 <a id="ref"></a>

- [01_详细设计_01_前端基础类](设计/01_详细设计_01_前端基础类.md)（本任务详细设计，已定稿）
- [01 实施记录](实施/01_实施_01_前端基础类.md)（实做内容、问题与处置、验证与遗留）
- [01 测试记录](测试/01_测试_01_前端基础类.md)（用例、执行结果、问题与覆盖率）
- [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md)（上游：工程初始化与 Axios 基线）
- [需求 01-4](../../../../需求/01_需求_工程骨架.md#r01-4)
- 《[前端开发规范](../../../../../../规范/前端开发规范.md)》
- 《[命名规范](../../../../../../规范/命名规范.md)》「前端命名」节

> 本文档依《文档生成规范》编写

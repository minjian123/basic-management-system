# 03 契约响应 schema 完整性与门禁

> 认证与安全 · 06 契约与模块请求能力 · 子任务 03（需求 06-4）

[文档首页](../../../../../文档首页.md) › [06 契约与模块请求能力](../06_契约与模块请求能力.md) › 03 契约响应 schema 完整性与门禁　|　[← 父任务](../06_契约与模块请求能力.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 03 |
| 父任务 | [06 契约与模块请求能力](../06_契约与模块请求能力.md) |
| 对应需求 | [06-4](../../../需求/06_需求_契约与模块请求能力.md#r06-4) |
| 依赖 | 阶段二 `03_01`（契约导出 / 生成 / 零漂移机制）；域六 `06_01`（契约快照、oasdiff 基线与路由覆盖护栏）；域一 `01_03`（认证端点响应模型） |
| 负责人 | minjian |

> **前置缺陷（实测，2026-10-02）**：公开契约快照中**全部响应体 schema 为空对象**——`ApiResponse` / 各 `ApiResponse_*` 包装 / `LoginResult` / `RefreshResult` / `UserSummary` / `ConfigResolveResponse` / `LoginStateResult` 等，9 个启用服务一致。根因：本基座 `BaseSchema._serialize_ids`（`@model_serializer(mode="wrap")` 返回 `Any`）使 **FastAPI 序列化模式**的 JSON Schema 塌陷为空；请求体走校验模式故字段完整。既有三道契约门禁（`contract_snapshot check` / `contract_gate` / `check_contracts` 路由覆盖）**均不校验 `components.schemas` 内容**，故缺口一直未被发现（06_01 未登记）。

> **前置契约（已交付 · 06_01，2026-10-02）**：`ops/contract_snapshot.py check`（快照 ↔ 公开契约零漂移）、`ops/contract_gate.py`（oasdiff 基线破坏性变更）、`ops/check_contracts.py`（实现路由 ⊆ 公开契约 `paths` + 不可见白名单）三道门禁已交付并接入 CI `swagger-snapshot` 与本地预检；本任务在其上**新增响应 schema 完整性断言**（同一命令、同一口径）。

> **前置契约（已交付 · 阶段二 `04-1-1`）**：`@bms/api-types` 生成机制（`openapi-typescript` 从 `deploy/contracts/*.json` 生成，`gen:check` 零漂移）与 `api-types-check` CI 门禁已交付；本任务按重生成后的类型交付，供域五 `05_02` 消费。

## 2. 任务内容 <a id="content"></a>

1. **基座序列化 schema 修复**：`BaseSchema` 在**序列化模式**生成 JSON Schema 时以字段口径输出（剥离模型序列化器）；**校验模式 schema 与运行时序列化行为保持不变**（ID 字符串化与敏感字段掩码照旧，既有用例回归全绿）。
2. **ID 字段输出口径对齐**：`id` / `*_id` 字段在序列化模式 schema 中标为字符串（与实际输出一致），判定规则与 `stringify_ids` **同源单点**（不重复实现判定）。
3. **快照与基线重生成**：9 个启用服务的 `deploy/contracts/*.json` 与 `deploy/contracts/baseline/*.json` 按新口径重生成；`contract_snapshot check` 与 `contract_gate` 全绿（无未登记破坏项）。
4. **前端类型重生成**：`@bms/api-types` 重新生成（`pnpm --filter @bms/api-types run gen`），响应类型不再为 `unknown`；`api-types:gen:check` 零漂移。
5. **响应契约门禁**：契约校验命令新增断言——`components.schemas` 不得存在空对象条目；每个操作的 2xx（含 `application/json`）响应 schema 必须可解析且非空（`$ref` 悬空即失败）；覆盖全部启用服务，CI 与本地预检同口径，fixture 用例锁定。
6. **用例**：序列化模式 schema 字段完整与 ID 字符串化口径；空 schema / 悬空 `$ref` 判失败；9 服务门禁全绿。

## 3. 完成标准 <a id="accept"></a>

9 个启用服务响应契约 schema 完整（无空 schema 条目，成功响应 schema 可解析且非空）；`@bms/api-types` 响应类型具字段可用且零漂移校验通过；契约门禁在响应 schema 为空 / `$ref` 悬空时失败（fixture 用例锁定）；`ruff`、`pyright`、定向 `pytest`、基座校验与 `preflight --fast` 全绿。

## 4. 参考文档 <a id="ref"></a>

- [需求 06-4](../../../需求/06_需求_契约与模块请求能力.md#r06-4)
- [需求 06-1 / 06-3](../../../需求/06_需求_契约与模块请求能力.md#r06-1)
- 《[后端开发规范](../../../../../规范/后端开发规范.md)》「契约与门禁」节
- 域六 [06_01 认证契约快照与前端类型生成](../06_契约与模块请求能力_01_认证契约快照与前端类型生成/06_契约与模块请求能力_01_认证契约快照与前端类型生成.md)（**契约机制与路由覆盖护栏已交付**）
- 《[后端基类清单](../../../../../后端基类清单.md)》「数据契约体系」节

> 交付物：详细设计、实施记录、测试记录（随任务开工建立，落本目录 `设计/`、`实施/`、`测试/`）。

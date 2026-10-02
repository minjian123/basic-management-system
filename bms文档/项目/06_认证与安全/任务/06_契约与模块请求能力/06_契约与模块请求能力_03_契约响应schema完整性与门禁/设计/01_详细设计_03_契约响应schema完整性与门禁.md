# 03 详细设计 · 契约响应 schema 完整性与门禁

> 认证与安全 · 06 契约与模块请求能力 · 子任务 03（需求 06-4）· 详细设计

[文档首页](../../../../../../文档首页.md) › [06 契约与模块请求能力](../../06_契约与模块请求能力.md) › [03 契约响应 schema 完整性与门禁](../06_契约与模块请求能力_03_契约响应schema完整性与门禁.md) › 详细设计　|　[需求 06-4](../../../../需求/06_需求_契约与模块请求能力.md#r06-4)

## 1. 设计目标与范围 <a id="goal"></a>

修复**基座响应契约 schema 塌陷**缺陷并补一层**契约内容完整性门禁**，使 `06_01` 的「前后端字段零漂移」承诺在**响应侧**真实成立：

- **修复（需求 06-4 第 1 / 2 条）**：`BaseSchema` 在**序列化模式**生成 JSON Schema 时以字段口径输出（剥离模型序列化器）；`id` / `*_id` 字段按实际输出口径标为字符串。**校验模式 schema 与运行时序列化行为保持不变**（ID 字符串化与敏感字段掩码照旧）。
- **重生成（需求 06-4 第 3 条）**：9 个启用服务的公开契约快照与 oasdiff 基线按新口径重生成；`@bms/api-types` 重新生成，响应类型不再为 `unknown`。
- **门禁（需求 06-4 第 4 条）**：在既有契约校验命令 `ops/check_contracts.py` 内新增响应 schema 完整性断言——`components.schemas` 不得存在空对象条目、每个操作的 2xx 响应 schema 必须可解析且非空；对**全部启用服务**生效，CI 与本地预检同口径。

**不在本任务**：模块请求能力 `api` 与模块契约版本升 2（需求 06-2，归子任务 [06_02](../../06_契约与模块请求能力_02_模块请求能力api与契约版本升2/06_契约与模块请求能力_02_模块请求能力api与契约版本升2.md)）；前端请求层与登录页消费生成类型（归[域五](../../../05_登录前端/05_登录前端.md) `05_02` 起）；契约导出 / 生成 / 零漂移机制与 oasdiff 门禁的既有实现（阶段二 `03_01` / `04-1-1`、`06_01` 已交付，**不重复建设**）；契约版本自动回写（既有开放项）。

**安全影响（SDL）**：契约是接口的**事实源**——响应契约 schema 为空会使前端类型退化为 `unknown`，而 `unknown` 在 TypeScript 下**绕过一切字段级类型检查**，字段漂移会推迟到运行期才暴露；本任务把该风险前移到构建期（接口治理面，非数据安全面）。

### 1.1 现状实测与缺口 <a id="gap"></a>

实测在开工前以当前工作区完成（命令见第 9 节）：

| # | 实测项 | 结论 |
| --- | --- | --- |
| 1 | `components.schemas` 空对象条目（9 服务） | **大量存在**：identity 56 个中 40 个为空、org 31 个中 21 个为空、platform 22 个中 3 个为空，其余服务各 1 个（`ApiResponse`） |
| 2 | 具体空条目 | `ApiResponse`、`ApiResponse_LoginResult_` / `ApiResponse_RefreshResult_` 等全部响应包装、`LoginResult`、`RefreshResult`、`UserSummary`、`ConfigResolveResponse`、`LoginStateResult` …… |
| 3 | 请求体 schema | **完整**（`LoginRequest` 具 `account` / `password` / `tenant` / `captcha`） |
| 4 | 根因定位（本机实测） | `LoginResult.model_json_schema(mode="validation")` **具完整 properties**；`mode="serialization"` 为 **`{}`**。`BaseSchema._serialize_ids` 为 `@model_serializer(mode="wrap")`，生成的核心 serialization schema 为 `{'type': 'function-wrap', 'return_schema': {'type': 'any'}}` —— 序列化模式 JSON Schema 取 `return_schema`，`any` 即塌陷为空对象 |
| 5 | 前端生成类型（`@bms/api-types`） | `identity.ts` 中 `LoginResult: unknown` / `RefreshResult: unknown` / `UserSummary: unknown` / 全部 `ApiResponse_*: unknown`（`packages/api-types/src/identity.ts`） |
| 6 | FastAPI 生成口径 | FastAPI 0.141.1 以 `mode="serialization"` 生成**响应**模型 schema、以 `mode="validation"` 生成**请求**模型 schema（`separate_input_output_schemas` 缺省 `True`）；请求体因此不受影响 |
| 7 | 既有三道门禁 | `contract_snapshot check`（快照零漂移）/ `contract_gate`（oasdiff 基线破坏）/ `check_contracts`（路由覆盖）**均不校验 `components.schemas` 内容**，故缺口「一致地」放行（`06_01` 未登记） |

| # | 缺口 | 事实 | 后果 |
| --- | --- | --- | --- |
| 1 | 序列化模式 JSON Schema 塌陷 | `BaseSchema` 的 wrap 模型序列化器返回标注为 `Any` | 全部响应体 schema 为空 → 前端响应类型 `unknown` |
| 2 | 无内容完整性门禁 | 三道门禁只覆盖「零漂移 / 破坏性 / 路由覆盖」 | 空 schema 是「一致地」缺失，任何门禁都不会失败；同类缺陷可再次引入 |
| 3 | `id` 输出口径未在契约表达 | 运行时 `stringify_ids` 把 `id` / `*_id` 整型值转字符串 | 即便补齐字段，若按校验模式照搬会把 `id` 标为 `integer`，与实收口径不符 |

## 2. 交付物清单 <a id="deliver"></a>

| # | 交付物 | 落点 | 类型 |
| --- | --- | --- | --- |
| 1 | ID 键判定公共函数（`id` / `*_id`，单点判定） | `backend/libs/bms_core/src/bms_core/core/serialization.py` | 修改 |
| 2 | 序列化模式 JSON Schema 以字段口径生成 + ID 属性类型对齐 | `backend/libs/bms_core/src/bms_core/schemas/base.py` | 修改 |
| 3 | 空 schema 与响应 schema 完整性纯判定 | `backend/libs/bms_core/src/bms_core/services/service_contract.py` | 修改 |
| 4 | 响应 schema 断言接入契约校验命令 | `backend/ops/check_contracts.py` | 修改 |
| 5 | 基座序列化 schema 用例（字段完整 / ID 字符串化 / 运行时行为不变） | `backend/libs/bms_core/tests/schemas/test_serialization_schema.py` | 新增 |
| 6 | 契约完整性判定用例（空条目 / 悬空 `$ref` / 正常契约） | `backend/libs/bms_core/tests/services/test_service_contract_schemas.py` | 新增 |
| 7 | 契约校验命令用例扩展（内容违规则失败） | `backend/libs/bms_core/tests/ops/test_check_contracts.py` | 修改 |
| 8 | 9 服务公开契约快照重生成 | `deploy/contracts/*.json` | 修改 |
| 9 | 9 服务 oasdiff 基线重生成 | `deploy/contracts/baseline/*.json` | 修改 |
| 10 | 前端契约类型重生成 | `frontend/packages/api-types/src/*.ts` | 修改 |
| 11 | 规范登记（响应契约完整性口径 + 门禁断言） | `bms文档/规范/后端开发规范.md` | 修改 |
| 12 | 清单登记（契约校验命令断言扩展） | `bms文档/后端基类清单.md` | 修改 |
| 13 | 需求 / 任务 / 父任务 / 计划回写 | 需求域 06、需求总览、任务 06_03、父任务 06、阶段计划 | 修改（**已完成**） |
| 14 | 实施 / 测试记录 | 本目录 `实施/`、`测试/` | 新增 |

> **CI / 预检零改动**：`ops/check_contracts.py` 已被 CI `swagger-snapshot`（`.gitlab-ci.yml:995`）与本地预检（`check-preflight.py:391`）调用，断言扩展后**自动同口径生效**，不改 CI 配置与预检脚本。

## 3. 设计与边界 <a id="design"></a>

### 3.1 基座序列化 schema 修复（需求 06-4 第 1 / 2 条） <a id="fix"></a>

**修复原则**：**只改 JSON Schema 的生成口径，不改运行时序列化**。`_serialize_ids`（`@model_serializer(mode="wrap")`）继续承担 ID 字符串化与敏感字段掩码；仅在其**序列化模式 JSON Schema** 生成时剥离该序列化器、回落到字段口径。

**落点**：`bms_core/schemas/base.py::BaseSchema` 新增类方法 `__get_pydantic_json_schema__`（pydantic 以 `getattr` 取该钩子，**子类继承生效**——已核实 pydantic 2.13 取法为 `getattr(tp, '__get_pydantic_json_schema__', None)`）。

```text
BaseSchema.__get_pydantic_json_schema__(cls, schema, handler) -> JsonSchemaValue
├── handler 无 mode 或 mode == "validation"  → handler(schema)                      # 原样（请求体口径不变）
└── mode == "serialization"                  → handler(schema 去掉 "serialization" 键)
                                               → 再按 ID 口径把 id / *_id 属性改为字符串
```

**ID 属性类型对齐**（与运行时 `stringify_ids` 同源）：`id` / `*_id` 属性若为 `{"type": "integer"}` → `{"type": "string"}`；若为 `anyOf: [integer, null]` → `anyOf: [string, null]`（递归同构改写 `anyOf` / `oneOf` 成员）。**只改本模型自身的 `properties`**——嵌套模型由其自身继承同一钩子处理（生成器逐类调用）。

**单点判定**：`core/serialization.py` 新增 `is_id_key(key: object) -> bool`（`key == "id"` 或以 `_id` 结尾），`_stringify_entry` 改调用之——**运行时与 schema 侧共用同一判定**，杜绝两处规则漂移。

**行为不变量**（回归断言）：

| 不变量 | 说明 |
| --- | --- |
| 校验模式 schema 不变 | 请求体契约与请求校验行为零变化 |
| 运行时序列化不变 | `model_dump()` / `model_dump_json()` 输出逐字节不变（ID 字符串化与掩码照旧） |
| 序列化模式 schema 由 `{}` 变具字段 | 修复目标 |
| 契约集合字段 schema 与内置容器逐字节一致 | `CONTRACT_COLLECTION` 既有门禁不变 |

### 3.2 契约内容完整性门禁（需求 06-4 第 4 条） <a id="guard"></a>

**判定口径**（对每个启用服务）：

| 断言 | 规则 | 违反即失败 |
| --- | --- | --- |
| C. 无空 schema 条目 | `components.schemas` 中不存在**空映射**条目（`{}`） | 列明细（服务 + 条目名） |
| D. 引用型响应 schema 完整 | 每个操作的 2xx（`2xx` 及 `2XX` 通配）`application/json` schema，**凡为 `$ref` 引用者**必须能解析到非空的 `components.schemas` 条目 | 列明细（服务 + 方法 + 路径 + 原因） |

> **断言 D 的口径收敛（2026-10-02 实施期拍板）**：初版把「内联空 schema」也判失败，实测触发 19 处——`/readyz`（9 服务）与 identity 的 `/oidc/jwks`、`/oidc/.well-known/openid-configuration`、`/oidc/authorize`、`/oidc/token`、`/oidc/userinfo`、`/auth/introspect`、`/auth/sso/{idp_key}/authorize`、`/callback`。根因是这些路由**直接返回 `Response` / `JSONResponse` / `RedirectResponse`**（不返回模型），OpenAPI 无从推导 schema——属**另一缺陷类**（「原始 `Response` 端点未声明响应契约」），与本次修复的「模型派生响应 schema 塌陷」不同。故 D 收敛为**只判引用型**（精确锁定本次缺陷类；模型派生响应必然经 `$ref` 引用 `components.schemas`），内联空 schema 不判定并登记遗留（见 §7）。

- 白名单 `EMPTY_SCHEMA_ALLOWLIST`：**初始为空集**；新增项须在设计 / 规范侧说明理由（与不可见路由白名单同纪律，**业务 schema 一律不得入白名单**）。
- **纯判定函数**（`bms_core/services/service_contract.py`，与 `route_coverage_gaps` 同处、纯函数可单测）：

```text
service_contract.py（新增）
├── EMPTY_SCHEMA_ALLOWLIST: ConcurrentStableSet[str]          # 空 schema 白名单（初始空）
├── empty_schema_entries(openapi) -> ConcurrentStableList[str]      # 断言 C 差异（升序）
└── response_schema_gaps(openapi) -> ConcurrentStableList[str]      # 断言 D 差异（升序）
```

- **命令接入**（`ops/check_contracts.py`）：`check_service` 追加 C / D 两组断言（打印前缀 `[契约 schema]`），`main` 汇总；**退出码语义不变**（通过 0 / 失败 1）。命令 docstring 与 `argparse` 描述同步更新为「路由覆盖 + 不可见白名单 + 响应 schema 完整性」。
- **失败分支**：`openapi()` 无 `components` / `paths` 段时按「无可判定内容」处理——**与既有「提取为空即判失败」同纪律**：`check_service` 已对「未提取到任何实现路由」判失败，内容断言在同一次构建上执行，构建失败即失败。

### 3.3 快照、基线与前端类型重生成（需求 06-4 第 3 条） <a id="regen"></a>

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 1 快照重生成 | `uv run python -m ops.contract_snapshot export` | 9 份 `deploy/contracts/*.json` 更新（响应 schema 具字段 + ID 字符串化） |
| 2 基线重生成 | `uv run python -m ops.contract_gate baseline-update --service <service>` | 9 份 `deploy/contracts/baseline/*.json` 同步（**评审节点**：把当前响应契约纳入已放行集合） |
| 3 前端类型重生成 | `pnpm --filter @bms/api-types run gen` | `packages/api-types/src/*.ts` 更新，响应类型具字段 |
| 4 零漂移校验 | `ops.contract_snapshot check` / `pnpm run api-types:gen:check` | 全绿 |

**变更性质判定**：本次变更**只向 `components.schemas` 的响应侧条目补字段信息**（请求侧 schema 走校验模式，逐字节不变），属**非破坏性新增**；契约版本保持 `0.1.0`（`info.version` / 服务包 `CONTRACT_VERSION` / 服务目录登记三处一致不改）。

**OAS 命名风险复核**：FastAPI 的 `separate_input_output_schemas` 会为「同时作输入与输出且两侧 schema 不同」的模型生成 `-Input` / `-Output` 后缀变体。实测当前 9 服务快照**无任何 `-Input` / `-Output` 条目**（无模型两侧同用）；重生成后须复核该结论不变（若出现后缀变体，则需在设计侧评估并回写）。

### 3.4 失败分支与边界 <a id="failures"></a>

| 场景 | 处理 |
| --- | --- |
| 基座修复后运行时序列化行为变化 | 由既有序列化 / 脱敏 / 契约集合用例 + 新增不变量用例回归拦截；不通过即回退方案 |
| 请求体 schema 被意外改动 | 校验模式走原路径（不改），由快照差异复核（仅响应侧变化） |
| 出现空 schema 条目 | 断言 C 失败，列「服务 + 条目名」，退出码 1 |
| 成功响应 `$ref` 悬空 / 引用目标为空 | 断言 D 失败，列「服务 + 方法 + 路径」，退出码 1 |
| 成功响应为**内联** schema（含空对象） | **不判定**（原始 `Response` 端点，属另一缺陷类）——登记遗留归口后续任务（见 §7），本门禁不对其设白名单 |
| 响应 schema 因业务合理原因确实为空（模型派生） | 走 `EMPTY_SCHEMA_ALLOWLIST` 申请，须在设计 / 规范侧说明理由 |
| FastAPI / pydantic 大版本升级后 `handler.mode` 取法变化 | 钩子以 `getattr` 容错读取；升级时复核（登记开放项） |
| `-Input` / `-Output` 后缀变体出现 | 复核契约差异并在设计侧评估（见 §3.3） |
| 基线重生成掩盖真实破坏性变更 | 基线更新前后以 oasdiff 复现比对，确认**仅新增**（无删除 / 改类型 / 改必填）；差异逐条复核 |

## 4. 兼容性与消费方影响 <a id="compat"></a>

- **运行时零影响**：只改 JSON Schema 生成路径；`model_dump()` / `model_dump_json()`、脱敏、ID 字符串化与请求校验行为不变。
- **契约内容变更**：响应侧 schema 由空对象变为具字段（新增信息）；请求侧不变；契约版本不变。
- **前端**：`@bms/api-types` 响应类型由 `unknown` 变为具字段类型——**类型收窄属「变严」**，现有以 `unknown` 消费的代码（当前无）不受破坏；域五 `05_02` 起按新类型消费。
- **CI 影响**：`swagger-snapshot` job 内 `check_contracts` 断言扩展（秒级，纯内存构建）；`contract_snapshot check` / `contract_gate` 全绿。
- **既有护栏不受影响**：`check-bare-collections` 基线已归零，本任务新增声明一律落插入序基座集合类，不新增基线条目。

## 5. 测试设计与验收映射 <a id="test"></a>

用例**先登记 Kiwi TCMS 再编码**（新登记 1 条策展用例，覆盖下表断言；编号以平台回读为准并回填实施 / 测试记录与代码标注）。

| # | 用例 / 文件 | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 1 | `libs/bms_core/tests/schemas/test_serialization_schema.py` | 单元 | 序列化模式 schema 具字段（与校验模式字段集合一致），不再是 `{}` |
| 2 | 同上 | 单元 | `id` / `*_id` 属性在序列化模式为字符串（含 `Optional` 联合形态）；非 ID 整型字段仍为 integer |
| 3 | 同上 | 单元 | **运行时不变量**：`model_dump()` 仍字符串化 ID；`model_dump_json()` 与校验模式 schema 不因修复改变 |
| 4 | 同上 | 单元 | 参数化泛型包装（`ApiResponse[X]`）序列化模式具 `data` 字段且嵌套模型定义非空 |
| 5 | `libs/bms_core/tests/services/test_service_contract_schemas.py` | 单元 | 断言 C：含空 schema 条目的契约 → 报明细；白名单命中 → 通过 |
| 6 | 同上 | 单元 | 断言 D：成功响应 `$ref` 悬空 / 引用目标为空 → 报明细；可解析引用与内联 schema（含空对象）→ 通过 |
| 7 | `libs/bms_core/tests/ops/test_check_contracts.py`（扩展） | 单元 | 桩应用含空 schema 条目 / 悬空响应引用 → `check_service` 报违规、`main` 退出码 1；契约完整 → 0 |
| 8 | `ops/check_contracts.py` 真跑 | 集成 | 9 服务全绿（空 schema 0、响应 `$ref` 全可解析） |
| 9 | `ops.contract_snapshot check` / `api-types:gen:check` | 集成 | 快照与生成类型零漂移 |
| 10 | 既有序列化 / 脱敏 / 契约集合用例 | 回归 | 运行时行为零变化 |

**验收映射**：需求 06-4「响应契约 schema 完整」→ 用例 1~4 + 8；「前端类型具字段可用且零漂移」→ 用例 9 + 实测生成物；「门禁在空 schema / 悬空 `$ref` 时失败」→ 用例 5~7；「CI 与本地预检同口径」→ 用例 8（命令复用既有接入点）；「运行时行为零变化」→ 用例 3 / 10。门禁：`pytest` / `ruff` / `ruff format --check` / `pyright` / 基座校验全绿，新增模块覆盖率 **100%**。

**执行范围**：只跑受变更影响的定向用例（`libs/bms_core/tests/schemas/` + `tests/services/` + `tests/ops/` + `services/identity/tests/` 认证契约回归 + 契约命令真跑 + 文档校验），不跑全量（口径见《[AI开发规范](../../../../../../规范/AI开发规范.md)》「测试产物复用不开口子」）。

## 6. 登记落点 <a id="registry"></a>

| 内容 | 落点 |
| --- | --- |
| 响应契约完整性口径（`components.schemas` 无空对象 + 成功响应 schema 可解析且非空） | 《[后端开发规范](../../../../../../规范/后端开发规范.md)》§7.4「契约与门禁（强制）」扩展为门禁**第四道** |
| 契约校验命令断言扩展 | 《[后端基类清单](../../../../../../后端基类清单.md)》§9「跨阶段基座」服务公开契约快照行 |
| 需求 06-4 计数与总清单（38 条） | 需求域 06、需求总览（**已回写**） |
| 阶段计划：06_03 条目与工作量 | 阶段计划表（进度唯一落点，**已回写**） |
| 任务 06_03 / 父任务 06 状态 | 任务 06_03、父任务 06（需求文档不承载进度） |
| Kiwi TCMS / 测试资产仓 | 登记本任务用例并回读编号 |
| 实施 / 测试记录 | 本目录 `实施/`、`测试/` |

> 架构节点（《[架构设计 · 接口与集成](../../../../../../设计/架构设计/09_架构设计_接口与集成.md)》「服务间通信与契约」）已表达语义（「每服务维护唯一公开契约（OpenAPI），契约快照入 CI；破坏性变更用 oasdiff 门禁拦截」）；本任务为**语义落地与门禁补强**，**不改架构节点**（实现标识落《后端基类清单》与本文档）。

## 7. 边界与开放项 <a id="boundary"></a>

- **ID 类型改写范围**：只覆盖模型**自身 `properties`** 中名为 `id` / `*_id` 的属性；`dict[str, X]` 内以 `id` 为键的动态映射无法在 schema 层表达（运行时仍字符串化），属既有表达力边界。
- **`handler.mode` 取法**：pydantic 的 `GetJsonSchemaHandler` 协议未声明 `mode`，实现以 `getattr` 容错读取；pydantic 大版本升级后复核（登记开放项）。
- **`-Input` / `-Output` 后缀变体**：本次重生成后复核不出现；若未来出现，需评估契约命名稳定性。
- **契约版本自动回写**（CI 取 OpenAPI 版本写入服务目录）仍归既有开放项（阶段二 `09_03` 边界），本任务不实施。
- **基线定期评审**：`deploy/contracts/baseline/*.json` 仅在明确评审节点更新；本任务 9 份一并更新（本次为同一口径变更）。
- **其他响应形态**：SSE / 文件流等非 `application/json` 响应不纳入断言 D（无 JSON schema 可比）；存在时按需扩展。
- **原始 `Response` 端点的响应契约缺失（遗留，2026-10-02 实施期发现）**：19 处成功响应为**内联空 schema**——`/readyz`（9 服务）与 identity 的 `/oidc/jwks`、`/oidc/.well-known/openid-configuration`、`/oidc/authorize`、`/oidc/token`、`/oidc/userinfo`、`/auth/introspect`、`/auth/sso/{idp_key}/authorize`、`/callback`；根因是这些路由直接返回 `Response` / `JSONResponse` / `RedirectResponse`。**另立子任务（域六 `06_05`，待立项）或归后续**；本任务不扩面（断言 D 不判定内联 schema，登记计划 §7 后续待办）。
- **基线现存漂移一并吸收**：8 个服务的 `baseline/*.json` 此前停留在较早评审节点（如 `tenant.json` 缺后续新增的 `tenant_id` 查询参数），本次随同一口径一并重生成；经结构差异核验**零移除键、零值变更**（仅新增），非破坏性。

## 8. 对齐记录 <a id="align"></a>

### 8.1 本轮拍板（2026-10-02，逐项确认） <a id="align-new"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 契约类型缺口处理 | **先立项补建基座修复**（不手写前端类型、不长期留 `unknown`），完成后再回域五 `05_02` 按生成类型消费 |
| 2 | 需求归类 | **新增需求 06-4**（顺延编号） |
| 3 | 任务落点 | **新建子任务 `06_03`**（与 `06_01` 平级、挂域 06 父任务）；**不重开已收口的 `06_01`** |
| 4 | 实施排序 | **立即提前实施、串行**：`06_03` → 域五 `05_02` |
| 5 | 工作口径 | 基座修复 + 门禁 + 9 服务快照 / 基线 / 前端类型重生成 + 定向回归 |
| 6 | 门禁形态 | 扩展现有 `ops/check_contracts.py`（**不新增 CI job**，复用既有 CI 与本地预检接入点） |
| 7 | 门禁断言 | `components.schemas` 无空对象 + 成功响应 schema 可解析且非空；白名单初始为空 |
| 8 | 快照与基线 | 9 服务**一并重生成**（同一口径变更，属同一评审节点） |
| 9 | 契约版本 | **保持 `0.1.0`**（非破坏性新增） |
| 10 | ID 输出口径 | 序列化模式把 `id` / `*_id` 标为字符串，判定与运行时 `stringify_ids` **同源单点** |
| 11 | Kiwi 用例 | 新登记 1 条策展用例（设计定稿后、编码前登记） |
| 12 | 登记落点 | 《后端开发规范》§7.4 + 《后端基类清单》§9 |
| 13 | 工作量大数 | 以详细设计重估为准，数值落阶段计划表（本文件不承载进度） |
| 14 | CI 触发 | 推送后按需手动触发（不盯守） |
| 15 | **实施期追加拍板（断言 D 口径）** | 实测 19 处内联空响应 schema（原始 `Response` 端点）→ **D 收敛为「只判引用型」**，内联不判定；不设路径级豁免清单 |
| 16 | **实施期追加拍板（遗留归口）** | 19 处「原始 `Response` 端点响应契约缺失」**登记计划 §7 后续待办**，另立子任务（域六 `06_05`，待立项）或归后续；本任务不扩面 |
| 17 | **实施期实测（基线漂移）** | 8 个服务基线此前停留在较早评审节点 → 本次一并重生成；结构差异核验**零移除键、零值变更**（仅新增），并在实施记录登记 |

### 8.2 复用既有口径 <a id="align-reuse"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 契约机制 | 阶段二 `03_01` / `04-1-1` / 域六 `06_01` 已交付（快照导出 / oasdiff 基线 / 类型生成零漂移 / 路由覆盖护栏），本任务不重复建设 |
| 2 | 集合形态 | 一律落插入序基座集合类 |
| 3 | 文档层级与链接 | 遵《文档生成规范》；改后跑 `check-links` |
| 4 | 外部服务操作 | Kiwi 登记先读《[KiwiTCMS部署使用说明](../../../../../../资料/开发服务器/linux/KiwiTCMS部署使用说明.md)》 |

## 9. 实施步骤与关键命令 <a id="steps"></a>

```mermaid
flowchart LR
    A["Kiwi 用例登记（先登记后编码）"] --> B["core/serialization 增 is_id_key"]
    B --> C["schemas/base 序列化模式 schema 修复 + 用例"]
    C --> D["service_contract 纯判定 + 用例"]
    D --> E["ops/check_contracts 断言 C / D 接入 + 用例"]
    E --> F["9 服务快照 + 基线重生成"]
    F --> G["api-types 重生成 + 零漂移校验"]
    G --> H["规范 / 清单登记"]
    H --> I["门禁全绿 + 计划与记录回写"]
    I --> J["提交（feat / docs 分开）+ 偏差遗留闭环"]
```

1. 读《[KiwiTCMS部署使用说明](../../../../../../资料/开发服务器/linux/KiwiTCMS部署使用说明.md)》「用例约定」节，登记本任务用例并**回读编号**（先登记后编码）。
2. `core/serialization.py` 新增 `is_id_key` 并改 `_stringify_entry` 调用之（行为不变）。
3. `schemas/base.py` 新增 `BaseSchema.__get_pydantic_json_schema__`（序列化模式字段口径 + ID 类型改写）；新增用例 1~4。
4. `service_contract.py` 新增 `EMPTY_SCHEMA_ALLOWLIST` / `empty_schema_entries` / `response_schema_gaps`；新增用例 5~6。
5. `ops/check_contracts.py` 接入断言 C / D 并更新命令说明；扩展现有用例 7。
6. 重生成快照 / 基线 / 前端类型；`contract_snapshot check` 与 `api-types:gen:check` 零漂移。
7. 《后端开发规范》§7.4 与《后端基类清单》§9 登记。
8. 门禁：定向 `pytest` / `ruff` / `ruff format --check` / `pyright`（CI 兜底）/ 基座校验 / `check-preflight --fast`；覆盖率核对。
9. 计划 / 任务 / 父任务状态回写 + 实施 / 测试记录 + 代码与文档分开提交（`feat` / `docs`）；偏差与遗留闭环另提。

关键命令：

```bash
# 后端（bms/backend）
uv run pytest -q libs/bms_core/tests/schemas/ libs/bms_core/tests/services/ libs/bms_core/tests/ops/
uv run python -m ops.check_contracts                      # 路由覆盖 + 响应 schema 完整性
uv run python -m ops.contract_snapshot export             # 快照重生成
uv run python -m ops.contract_snapshot check              # 快照零漂移
uv run python -m ops.contract_gate baseline-update --service <service>   # 基线重生成（逐服务）
uv run ruff check . && uv run ruff format --check .
# 前端（bms 根）
pnpm --filter @bms/api-types run gen && pnpm run api-types:gen:check
# 仓库根
python3 scripts/tools/base-check/check-base.py
python3 scripts/tools/base-check/check-links.py
python3 scripts/tools/check-docs/check-status.py --stage 06_认证与安全
python3 scripts/tools/preflight/check-preflight.py --fast
```

> 本机无 docker 时 `ops.contract_gate check` 无法本地复现（依赖 `tufin/oasdiff` 镜像）；本地以 oasdiff 官方二进制（v1.32.1）复现同口径比对，CI `contract-gate` job 为权威门禁。

## 10. 参考文档 <a id="ref"></a>

- [需求 06-4](../../../../需求/06_需求_契约与模块请求能力.md#r06-4)（含 [06-1](../../../../需求/06_需求_契约与模块请求能力.md#r06-1) / [06-3](../../../../需求/06_需求_契约与模块请求能力.md#r06-3)）
- 《[后端开发规范](../../../../../../规范/后端开发规范.md)》§7.4「契约与门禁（强制）」
- 《[后端基类清单](../../../../../../后端基类清单.md)》§9「跨阶段基座」服务公开契约快照行
- 《[架构设计 · 接口与集成](../../../../../../设计/架构设计/09_架构设计_接口与集成.md)》「服务间通信与契约」节
- 域六 [06_01 认证契约快照与前端类型生成](../../06_契约与模块请求能力_01_认证契约快照与前端类型生成/06_契约与模块请求能力_01_认证契约快照与前端类型生成.md)（**契约机制与路由覆盖护栏已交付**）
- 《[AI开发规范](../../../../../../规范/AI开发规范.md)》「单任务交付一条龙」与 §3.1 补充需求处理方式

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写 · 关键决策逐项确认（2026-10-02）

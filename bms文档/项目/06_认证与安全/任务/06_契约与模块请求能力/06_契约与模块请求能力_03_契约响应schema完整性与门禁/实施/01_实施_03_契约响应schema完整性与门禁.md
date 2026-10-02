# 03 实施记录 · 契约响应 schema 完整性与门禁

> 认证与安全 · 06 契约与模块请求能力 · 子任务 03（需求 06-4）· 实施记录

[文档首页](../../../../../../文档首页.md) › [06 契约与模块请求能力](../../06_契约与模块请求能力.md) › [03 契约响应 schema 完整性与门禁](../06_契约与模块请求能力_03_契约响应schema完整性与门禁.md) › 实施记录　|　[详细设计 →](../设计/01_详细设计_03_契约响应schema完整性与门禁.md)

## 1. 实施信息 <a id="info"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 契约响应 schema 完整性与门禁](../06_契约与模块请求能力_03_契约响应schema完整性与门禁.md)（需求 [06-4](../../../../需求/06_需求_契约与模块请求能力.md#r06-4)） |
| 实施日期 | 2026-10-02 |
| 实施人 | minjian |
| Kiwi 用例 | **2228**（策展，P2 / CONFIRMED / 自动化；登记后回读核对一致） |
| 依据 | 详细设计 [01_详细设计_03_契约响应schema完整性与门禁.md](../设计/01_详细设计_03_契约响应schema完整性与门禁.md) |
| 结论 | **完成**（含 2 项实施期偏差，均已回写设计） |

## 2. 实施过程 <a id="process"></a>

1. **立项与设计**：新增需求 06-4（域 06 计数 3 → 4）、新建子任务 `06_03`（与 `06_01` 平级）、父任务与需求总览与阶段计划表同步回写；落详细设计（基座修复 + 门禁 + 快照与类型重生成 + 测试设计）。定稿提交 `ba5f2ec6`。
2. **Kiwi 登记**：按《KiwiTCMS部署使用说明》「用例约定」节，经容器内 Django shell 批量登记 1 条策展用例，回读用例号 **2228**（标签「自动化」、状态 `CONFIRMED`）；脚本临时文件用后即删。
3. **ID 键单点判定**：`core/serialization.py` 新增公共函数 `is_id_key(key)`（`id` 或 `*_id` 结尾），`_stringify_entry` 改调用之——**运行时字符串化与 schema 侧改型共用同一判定**，行为逐字节不变。
4. **基座序列化 schema 修复**：`schemas/base.py` 新增 `BaseSchema.__get_pydantic_json_schema__`——**序列化模式**下剥离模型序列化器（`schema["serialization"]`）后交回处理器，使 JSON Schema 回落到字段口径；再经 `_stringify_id_properties` 把 `id` / `*_id` 属性按 `is_id_key` 改为字符串（`integer` → `string`、`anyOf: [integer, null]` → `anyOf: [string, null]`，`anyOf` / `oneOf` 成员递归）。校验模式与运行时序列化**均不变**。
   - 关键机制核实：pydantic 2.13 以 `getattr(tp, '__get_pydantic_json_schema__', None)` 取该钩子（**子类继承生效**）；实测处理器剥离序列化器后**不产生递归**（每个模型在每次生成中各调用一次），嵌套模型定义（`$defs`）经各自继承的同一钩子一并生效。
5. **契约完整性纯判定**：`services/service_contract.py` 新增 `EMPTY_SCHEMA_ALLOWLIST`（缺省空集）、`empty_schema_entries(openapi)`（断言 C：`components.schemas` 无空对象条目）、`response_schema_gaps(openapi)`（断言 D：成功响应**引用型** schema 可解析且引用目标非空）；辅助 `_as_mapping` / `_component_schemas` / `_is_success_status` / `_json_schema_gap` 以鸭子类型读取、全部落插入序基座集合类。
6. **命令接入**：`ops/check_contracts.py` 抽出 `_contract_openapi(app)` 复用一次 `openapi()` 调用，`_contract_paths` 改接契约映射；`check_service` 追加 C / D 两组断言（前缀 `[契约]`）；命令说明与成功/失败文案同步更新。**CI `swagger-snapshot` 与本地预检复用既有接入点，零配置改动**。
7. **快照与基线重生成**：`ops.contract_snapshot export`（9 服务）+ `ops.contract_gate baseline-update --all`（9 服务）。
   - **变更性质核验**：本机无 docker（无法跑 oasdiff）→ 以严格结构差异核验替代：基线 ↔ 新快照**逐服务零移除键、零值变更**（`ai` 249→260、`file` 198→209、`identity` 1028→1567、`notification` 175→186、`org` 146→835、`platform` 1359→1435、`report` 211→222、`search` 126→137、`tenant` 138→149，全部仅新增），属**非破坏性**。
   - **基线现存漂移一并吸收**：8 个服务基线此前停留在较早评审节点（如 `tenant.json` 缺后续新增的 `tenant_id` 查询参数）——本次随同一口径一并重生成，消除漂移；`identity` 基线为 `06_01` 更新点，本次再随响应 schema 更新。
8. **前端类型重生成**：`pnpm --filter @bms/api-types run gen` → `login:LoginResult` 具 `access_token` / `token_type` / `expires_in` / `user`（`UserSummary` 具 `id`（string）/ `username` / `name` / `tenant` / `locale` / `timezone` / `must_change_password`），`ApiResponse_LoginResult_` 等包装类型不再为 `unknown`；`gen:check` 零漂移。
9. **规范与清单登记**：《后端开发规范》§7.4 由「契约门禁三道」扩为**四道**并补「响应契约不得丢字段」强制口径；《后端基类清单》扩展 `BaseSchema` 行与新增「契约响应 schema 完整性护栏」行。

## 3. 关键命令 <a id="commands"></a>

```bash
# 后端（bms/backend）
uv run pytest -q libs/bms_core/tests/schemas libs/bms_core/tests/services libs/bms_core/tests/ops
uv run python -m ops.check_contracts
uv run python -m ops.contract_snapshot export
uv run python -m ops.contract_snapshot check
uv run python -m ops.contract_gate baseline-update --all
uv run ruff check . && uv run ruff format --check .
# 前端（bms 根）
pnpm --filter @bms/api-types run gen && pnpm run api-types:gen:check
# 仓库根
python3 scripts/tools/base-check/check-base.py
python3 scripts/tools/base-check/check-links.py
python3 scripts/tools/base-check/check-backend-base.py
python3 scripts/tools/base-check/check-docs-scope.py
python3 scripts/tools/base-check/check-bare-collections.py
python3 scripts/tools/check-docs/check-status.py --stage 06_认证与安全 --strict
python3 scripts/tools/preflight/check-preflight.py --fast
```

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 | 归口 |
| --- | --- | --- | --- |
| 1 | **断言 D 初版口径触发 19 处误报**：`/readyz`（9 服务）+ identity 的 `/oidc/jwks`、`/oidc/.well-known/openid-configuration`、`/oidc/authorize`、`/oidc/token`、`/oidc/userinfo`、`/auth/introspect`、`/auth/sso/{idp_key}/authorize`、`/callback` 成功响应为**内联空 schema**——这些路由直接返回 `Response` / `JSONResponse` / `RedirectResponse`，OpenAPI 无从推导 schema | **实施期追加拍板**：断言 D 收敛为「只判**引用型**（`$ref`）响应 schema」，内联不判定（属「原始 `Response` 端点未声明响应契约」另一缺陷类，不设路径级豁免清单）；设计 §3.2 / §3.4 / §7 / §8.1 与需求 06-4 内容 4 同步回写 | 19 处补声明**登记计划 §7 后续待办第 37 项**（域六后续子任务 `06_05`，待立项 / 或归后续） |
| 2 | 8 个服务 `baseline/*.json` 停留在较早评审节点（与当前公开契约本已存在差异，如 `tenant.json` 缺 `tenant_id` 参数） | 本次随同一口径 `baseline-update --all` 一并重生成，并逐服务结构差异核验（零移除键、零值变更）；设计 §7 与 §8.1 登记 | 本任务内闭环 |
| 3 | 本机无 docker → `ops.contract_gate check`（oasdiff）无法本地复现 | 以严格结构差异核验替代（基线 ↔ 新快照逐键比对）；权威门禁以 CI `contract-gate` job 为准 | 推送后按需手动触发一次流水线 |
| 4 | `test_serialization_schema` 中「无字段模型不含 `properties`」断言与实测不符 | 实测 pydantic 对无字段模型仍产出 `properties: {}`；改断言为「`properties` 为空映射」，并保留 ID 改写辅助边界（非映射值 / 无 `properties`）的直调断言以覆盖防御分支 | 本任务内闭环 |
| 5 | 早期尝试把模型 schema 作为序列化器 `return_schema` 会触发 `PydanticSerializationUnexpectedValue` 告警 | 弃用该方案，改走「仅在 JSON Schema 生成路径上剥离序列化器」——运行时零影响、零告警 | 本任务内闭环（设计 §3.1 已按此定稿） |

## 5. 验证结果 <a id="verify"></a>

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 定向用例 | `uv run pytest -q libs/bms_core/tests/schemas libs/bms_core/tests/services libs/bms_core/tests/ops` | **247 passed** |
| 受影响面回归 | `uv run pytest -q libs/bms_core/tests services/platform/tests services/identity/tests` | **1759 passed / 39 skipped** |
| 契约校验（四道同命令） | `uv run python -m ops.check_contracts` | 通过（9 服务：路由全覆盖、不可见均在白名单、**无空 schema、引用型响应 schema 均可解析**） |
| 快照零漂移 | `uv run python -m ops.contract_snapshot check` | 通过（9 服务） |
| 前端类型零漂移 | `pnpm run api-types:gen:check` | 通过（9 份一致） |
| 空 schema 残留 | 逐服务统计 `components.schemas` 空条目 | **全 9 服务为 0**（修复前 identity 40 / org 21 / platform 3 / 其余各 1） |
| `-Input` / `-Output` 变体 | 快照全文匹配 | **0**（无两侧同用模型，命名稳定性不受影响） |
| Lint / 格式 | `uv run ruff check .` / `uv run ruff format --check .` | 全绿 |
| 基座护栏 | `check-base` / `check-links` / `check-backend-base` / `check-docs-scope` / `check-bare-collections` / `check-status --strict` | 全绿 |
| 本地预检 | `check-preflight.py --fast` | **全部通过**（含契约两道与 `api-types` 零漂移） |
| 类型检查 | `pyright` | 本地因依赖外置不可用，由 CI 兜底（设计口径一致） |

## 6. 覆盖率 <a id="coverage"></a>

| 文件 | 覆盖率 | 说明 |
| --- | --- | --- |
| `bms_core/services/service_contract.py` | **100%** | 新增判定函数全分支覆盖 |
| `bms_core/schemas/base.py` | 74%（新增行 **100%**） | 缺口均为既有掩码分支（104 / 261-263 / 283-292 / 314-325 / 343-352 / 370-373），非本次改动 |
| `bms_core/core/serialization.py` | 89%（新增 `is_id_key` 全覆盖） | 缺口为既有 `rebuild_*` 回退分支 |
| `ops/check_contracts.py` | 99% | 唯一未覆盖＝`__main__` 启动块（命令真跑已覆盖该路径） |

## 7. 偏差与遗留 <a id="deviation"></a>

| # | 项 | 类型 | 处置与归口 |
| --- | --- | --- | --- |
| 1 | 断言 D 由「全量严格」收敛为「只判引用型」 | 偏差（设计已回写） | 设计 §3.2 / §3.4 / §7 / §8.1 + 需求 06-4 内容 4 已同步 |
| 2 | 19 处原始 `Response` 端点响应契约缺失 | 遗留 | 计划 §7 后续待办第 37 项；域六后续子任务 `06_05`（待立项）或归后续 |
| 3 | 8 服务基线现存漂移随本次一并吸收 | 偏差（已登记） | 设计 §7 / §8.1；结构差异核验零移除 |
| 4 | `handler.mode` 取法不属 `GetJsonSchemaHandler` 协议声明（以 `getattr` 容错） | 开放项 | pydantic 大版本升级时复核（设计 §7） |
| 5 | oasdiff 破坏性比对未在本地复现（无 docker） | 开放项 | CI `contract-gate` job 为权威门禁；推送后按需手动触发一次 |

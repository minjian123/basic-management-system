# 03 测试记录 · 契约响应 schema 完整性与门禁

> 认证与安全 · 06 契约与模块请求能力 · 子任务 03（需求 06-4）· 测试记录

[文档首页](../../../../../../文档首页.md) › [06 契约与模块请求能力](../../06_契约与模块请求能力.md) › [03 契约响应 schema 完整性与门禁](../06_契约与模块请求能力_03_契约响应schema完整性与门禁.md) › 测试记录　|　[详细设计 →](../设计/01_详细设计_03_契约响应schema完整性与门禁.md)

## 1. 测试信息 <a id="info"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 契约响应 schema 完整性与门禁](../06_契约与模块请求能力_03_契约响应schema完整性与门禁.md)（需求 [06-4](../../../../需求/06_需求_契约与模块请求能力.md#r06-4)） |
| 测试日期 | 2026-10-02 |
| 测试人 | minjian |
| Kiwi TCMS 用例 | **2228**（策展；分类「平台骨架」/ P2 / `CONFIRMED` / 标签「自动化」）——**先登记后编码**，编号回读一致并回填代码标注 |
| 被测物 | 构建产物＝当前工作区源码（后端 `uv run` 内联依赖 + 前端工作区源码直出），无临时构建物 |
| 执行范围 | **只跑受变更影响的定向用例**（`bms_core` 全量 + `platform` / `identity` 两个受影响服务；契约命令真跑；文档与基座护栏）——不跑全量后端用例（口径见《[AI开发规范](../../../../../../规范/AI开发规范.md)》） |

## 2. 用例清单与结果 <a id="cases"></a>

| # | 用例 / 文件 | 类型 | 断言要点 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | `libs/bms_core/tests/schemas/test_serialization_schema.py::test_serialization_schema_carries_fields` | 单元 | 序列化模式 schema 具字段且字段集合与校验模式一致 | 通过 |
| 2 | 同上 `::test_serialization_schema_stringifies_id_fields` | 单元 | `id` / `user_id`（`Optional` 联合）标字符串；`count` / `group_ids`（非 ID）保持 integer | 通过 |
| 3 | 同上 `::test_validation_schema_and_runtime_unchanged` | 单元 | 校验模式 `id` 仍 integer；`model_dump()` 仍字符串化 ID、`model_dump_json()` 一致 | 通过 |
| 4 | 同上 `::test_blank_model_and_helper_boundaries` | 单元 | 无字段模型 `properties` 为空映射；ID 改写辅助对非映射值 / 无 `properties` 原样返回 | 通过 |
| 5 | 同上 `::test_generic_wrapper_serialization_schema` | 单元 | 参数化泛型包装 `data` 引用可达、`$defs` 嵌套模型定义非空且 ID 为字符串 | 通过 |
| 6 | `libs/bms_core/tests/services/test_service_contract_schemas.py::test_empty_schema_entries_reports_and_allows_whitelist` | 单元 | 断言 C：空条目被报出；白名单命中即通过；无空条目通过 | 通过 |
| 7 | 同上 `::test_response_schema_gaps_accepts_resolvable_ref` | 单元 | 断言 D：可解析引用通过；无响应 / 无成功响应通过 | 通过 |
| 8 | 同上 `::test_response_schema_gaps_reports_dangling_and_empty_target` | 单元 | 引用目标为空 / 引用未解析被报出；内联 schema（含空对象）不判定 | 通过 |
| 9 | `libs/bms_core/tests/ops/test_check_contracts.py::test_check_service_reports_empty_schema_entry` | 单元 | 桩应用含空 schema 条目 → 报「空 schema 条目」 | 通过 |
| 10 | 同上 `::test_check_service_reports_unresolvable_response_schema` | 单元 | 悬空响应引用 → 报「成功响应 schema 不可用」 | 通过 |
| 11 | 同上 `::test_check_service_passes_when_response_schema_complete` | 单元 | 契约完整 → 无违规且 `main` 退出码 0 | 通过 |
| 12 | `ops.check_contracts` 真跑（9 启用服务） | 集成 | 路由全覆盖 + 不可见白名单 + 无空 schema + 引用型响应 schema 可解析 | 通过 |
| 13 | `ops.contract_snapshot check` | 集成 | 9 服务快照零漂移 | 通过 |
| 14 | `pnpm run api-types:gen:check` | 集成 | 9 份前端契约类型零漂移；认证响应类型具字段（非 `unknown`） | 通过 |
| 15 | 既有序列化 / 脱敏 / 契约集合用例（`bms_core` 全量 + `platform` / `identity`） | 回归 | 运行时行为零变化 | 通过 |

## 3. 执行结果 <a id="result"></a>

| 命令 | 结果 |
| --- | --- |
| `uv run pytest -q libs/bms_core/tests/schemas libs/bms_core/tests/services libs/bms_core/tests/ops` | **247 passed** |
| `uv run pytest -q libs/bms_core/tests services/platform/tests services/identity/tests` | **1759 passed / 39 skipped**（无失败） |
| `uv run python -m ops.check_contracts` | 通过（9 服务） |
| `uv run python -m ops.contract_snapshot check` | 通过（9 服务） |
| `pnpm run api-types:gen:check` | 通过（9 份一致） |
| `uv run ruff check .` / `uv run ruff format --check .` | 全绿（968 文件已格式化） |
| `check-base` / `check-links` / `check-backend-base` / `check-docs-scope` / `check-bare-collections` | 全绿 |
| `check-status --stage 06_认证与安全 --strict` | 检查 411 项，硬规则不合规 0、软提示 0 |
| `check-preflight.py --fast` | **全部通过** |

**修复前后对比（`components.schemas` 空条目数）**：

| 服务 | 修复前 | 修复后 |
| --- | --- | --- |
| identity | 40 / 56 | **0 / 56** |
| org | 21 / 31 | **0 / 31** |
| platform | 3 / 22 | **0 / 22** |
| ai / file / notification / report / search / tenant | 各 1（`ApiResponse`） | **各 0** |

## 4. 覆盖率 <a id="coverage"></a>

| 文件 | 覆盖率 | 说明 |
| --- | --- | --- |
| `bms_core/services/service_contract.py` | **100%** | 新增判定函数全分支覆盖 |
| `bms_core/schemas/base.py` | 74%（**新增行 100%**） | 缺口均为既有掩码分支，与本次改动无关 |
| `bms_core/core/serialization.py` | 89%（**新增 `is_id_key` 全覆盖**） | 缺口为既有 `rebuild_*` 回退分支 |
| `ops/check_contracts.py` | 99% | 唯一未覆盖＝`__main__` 启动块（命令真跑已覆盖） |

## 5. 问题与偏差 <a id="deviation"></a>

| # | 项 | 处置 |
| --- | --- | --- |
| 1 | 断言 D 初版「内联空 schema 亦判失败」触发 19 处误报（原始 `Response` 端点） | 实施期拍板**收敛为只判引用型**；用例 8 补「内联不判定」断言锁定新口径；设计与需求同步回写 |
| 2 | `test_serialization_schema` 首版「无字段模型不含 `properties`」断言与 pydantic 实测不符 | 修正为「`properties` 为空映射」；用例 4 |
| 3 | 19 处原始 `Response` 端点响应契约缺失 | 遗留登记（计划 §7 后续待办第 37 项）——**本任务不对其设门禁白名单** |
| 4 | `pyright` 本地不可用（依赖外置） | 由 CI 兜底；本地以 `ruff` / 定向用例 / 基座护栏把关 |
| 5 | oasdiff 本地不可复现（无 docker） | 以严格结构差异核验替代（基线 ↔ 新快照零移除键、零值变更）；CI `contract-gate` 为权威门禁 |

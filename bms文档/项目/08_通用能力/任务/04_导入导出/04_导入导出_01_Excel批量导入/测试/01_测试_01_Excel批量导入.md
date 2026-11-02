# Excel 批量导入测试记录

> 通用能力 · 04 导入导出 · 01 Excel 批量导入 · 测试记录

[文档首页](../../../../../../文档首页.md) › [08 通用能力](../../../../README.md) › [导入导出](../../04_导入导出.md) › [Excel 批量导入](../04_导入导出_01_Excel批量导入.md) › 测试　|　[详细设计](../设计/01_详细设计_01_Excel批量导入.md) · [实施记录](../实施/01_实施_01_Excel批量导入.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 Excel 批量导入](../04_导入导出_01_Excel批量导入.md) |
| 对应需求 | [02-2](../../../../需求/02_需求_文件与导入导出.md#r02-2) |
| 测试日期 | 2026-11-02 |
| 环境 | 本机（Windows / Python 3.14），临时 SQLite 租户库，本地对象存储，`fakeredis` |
| 执行方式 | 开发环 `scripts/tools/preflight/测试改动内容.py`（ruff + 六项护栏 + 定向 pyright + 定向选测；不含覆盖率门禁） |
| Kiwi 用例 | **2401**（模块级 `pytestmark = pytest.mark.kiwi_id(2401)`；一任务一条用例，文本列覆盖范围与自动化文件） |

## 2. 用例清单与执行结果 <a id="cases"></a>

新增自动化用例 **34 个**（平台导入域 18 + 基座 transfer 16），另补幂等 `release` 1 个；全部通过。连同既有 transfer / idempotency / 异常构造用例，定向集合共 **199 passed**；开发环全量 **3626 passed / 12 skipped**。

| 测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| `libs/bms_core/tests/transfer/test_openpyxl_importer.py` | 7 | 解析行号 / 空行跳过 / 表头错序 / 无数据行 / 类型与可选值校验 / 模板两 sheet / 错误明细 / zip 条目与解压上限 |
| `libs/bms_core/tests/transfer/test_import_definition.py` | 5 | 定义登记 / 重名非法 / 空列集 / 列键与标题重复 / 默认预取与写路径 / 批次工作单元 / 汇总字段 |
| `libs/bms_core/tests/transfer/test_import_source.py` | 2 | 对象 key 路径风格 / 读写删与缺失 |
| `libs/bms_core/tests/transfer/test_import_limits.py` | 2 | 代码默认 / 参数覆盖 / 非法与非正回落 |
| `services/platform/tests/import_export/test_import_api.py` | 13 | 模板（users / roles）/ 同步成功与幂等 / 全量原子 / 角色非法 / 表头与行数 / 扩展名与大小 / 异步提交与状态 / 错误明细 / 缺幂等键 / 未知业务 / 限流 / 业务写权限 |
| `services/platform/tests/import_export/test_import_job.py` | 5 | 异步成功与进度 / 校验拒绝 / 源文件缺失 / 批次取消 / 用户定义列集与校验 |
| `libs/bms_core/tests/idempotency/test_idempotency_redis.py`（新增 1） | 1 | `release` 后同键可重试 / Redis 不可用 fail-closed |
| `libs/bms_core/tests/transfer/test_transfer.py`（改动） | 1 | 依赖解析改为真实 `OpenpyxlImporter` |
| `libs/bms_core/tests/core/test_exception_constructors_paths.py`（改动） | 1 | `503xx` 十个异常构造路径 |
| 既有边界 / 作业 / 插件 / 发布用例（改动 5 处） | 5 | 域数 18、作业集合、handler 列表、导入器契约版本 `0.2.0`、结构就绪用例按有表域取样 |

**替身策略**：对象存储用本地临时目录（不连 MinIO）；幂等 / token 用 `MemoryCacheRegion` 与 `fakeredis`；作业用内存源文件与直接构造 `JobContext`，不启 worker；用户 / 角色写路径使用真实仓储与真实 SQLite 表。

## 3. 覆盖率 <a id="coverage"></a>

- 本次**未采集**覆盖率（开发环口径不含覆盖率门禁）；
- 推送前由推送环（`scripts/tools/preflight/推送.py`）跑定向用例 + 覆盖率门禁；
- 目标：新增 / 改动模块 100% 行 + 分支（《[测试规范](../../../../../../规范/测试规范.md)》）。已知待补分支：openpyxl 解析异常的部分底层异常路径、异步 worker 真实进程路径（本段用 handler 直调覆盖语义）。

## 4. 问题与偏差 <a id="issues"></a>

| # | 项 | 说明 |
| --- | --- | --- |
| 1 | 源文件根不一致 | API 覆盖对象存储与 inline 作业按 settings 解析不一致；测试统一 `BMS_STORAGE__OPTIONS__ROOT`，生产同源 |
| 2 | 批次事务冲突 | 单行服务自开事务；以 `ImportBatchUnitOfWork` 并入外层 savepoint，全量原子语义成立 |
| 3 | 通用校验漏跑 | 预检先跑 `BaseImporter.validate_rows`，再由业务定义校验 |
| 4 | 角色导入安全边界 | 模板仅 3 列，导入恒为 `custom`；内置 `system` / `security` / `audit` / `platform_admin` 不经导入创建 |
| 5 | 前端与操作日志 | 归阶段十五 / 06_01；本段以接口与 `AuditCapturer.capture` 边界验收 |

## 5. 验收映射 <a id="accept"></a>

| 完成标准（任务 §3 / 需求 02-2） | 用例 | 状态 |
| --- | --- | --- |
| 模板可下载且列头与字段一致 | `test_template_users_and_roles` | 通过 |
| 含非法行时逐行报错且不落库 | `test_execute_users_invalid_is_atomic` / `test_roles_invalid_is_atomic` | 通过（全量原子：`committed=false`、`blocked_count`） |
| 同一 `Idempotency-Key` 只生效一次 | `test_execute_users_success_and_idempotent`（重复提交 `duplicate=true`） | 通过 |
| 导入后操作日志可查 / 字段级审计可溯 | `test_user_definition_columns_and_validation` + `AuditCapturer.capture` 调用；落库归 06_01 / 06_02 | 本段边界通过，落库待 06 |
| 万行级不超时（异步 + 进度） | `test_async_submit_and_status` / `test_job_success_and_progress` | 通过（阈值以上异步、进度与状态可查） |
| 文件安全 | `test_file_extension_and_size` / `test_zip_security_limits` / `test_template_mismatch_and_row_limit` | 通过 |
| 幂等 release | `test_release_allows_retry` | 通过 |

> 本文档依《[任务文档规范](../../../../../../规范/任务文档规范.md)》编写 · 进度以阶段计划为唯一落点

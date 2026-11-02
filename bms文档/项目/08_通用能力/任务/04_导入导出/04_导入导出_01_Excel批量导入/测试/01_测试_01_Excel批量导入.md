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
| 执行方式 | 开发环 `scripts/tools/preflight/测试改动内容.py`（ruff + 六项护栏 + 定向 pyright + 定向选测）；推送前 `推送.py --check`（定向选测 + 覆盖率门禁）已全绿 |
| Kiwi 用例 | **2401**（模块级 `pytestmark = pytest.mark.kiwi_id(2401)`；一任务一条用例，文本列覆盖范围与自动化文件） |

## 2. 用例清单与执行结果 <a id="cases"></a>

新增自动化用例 **60 个**（平台导入域 36 + 基座 transfer 22 + 幂等 `release` 2），全部通过；定向集合 **56 passed**，开发环全量 **5148+ passed**；推送前覆盖率门禁 **37 文件 / 行 100% / 分支 100%**。

| 测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| `libs/bms_core/tests/transfer/test_openpyxl_importer.py` | 13 | 解析行号 / 空行跳过 / 表头错序 / 无数据行 / 类型与可选值校验 / 模板两 sheet / 错误明细 / zip 条目与解压上限 / 缺条目与路径 / 加密 / 坏 OOXML / 缺 sheet / 缺表头 / 尾空列头 / 日期单元格 / `from_limits` |
| `libs/bms_core/tests/transfer/test_import_definition.py` | 5 | 定义登记 / 重名非法 / 空列集 / 列键与标题重复 / 默认预取与写路径 / 批次工作单元 / 汇总字段 |
| `libs/bms_core/tests/transfer/test_import_source.py` | 2 | 对象 key 路径风格 / 读写删与缺失 |
| `libs/bms_core/tests/transfer/test_import_limits.py` | 2 | 代码默认 / 参数覆盖 / 非法与非正回落 |
| `services/platform/tests/import_export/test_import_api.py` | 17 | 模板 / 同步成功与幂等 / 全量原子 / 角色非法 / 表头与行数 / 扩展名、大小与坏内容 / 异步提交与状态 / 错误明细全分支 / 缺幂等键 / 未知业务 / 限流 / 业务写权限 / 处理中冲突 / release 异常 / 终态汇总 |
| `services/platform/tests/import_export/test_import_job.py` | 15 | 异步成功与进度 / 校验拒绝 / 源文件缺失 / 批次取消 / 写入失败 / 删除失败 / 角色成功（无审计）/ 配置源分支 / 定义无写权限 / 幂等作用域与负载解析 / 汇总与安全助手 |
| `services/platform/tests/import_export/test_import_definitions.py` | 4 | 用户 / 角色预取跳过非字符串与空值（空集早返回）/ 库内已存在 / 状态非法 |
| `libs/bms_core/tests/idempotency/test_idempotency_redis.py`（新增 2） | 2 | `release` 后同键可重试 / Redis 不可用 fail-closed（含 delete 直接抛 `RedisUnavailableError`） |
| `libs/bms_core/tests/transfer/test_transfer.py`（改动） | 1 | 依赖解析改为真实 `OpenpyxlImporter` |
| `libs/bms_core/tests/core/test_exception_constructors_paths.py`（改动） | 1 | `503xx` 十个异常构造路径 |
| 既有边界 / 作业 / 插件 / 发布用例（改动 5 处） | 5 | 域数 18、作业集合、handler 列表、导入器契约版本 `0.2.0`、结构就绪用例按有表域取样 |

**替身策略**：对象存储用本地临时目录（不连 MinIO）；幂等 / token 用 `MemoryCacheRegion` 与 `fakeredis`；作业用内存源文件与直接构造 `JobContext`，不启 worker；用户 / 角色写路径使用真实仓储与真实 SQLite 表。

## 3. 覆盖率 <a id="coverage"></a>

- 开发环不采集覆盖率；推送前 `推送.py --check` 已执行覆盖率门禁；
- 结果：**37 个模块 / 行 100.00% / 分支 100.00%**（缺行 0、缺分支 0）；
- 口径：新增 / 改动模块 100% 行 + 分支（《[测试规范](../../../../../../规范/测试规范.md)》）；防御性分支（鉴权路由下不可达的用户为空、openpyxl 读取自动补齐短行）以 `# pragma: no cover` 显式标注理由。

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

# Excel 批量导入实施记录

> 通用能力 · 04 导入导出 · 01 Excel 批量导入 · 实施记录

[文档首页](../../../../../../文档首页.md) › [08 通用能力](../../../../README.md) › [导入导出](../../04_导入导出.md) › [Excel 批量导入](../04_导入导出_01_Excel批量导入.md) › 实施　|　[详细设计](../设计/01_详细设计_01_Excel批量导入.md) · [测试记录](../测试/01_测试_01_Excel批量导入.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 Excel 批量导入](../04_导入导出_01_Excel批量导入.md) |
| 对应需求 | [02-2](../../../../需求/02_需求_文件与导入导出.md#r02-2) |
| 详细设计 | [01_详细设计_01_Excel批量导入](../设计/01_详细设计_01_Excel批量导入.md) |
| 实施日期 | 2026-11-02 |
| 实施范围 | 基座 Excel 引擎 / 平台导入域 / users + roles 定义 / 同步与异步 / 幂等 / 错误明细 / 配置与错误码 |
| Kiwi 用例 | **2401**（模块级 `pytestmark = pytest.mark.kiwi_id(2401)`） |

## 2. 实施概览 <a id="overview"></a>

本段把「Excel 批量导入」从契约占位做成可运行通道：通用引擎与定义契约落 `bms_core`，业务写入经所有者域服务，平台只做编排与接口。

| 批次 | 内容 | 落点 |
| --- | --- | --- |
| 1 | 基座契约：`ColumnSpec` 扩展、`ParsedRow` / `parse_rows` / `validate_rows`、`OpenpyxlImporter`、`openpyxl_io`、`NullImporter` | `libs/bms_core/src/bms_core/transfer/` |
| 2 | 定义与装配：`BaseImportDefinition` / 注册表 / 批次工作单元、`ImportSourceStore`、`ImportLimits` | `transfer/definition.py`、`transfer/source.py`、`transfer/limits.py` |
| 3 | 基座配套：`503xx` 错误码 + 异常、`import.*` 默认参数、`[importer]` 配置、幂等 `release`、失败作业 `result` 摘要 | `core/error_codes.py`、`core/exceptions.py`、`config/seed.py`、`idempotency/`、`jobs/runner.py` |
| 4 | 平台导入域：模板 / 执行 / 状态 / 错误明细、同步内联与异步提交、幂等与限流 | `domains/import_export/` |
| 5 | 业务定义：`users`（复用 `UserAdminService`）与 `roles`（复用 `RoleService`）、服务根装配、作业登记 | `domains/user/imports.py`、`domains/role/imports.py`、`imports.py`、`jobs.py` |
| 6 | 登记与契约：`platform.toml` / `domain_layout.json` / `contracts/platform.json`、文档与记录 | `deploy/`、`bms文档/` |

## 3. 实施过程 <a id="process"></a>

| 批次 | 验证 | 结果 |
| --- | --- | --- |
| 1~2 | `pytest libs/bms_core/tests/transfer` | 通过（新增 openpyxl / 定义 / 源文件 / 参数用例） |
| 3 | `pytest libs/bms_core/tests/idempotency libs/bms_core/tests/core/test_exception_constructors_paths.py` | 通过（release 与异常构造表齐备） |
| 4~5 | `pytest services/platform/tests/import_export` | 通过（同步 / 异步 / 幂等 / 错误明细 / 限流 / 权限） |
| 6 | `engkit links` / `docs-scope` / `eol`；`ops.contract_snapshot export/check` | 通过 |

**开发环**：`scripts/tools/preflight/测试改动内容.py`（Windows 侧用后端 venv Python 启动，确保 pyright 指向同一解释器）最终 **3626 passed / 12 skipped**；ruff check / format、集合声明 / 雪花 ID / 测试库隔离 / 产品字面量 / 服务边界 / 工作区卫生、定向 pyright 全过。

## 4. 问题与处置 <a id="issues"></a>

| # | 现象 | 根因 | 处置 |
| --- | --- | --- | --- |
| 1 | inline 作业报「导入源文件不存在」 | API 依赖覆盖对象存储到 `tmp_path`，作业侧按 `settings.storage.options.root` 另起实例 | 测试同时设置 `BMS_STORAGE__OPTIONS__ROOT`；生产同一 `[storage]` 根，语义一致 |
| 2 | 写入报「A transaction is already begun on this Session」 | `UserAdminService.create_user` / `RoleService.create_role` 内部各自 `uow.begin()`，与外层批次事务冲突 | 新增 `ImportBatchUnitOfWork`（`begin` 并入外层、`commit`/`rollback` 空操作）；批次统一用 `session.begin_nested()` |
| 3 | 非法邮箱未在预检阶段拦下，落到写失败 | `ImportExecutor.validate` 只跑业务定义，漏了导入器通用校验 | 先 `BaseImporter.validate_rows` 再做业务 `validate_row`，两类错误合并 |
| 4 | 错误明细 token 查不到 | `token_payload` 是 `ConcurrentStableDict`（`Mapping`，非 `dict` 子类），`isinstance(raw, dict)` 判假 | 改判 `Mapping` |
| 5 | 对象 key 含冒号，Windows 本地存储写入失败 | 初版 key 用 `bms:{tenant}:imports:source:{token}`，冒号在 Windows 非法 | 改路径风格 `{tenant|global}/imports/source/{token}.xlsx`，设计同步回写 |
| 6 | 静态护栏报「仅继承内建基类」 | 内部异常 `_ColumnInvalid` / `_RowInvalid` / xlsx 异常 / `ImportCanceled` 直接继承 `Exception` / `ValueError` | 内部列 / 行异常改继承 `ParamError`；xlsx 异常继承导入段位异常；取消改用 `asyncio.CancelledError` |
| 7 | 业务边界 / 作业 / 插件既有断言计数不符 | 新增域、作业类型与导入器契约版本 `0.2.0` | 同步更新边界域数 18、作业集合、handler 列表与端口版本断言 |

## 5. 验证结果 <a id="verify"></a>

- **开发环**：3626 passed / 12 skipped；ruff / pyright / 六项护栏全过（见上）。
- **契约快照**：`ops.contract_snapshot export` 后 `check` 通过（9 个服务快照与公开契约一致）。
- **接口**：`GET /api/v1/imports/{biz}/template`、`POST /api/v1/imports/{biz}/execute`、`GET /api/v1/imports/{biz}/jobs/{job_id}`、`GET /api/v1/imports/{biz}/error-report/{token}` 已进 `platform.json`。
- **未做**：覆盖率门禁（开发环不采集，推送前由推送环执行）；真对象存储 / 真 Redis 集成（单测用本地存储 + `fakeredis`）。

## 6. 登记回写 <a id="registry"></a>

| 文档 | 回写内容 |
| --- | --- |
| 《概要设计 · 导入导出》 | 全量原子、汇总字段、源文件与作业、状态 / 错误明细端点、权限、`503xx` |
| 《概要设计 · 角色管理》 | 批量导入入口、3 列模板、仅 `custom`、不做权限分配 |
| 《架构设计 · 接口与集成》 | 已发布码位补 `50301`~`50310` |
| 《架构设计 · 文件管理》 | Excel 导入通道与源文件落点 |
| 《数据库设计 · 异步作业中心》 | 导入 `run_inline` / 异步 / `sys_job_error` 口径、失败作业 `result` 摘要 |
| 《后端基类清单》/《后端基类实现契约》 | `BaseImporter` 新方法、`ColumnSpec` 字段、导入定义 / 源文件 / 参数 / openpyxl 实现、幂等 `release` |
| 《命名规范》§10 | 对象 key `{tenant}/imports/source/{token}.xlsx`、Redis `bms:{tenant}:imports:report:{token}` |
| [需求 02-2](../../../../需求/02_需求_文件与导入导出.md#r02-2) | 交付注块（Kiwi 2401 / 全量原子 / 遗留归口） |
| [阶段计划](../../../../计划/01_计划_通用能力.md) | 04_01 归档 §2、移出 §3、后续窗口按计划表顺延 |

## 7. 偏差与遗留 <a id="deviations"></a>

1. **语义偏差（用户拍板）**：需求原文「落库阶段按行事务 / 部分成功」改为**全量原子 + 整批一个事务 / savepoint**；响应新增 `committed` / `blocked_count`，非法行绝不落库。
2. **前端未做**：导入对话框、菜单 / 按钮种子、i18n 文案归阶段十五；本段接口可直调验收。
3. **操作日志未落库**：本段只到 `AuditCapturer.capture` 边界；`sys_operation_log` 中间件与字段级审计表归 06_01 / 06_02。
4. **源文件孤儿**：作业 `finally` 删除；进程崩溃或删除失败会留孤儿对象，暂不做定时回收。
5. **长事务**：单次上限 50000 行、全量原子、整批事务，极端批量可能长持锁；真库出现瓶颈时再评估 staging 表 / 分批标记。
6. **产品仓接入**：mdm / biz / cw 按同一 `BaseImportDefinition` 契约在各服务根装配；本段只验证平台 users / roles。

> 本文档依《[任务文档规范](../../../../../../规范/任务文档规范.md)》编写 · 进度以阶段计划为唯一落点

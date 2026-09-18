# minio 实现与双实现纳管测试记录

> 后端插件化 · 04 首个能力与阶段验收 · 01 对象存储接入验证 · 04-1-1 minio 实现与双实现纳管 · 测试记录

[文档首页](../../../../../../../文档首页.md) › [04-1-1 minio 实现与双实现纳管](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md) › 01 测试　|　[← 父任务](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04-1-1 minio 实现与双实现纳管](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md) |
| 对应需求 | [04-1](../../../../../需求/04_需求_首个能力与阶段验收.md#r04-1) |
| 详细设计 | [01_详细设计_01_minio实现与双实现纳管](../设计/01_详细设计_01_minio实现与双实现纳管.md) |
| 实施记录 | [01 实施记录](../实施/01_实施_01_minio实现与双实现纳管.md) |
| 父任务测试记录 | [01 测试记录](../../测试/01_测试_01_对象存储接入验证.md) |
| 测试日期 | 2026-09-15 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7） |
| Kiwi 用例 | 662 |
| 结论 | 通过 |

## 2. 测试范围与用例 <a id="scope"></a>

自动化文件：`backend/tests/storage/test_storage.py`（`@pytest.mark.kiwi_id(662)`）；MinIO 交互面全部走假客户端 / 假异常（不连通、不依赖服务）。

| Kiwi | 用例（函数） | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 662 | `test_minio_module_import_is_lazy` | 单元 | 构造实例不导入 SDK（`sys.modules` 无 `minio*`） |
| 662 | `test_minio_rejects_missing_config` | 集成 | 端点 / 凭据缺失 → lifespan 装配 `PluginError`（`match="端点 / 凭据"`） |
| 662 | `test_minio_secret_not_leaked` | 集成 | 哨兵私钥注入后启动日志与 `/api/v1/plugins` 响应均不含 |
| 662 | `test_minio_client_methods_with_stub` | 单元 | 假客户端：写入 / 回读 / 存在 / 幂等删除 / 未命中 `NotFoundError` / presign GET·PUT 分派 |

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ uv run pytest tests/storage -q
14 passed

$ uv run pytest --cov=app --cov-branch -q
544 passed, 7 skipped

$ uv run ruff check . && uv run ruff format --check . && uv run pyright
All checks passed! / 274 files already formatted / 0 errors, 0 warnings, 0 informations
```

结果汇总：延迟导入 / 缺配置拒启 / 密钥分离 / 方法映射四组用例全部通过；`minio` 依赖已装（dev 组）但测试不建连、不依赖外部服务。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 原因 | 处置与落点 |
| --- | --- | --- |
| 假异常需匹配 SDK 类型 | 实现按 `minio.error.S3Error` 捕获 | monkeypatch 该符号为带 `code` 的假类（实施记录 §4 已记） |

## 5. 覆盖率 <a id="coverage"></a>

- `app/storage/minio.py` 方法路径经假客户端覆盖；真实 SDK 网络路径不计（阶段八实测）。
- 全量快照 TOTAL 99%。

## 6. 偏差与遗留 <a id="deviations"></a>

- 真实连通 E2E（服务可达 / 桶策略 / 端到端上传下载）随后续文件管理。
- 缺依赖拒启路径与缺配置同法（工厂校验），本次以缺配置路径实测。

> 本文档依《文档生成规范》编写

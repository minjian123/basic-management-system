# minio 实现与双实现纳管实施记录

> 后端插件化 · 04 首个能力与阶段验收 · 01 对象存储接入验证 · 04-1-1 minio 实现与双实现纳管 · 实施记录

[文档首页](../../../../../../../文档首页.md) › [04-1-1 minio 实现与双实现纳管](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md) › 01 实施　|　[← 父任务](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04-1-1 minio 实现与双实现纳管](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md) |
| 对应需求 | [04-1](../../../../../需求/04_需求_首个能力与阶段验收.md#r04-1) |
| 详细设计 | [01_详细设计_01_minio实现与双实现纳管](../设计/01_详细设计_01_minio实现与双实现纳管.md) |
| 实施日期 | 2026-09-15 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7） |
| 提交 | `3924884`（feat(storage)：04-1 对象存储双实现，含本嵌套交付） |
| 结论 | 完成（Kiwi 662） |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[MinioObjectStorage<br/>顶层不导入 SDK] --> B[惰性客户端<br/>to_thread 包装同步调用]
    B --> C[工厂校验<br/>依赖 + 端点 / 凭据]
    C --> D[object_storage:minio 登记<br/>清单 registered]
    D --> E[密钥分离断言<br/>启动 / 清单 / 日志]
```

结果小结：`MinioObjectStorage` 落 `app/storage/minio.py`——延迟导入（构造实例不拉 SDK）、惰性客户端、同步 SDK 经 `asyncio.to_thread`；`NoSuchKey → NotFoundError`、删除幂等、`presign` GET/PUT 分派；工厂校验 SDK 依赖与端点 / 凭据（`PluginError` 可读）；桶名统一 `[storage].options.bucket`（缺省 `bms-files`）；`[minio].bucket` 注记废弃；可选依赖组 `storage-minio` + dev 组引入。

## 3. 实施过程 <a id="process"></a>

1. **实现模块**：顶层仅标准库与域契约导入；`_ensure_client` 内 `from minio import Minio`；`_put_sync` / `_get_sync` / `_delete_sync` / `_exists_sync` 线程内执行（响应体 `close` / `release_conn` 兜底）。
2. **工厂校验（不连通）**：`import_module("minio")` 失败 → `PluginError`（提示 `uv sync --extra storage-minio`）；端点 / `access_key` / `secret_key` 任一为空 → `PluginError`（信息可读、不含密钥值）；通过即构造（不建连）。
3. **配置口径**：桶名读 `[storage].options.bucket`；`config.toml [minio]` 注释同步（`bucket` 废弃、凭据经 `BMS_MINIO__*` 注入）。
4. **依赖组**：`uv add --optional storage-minio "minio>=7.2"` + `uv add --group dev "minio>=7.2"`（实测 minio 7.2.20；清华镜像）。
5. **纳管与用例**：契约快照自动多出 `object_storage:minio`；清单状态 `registered`；用例覆盖延迟导入 / 缺配置拒启 / 密钥分离 / 假客户端方法映射（Kiwi 662）。

关键命令：

```bash
uv run pytest --cov=app --cov-branch -q
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

## 4. 问题与处置 <a id="issues"></a>

| 问题 / 现象 | 原因 | 处置与落点 |
| --- | --- | --- |
| minio 用例受默认注册表工厂缓存影响（自定义 settings 不生效） | `register_platform_plugins` 按注册表身份幂等 | 用例改隔离注册表注入（与 02-2 同法） |
| 假客户端异常需为 `minio.error.S3Error` 实例 | 实现按 SDK 异常类捕获 | 测试 monkeypatch `minio.error.S3Error` 为带 `code` 的假类 + 假客户端 |
| `pyright` 假客户端 lambda 参数类型未知（strict） | 匿名函数参数 | 改带注解的闭包函数 |

## 5. 验证结果 <a id="verify"></a>

| 完成标准 | 验证方法 | 实测结果 |
| --- | --- | --- |
| 延迟导入可证 | 构造实例前后 `sys.modules` 无 `minio*` | 通过 |
| 缺依赖 / 缺配置拒启 | 工厂校验（`PluginError` 可读） | 通过（缺配置路径实测；缺依赖路径同法） |
| 密钥分离 | 哨兵经 `BMS_MINIO__SECRET_KEY` 注入 → 启动 / 清单 / 日志不含 | 通过 |
| 方法映射正确 | 假客户端（不连通）：未命中转错 / 幂等删除 / presign 分派 | 通过 |
| 双实现纳管 | 快照 + 清单断言 | 通过（`minio` registered） |
| 全量绿 | 验证命令 | 544 passed / 7 skipped；ruff / pyright 0 |

## 6. 偏差与遗留 <a id="deviations"></a>

- 真实连通（服务可达 / 桶策略）与端到端上传下载随后续文件管理。
- `[minio].bucket` 键位保留兼容（注记废弃），清理随后续版本。

> 本文档依《文档生成规范》编写

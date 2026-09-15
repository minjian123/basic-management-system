# minio 实现与双实现纳管详细设计

> 后端插件化 · 04 首个能力与阶段验收 · 01 对象存储接入验证 · 04-1-1 minio 实现与双实现纳管 · 详细设计

[文档首页](../../../../../../../文档首页.md) › [04-1-1 minio 实现与双实现纳管](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md) › 01 详细设计　|　[← 父任务](../04_首个能力与阶段验收_01_对象存储接入验证_01_minio实现与双实现纳管.md)

## 1. 概述 <a id="overview"></a>

- **目标**：`MinioObjectStorage` 落 `app/storage/minio.py`——**延迟导入**（模块导入不拉 SDK）、端点 / 凭据取 `settings.minio`（密钥分离）、桶名统一 `[storage].options.bucket`；工厂登记 `object_storage:minio`；双实现（`local` / `minio`）纳入契约套件与插件清单。
- **范围**：`app/storage/minio.py`、`[minio].bucket` 口径收敛、可选依赖组登记、密钥分离与延迟导入验证。
- **不含**：MinIO 真实连通 E2E（随阶段八文件管理）；分片 / 断点续传。
- **依据**：[需求 04-1](../../../../../需求/04_需求_首个能力与阶段验收.md#r04-1)、《架构设计 · 扩展点与插件化》「配置驱动装配」节（延迟导入 / 密钥分离）、《安全开发规范》「密钥与脱敏」节、《[04-1 详细设计](../../设计/01_详细设计_01_对象存储接入验证.md)》。

## 2. 现状与差距 <a id="gap"></a>

| 现状 | 差距 |
| --- | --- |
| `MinioSettings`（`endpoint` / `access_key` / `secret_key` / `bucket` / `secure`）已预留 | 无实现；`bucket` 与 `STORAGE_BUCKET` 口径不一致 |
| 无 minio 依赖（可选组未登记） | 缺 SDK 的拒启路径与延迟导入断言缺失 |

## 3. 交付物清单 <a id="tree"></a>

```text
backend/app/storage/minio.py        # 新增：MinioObjectStorage（延迟导入；SDK 同步调用经 to_thread）
backend/app/core/assembly.py        # 修改：登记 object_storage:minio 工厂（工厂内校验依赖与配置）
backend/config.toml                 # 修改：[minio] 注释（bucket 废弃）；[storage].options 注释（bucket 口径）
backend/pyproject.toml              # 修改：optional-dependencies storage-minio + dev 组引入
backend/tests/storage/test_storage.py  # 修改：minio 延迟导入 / 缺配置拒启 / 缺依赖拒启 / 密钥分离
```

## 4. 设计 <a id="design"></a>

### 4.1 MinioObjectStorage

```python
class MinioObjectStorage(BaseObjectStorage):
    """MinIO 对象存储：延迟导入 SDK；端点 / 凭据取 settings.minio，桶名取 options.bucket。"""
    def __init__(self, *, endpoint: str, access_key: str, secret_key: str,
                 bucket: str = STORAGE_BUCKET, secure: bool = False) -> None: ...
```

| 项 | 口径 |
| --- | --- |
| 延迟导入 | `app/storage/minio.py` 顶层**不** `import minio`；方法内 / 惰性客户端构造时导入（模块导入不拉 SDK） |
| 客户端 | 惰性构造（首次调用时 `Minio(...)`）；SDK 为同步客户端 → 统一 `asyncio.to_thread` |
| `put` / `get` / `delete` / `exists` | `put_object` / `get_object`（`NoSuchKey` → `NotFoundError`）/ `remove_object`（幂等）/ `stat_object`（`S3Error` → False） |
| `presign` | `method=GET` → `presigned_get_object`；`PUT` → `presigned_put_object`（`expires_in` 透传） |
| 桶名 | `[storage].options.bucket`（缺省 `STORAGE_BUCKET = bms-files`）；`[minio].bucket` 不再读取（配置注释注记废弃，避免两处口径） |

### 4.2 工厂登记与启动校验（不连通）

- `register_plugin("object_storage", "minio", _minio_storage_factory(settings))`；工厂实例化时：
  1. `import_module("minio")` 失败 → `PluginError`（提示 `uv sync --extra storage-minio`）；
  2. `settings.minio.endpoint` / `access_key` / `secret_key` 任一为空 → `PluginError`（可读信息，不含密钥值）；
  3. 通过则构造实例（**不建连**；真实连通随阶段八），超时 / 探活不做。
- 缺省 `provider = local`，`minio` 工厂不实例化 → `minio` SDK 不被导入（延迟导入可证：`sys.modules` 断言）。

### 4.3 密钥分离

- `secret_key` 仅经环境变量 `BMS_MINIO__SECRET_KEY` 注入（配置文件保持空串）；启动日志不含 options（01-2 既有口径）；插件清单不含 `options`（01-3 既有口径）。
- 验证用例：注入哨兵密钥 → 启动 + `/api/v1/plugins` 响应 + 日志捕获均不含该哨兵串。

### 4.4 双实现纳管（零套件改动）

- 契约快照自动多出 `object_storage:local` / `object_storage:minio` 条目（工厂只读分支），03-1 套件无需改动；插件清单自动呈现 `local`（active）/ `minio` / `null`（registered）。

## 5. 测试设计（Kiwi 先行） <a id="tests"></a>

用例先登记 Kiwi（**一条**：延迟导入 / 校验拒启 / 密钥分离 / 纳管；平台实际登记 **662**）：

| Kiwi | 用例 | 断言要点 |
| --- | --- | --- |
| 662 | `test_minio_module_import_is_lazy` | 构造实例不导入 SDK（`sys.modules` 无 `minio*`）；快照含 `object_storage:minio` |
| 662 | `test_minio_rejects_missing_config` | 端点 / 凭据缺失 → `PluginError`（信息可读、不含密钥值） |
| 662 | `test_minio_secret_not_leaked` | 哨兵密钥经环境变量注入 → 启动 / 清单 / 日志不含哨兵 |
| 662 | `test_minio_client_methods_with_stub` | 以假客户端验证方法映射（无服务连通）：`NoSuchKey → NotFoundError` / `remove_object` 幂等 / presign 方法分派 |

（缺依赖拒启路径：SDK 未安装时断言 `PluginError` 提示安装；安装后该路径由缺配置用例覆盖——条件断言，不依赖外部服务。）

## 6. 实施步骤 <a id="steps"></a>

1. `app/storage/minio.py`（惰性 SDK + 方法映射 + 错误语义）。
2. 工厂登记 + pyproject 可选组 / dev 组 + config 注释同步。
3. 测试（延迟导入 / 拒启 / 密钥分离 / 假客户端方法）与纳管断言（Kiwi 先行登记）。
4. 验证：全量 `pytest` / `ruff` / `pyright` / `check_plugins`。
5. 回写：架构 10 代码结构、基类清单、任务 / 需求 / 计划状态与记录。

## 7. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| `minio` 落点 / 延迟导入 / 密钥分离可证 | `sys.modules` 断言 + 哨兵用例 + 工厂校验 |
| 双实现纳入契约套件与插件清单 | 快照参数化 + 清单响应断言 |
| `pytest` / `ruff` / `pyright` 全绿 | 验证命令输出 |

## 8. 边界与开放项 <a id="boundary"></a>

- 真实连通与桶策略 / 生命周期归阶段八；本任务不建连。
- `[minio].bucket` 废弃注记随后续版本清理（保留键位兼容环境变量覆盖）。
- SDK 版本下限：`minio>=7.2`（可选组约束）。

## 9. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 依赖引入 | 可选依赖组 `storage-minio`（dev 组引入供测试） |
| 2 | 启动校验 | 不连通：SDK 可导入 + 端点 / 凭据齐备 |
| 3 | 密钥分离 | 仅环境变量注入；启动 / 清单 / 日志三方断言 |
| 4 | 桶名口径 | `[storage].options.bucket`（缺省 `bms-files`）；`[minio].bucket` 注记废弃 |
| 5 | 测试编号 | 一条 Kiwi：**662**（平台实际登记） |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认

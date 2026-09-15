# 提供者改经 resolve_plugin 详细设计

> 后端插件化 · 02 能力域改造 · 02 提供者改经 resolve_plugin · 详细设计

[文档首页](../../../../../../文档首页.md) › [02 提供者改经 resolve_plugin](../02_能力域改造_02_提供者改经resolve_plugin.md) › 01 详细设计　|　[← 父任务](../02_能力域改造_02_提供者改经resolve_plugin.md)

## 1. 概述 <a id="overview"></a>

- **目标**：全部能力提供者 `get_xxx` 收口为薄封装——从配置（`app.state.settings`）取 provider、经 `resolve_plugin`（请求期只取缓存引用 + 主版本复核）返回实例；健康检查注册表完成插件化（拆真实实现 + 提取 `BaseProviderRegistry` 中间层基类）；消除绕过注册表的直连实现路径。
- **范围**：34 个提供者（32 同步 + `get_masker` 异步生成器 + `get_health_check_registry`）；`app/core/capability.py`（新基类）；`app/health/`（继承重构 + `local` 实现工厂）；`app/core/assembly.py`（登记签名扩展）；`app/main.py`；`config.toml`；`ops/check_plugins.py`。
- **不含**：其余 3 个域注册表（字段类型 / 查询 / 仪表盘）改继承 `BaseProviderRegistry`（归域三 [03-3](../../../../需求/03_需求_契约与收敛提取.md#r03-3)）；`BaseProvider` 提取（03-2）；平台内建实现（04-1）。
- **依据**：[需求 02-2](../../../../需求/02_需求_能力域改造.md#r02-2)、《架构设计 · 扩展点与插件化》「配置驱动装配」节、《[01_02 详细设计 · 配置分区与启动装配](../../../01_插件化基座/01_插件化基座_02_配置分区与启动装配/设计/01_详细设计_01_配置分区与启动装配.md)》、「01-2-1 详细设计」。

## 2. 现状与差距 <a id="gap"></a>

| 现状 | 差距 |
| --- | --- |
| 34 个提供者读 `request.app.state.<attr>`（装配结果） | 未按配置解析；配置切换对消费方不可见（同一实现路径） |
| 健康注册表由 `main.py` 手工构造（超时 + redis/database 检查项 + 资源登记） | 未入插件体系；`HealthCheckRegistry` 构造依赖运行时对象 |
| `BaseProviderRegistry` 缺位（域三 03-3 计划提取） | 健康迁移需要公共注册表实现（登记唯一性 / 未命中 / keys） |

## 3. 交付物清单 <a id="tree"></a>

```text
backend/
├── app/core/capability.py     # 新增：BaseProviderRegistry[ItemT] 中间层基类
├── app/health/base.py         # 修改：BaseHealthCheckRegistry 继承新基类（_provider_key/checks/aggregate）
├── app/health/registry.py     # 修改：HealthCheckRegistry 复用基类存储（真实实现，实现名 local）
├── app/health/null.py         # 修改：语义不变（register 空操作 / checks 空）
├── app/core/assembly.py       # 修改：register_platform_plugins(settings, app, resources) + health local 工厂
├── app/main.py                # 修改：app.state.settings；删健康注册表手工构造（探针注册移入工厂）
├── config.toml                # 修改：[health_check_registry] provider = "local"
├── app/<各域>/*.py            # 修改：33 个提供者薄封装（get_masker 保异步生成器）
├── ops/check_plugins.py       # 修改：以 create_app() 提供离线 app/resources 后登记平台实现
└── tests/crosscut/test_plugin_providers.py   # 新增：Kiwi 565 用例
```

## 4. 提供者薄封装口径 <a id="providers"></a>

统一模板（调用签名不变，`request` 参数保留；每请求主版本复核）：

```python
def get_object_storage(request: Request) -> BaseObjectStorage:
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseObjectStorage",
        resolve_plugin("object_storage", settings.storage.provider, expected_version=BaseObjectStorage.contract_version),
    )
```

- **settings 来源**：`app.state.settings`（`create_app` 落装配配置；与装配、CI 校验同源）。
- **`get_masker`**：保留异步生成器与 `current_masker` 上下文写入/复位，仅内部取值改 `resolve_plugin("masking", settings.masking.provider, …)`。
- **`get_health_check_registry`**：同样薄封装（见第 5 节）。
- 34 个提供者全覆盖；改造后提供者内不得再出现 `app.state.<能力属性>` 直读（护栏用例）。

## 5. 健康检查注册表插件化 <a id="health"></a>

### 5.1 中间层基类提取（`core/capability.py`）

```python
class BaseProviderRegistry[ItemT](BasePluggable, ABC):
    """提供者注册表中间层：唯一性登记 / 未命中语义 / keys 公共实现（聚合模板留各域）。"""

    def __init__(self) -> None: ...            # 保序 dict
    @classmethod
    @abstractmethod
    def _provider_key(cls, provider: ItemT) -> str: ...   # 注册项键（各域覆写）
    def register(self, provider: ItemT) -> None: ...      # 重复键 → ConflictError（不静默覆盖）
    def get(self, key: str) -> ItemT | None: ...          # 未命中 → None（各域聚合模板转 NotFoundError）
    def keys(self) -> tuple[str, ...]: ...
    def values(self) -> tuple[ItemT, ...]: ...            # 保序
```

- 语义与既有 3 个域注册表（`get → None`、保序 `keys`）对齐，供域三 03-3 直接复用；`BaseProvider`（03-2）提取另行。
- `register` 唯一性为新增约束（重复键 `ConflictError`，不静默覆盖）——健康检查项重名即拒。

### 5.2 健康域重构

| 落点 | 变化 |
| --- | --- |
| `BaseHealthCheckRegistry` | 继承 `BaseProviderRegistry[BaseHealthCheck]`；`_provider_key = check.name`；`checks()` 返回 `values()`；`aggregate` 模板保留 |
| `NullHealthCheckRegistry` | 语义不变：`register` 空操作、`checks()` 空元组（不探依赖、恒定就绪） |
| `HealthCheckRegistry`（真实实现） | 复用基类存储与唯一性；实现名 `local`，经**工厂**登记（超时取 `[health]` 配置、注册 `RedisHealthCheck`（并登记 `resources`）与 `DatabaseHealthCheck(engine_registry)`） |
| 工厂登记 | `register_platform_plugins(settings, app, resources)`（签名扩展）：masker + health `local`；装配与 CI 校验共用（CI 以 `create_app()` 提供离线 app/resources） |
| 配置 | `config.toml [health_check_registry] provider = "local"`（缺配置 → null；`/readyz` 由 local 保障真实探针） |

## 6. 测试设计（Kiwi 先行） <a id="tests"></a>

用例先登记 Kiwi（本任务登记 **Kiwi 565（平台登记为 565，自增顺延）**，平台自增顺延）；新增 `tests/crosscut/test_plugin_providers.py`：

| Kiwi | 用例 | 断言要点 |
| --- | --- | --- |
| 535 | 提供者经注册表解析 | probe 路由经 `Depends(get_object_storage)` 取到的实例与 `resolve_plugin` 同一（且与 `app.state` 同实例） |
| 535 | 配置切换零改动 | 隔离注册表 + 自定义 `Settings(storage.provider="custom")`：既有路由（消费方代码未改）返回自定义实现 |
| 535 | 健康注册表插件化 | `/readyz` 保留真实探针（`local` 注册表含 `redis` / `database` 检查项）；`null` 仍登记；解析同实例 |
| 535 | 基类语义 | `register` 重名 `ConflictError`；`get` 未命中 `None`；`keys` 保序 |
| 535 | 直连残留护栏 | 扫描 34 个提供者源码：均含 `resolve_plugin(`，且不含 `app.state.<能力属性>` 直读 |
| 535 | masker 上下文 | `get_masker` 异步生成器写入 / 复位 `current_masker`（既有行为回归） |

- 覆盖率：`core/capability.py` / `assembly.py` / `plugin.py` 保持 100%；全量回归。

## 7. 实施步骤 <a id="steps"></a>

1. `core/capability.py` 落 `BaseProviderRegistry[ItemT]`（导出登记）。
2. 健康域重构（base / registry / null）；`assembly.py` 签名扩展 + health `local` 工厂；`main.py` 删手工健康构造、加 `app.state.settings`；`config.toml` 分区。
3. 33 个提供者薄封装（含 `get_masker`）；`ops/check_plugins.py` 同步（离线 app）。
4. Kiwi 565（平台登记为 565，自增顺延） 登记 → 新增用例；`test_health_registry` / 集成用例回归。
5. 验证：全量 `pytest` / `ruff` / `pyright`；`python -m ops.check_plugins`。
6. 回写：01_02 设计（登记签名 + 健康口径）、基类清单 / 架构 04（`BaseProviderRegistry` 提前交付登记、03-3 边界）；任务 / 需求 / 计划状态与记录。

## 8. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| 切换 provider 后消费方零改动 | 配置切换用例（既有路由 + 自定义 Settings） |
| 34 个提供者全部经 `resolve_plugin` | 直连残留护栏用例 |
| 无绕过注册表的直连实现 | 护栏扫描（提供者源码） |
| `pytest` / `ruff` / `pyright` 全绿 | 验证命令输出 |

## 9. 边界与开放项 <a id="boundary"></a>

- 域三 03-3：其余 3 个域注册表（字段类型 / 查询 / 仪表盘）与各自 `Null` 注册表改继承 `BaseProviderRegistry`；聚合模板留域；本次只交付基类与健康域，避免边界混杂。
- 域三 03-2：`BaseProvider`（注册项契约）提取另行；本次以 `_provider_key` 钩子兼容 `BaseHealthCheck.name` 与各域 `key`。
- 平台内建实现（`storage/local.py` / `storage/minio.py`）经工厂登记 → 04-1；`get_masker` 的真实实现随 RBAC 阶段。

## 10. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 提供者口径 | 薄封装（settings 取 `app.state.settings`；`expected_version` 每请求复核；`request` 参数保留） |
| 2 | 健康注册表 | 拆真实实现 + 提取 `BaseProviderRegistry`；`local` 工厂注入超时 / 检查项 / 资源；`config.toml` 显式 `provider = "local"` |
| 3 | 基类边界 | `BaseProviderRegistry` 本次随 02-2 提前交付；其余 3 注册表归 03-3 |
| 4 | 登记签名 | `register_platform_plugins(settings, app, resources)`（01_02 设计口径回写） |
| 5 | 测试编号 | Kiwi 565（平台登记为 565，自增顺延）（平台自增顺延） |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认

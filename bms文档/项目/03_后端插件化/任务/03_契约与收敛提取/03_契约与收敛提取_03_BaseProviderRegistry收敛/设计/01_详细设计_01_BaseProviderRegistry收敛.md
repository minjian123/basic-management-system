# BaseProviderRegistry 收敛详细设计

> 后端插件化 · 03 契约与收敛提取 · 03 BaseProviderRegistry 收敛 · 详细设计

[文档首页](../../../../../../文档首页.md) › [03 BaseProviderRegistry 收敛](../03_契约与收敛提取_03_BaseProviderRegistry收敛.md) › 01 详细设计　|　[← 父任务](../03_契约与收敛提取_03_BaseProviderRegistry收敛.md)

## 1. 概述 <a id="overview"></a>

- **目标**：其余 3 个域注册表（字段类型 / 查询提供者 / 仪表盘卡片）改继承 `BaseProviderRegistry[ItemT]`，删除各自重复的 `register` / `get` / `keys` 实现；`Null` 注册表同步收敛（**改真实登记**，唯一性拒重与其余域一致）；唯一性断言以独立清单开启（4 域）；聚合模板（校验 / 查询 / 元数据 / 取数）留各域不变。
- **范围**：3 域 `base.py` / `null.py`；3 域测试替身与 contracts 套件适配；架构 04 / 基类清单登记回写。
- **不含**：健康检查注册表（已随 02-2 接入；其 `Null` 保留 no-op 登记语义——聚合不探依赖）；真实域实现（字段类型 / 查询 / 卡片的真实提供者随对应能力阶段）。
- **依据**：[需求 03-3](../../../../需求/03_需求_契约与收敛提取.md#r03-3)、《[03-1-1 详细设计](../../03_契约与收敛提取_01_契约测试基座/03_契约与收敛提取_01_契约测试基座_01_域注册表与实现覆盖/设计/01_详细设计_01_域注册表与实现覆盖.md)》、《架构设计 · 后端基础类体系》「基类候选」节、《后端基类清单》候选表。

## 2. 现状与差距 <a id="gap"></a>

| 现状 | 差距 |
| --- | --- |
| 3 域注册表基类各自 `(BasePluggable, ABC)` 并声明抽象 `register` / `get` / `keys`；`Null` 各自实现存储与三方法 | 与健康域（`BaseProviderRegistry` 公共实现）语义同构、代码重复 |
| `Null` 注册表 `register` 为 no-op、`keys` 恒空 | 唯一性拒重缺位（重名静默丢弃）；与插件注册表「重名拒」口径不一致 |
| 03-1-1 契约清单以 `uniqueness` 开关标记「3 域待 03-3 翻转」 | 断言开关与域语义耦合，翻转即结构变动 |

## 3. 交付物清单 <a id="tree"></a>

```text
backend/app/{fieldtype,query,dashboard}/base.py    # 3 基类改继承 BaseProviderRegistry；删抽象 register/get/keys（聚合模板保留）
backend/app/{fieldtype,query,dashboard}/null.py    # Null 删 register/get/keys 覆写；实现 _provider_key（登记改真实）
backend/tests/{fieldtype,query,dashboard}/test_*.py  # 内存替身删重复实现（改继承）；断言适配
backend/tests/contracts/support.py                 # Memory* 替身收敛；RegistryContract 去 uniqueness；新增唯一性独立清单
backend/tests/contracts/test_domain_registry_contracts.py  # 唯一性断言改独立清单；Null 登记语义适配
```

## 4. 设计 <a id="design"></a>

### 4.1 3 域基类改继承（抽象性保持）

```python
class BaseFieldTypeRegistry(BaseProviderRegistry[BaseFieldType], ABC):
    """字段类型注册表契约：注册 / 解析 / 清单（公共实现继承） + 校验与类型映射聚合（模板留域）。"""

    key: str = "field_type_registry"
    plugin_key: str = "field_type_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def validate(...) -> tuple[str, ...]: ...       # 聚合模板（保留，改走继承的 get）
    def column_type(...) -> str: ...
```

- 基类不再声明 `register` / `get` / `keys`（由 `BaseProviderRegistry` 提供）；`values()` 随基类可用。
- **不可实例化**：`_provider_key` 抽象由中间层承载，基类不实现 → 基类保持抽象、不会作为可实例化实现误登记进插件注册表（口径同健康域）。

### 4.2 `Null` 注册表收敛（改真实登记）

| 项 | 原 | 收敛后 |
| --- | --- | --- |
| `register` | no-op | 继承基类（真实登记、重名 `ConflictError`） |
| `get` / `keys` | 各自实现（恒 `None` / 恒空） | 继承基类（未命中 `None` / 注册顺序） |
| `_provider_key` | 无 | 实现（统一取 `provider.key`） |
| 聚合模板 | 恒过 / 固定映射 / 空结果 / 空卡片 | **不变**（特性留域） |

- 「`Null` 无副作用」口径收窄为**聚合语义**（不探依赖 / 恒过 / 空结果）；登记行为与其余实现一致（唯一性拒重）。
- 影响面：装配层当前不向 3 域 Null 注册表登记；后续真实提供者接入时由域基类统一拒重。
- 健康 `Null` 注册表（`NullHealthCheckRegistry`）**不在本任务范围**：保留 no-op 登记与空集聚合（`/readyz` 不探依赖语义）。

### 4.3 唯一性断言独立清单（契约套件）

```python
UNIQUENESS_REGISTRIES: tuple[tuple[str, Callable[[], object]], ...] = (
    ("fieldtype", NullFieldTypeRegistry),   # 收敛后 register 真实拒重
    ("query", NullQueryProviderRegistry),
    ("dashboard", NullDashboardCardRegistry),
    ("health", HealthCheckRegistry),        # 02-2 已接入
)
```

- `RegistryContract` 去掉 `uniqueness` 字段（域语义不与断言开关耦合）；空集变体断言仍由 `REGISTRY_CONTRACTS` 承载。
- 唯一性用例：逐清单构造注册表 → 同键注册两次 → `ConflictError`（与插件注册表同异常类型，口径对齐）。
- 登记项用既有测试替身（`TextFieldType` / `DictQueryProvider` / `TodoCardProvider` / `NamedCheck`），键各异、互不冲突。

### 4.4 测试替身收敛

- 3 域测试 `_InMemoryRegistry` 与 contracts `Memory*`：删除 `_providers` 存储与 `register` / `get` / `keys` 重复实现，改继承基类公共实现；新增 `_provider_key`（取 `provider.key`）。
- 既有断言（聚合委托 / 未命中转 `NotFoundError` / 枚举）不变，验证「新基类与旧语义等价」。

## 5. 测试设计（Kiwi 先行） <a id="tests"></a>

用例先登记 Kiwi（**一条**：域注册表唯一性口径对齐与 Null 真实登记；平台自增顺延，以实际登记为准）→ 扩展 `tests/contracts/test_domain_registry_contracts.py`：

| Kiwi | 用例 | 断言要点 |
| --- | --- | --- |
| 待登记 | `test_uniqueness_registries_reject_duplicates` | 4 域清单：同键二次登记 → `ConflictError`（与插件注册表语义一致） |
| 待登记 | `test_null_registry_registers_really` | 3 域 `Null`：登记后 `keys()` / `get` 反映、聚合模板仍恒过 / 空结果 |

## 6. 实施步骤 <a id="steps"></a>

1. 3 域基类改继承（删抽象三方法；`BaseProviderRegistry` 导入换 `app/core/provider.py`）。
2. 3 域 `Null` 收敛（删覆写、加 `_provider_key`）。
3. 测试替身收敛 + 契约套件唯一性独立清单（Kiwi 先行登记）。
4. 验证：`pytest`（域用例 / 契约套件 / 全量）、`ruff`、`pyright`、`check_plugins`。
5. 回写：03-1-1 设计（唯一性清单与 Null 语义）、架构 04 / 基类清单、任务 / 需求 / 计划状态与记录。

## 7. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| 4 个域注册表收敛且行为不变 | 既有域用例 + 契约套件全绿（聚合模板不变） |
| 插件注册表语义口径对齐 | 唯一性独立清单（`ConflictError`）/ 未命中 `None` 断言 |
| 全量 `pytest` / `ruff` / `pyright` 通过 | 验证命令输出 |
| 文档登记同步 | 架构 04 / 基类清单 diff |

## 8. 边界与开放项 <a id="boundary"></a>

- 3 域真实注册实现（含真实提供者）随对应能力阶段；本任务只收敛基类与 `Null`。
- 健康 `Null` 登记语义保持 no-op（与 3 域不同，属既有口径；如需统一另行登记）。
- `Null` 登记改真实后，「无副作用」断言范围收窄——03-1-1 设计与记录同步回写。

## 9. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | `Null` 登记口径 | 3 域改**真实登记**（重名 `ConflictError`）；健康 `Null` 维持 no-op |
| 2 | 唯一性断言 | **独立清单**（4 域），`RegistryContract` 去 `uniqueness` 开关 |
| 3 | 基类抽象性 | 保留 `_provider_key` 抽象（基类不可实例化，防误登记） |
| 4 | 测试替身 | 删重复实现改继承（验证语义等价） |
| 5 | 测试编号 | 一条 Kiwi（平台自增顺延，以实际登记为准） |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认

# BaseProvider 提取详细设计

> 后端插件化 · 03 契约与收敛提取 · 02 BaseProvider 提取 · 详细设计

[文档首页](../../../../../../文档首页.md) › [02 BaseProvider 提取](../03_契约与收敛提取_02_BaseProvider提取.md) › 01 详细设计　|　[← 父任务](../03_契约与收敛提取_02_BaseProvider提取.md)

## 1. 概述 <a id="overview"></a>

- **目标**：提取注册项公共契约 `BaseProvider(BaseCapability)`（抽象 `key` + 抽象 `describe` 元信息），4 类提供者（`BaseFieldType` / `BaseQueryProvider` / `BaseDashboardCardProvider` / `BaseHealthCheck`）改继承；`BaseProviderRegistry` 随契约归位 `app/core/provider.py`（`registry.py` 保留过渡导出）；提供者保持**组合轨**（不经继承自动登记）。
- **范围**：`app/core/provider.py`（新增）；4 个端口基类、健康检查项、测试替身与用例适配；`app/core/registry.py` 过渡导出；登记回写（架构 04 / 基类清单）。
- **不含**：其余 3 个域注册表收敛（归 03-3，注册表 `_provider_key` 统一到 `.key` 随其推进）；聚合模板行为（不变）。
- **依据**：[需求 03-2](../../../../需求/03_需求_契约与收敛提取.md#r03-2)、《架构设计 · 后端基础类体系》「基类候选」节、《[后端基类清单](../../../../../../后端基类清单.md)》候选表、《架构设计 · 扩展点与插件化》「基类承载与双轨」节、《[03-1 详细设计](../../03_契约与收敛提取_01_契约测试基座/设计/01_详细设计_01_契约测试基座.md)》。

## 2. 现状与差距 <a id="gap"></a>

| 现状 | 差距 |
| --- | --- |
| 4 类提供者各自 `class BaseXxx(BaseObject, ABC)` 并各自声明抽象 `key`（健康为抽象 `name`） | 注册项契约形似而神散；无统一元信息（`describe`） |
| 实现类 16 个（app 3：`NullQueryProvider` / `RedisHealthCheck` / `DatabaseHealthCheck`；测试替身 13 个） | 键名不一致（`key` / `name`）；无元信息可断言 |
| `BaseProviderRegistry` 落 `app/core/registry.py`（02-2 交付） | 与注册项契约分处两模块，域三收敛期归位收益 |

## 3. 交付物清单 <a id="tree"></a>

```text
backend/app/core/
├── provider.py                 # 新增：BaseProvider（注册项契约）+ BaseProviderRegistry 归位（自 registry.py 移入）
└── registry.py                 # 修改：过渡导出 BaseProviderRegistry（兼容既有导入，注释标注过渡期）
backend/app/{fieldtype,query,dashboard,health}/base.py   # 修改：4 类提供者改继承 BaseProvider
backend/app/health/checks.py    # 修改：检查项 name → key + describe（app 侧 3 实现）
backend/app/query/null.py       # 修改：NullQueryProvider describe
backend/tests/                  # 修改：13 个替身适配 key / describe；新增边界护栏用例文件
backend/app/core/__init__.py    # 视包导出惯例同步（如有）
```

## 4. 套件设计 <a id="design"></a>

### 4.1 BaseProvider 契约（app/core/provider.py）

```python
class BaseProvider(BaseCapability, ABC):
    """注册项公共契约：键 + 元信息（组合轨：不经继承自动登记，经域注册表 / register_plugin 显式登记）。"""

    @property
    @abstractmethod
    def key(self) -> str:
        """注册项键（域内唯一；注册表以 key 解析）。"""

    @abstractmethod
    def describe(self) -> str:
        """元信息描述（供清单 / 日志 / 校验；实现类强制提供）。"""
```

- 继承 `BaseCapability`（`BaseObject` 链），**不继承** `BasePluggable` → 无 `__init_subclass__` 收集，组合轨边界由类型系统天然保证。
- `describe` 为**抽象强约束**：4 类端口保持抽象（不代实现），全部实现类显式提供（当前 16 个）。
- `BaseProviderRegistry[ItemT]` 自 `registry.py` 移入本模块；`registry.py` 保留 `from app.core.provider import BaseProviderRegistry` 过渡导出（`__all__` 不变，既有导入零改动；清理随后续阶段）。

### 4.2 4 类提供者改造

| 端口 | 改造 |
| --- | --- |
| `BaseFieldType` | 改继承 `BaseProvider`；抽象 `key` 上收（删除重复声明）；业务抽象方法不变 |
| `BaseQueryProvider` | 同上 |
| `BaseDashboardCardProvider` | 同上 |
| `BaseHealthCheck` | 改继承 `BaseProvider`；**抽象 `name` → 抽象 `key`**；`name` 保留为具体别名属性（`return self.key`，`/readyz` 响应与 `DEPENDENCIES` 口径不变）；`check()` 不变 |

### 4.3 实现类适配（16 个）

| 侧 | 类 | 改动 |
| --- | --- | --- |
| app | `NullQueryProvider` | `describe`（`f"查询提供者 {self.key}"` 口径） |
| app | `RedisHealthCheck` / `DatabaseHealthCheck` | `name` → `key`；新增 `describe` |
| 测试 | `_FakeFieldType` / `_FakeProvider` / `_FakeCard` / `_NamedCheck` / `_PassingCheck`×2 / `_FailingCheck`×2 / `_RaisingCheck` | 健康类 `name` → `key`；补 `describe` |
| 测试 | `TextFieldType` / `DictQueryProvider` / `TodoCardProvider` / `NamedCheck`（contracts 替身） | 同上；`NamedCheck` 的 `health_local` / 聚合用例断言不受影响 |

### 4.4 组合轨边界（护栏用例，新增 `backend/tests/crosscut/test_provider_contracts.py`）

- 4 类端口均为 `BaseProvider` 子类且**非** `BasePluggable` 子类（继承轨不混入）；
- 全部实现类均实现 `key` / `describe`（实例化 + 元信息非空 + 键一致性）；
- 健康 `name` 别名与 `key` 等价（响应 / 注册表口径不破）；
- 插件快照不受影响（36 键不变，既有契约套件互证）。

## 5. 测试设计（Kiwi 先行） <a id="tests"></a>

用例先登记 Kiwi（**两条**：契约与键口径 / 组合轨边界；平台实际登记 **651 / 652**，自增序列被 CI 导入用例推进）→ `tests/crosscut/test_provider_contracts.py`：

| Kiwi | 用例 | 断言要点 |
| --- | --- | --- |
| 651 | `test_provider_contract_semantics` | 4 端口 `issubclass(BaseProvider)`；实现类 `key` 非空 + `describe` 含键名；健康 `name == key` |
| 652 | `test_provider_composition_track_boundary` | 4 端口非 `BasePluggable` 子类；插件快照与提供者实现类互斥（组合轨不由继承混入） |

## 6. 实施步骤 <a id="steps"></a>

1. `app/core/provider.py`：`BaseProvider` + `BaseProviderRegistry` 归位；`registry.py` 过渡导出。
2. 4 类端口改继承；`BaseHealthCheck` 键口径迁移（`key` 抽象 + `name` 别名）。
3. 16 个实现类适配（app → 测试）。
4. 护栏用例（Kiwi 先行登记）；全量回归（契约套件 / 域用例不破）。
5. 回写：架构 04、基类清单、本任务与需求 / 计划状态；实施 / 测试记录。

## 7. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| 4 类提供者统一继承 `BaseProvider` | 护栏用例 + 类型检查 |
| 既有注册表与契约套件（03-1）不破 | `pytest` 全量（含 57 条契约用例） |
| 文档登记同步 | 架构 04 / 基类清单 diff |
| `ruff` / `pyright` 全绿 | 验证命令输出 |

## 8. 边界与开放项 <a id="boundary"></a>

- `describe` 强约束带来样板成本（16 类显式实现）——收益为「每实现自带元信息」，后续新增提供者按登记规范执行（回写基类清单）。
- `BaseProviderRegistry._provider_key` 钩子统一到 `.key`：健康随本任务切换，其余 3 域随 03-3 收敛切换。
- `registry.py` 过渡导出的清理时机：后续阶段（无外部引用后）。

## 9. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 落点 | `app/core/provider.py` 新建（不动 capability.py） |
| 2 | 健康键口径 | 抽象改 `key`，`name` 当别名（响应 / `DEPENDENCIES` 口径不变） |
| 3 | 元信息 | `describe` 抽象强约束（4 端口抽象、16 实现类显式提供） |
| 4 | 组合轨边界 | 新增护栏用例（非 `BasePluggable` 子类 + 快照不含提供者） |
| 5 | 注册表归位 | `BaseProviderRegistry` 移入 `provider.py` + `registry.py` 过渡导出 |
| 6 | 测试编号 | 两条 Kiwi：**651 / 652**（平台实际登记，CI 导入推进自增） |
| 7 | 快照断言口径 | 边界用例以「实现类与快照条目互斥」断言（36 键完整性由 03-1 完整性用例承载，避免重复断言） |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认

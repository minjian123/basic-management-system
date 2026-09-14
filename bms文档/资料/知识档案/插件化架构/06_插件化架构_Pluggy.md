# Pluggy 技术介绍

> 钩子式插件框架 · 主程序定义扩展点、插件实现钩子

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [插件化架构](../技术栈知识档案总览.md#plugin) › Pluggy 技术介绍　|　[← 返回总览](01_插件化架构_总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Pluggy** 是一个轻量级、无外部依赖的**钩子（hook）框架**，从 pytest 中演化而来：主程序定义一组**钩子规范**（hook spec，即扩展点），插件提供**钩子实现**（hook impl），`PluginManager` 负责注册、校验与调用。它与「一个能力选一个实现」的策略/驱动模式不同，更擅长**一件事允许多个插件叠加参与**（如 pytest 的采集、报告钩子）。

- **定位**：细粒度、函数级扩展点框架；适合「广播/竞争」型扩展，不适合「单选实现」型替换。
- **依赖**：无；`pluggy` 本身即一个可复用库（不是某个宿主应用）。
- **关键 API**：`HookspecMarker` / `HookimplMarker` / `PluginManager` / `HookCaller`。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 钩子规范（hookspec） | 主程序声明的扩展点函数签名，插件按此实现；参与签名校验 |
| 钩子实现（hookimpl） | 插件用标记装饰的函数，与 spec 同名即被识别 |
| PluginManager | 注册插件、校验签名、调用钩子；名称用于区分插件 |
| 广播模式 | 普通钩子调用所有实现，返回结果列表 |
| `firstresult=True` | 竞争模式：返回第一个非 `None` 结果，适合「单选」语义 |
| `historic=True` | 历史回放：后注册的插件也能收到此前的调用 |
| `tryfirst` / `trylast` | 控制同一钩子内多实现的执行顺序 |
| hookwrapper | 包裹式实现，可在其他实现前后插入逻辑（如计时、事务） |

```python
import pluggy

hookspec = pluggy.HookspecMarker("bms")
hookimpl = pluggy.HookimplMarker("bms")

class IdGenSpec:
    @hookspec(firstresult=True)
    def generate_id(self, tenant_id: int) -> int | None:
        """生成 ID：单选语义，返回第一个非 None 的实现结果"""

    @hookspec(historic=True)
    def on_startup(self, config: dict) -> None:
        """启动通知：广播语义，后注册插件可回放"""

pm = pluggy.PluginManager("bms")
pm.add_hookspecs(IdGenSpec)

class SnowflakePlugin:
    @hookimpl(tryfirst=True)
    def generate_id(self, tenant_id: int) -> int | None:
        return 123456789012345678

pm.register(SnowflakePlugin(), name="snowflake")
pm.hook.generate_id(tenant_id=1)   # firstresult 模式下返回单个值
```

> 项目名（`pluggy.PluginManager("bms")`）用于隔离不同的钩子命名空间，务必与 `HookspecMarker` / `HookimplMarker` 的项目名一致。

## 3. 在本项目中的用途 <a id="usage"></a>

- **多插件协作的扩展点**：如「路由注册后处理」「模型注册后处理」「启动/关闭回调」这类需要多个扩展参与的时点，用钩子比显式注册表更自然。
- **选择性实现（firstresult）**：ID 生成、默认存储后端等「单选」能力，可用 `firstresult=True` 表达，让优先级最高的可用实现生效。
- **启动通知（historic）**：`on_startup` 标注 `historic=True`，晚注册的插件也能收到已发生的启动事件，避免时序问题。
- **与自建注册表并用**：阶段一/二可用自建注册表承载单选能力；出现「多插件叠加」需求时，再评估引入 Pluggy 作为钩子层（见 [08 自建注册表](08_插件化架构_自建注册表.md)）。

## 4. 与 Stevedore / 自建注册表对比 <a id="compare"></a>

| 维度 | Pluggy | Stevedore | 自建注册表 |
| --- | --- | --- | --- |
| 扩展形态 | 钩子，多实现叠加 | 驱动/扩展管理器，单选或多选 | 名称→实现映射 |
| 发现机制 | 可选用入口点，通常显式注册 | 基于 entry points | 启动时显式注册 |
| 核心价值 | 调用顺序、结果收集、签名校验 | 驱动加载、懒加载、缓存 | 零依赖、完全可控 |
| 适合 | 函数级扩展点（前后置、广播） | 多类型后端驱动 | 平台内建单选实现 |
| 依赖 | 无（本身即库） | 第三方 | 无 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **`HookManager` 不存在**：正确类是 `Pluggy` 的 `PluginManager`，并需传入项目名。
- **firstresult 与广播混淆**：`firstresult=True` 只取第一个非 `None`，其余实现不执行也不返回；广播模式才返回列表。
- **签名校验**：spec 与 impl 参数不匹配会被校验拒绝；插件升级需对齐规范。
- **执行顺序**：多实现顺序不确定时用 `tryfirst`/`trylast` 显式声明，别依赖注册顺序。
- **异常传播**：钩子调用默认不隔离异常，需自行 `try/except` 或使用 wrapper；单个插件异常可能中断整个调用链。
- **发现副作用**：同 entry points，注册/加载阶段不应执行业务初始化。
- **过度使用**：把「单选能力」硬套钩子广播，会让语义含糊；单选用策略/注册表更清晰。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Pluggy 官方文档 | https://pluggy.readthedocs.io/ | API、钩子语义与最佳实践 |
| Pluggy GitHub | https://github.com/pytest-dev/pluggy | 源码与示例 |
| pytest 插件机制文档 | https://docs.pytest.org/en/stable/how-to/writing_plugins.html | 真实宿主中的钩子用法 |
| Plugins case study: Pluggy | https://eli.thegreenplace.net/2026/plugins-case-study-pluggy/ | 钩子框架设计剖析 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[04 插件发现机制](04_插件化架构_插件发现机制.md)》 | 插件如何被发现 |
| 《[07 Stevedore](07_插件化架构_Stevedore.md)》 | 驱动管理式方案对比 |
| 《[08 自建注册表](08_插件化架构_自建注册表.md)》 | 单选能力的零依赖实现 |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | Pluggy 的典型宿主 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写

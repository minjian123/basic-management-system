# 01 实施 · `bms_core` 存量整改（批次 1 · 基座原型先行）

> 认证与安全 · 08 裸无序集合治理 · 子任务 02（需求 08-2，补充需求）· 实施记录

[文档首页](../../../../../../文档首页.md) › [02 `bms_core` 存量整改](../08_裸无序集合治理_02_bms_core存量整改.md) › 实施记录　|　[← 任务](../08_裸无序集合治理_02_bms_core存量整改.md)　[测试记录 →](../测试/01_测试_02_bms_core存量整改.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [02 `bms_core` 存量整改](../08_裸无序集合治理_02_bms_core存量整改.md) |
| 对应需求 | [08-2](../../../../需求/08_需求_裸无序集合治理.md#r08-2) |
| 详细设计 | [01 详细设计](../设计/01_详细设计_02_bms_core存量整改.md) |
| 实施日期 | 2026-09-29（**基座原型先行**；早于计划窗口 2026-10-23 ~ 11-20） |
| 实施人 | minjian |
| 实施环境 | 本地开发机（Python 3.14；uv 工作区；`uv run` 跑 `ruff` / `pyright` / `pytest`） |
| 提交 | 未提交（本轮改动未提交，待用户指令） |
| 结论 | **基座能力与护栏收紧完成**（`core/concurrent.py` 只读 API + `ConcurrentStable*` 分段写；`schemas/base.py` 契约元数据；`core/serialization.py` / `core/base.py` 序列化链；护栏白名单收紧 + 实现文件豁免 + 基线如实吸收 **548 → 920**）；596 处存量整改与调用方适配续行 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A["Kiwi 先登记取号<br/>2222 / 2223 / 2224"] --> B["core/concurrent.py 只读 API<br/>Sequence / Mapping / Set + __eq__/__hash__（含升序类）"]
    B --> C["新增 ConcurrentStable*<br/>collection_kind=stable + 分段写 + 插入序号归并"]
    C --> D["删除 ConcurrentSortedList.key= 坏参数"]
    D --> E["schemas/base.py 契约元数据<br/>CONTRACT_COLLECTION + 空集合工厂常量"]
    E --> F["序列化链识别集合类<br/>stringify_ids / _convert 同型重组；stable_json_dumps 前置规整"]
    F --> G["护栏白名单收紧 + 实现文件豁免<br/>裸容器 / 抽象 / 升序形态一律违规；自测矩阵 24 项"]
    G --> H["基线如实吸收 548 → 920<br/>复跑「新增 0 / 残留 0」"]
    H --> I["用例 + 文档回写<br/>tests/core·schemas·护栏；数字全域修正；清单/任务状态"]
```

## 3. 实施过程 <a id="process"></a>

1. **Kiwi 先登记取号（设计口径：先登记、后写自动化）**：经内网 Kiwi TCMS（容器 `bms-kiwi`，Django shell 脚本化登记，分类「平台骨架」/ 优先级 `P2` / 状态 `CONFIRMED` / 标签「自动化」）登记 3 条用例并回读核对，取号 **2222**（插入序形态与并发）/ **2223**（契约零漂移与序列化形态）/ **2224**（存量归零与护栏收紧）。
2. **并发集合只读 API**（`backend/libs/bms_core/src/bms_core/core/concurrent.py`）：
   - `ConcurrentSortedList` 补 `Sequence` 只读面（`__getitem__` 索引 / 切片、`index` / `count` / `__reversed__`），并显式实现 `__eq__`（与 `list` / `tuple` / 同类集合内容相等）与重声明 `__hash__`（`= BaseObject.__hash__`，避免 `__eq__` 覆盖连带置空）；切片返回同类实例。
   - `ConcurrentSortedSet` 补 `Set` 只读面（集合运算 `&` / `|` / `-` / `^` 返回同类且保插入序）与 `__eq__` / `__hash__`。
   - `ConcurrentSortedDict` 补 `Mapping` 只读面（`__getitem__`、`keys` / `items` / `values` / `get` / `__eq__` / `__hash__`）；**`__iter__` 由「键值对」改为「键」**（Mapping 协议，`dict(x)` 仍可用，键值对遍历走 `to_list()` / `items()`）。
3. **删除 `ConcurrentSortedList.key=` 坏参数**（2026-09-29 拍板）：`sortedcontainers` 不支持 `key`（实测 `TypeError: inherit SortedKeyList for key argument`）且零使用零测试，升序形态已退为基座内部实现，直接删除以免误用。
4. **新增插入序形态 `ConcurrentStableList` / `ConcurrentStableSet` / `ConcurrentStableDict`**（`BaseConcurrentSorted` 子类，`collection_kind="stable"`，**默认 `SHARDED`**）：
   - **分段写 + 插入序号归并**：每次写从实例全局单调计数器取号（独立轻量锁，仅整数自增），段内按序号有序；读 / 遍历 / 快照按整数序号用 `heapq.merge` 归并还原全局插入序（归并在锁外）。
   - `list` 按**轮转**分派段（与序号解耦）、`set` / `dict` 按**元素 / 键哈希**分派段（同元素固定落同段，定位 O(1)）；段锁内取号保证段内序号递增（`heapq.merge` 前提）。
   - 元素无需可比较（`dict` / Pydantic 模型 / ORM 模型可入）；`set` 去重（保留首次插入位置）、`dict` 更新已存在键保持原插入位置。
   - 只读面、原子方法集合、非 `SHARDED` 策略（`RW` / `RLCK` / `SNAPSHOT`）与升序形态对齐。
5. **护栏实现文件豁免**（`scripts/tools/base-check/check-bare-collections.py`）：新增 `EXEMPT_FILES`（`core/collections.py` / `core/concurrent.py` / `core/redis_collections.py`）按文件路径白名单豁免，`collect` 跳过豁免文件；`--self-test` 矩阵新增「实现文件豁免」断言（**19 项**）；docstring 口径与用例覆盖说明同步。
6. **Pydantic 契约元数据 `CONTRACT_COLLECTION`**（`schemas/base.py`）：`_ContractCollection`（落 `BaseFrameworkObject`——自定义类须有基类）按 `get_origin` 分派同类内置容器 schema（映射 → `dict_schema`，其余 → `list_schema`；**集合类以 `list` 校验保插入序**，去重交集合类）；`__get_pydantic_json_schema__` 为集合类补 `uniqueItems`（与 `frozenset[X]` 一致）；序列化器按 `info.mode` 区分（Python 同类重组 / JSON 内置容器）；`Optional` 联合形态经 `union_schema` 逐成员处理。新增空集合工厂常量 `CONTRACT_STABLE_LIST` / `CONTRACT_STABLE_DICT` / `CONTRACT_STABLE_SET`。
7. **序列化链识别集合类**（只依赖 `collections.abc`，不反向 import `core.collections` / `core.concurrent`）：`core/serialization.py` 新增 `rebuild_mapping` / `rebuild_sequence`（同型重组，构造不可用时回退内置）与 `normalize_collections`（前置规整为内置容器）；`stringify_ids` 递归映射 / 序列 / 集合（`str` / `bytes` 不参与，内置 `set` / `frozenset` 保持原样），`stable_json_dumps` 前置规整；`core/base.py` 的 `_convert` 同步按只读面识别并同型重组。
8. **用例与回归**：新增 `tests/core/test_concurrent_stable.py`（Kiwi 2222）与 `tests/schemas/test_contract_collections.py`（Kiwi 2223）；既有 `tests/core/test_concurrent.py` 适配 `__iter__` 语义。
9. **护栏白名单收紧**（`check-bare-collections.py`）：判违规形态收敛为**固定违规集**（裸容器 + typing 别名 + 只读 / 可变抽象 `Sequence` / `Mapping` / `AbstractSet` / `Collection` / `Mutable*` + 升序形态 `Sorted*` / `ConcurrentSorted*`），**插入序形态为白名单**（`ConcurrentStable*`），迭代 / 调用协议（`Iterable` / `Iterator` / `Generator` / `Callable` 等）不查；实现文件豁免保留；docstring 口径改写；`--self-test` 矩阵由 19 项扩到 **24 项**（新增抽象落点 / 升序形态 / 白名单命中不报 / 迭代协议不报）。
10. **基线如实吸收**：`--update-baseline` 吸收口径收紧后的现状——**548 → 920 条**（854 个聚合条目；`libs` 596 / `services` 104 / `ops` 75 / `scripts/tools` 145），复跑「**新增 0 / 残留 0**」；与初稿 940 的差异（未扣实现文件豁免 20 处）按用户拍板修正全域数字。
11. **文档回写**：详细设计回填 Kiwi 编号（§2 / §5 / §7）、插入序默认 `SHARDED`（§3.4）、`key=` 删除（§1.1 / §3.3）、契约元数据实现细化（§3.5）与**数字修正**（§1.1 新增说明：940 → 920、616 → 596）、《后端基类清单》§10 登记 `ConcurrentStable*` 完整继承链并回写状态；任务状态「未开始」→「进行中」；**数字全域修正**（设计 / 任务 02~03 / 父任务 / 需求 08-2 / 需求总览 / 计划 / 清单 / 盘点报告）。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置与落点 |
| --- | --- | --- | --- |
| 1 | 分段写可能破坏「段内按序号有序」 | 若先取号再进段锁，同段两次追加可能乱序（先取的号后落段） | 改为**段锁内取号**；`list` 段分派用与序号解耦的**轮转计数**，保段内序号递增（`heapq.merge` 前提） |
| 2 | 集合对称差集 `^` 结果多出交集元素 | 初版第二段用 `not in result` 判重（`result` 已含第一段结果） | 改为 `not in self`（语义：`other` 独有）；升序 / 插入序两处同改 |
| 3 | `AbstractSet` 从 `collections.abc` 导入失败（pyright） | `collections.abc` 无 `AbstractSet`（应为 `typing` 别名，等价 `collections.abc.Set`） | 集合运算参数改用 `Set[Any]`（已导入） |
| 4 | `__eq__` 覆盖连带把 `__hash__` 置 `None`，且 `BaseObject.__eq__` 经 MRO 盖住 ABC 的 `__eq__` | Python 语义 | 每个集合类**显式实现 `__eq__`** 并 `__hash__ = BaseObject.__hash__`（设计 §3.3 已预判） |
| 5 | `ConcurrentSortedDict.__iter__` 改键遍历后既有断言失败 | 语义变更（设计 §7 已登记） | 适配 `tests/core/test_concurrent.py`（键遍历 + `items()` 等），并回填设计 |
| 6 | `to_dict` / `get` 覆写与 `Mapping` / 基类签名不兼容（pyright strict） | 返回型收窄 / 默认参差异 | 沿用既有 `# pyright: ignore[reportIncompatibleMethodOverride]` 标注（与 `ConcurrentSortedDict.to_dict` 同口径） |
| 7 | 实现文件豁免后基线出现 **18 处「可递减」** 条目 | 豁免文件原基线条目不再命中 | 已随护栏白名单收紧步骤 `--update-baseline` 一次性吸收（548 → **920**）而清除 |
| 8 | 契约集合 `model_dump_json()` 报 `_serialize_ids` 收到 `dict`（集合序列化器 `return_schema` 触发对返回值的二次模型序列化） | `wrap_serializer_function_ser_schema(return_schema=...)` 使 Pydantic 对返回的 list 再次按元素模型序列化 | **移除 `return_schema`**（JSON Schema 序列化模式对 `BaseSchema` 本就为 `{}`，由既有 wrap model serializer 决定；契约走校验模式） |
| 9 | 集合类契约字段 JSON 串顺序非插入序 | 校验 / 序列化经 `frozenset_schema`，元素序丢失 | 校验改 `list_schema`（保插入序，去重交集合类）；`uniqueItems` 由 `__get_pydantic_json_schema__` 补齐（与 `frozenset[X]` 逐字节一致） |
| 10 | 「所有自定义类必须继承基类」用例拦截无基类的 `_ContractCollection` | 规范要求一切自定义类必继承基类 | 落 `BaseFrameworkObject`（非数据对象）（设计 §3.5 已回写） |
| 11 | `stringify_ids` / `_convert` / 元数据实现触发 pyright strict「partially unknown」 | `object` 经 `isinstance` 收窄为 `Mapping[Unknown, Unknown]`；`type(x)(...)` 动态构造 | 显式 `cast` 收窄（`Mapping[object, object]` / `Sequence[object]` / `Set[object]` / `Callable[...]`），运行时行为不变 |
| 12 | 护栏收紧后实测 920 处，与设计初稿 940 不符 | 初稿测绘未扣除**实现文件豁免**（§3.7）的 20 处；且 920 − 596 = 324 恰与批次 1 递减目标一致 | 按用户拍板**如实吸收 920** 并**全域修正数字**（940→920、616→596、裸 305→287、抽象 311→309、位置 245/241→248/218；设计 §1.1 加「数字修正」说明） |
| 13 | `_ContractCollection` 触发「所有自定义类必须继承基类」用例与 pyright 未知类型 | 无基类 / `isinstance` 收窄为 `Unknown` / 动态构造 | 落 `BaseFrameworkObject`；显式 `cast`（`CollectionType` / `Callable[[Any], Any]`） |

## 5. 验证结果 <a id="verify"></a>

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 定向用例 | `uv run pytest libs/bms_core/tests`（`bms_core` 全量） | **1099 passed / 37 skipped**（含 Kiwi 2222 的 18 项并发与只读面、Kiwi 2223 的 9 项契约与序列化链） |
| 并发稳定性 | 新并发用例重复执行 15 轮 | 全通过（无顺序抖动 / 无丢失） |
| 静态检查 | `uv run ruff check` / `ruff format --check`（改动文件） | 通过 |
| 类型检查 | `uv run pyright`（backend 全量 `libs` + `services`） | **0 errors, 0 warnings** |
| 护栏自测 | `python3 scripts/tools/base-check/check-bare-collections.py --self-test` | **24 项断言全通过**（白名单 / 抽象落点 / 升序形态 / 实现文件豁免 / 迭代协议 / 基线语义） |
| 护栏报告 | `python3 scripts/tools/base-check/check-bare-collections.py . --report --json` | 命中 **920** 处（类字段 155 / 参数 390 / 返回 375；`libs` 596 / `services` 104 / `ops` 75 / `scripts/tools` 145） |
| 基线吸收与复跑 | `--update-baseline` → 直跑检查 | 基线 **920** 条（854 聚合条目）；复跑「新增 0 / 残留 0」 |
| 本地预检 | `python3 scripts/tools/preflight/check-preflight.py --fast` | **全部通过**（静态 / 基座与边界 / 网关 / 契约零漂移 / 前端类型 / check-status 310 项 0 硬 0 软） |
| 阶段状态 | `python3 scripts/tools/check-docs/check-status.py --root . --stage 06_认证与安全` | 502 项 0 硬 0 软 |
| 文档链接 | `python3 scripts/tools/base-check/check-links.py` | 0 断链 / 0 失效锚点 |

## 6. 偏差与遗留 <a id="deviations"></a>

- **偏差 1（进度）**：实施日期 **2026-09-29** 早于计划窗口 **2026-10-23 ~ 11-20**——按 2026-09-29 拍板「基座原型先行、再铺开其余改造」提前落地风险最高的并发分段写与契约元数据，后续会话在窗口内续行（不影响排期与工时口径）。
- **偏差 2（口径细化）**：插入序默认锁策略由设计原文「默认 `RW`、高并发显式传 `SHARDED`」改为**默认 `SHARDED`**（2026-09-29 拍板并回写设计 §3.4 / §8），使各处落点无需传参即得高并发写。
- **偏差 3（护栏范围）**：先加「实现文件豁免」（最小改动，2026-09-29 拍板），随后**完成白名单收紧**（裸容器 / 抽象 / 升序形态一律违规）并 `--update-baseline` 吸收至 **920** —— 两项已闭环。
- **偏差 4（实现细化）**：契约集合的校验 / JSON Schema 实现以「`list` 校验保插入序 + `uniqueItems` 元数据补丁」替代设计初稿的「`frozenset` 校验」（见 §4 问题 9；已回写设计 §3.5）。
- **偏差 5（数字修正）**：护栏实测 920（libs 596）而非初稿 940（616）——初稿未扣除实现文件豁免的 20 处；按用户拍板如实吸收并**全域修正数字**（设计 / 任务 02~03 / 父任务 / 需求 08-2 / 需求总览 / 计划 / 清单 / 盘点报告）；批次递减目标 324 / 220 / 0 **不变**。
- **遗留**：
  1. **596 处存量整改**（批内先类字段、后签名）与调用方适配续行（含契约字段落 `Annotated[..., CONTRACT_COLLECTION]` 与 `default_factory` 换工厂常量）。
  2. 用例 2224 的完整自动化（`tests/boundary/test_bare_collections_guard.py`：断言 `by_area.libs == 0` 与基线递减至 324）待遗留项 1 完成后落。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

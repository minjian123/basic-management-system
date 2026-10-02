# 02 裸无序集合存量整改（批次 1~4）

> 认证与安全 · 08 裸无序集合治理 · 子任务 02（需求 08-2，补充需求）

[文档首页](../../../../../文档首页.md) › [08 裸无序集合治理](../08_裸无序集合治理.md) › 02 裸无序集合存量整改（批次 1~4）　|　[← 父任务](../08_裸无序集合治理.md)　[需求 →](../../../需求/08_需求_裸无序集合治理.md)

## 1. 任务信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 编号 | 02 |
| 父任务 | [08 裸无序集合治理](../08_裸无序集合治理.md) |
| 对应需求 | [08-2](../../../需求/08_需求_裸无序集合治理.md#r08-2) |
| 依赖 | 08_01（护栏与基线，已交付） |
| 负责人 | minjian |

## 2. 任务内容 <a id="content"></a>

1. **集合体系唯一链收口（并入本任务）**：**所有集合类一律（间接）继承基础集合基类 `BaseCollection`、无任何例外**——`BaseCollection`（集合体系唯根：集合通用语义 + 稳定序约定 + `collection_kind`）→ `BaseSorted`（非并发有序 · 无锁高效；`SortedList` / `SortedDict` / `SortedSet` 落点）→ `BaseConcurrent`（基础并发：锁策略守卫 + 原子复合操作 + 快照遍历模板）与 `BaseAsyncSorted`（跨副本异步有序：并发由 Lua 原子脚本 + 版本号承载、**无同步锁层、无同步读入口**）；`BaseCacheSnapshot`（通用缓存层）→ `RedisSnapshot`（由框架对象体系**改挂集合体系**）。旧名 `BaseSorted`（旧语义根）/ `BaseSyncSorted` / `BaseConcurrentSorted` 退场。落点：`core/collections.py`、`core/concurrent.py`、`core/redis_collections.py`、`core/objects/roots.py`、`schemas/base.py`。
2. **基座能力新增（并入本任务）**：① 并发集合补齐**只读 API**——`Sequence` / `Mapping` / `Set` 只读面（索引 / 切片 / `keys` / `items` / `values` / 集合运算 / 与内置容器内容相等），**写入仍走显式原子方法**（不提供 `append` / `__setitem__`）；② 新增**插入序形态** `ConcurrentStableList` / `ConcurrentStableSet` / `ConcurrentStableDict`（继承 `BaseConcurrent`、`collection_kind="stable"`、不比较元素、插入序稳定输出），**支持分段写 + 插入序号归并的高并发写**（`SHARDED`，写并发 ≈ 段数）；③ 新增 **Pydantic 契约元数据** `CONTRACT_COLLECTION` 与插入序空集合工厂常量（落 `schemas/base.py`，`core` 不引入 Pydantic；契约 JSON Schema 与 `list[X]` / `dict[K, V]` / `frozenset[X]` 逐字节一致）；④ 序列化链识别集合类（`stringify_ids` / `BaseObject._convert` / `stable_json_dumps`）。
3. **存量整改（批次 1~4）**：批次 1 `bms_core`（`backend/libs/bms_core` 的 `src` + `tests`）**1036 处**（2026-09-30 实测）、批次 2 `services` **348 处**、批次 3 `ops` 与 `scripts/tools` **327 处**（各批实施记录见实施记录 §28~§45）**全落插入序形态**（`ConcurrentStableList` / `ConcurrentStableSet` / `ConcurrentStableDict`，类字段 / 参数 / 返回 / 局部变量位置全覆盖）；**升序形态 `ConcurrentSorted*` 与 `SortedList` / `SortedDict` / `SortedSet` 为体系内部基础实现，不作为整改落点**（业务与契约不得直接声明 / 继承，排序走排序契约）；**批内先类字段、后签名参数与返回、再局部变量**（契约影响面优先）；含集合体系自身公共契约。
4. **验收基准**：**形态一致 + 逐处登记**（声明与运行期均为插入序集合类；加锁与插入序为预期行为；契约字段 `model_dump()` 输出集合类实例、`model_dump_json()` 输出 `array` / `object`）；原「运行期零变更」作废。
5. **调用方适配**：只读 API 覆盖读用法；参数位落集合类后，向函数传内置容器处改为构造集合类实例；需可变操作处走集合类显式方法或显式拷贝，逐条记入实施记录（不顺手改逻辑）；`services` 侧因参数位收窄报错登记为批次 2 前置输入。
6. **护栏收紧与基线递减**：`check-bare-collections.py` 改为**插入序白名单 + 无例外**判定（裸容器、只读 / 可变抽象、升序形态、`ClassVar` 类级常量、`BaseSettings` 配置字段、测试目录与函数体带注解局部变量一律纳入；集合体系实现文件为**不属约束对象**；迭代 / 调用协议不查），补 `--self-test` 矩阵；**先 `--update-baseline` 如实吸收口径收紧后的现状（918 → 1711）**，批次完成后递减（`bms_core` 条目归零），**不得手工增删基线条目**（基线即台账）。
7. **登记回写**：《[后端基类清单](../../../../../后端基类清单.md)》「集合体系」节与§10「体系根清单」（唯一链 / 新根 `BaseCollection` / 新层 / 分段写 / 只读 API / 契约元数据 / 护栏与基线）、[需求 08-2](../../../需求/08_需求_裸无序集合治理.md#r08-2)、[父任务](../08_裸无序集合治理.md) 与后续子任务口径、《[后端开发规范](../../../../../规范/后端开发规范.md)》「集合与排序」、《[架构设计 · 后端基础类体系](../../../../../设计/架构设计/04_架构设计_后端基础类体系.md)》。
8. **测试**：先登记 Kiwi TCMS 用例取号（**3 条**：唯一链与插入序形态 / 契约零漂移与序列化 / 存量归零与护栏），后写自动化——断言所有集合类（间接）继承 `BaseCollection`、跨副本形态无同步读入口、`bms_core` 命中归零、基线递减、护栏复跑「新增 0 / 残留 0」、契约 schema 与前端类型零漂移、`SHARDED` 并发写后读回插入序；受影响定向回归（`bms_core` 相关用例）与门禁全绿。

## 3. 完成标准 <a id="accept"></a>

集合体系**唯一链**落地（`BaseCollection` 唯根；`BaseSorted` / `BaseConcurrent` / `BaseAsyncSorted` / `BaseCacheSnapshot` 分支；`RedisSnapshot` 入链）且与清单、规范、架构三处零漂移；全链 **1711 处**（批次 1 `bms_core` 1036 / 批次 2 `services` 348 / 批次 3 `ops` 与 `scripts/tools` 327）全部改为**插入序集合类**（`ConcurrentStable*`；`Sorted*` 与 `ConcurrentSorted*` 不作为整改落点、不得新增直接声明 / 继承）且**形态一致 + 逐处登记**；基座新增（只读 API / `ConcurrentStable*`（含分段写）/ `CONTRACT_COLLECTION` / 序列化链）落地并有用例覆盖；护栏为**插入序白名单 + 无例外**（实现文件不属约束对象）、基线由 918 吸收至 1711 后递减且 `check-bare-collections.py` 复跑「新增 0 / 残留 0」；契约 JSON Schema 与前端 `api-types` 零漂移；受影响定向 `pytest`、`ruff`、`pyright`、基座校验与 `preflight --fast` 全绿。

## 4. 参考文档 <a id="ref"></a>

- [需求 08-2](../../../需求/08_需求_裸无序集合治理.md#r08-2)
- [08_01 护栏与基线盘点](../08_裸无序集合治理_01_护栏与基线盘点/08_裸无序集合治理_01_护栏与基线盘点.md)（护栏 / 基线 / 盘点报告）
- 《[存量盘点报告](../08_裸无序集合治理_01_护栏与基线盘点/实施/02_存量盘点报告_01_护栏与基线盘点.md)》§4「分批整改建议」/ §5「基线与递减口径」
- 《[后端开发规范](../../../../../规范/后端开发规范.md)》「后端基座体系（强制）」节「集合与排序」
- 《[后端基类清单](../../../../../后端基类清单.md)》「集合体系」节

> 交付物：详细设计、实施记录、测试记录（随任务开工建立，落本目录 `设计/`、`实施/`、`测试/`）。

# 01 测试 · `bms_core` 存量整改（批次 1 · 基座原型先行）

> 认证与安全 · 08 裸无序集合治理 · 子任务 02（需求 08-2，补充需求）· 测试记录

[文档首页](../../../../../../文档首页.md) › [02 `bms_core` 存量整改](../08_裸无序集合治理_02_bms_core存量整改.md) › 测试记录　|　[← 任务](../08_裸无序集合治理_02_bms_core存量整改.md)　[实施记录 →](../实施/01_实施_02_bms_core存量整改.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [02 `bms_core` 存量整改](../08_裸无序集合治理_02_bms_core存量整改.md) |
| 对应需求 | [08-2](../../../../需求/08_需求_裸无序集合治理.md#r08-2) |
| 详细设计 | [01 详细设计](../设计/01_详细设计_02_bms_core存量整改.md) |
| 实施记录 | [01 实施](../实施/01_实施_02_bms_core存量整改.md) |
| 测试日期 | 2026-09-29（基座原型先行） |
| 测试人 | minjian |
| 测试环境 | 本地开发机（Python 3.14；`uv run pytest` / `ruff` / `pyright`） |
| 用例落点 | `backend/libs/bms_core/tests/core/test_concurrent_stable.py`（Kiwi 2222）+ `backend/libs/bms_core/tests/schemas/test_contract_collections.py`（Kiwi 2223）+ 护栏 `--self-test` 矩阵 |
| 用例编号 | Kiwi **2222**（插入序形态与并发）/ **2223**（契约零漂移与序列化形态）/ **2224**（存量归零与护栏收紧） |

## 2. 用例登记（Kiwi 先登记后编码） <a id="kiwi"></a>

| 项 | 值 |
| --- | --- |
| 用例编号 | **2222 / 2223 / 2224**（平台自增主键，已回读核对） |
| 产品 / 分类 | BMS 基础管理系统 / 平台骨架 |
| 优先级 / 状态 / 标签 | `P2` / `CONFIRMED` / 自动化 |
| 登记方式 | 内网 Kiwi TCMS 容器 `bms-kiwi` 的 Django shell 脚本化登记（主机、账号与访问方式见《[Kiwi TCMS 部署使用说明](../../../../../../资料/开发服务器/linux/KiwiTCMS部署使用说明.md)》「用例约定」节） |
| 覆盖范围 | 写入用例 `text` 字段（2222 插入序形态与并发 / 2223 契约零漂移与序列化 / 2224 存量归零与护栏收紧，各含自动化文件路径与 `kiwi_id` 标注方式） |
| 当前状态 | 2222 / 2223 已落自动化；2224 的护栏收紧、`--self-test` 矩阵（24 项）与基线吸收（548 → 918）本轮已落，`by_area.libs == 0` / 基线递减至 324 断言待 594 处存量整改后续写 |

## 3. 用例清单与执行结果 <a id="cases"></a>

### 3.1 用例 2222「插入序形态与并发」（`test_concurrent_stable.py`，18 项断言） <a id="case-2222"></a>

| 组 | 断言 | 结果 |
| --- | --- | --- |
| 形态与继承链 | `ConcurrentStable*` → `BaseConcurrentSorted` → `BaseSorted` → `BaseObject`；`collection_kind="stable"`；分别实现 `Sequence` / `Set` / `Mapping` | 通过 |
| 插入序（列表） | 不可比较元素可入且保插入序；索引 / 切片 / `index` / `count` / 反转 / 相等；`discard` / `remove` / `clear` | 通过 ×4 策略 |
| 插入序 + 去重（集合） | 保插入序 + 去重、不比较元素；`&` / `\|` / `-` / `^` 返回同类且保插入序；`add_if_absent` / `remove_atomic` | 通过 ×4 策略 |
| 插入序（映射） | 保插入序、不比较键；更新已存在键保持原位置；`[k]` / `get` / `keys` / `items` / `values` / 相等；原子方法语义不变 | 通过 ×4 策略 |
| 分段写并发 | `SHARDED` 多线程并发写后读回：元素不丢不重、每线程子序列保插入序（列表 / 映射） | 通过（重复 15 轮无抖动） |
| 只读面与边界 | 升序类只读 API 与内置容器内容相等；写入仅显式方法（无 `append` / `__setitem__`）；分片数校验 | 通过 |
| `__iter__` 语义 | `ConcurrentSortedDict` 遍历键（既有用例 `test_concurrent.py` 同步适配） | 通过 |

**合计**：42 项 pytest 断言通过（`test_concurrent.py` 24 + `test_concurrent_stable.py` 18）。

### 3.2 用例 2223「契约零漂移与序列化形态」（`test_contract_collections.py`，9 项断言） <a id="case-2223"></a>

| 组 | 断言 | 结果 |
| --- | --- | --- |
| 校验与形态 | 契约字段校验后落 `ConcurrentStable*`（保输入插入序）；空集合工厂默认值；`Optional` 联合可空；传入集合类实例 / ORM 属性可校验（`from_attributes`） | 通过 |
| `model_dump()` | 输出**集合类实例**（列表 / 映射 / 集合），元素递归 dump 且 ID 字符串化 | 通过 |
| `model_dump_json()` | 输出 `array` / `object`，无 `ConcurrentStable` 字符串泄漏；空默认输出 `[]` / `{}` / `null` | 通过 |
| JSON Schema 逐字节一致 | `items` / `index` / `tags`（含 `uniqueItems`）/ `optional_items` 与 `list[X]` / `dict[K, V]` / `frozenset[X]` / `list[X] \| None` 一致；不产生 `$defs` 命名漂移 | 通过 |
| 序列化链 | `stringify_ids` 同型重组（映射键 `*_id` 递归）；`BaseObject._convert` 识别集合类；`stable_json_dumps` 前置规整（无集合类字符串） | 通过 |

**合计**：9 项 pytest 断言通过。

### 3.3 护栏自测矩阵（Kiwi 2213 覆盖，本轮 19 → 24 项） <a id="self-test"></a>

| 组 | 断言 | 结果 |
| --- | --- | --- |
| 检出（裸容器 / typing 别名） | 类字段 `list` / `dict`；签名参数 `dict`；签名返回 `set` / `frozenset`；typing 别名 `List` / `DefaultDict`；字符串前向引用 `'list[int]'` | 通过 |
| 抽象落点（新规） | 签名参数 `Sequence` / `Mapping` / `AbstractSet` 判违规 | 通过（新增） |
| 升序形态（新规） | 类字段 `ConcurrentSortedList` 判违规 | 通过（新增） |
| 白名单命中不报（新规） | `ConcurrentStableList` 不报 | 通过（新增） |
| `ClassVar` 常量不报（新规） | `ClassVar[frozenset[str]]` 类级常量不报 | 通过（新增） |
| 迭代 / 调用协议不报（新规） | `Iterable` / `Iterator` / `Callable` 不报 | 通过（新增） |
| 实现文件豁免 | 集合体系实现文件（`core/concurrent.py` 等）内的裸容器注解不报 | 通过 |
| 位置与排除 | 测试目录不扫描；函数体内局部注解不报 | 通过 |
| 基线语义 / 模式输出 | 无基线即新增 → 不通过；入基线后通过；零漂移；新增被拦截；更新基线后通过；可递减不改结论；报告 JSON 合法 | 通过 |

**合计**：25 项断言全通过，`--self-test` 退出码 `0`。

## 4. 覆盖率 <a id="coverage"></a>

**定向验证 + 既有门禁**（口径见详细设计 §5）：本轮有运行时代码改动（`core/concurrent.py` / `schemas/base.py` / `core/serialization.py` / `core/base.py`）与护栏脚本改动，按《[测试规范](../../../../../../规范/测试规范.md)》「只跑受变更影响的部分」跑定向 `pytest`（`bms_core` 全量）与后端 `pyright` / `ruff`；护栏脚本自身不在 `ruff` / `pyright` 覆盖范围，以 `--self-test` 矩阵保障；`bms_core` 覆盖率门槛（≥70%）随既有门禁执行，全量与集成验证交 CI 按需触发。

## 5. 验证命令与结果 <a id="verify"></a>

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 定向回归 | `uv run pytest libs/bms_core/tests` | 1099 passed / 37 skipped |
| 护栏自测 | `python3 scripts/tools/base-check/check-bare-collections.py --self-test` | **25 项通过 / exit 0** |
| 护栏报告 | `python3 scripts/tools/base-check/check-bare-collections.py . --report --json` | 命中 **918** 处（`libs` 594 / `services` 104 / `ops` 75 / `scripts/tools` 145） |
| 基线吸收与复跑 | `--update-baseline` → 直跑检查 | 基线 **918** 条；复跑「新增 0 / 残留 0」 |
| 静态检查 | `uv run ruff check` / `ruff format --check`（改动文件） | 通过 |
| 类型检查 | `uv run pyright`（backend 全量） | 0 errors |
| 本地预检 | `python3 scripts/tools/preflight/check-preflight.py --fast` | 全部通过（含契约零漂移 / `api-types` 零漂移） |
| 阶段状态 | `python3 scripts/tools/check-docs/check-status.py --root . --stage 06_认证与安全` | 502 项 0 硬 0 软 |
| 文档链接 | `python3 scripts/tools/base-check/check-links.py` | 0 断链 / 0 失效锚点 |

## 6. 问题与偏差 <a id="issues"></a>

| # | 问题 / 现象 | 处置 |
| --- | --- | --- |
| 1 | 分段写并发时序竞争（段内乱序破坏 `heapq.merge` 前提） | 段锁内取号 + 轮转分派段；实施记录 §4 问题 1 |
| 2 | 集合对称差集 `^` 语义错误 | 改 `not in self`；实施记录 §4 问题 2 |
| 3 | pyright strict：`AbstractSet` 导入 / `__eq__` 覆写 / `to_dict` `get` 兼容 | 逐一修正或按既有口径 `# pyright: ignore[...]`；实施记录 §4 问题 3 / 4 / 6 |
| 4 | `ConcurrentSortedDict.__iter__` 语义变更致既有断言失败 | 适配既有用例（设计 §7 已登记）；实施记录 §4 问题 5 |
| 5 | 集合契约 JSON 串顺序非插入序 / `model_dump_json()` 序列化报错 | 校验改 `list`（保插入序）+ `uniqueItems` 元数据补丁；移除 `return_schema`；实施记录 §4 问题 8 / 9 |
| 6 | 「所有自定义类必须继承基类」用例拦截 `_ContractCollection` | 落 `BaseFrameworkObject`；实施记录 §4 问题 10 |
| 7 | 护栏收紧后实测 918（初稿 940） | 初稿未扣实现文件豁免 20 处与 `ClassVar` 常量 2 处；按拍板如实吸收 918 并全域修正数字（实施记录 §4 问题 12） |

## 7. 遗留 <a id="leftover"></a>

1. 用例 **2224**（存量归零与护栏收紧）：**护栏收紧、`--self-test` 矩阵与基线吸收（548 → 918）本轮已落**；`by_area.libs == 0` 与「基线递减至 324」断言待 594 处存量整改完成后落 `tests/boundary/test_bare_collections_guard.py`。
2. 本任务尚无运行期全量回归；594 处存量整改完成后按详细设计 §5 用例 4~6 跑门禁与文档一致性核对。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

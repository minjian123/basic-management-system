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
| 用例落点 | `backend/libs/bms_core/tests/core/test_concurrent_stable.py`（Kiwi 2222）+ 护栏 `--self-test` 矩阵 |
| 用例编号 | Kiwi **2222**（插入序形态与并发）/ **2223**（契约零漂移与序列化形态）/ **2224**（存量归零与护栏收紧） |

## 2. 用例登记（Kiwi 先登记后编码） <a id="kiwi"></a>

| 项 | 值 |
| --- | --- |
| 用例编号 | **2222 / 2223 / 2224**（平台自增主键，已回读核对） |
| 产品 / 分类 | BMS 基础管理系统 / 平台骨架 |
| 优先级 / 状态 / 标签 | `P2` / `CONFIRMED` / 自动化 |
| 登记方式 | 内网 Kiwi TCMS 容器 `bms-kiwi` 的 Django shell 脚本化登记（主机、账号与访问方式见《[Kiwi TCMS 部署使用说明](../../../../../../资料/开发服务器/linux/KiwiTCMS部署使用说明.md)》「用例约定」节） |
| 覆盖范围 | 写入用例 `text` 字段（2222 插入序形态与并发 / 2223 契约零漂移与序列化 / 2224 存量归零与护栏收紧，各含自动化文件路径与 `kiwi_id` 标注方式） |
| 当前状态 | 2222 已落自动化；2223 / 2224 待对应基座能力与护栏收紧落地后续写 |

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

### 3.2 护栏自测矩阵（Kiwi 2213 覆盖，本轮增 1 项） <a id="self-test"></a>

| 组 | 断言 | 结果 |
| --- | --- | --- |
| 实现文件豁免 | 集合体系实现文件（`core/concurrent.py` 等）内的裸容器注解不报 | 通过（新增） |
| 其余 | 检出 / 不检出（只读抽象）/ 位置与排除 / 基线语义 / 模式与输出 | 通过 |

**合计**：19 项断言全通过，`--self-test` 退出码 `0`。

## 4. 覆盖率 <a id="coverage"></a>

**定向验证 + 既有门禁**（口径见详细设计 §5）：本轮有运行时代码改动（`core/concurrent.py`），按《[测试规范](../../../../../../规范/测试规范.md)》「只跑受变更影响的部分」跑定向 `pytest`（`bms_core` 集合相关）与后端 `pyright` / `ruff`；`bms_core` 覆盖率门槛（≥70%）随既有门禁执行，全量与集成验证交 CI 按需触发。

## 5. 验证命令与结果 <a id="verify"></a>

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 定向用例 | `uv run pytest libs/bms_core/tests/core/test_concurrent.py libs/bms_core/tests/core/test_concurrent_stable.py` | 42 passed |
| 护栏自测 | `python3 scripts/tools/base-check/check-bare-collections.py --self-test` | 19 项通过 / exit 0 |
| 护栏复跑 | `python3 scripts/tools/base-check/check-bare-collections.py .` | 通过（基线 18 处可递减提示，无新增） |
| 静态检查 | `uv run ruff check` / `ruff format --check`（改动文件） | 通过 |
| 类型检查 | `uv run pyright`（backend 全量） | 0 errors |
| 本地预检 | `python3 scripts/tools/preflight/check-preflight.py --fast` | 全部通过 |
| 阶段状态 | `python3 scripts/tools/check-docs/check-status.py --root . --stage 06_认证与安全` | 502 项 0 硬 0 软 |
| 文档链接 | `python3 scripts/tools/base-check/check-links.py` | 0 断链 / 0 失效锚点 |

## 6. 问题与偏差 <a id="issues"></a>

| # | 问题 / 现象 | 处置 |
| --- | --- | --- |
| 1 | 分段写并发时序竞争（段内乱序破坏 `heapq.merge` 前提） | 段锁内取号 + 轮转分派段；实施记录 §4 问题 1 |
| 2 | 集合对称差集 `^` 语义错误 | 改 `not in self`；实施记录 §4 问题 2 |
| 3 | pyright strict：`AbstractSet` 导入 / `__eq__` 覆写 / `to_dict` `get` 兼容 | 逐一修正或按既有口径 `# pyright: ignore[...]`；实施记录 §4 问题 3 / 4 / 6 |
| 4 | `ConcurrentSortedDict.__iter__` 语义变更致既有断言失败 | 适配既有用例（设计 §7 已登记）；实施记录 §4 问题 5 |

## 7. 遗留 <a id="leftover"></a>

1. 用例 **2223**（契约零漂移与序列化形态）→ 随 `CONTRACT_COLLECTION` 与序列化链落地续写。
2. 用例 **2224**（存量归零与护栏收紧）→ 随护栏白名单收紧、基线吸收至 940 与 616 处存量整改续写。
3. 本任务尚无运行期全量回归；616 处存量整改完成后按详细设计 §5 用例 4~6 跑门禁与文档一致性核对。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

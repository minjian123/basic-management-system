# Redis 复合操作与并发语义测试记录

> 项目骨架 · 01 工程骨架 · 03 backend 分层目录与职责 · 嵌套子任务 03 · 测试记录 01

[文档首页](../../../../../../../文档首页.md) › [03 Redis 复合操作与并发语义](../01_工程骨架_03_backend分层目录与职责_03_Redis复合操作与并发语义.md) › 01 测试记录　|　[实施记录 →](../实施/03_实施_01_Redis复合操作与并发语义.md)　[详细设计 →](../设计/03_详细设计_01_Redis复合操作与并发语义.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 Redis 复合操作与并发语义](../01_工程骨架_03_backend分层目录与职责_03_Redis复合操作与并发语义.md) |
| 对应需求 | [01-3](../../../../../需求/01_需求_工程骨架.md#r01-3) |
| 详细设计 | [03_详细设计_01_Redis复合操作与并发语义](../设计/03_详细设计_01_Redis复合操作与并发语义.md) |
| 实施记录 | [01 实施记录](../实施/03_实施_01_Redis复合操作与并发语义.md) |
| 测试日期 | 2026-09-10 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；fakeredis 2.38.0；mjbk 真实 Redis 8（integration 实测） |
| Kiwi 用例 | 本任务新增 Case 18（Redis 复合操作与并发语义）；回归 Case 1–17 |
| 结论 | 69/69 通过（2 条 integration 未配置环境时跳过，实测真实 Redis 全绿）；全仓覆盖率 100% |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：`replace_if_equal`（命中/未命中/缺失）、`get_and_remove`（命中/缺失）、`update_atomic`（成功/缺失/重试/超限）、`get_locked`（提交/缺失）；真实 Redis 上的 Lua 原子与 WATCH 行为。不含：Redis Cluster、阶段十压测、02-3 异常体系替换后的响应口径。

| Kiwi ID | 用例 | 类型 | 自动化文件 | 结果 |
| --- | --- | --- | --- | --- |
| 18 | Redis 复合操作与并发语义（CAS 三分支、取走删除、乐观更新与重试、上下文提交、缺失分支） | 单元 | `tests/core/test_redis_collections.py`（3 条） | 通过 |
| 18 | 真实 Redis：Lua 原子、乐观更新、上下文提交、版本号 | 集成 | `tests/integration/test_redis_collections_integration.py`（2 条） | 通过（真实 Redis 实测） |
| 17 | 01-3-2 Redis 有序封装回归 | 单元 | `tests/core/test_redis_collections.py` | 通过 |
| 14 | BaseObject 取字段混合口径（fields 回退分支） | 单元 | `tests/core/test_base_object.py` | 通过 |
| 1–16 | 其余既有用例回归 | 接口·单元 | 既有 `tests/*` | 通过 |

## 3. 执行记录与结果 <a id="run"></a>

```bash
cd backend
uv run pytest -q
# 69 passed, 2 skipped（integration 未配置 BMS_TEST_REDIS_URL 时跳过）

BMS_TEST_REDIS_URL="redis://<mjbk>:6379/0" uv run pytest tests/integration -q -m integration
# 2 passed（真实 Redis 8 实测）
```

| 验证点 | 实测 |
| --- | --- |
| `replace_if_equal` 命中/不匹配/缺失 | `True / False / False`，值正确更新 |
| `get_and_remove` | 返回旧值并删除；再取返回 None |
| `update_atomic` 成功/缺失/重试/超限 | 成功返回新值；缺失 `KeyError`；首个 `WatchError` 后重放成功；持续冲突 `ConcurrentConflictError` |
| `get_locked` 提交/缺失 | holder 写回生效；缺失进入时 `KeyError` |
| 真实 Redis Lua/WATCH/版本号 | integration 2 条全绿，无 key 残留（用例自清理） |

质量门禁（辅助）：`ruff` 通过；`pyright` 0 errors。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 真实并发竞态难以稳定复现（重试分支） | 时序调度依赖 | monkeypatch `_optimistic` 确定性模拟 `WatchError`（重试成功/超限），真实 WATCH 冲突检测另行验证 | [实施记录 §4](../实施/03_实施_01_Redis复合操作与并发语义.md#issues) |

## 5. 覆盖率 <a id="coverage"></a>

| 文件 | 语句 | 未覆盖 | 覆盖率 |
| --- | --- | --- | --- |
| `app/core/redis_collections.py` | 179 | 0 | 100% |
| `app/core/base.py`（含 ValueHolder 与混合取字段） | 50 | 0 | 100% |
| `app/core/concurrent.py`（ValueHolder 迁移后） | 383 | 0 | 100% |
| 其余模块 | 230 | 0 | 100% |
| **合计** | **842** | **0** | **100%** |

口径：任务级覆盖率快照；门禁随 05-1 接入 CI。

## 6. 偏差与遗留 <a id="deviations"></a>

- `get_locked` 冲突不重试为设计语义（调用方决策），非缺陷；相关说明见设计 §4。
- integration 用例在 CI 中的执行依赖 05-02 注入 `BMS_TEST_REDIS_URL`（已补入该任务集成用例清单）。
- Redis Cluster 与压测口径随阶段十；02-3 接管 `ConcurrentConflictError` 后如需调整断言在设计修订同步。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「测试文档（任务测试记录）」节测试文档结构组织

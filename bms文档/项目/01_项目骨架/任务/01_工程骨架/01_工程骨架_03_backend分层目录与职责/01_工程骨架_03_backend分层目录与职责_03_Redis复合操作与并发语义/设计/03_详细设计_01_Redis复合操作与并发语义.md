# Redis 复合操作与并发语义详细设计

> 项目骨架 · 01 工程骨架 · 03 backend 分层目录与职责 · 嵌套子任务 03 · 详细设计

[文档首页](../../../../../../../文档首页.md) › [03-3 Redis 复合操作与并发语义](../01_工程骨架_03_backend分层目录与职责_03_Redis复合操作与并发语义.md) › 01 详细设计　|　[← 父任务](../../01_工程骨架_03_backend分层目录与职责.md)

## 1. 概述 <a id="overview"></a>

- **目标**：补全 01-3-2 遗留的 Redis 复合操作与并发语义——`replace_if_equal` / `get_and_remove` 以 Lua 原子化，`update_atomic` / `get_locked` 以 WATCH+MULTI 乐观并发实现，使 Redis 有序封装具备与进程内并发集合对等的读-改-写能力。
- **范围**：仅扩展 `core/redis_collections.py` 与配套异常/测试；不改 01-3-2 已交付接口语义（set/get/delete/items 不变）。
- **依据**：需求 [01-3](../../../../../需求/01_需求_工程骨架.md#r01-3) 第 7 条、01-3-2 设计 §5.2/§10 开放项、《[后端开发规范](../../../../../../../规范/后端开发规范.md)》第 8 节、2026-09-10 偏差核对结论。

## 2. 差距与机制选型 <a id="gap"></a>

| 操作 | 01-3-2 现状 | 本轮机制 | 理由 |
| --- | --- | --- | --- |
| `replace_if_equal`（CAS） | 无 | **Lua** | 比较对象是序列化值，脚本内可完成「比较 + 双结构写」 |
| `get_and_remove` | 无 | **Lua** | 读+删+双结构一致，天然脚本化 |
| `update_atomic` | 无 | **WATCH + MULTI 乐观重试** | 变换函数是 Python 代码，无法进 Lua；WATCH 检测并发写后整体重放 |
| `get_locked` | 无 | **WATCH 提交（不重试）** | 调用方变换发生在上下文内，重放会丢失其副作用；冲突上抛由调用方决策 |

## 3. Lua 脚本设计 <a id="lua"></a>

```lua
-- replace_if_equal：current == expected 才写入
local current = redis.call('HGET', KEYS[2], ARGV[1])
if not current then return 0 end
if current == ARGV[2] then
  redis.call('HSET', KEYS[2], ARGV[1], ARGV[3])
  redis.call('ZADD', KEYS[1], ARGV[4], ARGV[1])
  return 1
end
return 0
```

```lua
-- get_and_remove：取旧值并双结构删除
local current = redis.call('HGET', KEYS[2], ARGV[1])
if not current then return false end
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('ZREM', KEYS[1], ARGV[1])
return current
```

- 比较口径：`expected` 与既有值均以**稳定 JSON 序列化**（`_dump`，键排序）后逐字节比较；
- 返回值：`replace_if_equal` → 布尔；`get_and_remove` → 旧值或 None；均在成功变更时 `INCR {key}:version`。

## 4. WATCH 乐观重试设计 <a id="watch"></a>

```python
async def update_atomic(self, key, func, *, max_retries: int = 3) -> ValueT: ...

async def _optimistic(self, key, mutate: Callable[[str | None], str]) -> str:
    async with self._client.pipeline(transaction=True) as pipe:
        await pipe.watch(self._data_key)
        current = await pipe.hget(self._data_key, member)
        new_value = mutate(current)          # 键缺失时 mutate 抛 KeyError
        pipe.multi()
        pipe.hset(...); pipe.zadd(...)
        await pipe.execute()                 # 冲突抛 WatchError
    return new_value
```

- 重试循环：捕获 `WatchError` 整体重放 `_optimistic`；成功 → `_bump()` 一次并返回新值；
- 上限 `max_retries`（默认 3，可调）；耗尽抛 `ConcurrentConflictError`；
- `update_atomic` 的 `func` 必须**纯计算**（禁 IO/耗时），重放语义安全；
- `get_locked`：`@asynccontextmanager`——WATCH 后读取并 yield `ValueHolder`；退出时 `MULTI` 提交（`hset + zadd`）并 `_bump()`；提交遇 `WatchError` **上抛**（不重放，避免覆盖调用方基于旧值的变换）；键缺失在进入上下文时抛 `KeyError`。

## 5. 异常与类型口径 <a id="exception"></a>

- `core/exceptions.py` 新增 `ConcurrentConflictError(Exception)` 占位（02-3 接入 BizError 体系后替换）；
- `ValueHolder[ValueT]` 提升到 `core/base.py` 公共类（原 01-3-2 的 `_ValueHolder`），进程内与 Redis 两处复用。

## 6. 测试设计（Kiwi 先行） <a id="tests"></a>

| Kiwi | 用例 | 自动化文件 |
| --- | --- | --- |
| 18 | Redis 复合操作与并发语义（CAS 命中/未命中/缺失、取走删除、update_atomic 成功/重试/超限/缺失、get_locked 提交/缺失/冲突上抛） | `tests/core/test_redis_collections.py` |
| 17 | 01-3-2 既有 Redis 用例回归 | 同上 |
| 14 | BaseObject 取字段口径（dataclass fields 优先、回退 `__dict__`） | `tests/core/test_base_object.py` |

真实 Redis integration：`tests/integration/test_redis_collections_integration.py`（`pytestmark = pytest.mark.integration`，读 `BMS_TEST_REDIS_URL`，未配置跳过；随 05-02 流水线执行）。

## 7. 实施步骤 <a id="steps"></a>

1. Kiwi 登记 Case 18。
2. `ValueHolder` 上移 `core/base.py`；新增 `ConcurrentConflictError`。
3. `core/redis_collections.py`：新增 Lua 两脚本；实现 `replace_if_equal / get_and_remove / update_atomic / get_locked`。
4. 单元用例（fakeredis + monkeypatch 模拟冲突/重试/超限）与 integration 用例。
5. `pyproject.toml` 注册 `integration` marker；05-02 任务清单补 Redis 集成用例。
6. 验证与回写（ruff / pyright / 覆盖率 / integration 实测）。

## 8. 验收映射 <a id="accept-map"></a>

| 完成标准 | 验证方式 |
| --- | --- |
| 四类复合操作语义与失败分支 | Kiwi 18 用例（含重试/超限/缺失/冲突） |
| 真实 Redis 可运行 | `BMS_TEST_REDIS_URL` 实测 integration 用例通过 |
| 无 lint/类型错误 | ruff / pyright |
| 覆盖率 100% | `pytest --cov=app` |
| Kiwi 登记并标注 | 平台 + `kiwi_id` |

## 9. 边界与开放项 <a id="boundary"></a>

- `get_locked` 不做自动重试（语义原因见 §4）；需要重试的调用方自行捕获 `WatchError`/`ConcurrentConflictError` 重做变换。
- Redis Cluster 下 WATCH 的跨槽限制随部署口径（当前单实例 compose），Cluster 适配随阶段十。
- 分片/大 key、压测口径沿用 01-3-2 边界。

## 10. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 归属 | 01_03 下嵌套子任务 01-3-3，依赖 01-3-2 |
| 2 | 机制 | CAS/取走删除用 Lua；update_atomic 用 WATCH 乐观重试（≤3）；get_locked WATCH 提交不重试 |
| 3 | 工时 | 6h；01_03 重估 21h；父任务 35h；阶段总 86h |
| 4 | 测试 | fakeredis 单元 + 真实 Redis integration（标 integration，随 05-02） |
| 5 | 基线 | 需求 01-3 追加第 7 条；状态与账目沿用前例同步 |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认

# Redis 复合操作与并发语义实施记录

> 项目骨架 · 01 工程骨架 · 03 backend 分层目录与职责 · 嵌套子任务 03 · 实施记录 01

[文档首页](../../../../../../../文档首页.md) › [03 Redis 复合操作与并发语义](../01_工程骨架_03_backend分层目录与职责_03_Redis复合操作与并发语义.md) › 01 实施记录　|　[详细设计 →](../设计/03_详细设计_01_Redis复合操作与并发语义.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 Redis 复合操作与并发语义](../01_工程骨架_03_backend分层目录与职责_03_Redis复合操作与并发语义.md) |
| 对应需求 | [01-3](../../../../../需求/01_需求_工程骨架.md#r01-3) |
| 详细设计 | [03_详细设计_01_Redis复合操作与并发语义](../设计/03_详细设计_01_Redis复合操作与并发语义.md) |
| 实施日期 | 2026-09-10 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；fakeredis 2.38.0（lupa 2.8）；mjbk 真实 Redis 8（6379，integration 实测，连接串经环境变量注入不落盘） |
| 提交 | —（随本批提交，见仓库 git log） |
| 结论 | Lua CAS/取走删除、WATCH 乐观重试、get_locked 提交上下文全部落地；单元 + 真实 Redis 双口径验证通过 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[Kiwi 18 登记] --> B[ValueHolder 上移 + 冲突异常]
    B --> C[Lua CAS/取走删除]
    C --> D[WATCH 乐观重试 + get_locked]
    D --> E[integration 用例与 marker]
    E --> F[05-02 清单 + 真实 Redis 实测]
    F --> G[验证与回写]
```

| 步骤 | 内容 | 结果 |
| --- | --- | --- |
| 1 | `ValueHolder` 上移 `core/base.py`；新增 `ConcurrentConflictError` | 完成 |
| 2 | Lua 脚本：`replace_if_equal`、`get_and_remove` | 完成 |
| 3 | WATCH：`update_atomic`（重试 ≤3）、`get_locked`（提交不重试） | 完成 |
| 4 | 单元用例（Kiwi 18）+ integration 用例 + `integration` marker | 完成 |
| 5 | 05-02 集成用例清单补录；真实 Redis 实测 | 通过（2 passed） |
| 6 | 验证（ruff / pyright / 覆盖率 100%） | 全部通过 |

## 3. 实施过程 <a id="process"></a>

### 3.1 公共件与异常

- `ValueHolder[ValueT]` 从 `core/concurrent.py` 提升到 `core/base.py`（进程内 `get_locked` 与 Redis `get_locked` 复用同一容器）；
- `core/exceptions.py` 新增 `ConcurrentConflictError(Exception)` 占位（02-3 归入 BizError 体系）。

### 3.2 Lua 原子操作

- `replace_if_equal`：脚本内 `HGET` 比较稳定 JSON 序列化值，命中才 `HSET + ZADD`，返回布尔；
- `get_and_remove`：脚本内取值后 `HDEL + ZREM`，返回旧值或 nil；
- 两者均在成功变更时 `INCR {key}:version`（快照失效）。

### 3.3 WATCH 乐观并发

- `update_atomic`：`_optimistic` 单轮 WATCH+MULTI（WATCH 数据 key → HGET → mutate（键缺失抛 KeyError）→ MULTI → HSET+ZADD → EXECUTE）；`WatchError` 由 `_optimistic_with_retry` 整体重放，上限默认 3，超限抛 `ConcurrentConflictError`；成功后 `_bump()` 一次；
- `get_locked`：`@asynccontextmanager`——WATCH 读并 yield `ValueHolder`，退出时 MULTI 提交（冲突上抛不重试，避免覆盖调用方基于旧值的变换）；键缺失在进入上下文时抛 `KeyError`。

### 3.4 测试与集成

- 单元：Kiwi 18 覆盖 CAS 三分支、取走删除、乐观更新成功/缺失、重试成功（monkeypatch 单轮方法确定性模拟 `WatchError`）、超限；
- integration：`tests/integration/test_redis_collections_integration.py`（`pytestmark = integration`，`BMS_TEST_REDIS_URL` 未配置则跳过），逻辑覆盖 Lua 原子、乐观更新、上下文提交与版本号；
- `pyproject.toml` 注册 `integration` marker；05-02 任务「集成用例清单」补录本项目。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | `get_locked` 冲突后无法自动重放 | 调用方变换发生在上下文内，重放会重复/丢失其副作用 | 设计明确「WATCH 提交、冲突上抛、调用方决策」；与 `update_atomic`（纯函数、可重放）语义区分 | 设计 §4 |
| 2 | 并发重试分支用真实竞态难以稳定触发 | 时序依赖调度 | 用例 monkeypatch `_optimistic` 单轮方法，确定性覆盖重试与超限分支（真实冲突检测已单独验证 fakeredis/真实 Redis WATCH 行为） | 测试记录 §4 |

## 5. 验证结果 <a id="verify"></a>

| 验证点（完成标准） | 方法 | 结果 |
| --- | --- | --- |
| 四类复合操作语义与失败分支 | Kiwi 18（fakeredis） | 通过 |
| 真实 Redis 可运行 | `BMS_TEST_REDIS_URL=redis://<mjbk>:6379/0 uv run pytest tests/integration -m integration` | 通过（2 passed） |
| `uv run ruff check .` / `uv run pyright` | 命令 | 通过（0 错误） |
| `uv run pytest` | 命令 | 通过（69 passed、2 skipped 为未配置集成环境时的跳过） |
| 覆盖率 | `pytest --cov=app` | 通过（842 语句 100%） |
| Kiwi 登记并标注 | 平台 Case 18 + `kiwi_id` | 通过 |

## 6. 偏差与遗留 <a id="deviations"></a>

- `get_locked` 非重试语义为设计决策（见 §4 问题 1），非偏差；调用方需重试时自行捕获 `WatchError`/`ConcurrentConflictError` 重做变换。
- Redis Cluster 下 WATCH 跨槽限制随部署口径（当前单实例 compose），Cluster 适配随阶段十二。
- `ConcurrentConflictError` 为过渡异常，02-3 统一异常体系接管后替换。
- 大 key 阈值/分片数、free-threading 复测沿用 01-3-2 边界（阶段十二）。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「实施文档（任务执行记录）」节实施文档结构组织

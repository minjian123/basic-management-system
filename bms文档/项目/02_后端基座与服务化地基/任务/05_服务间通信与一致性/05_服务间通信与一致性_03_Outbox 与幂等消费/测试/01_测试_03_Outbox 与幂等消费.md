# Outbox 与幂等消费测试记录

> 后端基座与服务化地基 · 05 服务间通信与一致性 · 03 Outbox 与幂等消费 · 测试记录

[文档首页](../../../../../../文档首页.md) › [03 Outbox 与幂等消费](../05_服务间通信与一致性_03_Outbox 与幂等消费.md) › 01 测试　|　[详细设计](../设计/01_详细设计_03_Outbox 与幂等消费.md) · [实施记录](../实施/01_实施_03_Outbox 与幂等消费.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 Outbox 与幂等消费](../05_服务间通信与一致性_03_Outbox 与幂等消费.md) |
| 对应需求 | [05-3](../../../../需求/05_需求_服务间通信与一致性.md#r05-3) |
| 详细设计 | [01_详细设计_03_Outbox 与幂等消费](../设计/01_详细设计_03_Outbox 与幂等消费.md) |
| 测试日期 | 2026-09-23 |
| 测试环境 | 开发机（Ubuntu，Python 3.14.4 / uv；SQLite；fakeredis） |
| Kiwi 用例 | 2172（发件箱与投递器）/ 2173（幂等消费与业务幂等键） |
| 结论 | 通过 |

## 2. 用例清单与执行结果 <a id="cases"></a>

| 用例文件 | Kiwi | 类型 | 断言要点 | 结果 |
| --- | --- | --- | --- | --- |
| `libs/bms_core/tests/outbox/test_outbox_store.py` | 2172 | 单元 | `enqueue` 缺省补齐 / 事务回滚不发事件；`claim_pending` 同聚合队首与未到期阻塞 / limit 边界与截断；`mark_delivered`；`mark_failed` 截断 / 退避 / 超限转死信；`replay` 按 事件 ID / 类型 / 聚合 / 时间 与 limit / 无匹配；死信列表 / 筛选 / 详情 / 状态读写 | 通过 |
| `libs/bms_core/tests/outbox/test_outbox_dispatcher.py` | 2172 | 单元 | 转发 + 标记 + 指标；同聚合跨轮顺序；失败退避 / 转死信；多库异常隔离；`OutboxDeliveryError` 原样上抛与单库隔离；后台启停与单轮异常不终止；空实现无副作用；提供者解析 | 通过 |
| `libs/bms_core/tests/outbox/test_consumed.py` | 2173 | 单元 | 首次 `mark` True / 重复 False；不同消费者各自首次；与副作用同事务提交；回滚时幂等登记一并撤销 | 通过 |
| `libs/bms_core/tests/idempotency/test_idempotency_redis.py` | 2173 | 单元 | SETNX 首次 / 重复；处理中返回 None；首结果复用；TTL；反序列化边界；Redis 不可用降级 | 通过 |
| `libs/bms_core/tests/ops/test_outbox_cli.py` | 2172 | 集成 | `dispatch` 手动投递并标记；`replay` 条件重置；库不可用非 0 退出码 | 通过 |
| `services/platform/tests/api/test_outbox.py` | 2173 | 集成 | 死信列表分页 / 筛选 / 详情；重投（重置发件箱待投递）与状态冲突 10003；忽略；404 / 10002 | 通过 |
| 既有回归 | — | 单元 + 集成 | 全量 pytest / ruff / pyright / 基座 / 预检 | 通过 |

## 3. 覆盖率 <a id="coverage"></a>

| 模块 | 语句 / 分支 | 覆盖率 |
| --- | --- | --- |
| `bms_core/outbox/`（base / store / dispatcher / consumed / null / `__init__`） | — | **100%** |
| `bms_core/idempotency/redis.py` | — | **100%** |
| `bms_core/models/outbox.py` | — | **100%** |
| 全量套件 | — | 1078 passed / 36 skipped |

命令：`uv run pytest -q libs/bms_core/tests/outbox libs/bms_core/tests/idempotency/test_idempotency_redis.py libs/bms_core/tests/ops/test_outbox_cli.py services/platform/tests/api/test_outbox.py --cov=bms_core.outbox --cov=bms_core.idempotency.redis --cov=bms_core.models.outbox --cov-branch`

## 4. 问题与偏差 <a id="issues"></a>

- 消费幂等去重实现偏离设计初稿（`SAVEPOINT` → 事务内查 + 唯一约束兜底），原因与处置见[实施记录 §4](../实施/01_实施_03_Outbox 与幂等消费.md#issues)与[详细设计 §4.5](../设计/01_详细设计_03_Outbox 与幂等消费.md#consumed)；用例覆盖「重复不破坏外层事务」与「回滚一并撤销」两条路径。
- 死信看板接口按请求租户库读取（演示租户回落）；跨租户全局视图登记为开放项（归运维阶段）。
- 后台轮询生产默认关（`[outbox].enabled = false`）；用例以短间隔启停验证循环与单轮异常隔离。

## 5. 验收映射 <a id="accept"></a>

| 完成标准（需求 05-3） | 验证用例 | 结论 |
| --- | --- | --- |
| 库↔事件原子（回滚不发事件） | `test_outbox_store.py::test_enqueue_defaults_and_rollback` | 通过 |
| 投递器转发与标记正确 | `test_outbox_dispatcher.py`（假发布器 + 指标）+ `ops` CLI 用例 | 通过 |
| 消费幂等去重 | `test_consumed.py` + `test_idempotency_redis.py` | 通过 |
| 重放安全 | `replay` 用例 + 消费端 `event_id` 幂等 | 通过 |
| 顺序投递 / 死信看板 | 同聚合顺序用例 + `test_outbox.py` 接口用例 | 通过 |
| `pytest` / `ruff` / `pyright` 全绿 | 门禁命令（见实施记录 §5） | 通过 |

> 依《文档生成规范》编写 · 与《实施记录》配套

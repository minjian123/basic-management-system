# 01 测试记录 · Redis 基础能力统一

> 项目骨架 · 03 后端基础能力 · 子任务 04（需求 03-5）· 测试记录

[文档首页](../../../../../../文档首页.md) › [03 后端基础能力](../../03_后端基础能力.md) › 测试记录　|　[← 任务](../03_后端基础能力_04_Redis基础能力统一.md)　[实施记录 →](../实施/01_实施_04_Redis基础能力统一.md)

## 1. 执行与结果 <a id="run"></a>

| 项 | 命令（`backend/`） | 结果 |
| --- | --- | --- |
| 后端全量 | `uv run pytest -q` | **2127 passed / 51 skipped / 0 failed**（158s） |
| 静态（lint） | `uv run ruff check libs services ops tests_support` | 全绿 |
| 静态（类型） | `uv run pyright` | **0 errors / 0 warnings** |
| 裸集合护栏 | `pytest libs/bms_core/tests/boundary/test_bare_collections_guard.py` | 4 passed（全链集合声明命中 **0**、基线 0） |
| 插件契约 | `pytest services/platform/tests/contracts services/platform/tests/crosscut tests/test_plugin_registration.py -q` | 全绿（含新增 `redis_client` 键与 null 实现断言） |
| 预检 | `python3 scripts/tools/preflight/check-preflight.py --fast` | 全部通过 |
| 文档门禁 | `check-links` / `check-docs-scope` / `check-status --stage 01_项目骨架` / `check-base` | 断链 0 / 违规 0 / 硬 0 软 0 / 通过 |

## 2. 覆盖的关键路径 <a id="coverage"></a>

| 验收点（需求 03-5） | 用例证据 |
| --- | --- |
| 无能力域自建 Redis 客户端 | 源码检索（`from_url` 仅出现在 `bms_core/redis/redis.py`）；`test_plugin_registration` 端口清单一致 |
| 共享客户端与配置生效 | `tests/core/test_config.py`（`[redis]` 键缺省）；`tests/idp/test_state_store.py`（共享客户端同一实例） |
| 必需域 fail-closed | `tests/idempotency/test_idempotency_redis.py::test_unavailable_fails_closed`、`tests/consistency/test_barrier.py::test_redis_unavailable_fails_closed`、`tests/lock/test_lock_redis.py::test_redis_lock_fails_closed`（均断言 `code == 10012` / `http_status == 503`） |
| 缓存域可降级 | `tests/cache/*`、`tests/config/test_config_edges.py`、`tests/dict/*`（不可用回落来源，不抛错） |
| 限流可降级 + 状态可见 | `tests/ratelimit/test_rate_limiter.py`（降级 memory 判定 + `is_degraded`） |
| 就绪探针 | `services/platform/tests/health/test_checks.py`（注入客户端：成功 / 失败两态；经统一端口取共享客户端） |
| 插件契约与注册表 | `services/platform/tests/contracts/test_plugin_contracts.py`、`services/platform/tests/crosscut/test_plugin_registration.py`（`redis_client` 端口 / null 实现 / 版本） |

## 3. 口径变更适配的用例 <a id="adapt"></a>

| 用例 | 变更 |
| --- | --- |
| `test_idempotency_redis.py::test_unavailable_degrades` | 改为 `test_unavailable_fails_closed`（放行 → 报错 `10012` / 503） |
| `test_barrier.py::test_redis_unavailable_degrades` | 改为 `test_redis_unavailable_fails_closed`（degrade-open 作废） |
| `test_lock_redis.py::test_redis_lock_degrades_to_memory` | 改为 `test_redis_lock_fails_closed`（不降级进程内锁） |
| `test_config.py::test_defaults_and_sections` | 缓存 provider 断言按 dev 口径（`memory`）；新增 `RedisSettings` 类缺省断言 |
| `test_plugin_registration.py::_EXPECTED_PLUGIN_KEYS` | 补 `redis_client` |
| `tests/health/test_checks.py` | 由「patch `Redis.from_url`」改为**注入 `client=`** |

## 4. 遗留与再验 <a id="leftover"></a>

1. **真实 Redis 集成用例**（`BMS_TEST_REDIS_URL` 已加入 CI `.integration-base`）：待下次流水线命中集成档后回填执行证据。
2. **限流「降级中」指标**与告警规则未接线（当前有 `is_degraded` 与日志事件）。
3. 三库真库 / 达梦环境下的 Redis 真实链路（本地开发机默认走远端开发机实例）待部署联调复核。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

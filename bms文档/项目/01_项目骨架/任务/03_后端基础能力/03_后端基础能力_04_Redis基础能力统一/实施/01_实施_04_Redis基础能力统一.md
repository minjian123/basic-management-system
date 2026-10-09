# 01 实施记录 · Redis 基础能力统一

> 项目骨架 · 03 后端基础能力 · 子任务 04（需求 03-5）· 实施记录

[文档首页](../../../../../../文档首页.md) › [03 后端基础能力](../../03_后端基础能力.md) › 实施记录　|　[← 任务](../03_后端基础能力_04_Redis基础能力统一.md)　[详细设计 →](../设计/01_详细设计_04_Redis基础能力统一.md)

## 1. 概述 <a id="intro"></a>

按[详细设计](../设计/01_详细设计_04_Redis基础能力统一.md)五步实施：**统一客户端能力域 → 配置加厚 → 不可用口径统一 → provider 缺省翻转 → 环境前置**。代码提交 `feat(03): Redis 基础能力统一（统一客户端能力域 + fail-closed 口径 + 缺省启用）`。

## 2. 交付物清单 <a id="deliver"></a>

| # | 交付物 | 落点 |
| --- | --- | --- |
| 1 | 统一客户端能力域（端口 / 真实实现 / 缺省实现 / 进程共享登记） | `libs/bms_core/src/bms_core/redis/{__init__,base,redis,null}.py` |
| 2 | 配置加厚（8 键）与三环境 + 模板 | `core/config.py`（`RedisSettings`）、`config.toml`、`config.dev.toml`、`backend/.env.example` |
| 3 | 装配接线（能力清单 / 缺省模块 / 工厂 / 必需校验） | `core/assembly.py` |
| 4 | 错误码与异常 | `core/error_codes.py`（`10012`）、`core/exceptions.py`（`RedisUnavailableError`） |
| 5 | 十域改共享客户端 | `cache`（同步 / 异步）、`idempotency`、`consistency`、`lock`、`ratelimit`、`session`、`idp/state`、`captcha`、`health` |
| 6 | 不可用口径统一（fail-closed / 可降级） | 同上（幂等 / 屏障 / 锁改 fail-closed；限流保留降级并暴露 `is_degraded`） |
| 7 | provider 缺省翻转 | `config.toml`：`cache` / `consistency_barrier` / `idempotency` → `redis` |
| 8 | 测试夹具（零外部依赖） | `backend/tests_support/redis.py`（新）+ 10 份 `tests/conftest.py` |
| 9 | CI Redis service 与集成变量 | `.gitlab-ci.yml`（`.integration-base`） |

## 3. 实施要点 <a id="impl"></a>

1. **共享语义**：`RedisRedisClient` 持进程内同步 / 异步各一个客户端（各一连接池）；装配期 `setup()` 经 `set_shared_redis_client` 登记为进程共享实例；十域实现「**显式注入优先，否则取 `shared_*_client()`**」，全仓不再有域自建 `from_url`。
2. **必需校验**：`assemble_plugins` 增「`[redis].required=true` 且 `provider` 为空 → 拒启」；同时把能力选择分区的 `provider` 读取改为鸭子类型（`[redis]` 为「连接参数 + 实现选择」同区分区）。
3. **短超时**：`socket_timeout` / `socket_connect_timeout` 取 `[redis].socket_timeout_ms`（缺省 500ms）；`max_connections` 取 `pool_size`（0 = 客户端默认）。
4. **fail-closed**：幂等（`begin` / `load` / `save`）、一致性屏障（`_read` / `mark_applied` / `applied_version`，**取消 degrade-open**）、分布式锁（`acquire` / `release` / `extend`，**取消降级 memory**）不可用即抛 `RedisUnavailableError`（`10012` / 503）；缓存三域仍降级直连库；限流保留降级 `MemoryRateLimiter` 并新增 `is_degraded` 与 `ratelimit_redis_degraded` / `ratelimit_redis_recovered` 事件。
5. **测试零外部依赖**：夹具装入 `install_process_fake_redis_client()`（fakeredis 承载的共享客户端），并在夹具内关闭统一客户端 provider（`REQUIRED=false`）与 `idempotency` / `consistency_barrier` 的 provider，保持既有用例行为不变。

## 4. 偏差与决策 <a id="deviation"></a>

| # | 项 | 实施口径 | 理由 |
| --- | --- | --- | --- |
| 1 | **dev 三域缓存保留 `memory`** | `config.dev.toml` 的 `cache` / `dict_cache_region` / `config_cache_region` **未随 test / prod 翻 Redis** | 均为**可降级**域（语义不受影响）；保留可让「本地无 Redis 亦能跑完整链路」，且既有用例（租户解析缓存、菜单版本失效）依赖进程内实现内部行为。**test / prod 走 Redis** |
| 2 | 共享实例登记方式 | 由 `redis` 实现的 `setup()` 登记**进程共享实例**，各域默认取共享（而非由装配工厂逐个注入 client） | 十域实现已支持 `client=` 注入（测试通道），共享登记可**零改造工厂签名**达成「单进程共享连接池」，改造面最小、语义等价 |
| 3 | `fallback` 参数 | 分布式锁的 `fallback` 构造参数**保留但不再使用**；限流的 `fallback` 保留并继续使用 | 前者取消降级（fail-closed），后者按口径定稿保留降级 |
| 4 | 本地一键拉起 Redis | **未实施**（留待后续） | 现 `本地全套.sh` 默认指向远端开发机 Redis（`redis://192.168.0.107:6379/5`）可用；自动拉起容器属便利项，避免在收口轮引入 shell 改动风险 |

## 5. 遗留 <a id="leftover"></a>

| # | 事项 | 归口 |
| --- | --- | --- |
| 1 | 《后端基类清单》登记 `BaseRedisClient` / `RedisRedisClient` / `NullRedisClient`（清单对账守卫当前未覆盖 `bms_core/redis/`，登记需与守卫口径同步） | 后续基座文档维护（与守卫口径一并） |
| 2 | 本地一键脚本自动拉起 Redis（含 `status` 增 Redis 一行） | 03_04 后续小项 / 运维 |
| 3 | 限流「降级中」**指标**（当前已具备 `is_degraded` 与日志事件，指标接线与告警规则未接） | 可观测性 / 运维（随 `08` 域或运维阶段） |
| 4 | 真实 Redis 集成用例在 CI 的执行实证（本次已加 service 与 `BMS_TEST_REDIS_URL`，待流水线命中） | 下次流水线（集成档） |

## 6. 门禁 <a id="gate"></a>

后端 `pytest` **2127 passed / 51 skipped / 0 failed**；`ruff` 全绿；`pyright` **0 error**；裸集合护栏归零；`check-links` / `check-docs-scope` / `check-status`（阶段一硬 0 软 0）/ `check-base` / `preflight --fast` 全绿。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》与《[AI开发规范](../../../../../../规范/AI开发规范.md)》编写

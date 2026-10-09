# 01 详细设计 · Redis 基础能力统一

> 项目骨架 · 03 后端基础能力 · 子任务 04（需求 03-5）· 详细设计

[文档首页](../../../../../../文档首页.md) › [03 后端基础能力](../../03_后端基础能力.md) › 详细设计　|　[← 任务](../03_后端基础能力_04_Redis基础能力统一.md)

## 1. 设计目标与范围 <a id="goal"></a>

把 Redis 从「十个能力域各自接线的可选件」提升为**基础（必需）功能**，一次统一，后续新增用 Redis 的能力**只接共享 client**：

1. **统一客户端能力域** `bms_core/redis/`：端口 `BaseRedisClient` + `redis` / `null` 实现 + **共享连接池**（进程内同步 / 异步各一池）+ 统一 key 前缀 / TTL / 超时口径。
2. **配置加厚**：`[redis]` 由「只有 `url`」扩到含库号 / 池 / 短超时 / 键前缀 / 必需标志。
3. **不可用口径统一**：必需域 fail-closed、缓存域可降级。
4. **provider 默认翻转**：缺省即真实 Redis。
5. **环境前置**：本地自动拉起、CI 增 Redis service、单测 fakeredis 通道。

**范围外**：Redis 集群 / Sentinel 部署（归部署与运维阶段）；key 业务语义与各域缓存策略（沿用现状）；不新增业务能力。

## 2. 现状事实（对齐基线） <a id="baseline"></a>

| # | 事实 | 位置 |
| --- | --- | --- |
| 1 | `RedisSettings` **只有 `url` 一个字段**，无库号 / 池 / 超时 / 必需标志 | `core/config.py`「RedisSettings」 |
| 2 | 十个域**各自建连**：`RedisIdempotencyStore`、`RedisConsistencyBarrier`、`RedisDistributedLock`、`RedisRateLimiter`、`RedisSessionStore`、`RedisIdpStateStore`、`DefaultCaptcha`、`RedisCacheRegion`（同步 + 异步两套）、`RedisHealthCheck` 均自持 `from_url` | `idempotency/redis.py`、`consistency/redis.py`、`lock/redis.py`、`ratelimit/redis.py`、`session/redis.py`、`idp/state/redis.py`、`captcha/default.py`、`cache/redis.py`、`health/checks.py` |
| 3 | 不可用行为**五套并存**：degrade-open（幂等 / 一致性屏障）、降级 memory（锁 / 限流）、忽略 + warning（缓存三域）、fail-closed（会话 load / IdP consume / 验证码）、仅探针（健康检查） | 同上 |
| 4 | 架构要求「Redis 操作短超时快速失败（如 500ms）」**未落地**（全仓无 `socket_timeout` / `retry_on_timeout`） | 《架构设计 · 性能与安全》「Redis 短超时」 |
| 5 | 缺省**已用真 Redis**：`session_store` / `rate_limiter` / `distributed_lock` / `idp_state_store` / `captcha`；缺省**未启用**：`cache` / `dict_cache_region` / `config_cache_region`（dev=memory）、`idempotency`（null）、`consistency_barrier`（null） | `config.toml`、`config.dev.toml` |
| 6 | 开发 / 测试环境为「可选」姿态：单测 `conftest` 强制把会话 / 限流 / 验证码 / 分布式锁 provider **置空回落 null**；dev 用 memory；**CI 无 Redis service、无 `BMS_TEST_REDIS_URL`**；本地脚本默认指向**远端开发机**实例且不自动拉起 | `libs/bms_core/tests/conftest.py`、`.gitlab-ci.yml`、`scripts/tools/dev/本地全套.sh` |
| 7 | 单测已具备 fakeredis 通道（`fakeredis[lua]`，各实现支持 `client=` 构造注入） | 各域单测、`typings/fakeredis/` |

**结论**：调用点**不需要改**（能力域端口化 + 规范强制「禁止模块内自建 Redis 客户端」），真正的成本集中在**统一 client、口径一致、默认启用、环境前置**四件事。

## 3. 统一客户端能力域 <a id="domain"></a>

```text
backend/libs/bms_core/src/bms_core/redis/
├── __init__.py        # 导出端口与实现
├── base.py            # BaseRedisClient（端口）+ 键前缀 / 超时 / 池参数访问器
├── redis.py           # RedisRedisClient（plugin_name=redis）：共享同步 / 异步连接池
└── null.py            # NullRedisClient（plugin_name=null）：取客户端即报 RedisUnavailableError
```

**端口契约（示意）**：

```python
class BaseRedisClient(BasePluggable, BaseAsyncResource, ABC):
    plugin_key: str = "redis_client"

    def sync_client(self) -> Redis: ...          # 同步客户端（缓存 / 健康检查等同步调用点）
    async def async_client(self) -> AsyncRedis: ...  # 异步客户端（会话 / 限流 / 锁 / 幂等 / 屏障）
    async def ping(self) -> None: ...            # 就绪探针复用
    @property
    def key_prefix(self) -> str: ...             # 统一前缀（缺省 bms）
```

- **连接参数**（统一在一处装配）：`decode_responses=True`、`socket_timeout` / `socket_connect_timeout` 取 `[redis].socket_timeout_ms`、`health_check_interval` 取 `[redis].health_check_interval_s`、`max_connections` 取 `[redis].pool_size`（0 = 客户端默认）。
- **共享语义**：进程内**同步池 / 异步池各一个**，十个域经端口取同一实例（`ResourceManager` 统一释放）。
- **装配**：`PLUGIN_WIRINGS` 增 `PluginWiring("redis_client", BaseRedisClient, "redis_client", "redis_client")`；`_NULL_MODULES` 增 `bms_core.redis.null`；`register_plugin("redis_client", "redis", RedisRedisClientFactory(settings))`。
- **各域改造**：工厂先解析 `redis_client` 插件实例，再以其 client 注入既有两个实现（现有 `client=` 构造注入即为改造通道；`url` 参数废弃，测试仍可直投 fakeredis）。
- **健康检查**：`RedisHealthCheck` 改为经统一端口 `ping()`（不再自建客户端）；`required` 语义不变（Redis 为必需就绪项）。

## 4. 配置加厚 <a id="config"></a>

| 键（`[redis]` / `BMS_REDIS__*`） | 缺省 | 说明 |
| --- | --- | --- |
| `url` | `redis://localhost:6379/0` | 连接串（保持） |
| `db` | 无（不覆盖） | 非空时覆盖 `url` 中的库号（部署切换库号不必改 url） |
| `pool_size` | `0`（客户端默认） | 单进程连接池上限（每服务独立进程） |
| `socket_timeout_ms` | `500` | 命令超时（架构要求的短超时快速失败） |
| `socket_connect_timeout_ms` | `500` | 建连超时 |
| `health_check_interval_s` | `30` | 连接健康探测间隔 |
| `key_prefix` | `bms` | 统一键前缀（现为常量，落为配置项） |
| `required` | `true` | 必需标志：为真时缺省 provider 解析为 `redis`（不再静默回落 `null`） |

三环境（dev / test / prod）与 `backend/.env.example` 显式声明；`deploy/compose/services.yml` 的 `BMS_REDIS__URL` 保持，另可在 `deploy/.env.example` 增服务侧 `BMS_REDIS__URL` 项（现仅网关侧）。

## 5. 不可用口径统一 <a id="semantics"></a>

| 域 | 新口径 | 变更 |
| --- | --- | --- |
| 会话 `session_store` | **fail-closed** | 存量已 fail-closed（`save` / `delete` / `blacklist` 抛错），保持 |
| 验证码 `captcha` | **fail-closed** | 存量已抛 `ServiceUnavailableError`，保持 |
| 幂等 `idempotency` | **fail-closed** | **变更**：取消 `begin` / `load` / `save` 的 degrade-open（Redis 不可用 ⇒ 报错，不再「放行 + 唯一约束兜底」） |
| 分布式锁 `distributed_lock` | **fail-closed** | **变更**：取消降级 `MemoryDistributedLock`（多副本下静默降进程内锁会**真的失去互斥**） |
| 限流 `rate_limiter` | **可降级 + 告警** | **保持**降级 `MemoryRateLimiter`（单机计数仍有保护），**新增「降级中」指标与告警**（见 §8 口径定稿） |
| IdP 流程状态 `idp_state_store` | **fail-closed** | 存量已 fail-closed，保持 |
| 缓存 `cache` / `dict_cache_region` / `config_cache_region` | **可降级** | 保持：命中失败直连库 / 回落来源，记 warning |
| 健康检查 `health_check_registry` | 探针（required） | 保持：Redis 不可达 ⇒ `/readyz` 503 |

- 新增错误码 **`10012 REDIS_UNAVAILABLE`**（HTTP 503，可重试），异常类 `RedisUnavailableError`；命名与 `10006 DATABASE_UNAVAILABLE` / `10007 SERVICE_UNAVAILABLE` 同族。
- 统一日志事件名 `redis_unavailable`（含 `op` / `domain`），并由统一端口上报指标（建议 `bms_dependency_up{dependency="redis"}` 复用既有口径）。

**需同步修订的口径文档**（本次实施一并回写，避免文档与代码背离）：

| 现行表述 | 位置 | 修订方向 |
| --- | --- | --- |
| 一致性屏障「存储不可用时放行（degrade-open）」 | 《后端开发规范》「强一致场景口径」、《架构设计 · 服务间通信与分布式一致性》、知识档案《一致性屏障》《选型对比（BMS）》 | 改为**不可用即报错**（`10012` / 503），不得放行半套状态 |
| 幂等「Redis 不可用降级放行 + 唯一约束兜底」 | 《架构设计 · 事件总线》「幂等」、知识档案 | 改为 fail-closed（唯一约束仍保留，但不再作为「放行」的依据） |
| 限流 / 分布式锁「Redis 故障降级 memory 后端」 | 《架构设计 · 性能与安全》「限流」「Redis 故障降级」 | 见 §8 开放项 1（建议：锁 fail-closed；限流保留降级但补「降级中」指标与告警） |

## 6. provider 默认翻转 <a id="provider"></a>

| 配置分区 | 现值（三环境） | 新值 |
| --- | --- | --- |
| `[idempotency]` | 未出现 → `null` | `redis` |
| `[consistency_barrier]` | `""` → `null` | `redis` |
| `[cache]` | `""` → `null`（dev 覆盖 `memory`） | `redis`（dev 同口径） |
| `[dict_cache_region]` | dev `memory` | `redis` |
| `[config_cache_region]` | dev `memory` | `redis` |

`[session_store]` / `[rate_limiter]` / `[distributed_lock]` / `[idp_state_store]` / `[captcha]` 基线已是 `redis`，不动。`config.toml` 各分区补中文注释说明「Redis 为基础能力，缺省启用」。

## 7. 环境前置 <a id="env"></a>

| 环境 | 现状 | 目标 |
| --- | --- | --- |
| 本地开发 | Redis 默认指**远端开发机** `redis://192.168.0.107:6379/5`，不自动拉起；`unlock` 子命令依赖 Redis | `本地全套.sh up` 增 Redis 就绪检查：本机无实例时**自动拉起容器**（复用 `deploy/compose/base.yml` 的 `redis:8`），`--redis` / `BMS_LOCAL_REDIS` 仍可覆盖；`status` 增 Redis 一行 |
| CI | **无 Redis service、无 `BMS_TEST_REDIS_URL`** | 后端 job 增 `services: redis:8`（alias `redis`）+ `BMS_TEST_REDIS_URL: redis://redis:6379/0`；`integration` 档的 Redis 用例由 skip 转执行 |
| 单测 | `conftest` 置空 provider 回落 null | 保持 hermetic（默认不真连）；**新增** fake 通道：`tests_support` 提供 `make_fake_redis_client()`（fakeredis 承载，注册为测试专用 provider），应用级用例按需启用 |
| 部署 | `services.yml` 已注入 `BMS_REDIS__URL` 且 `depends_on: redis` | 不变；`deploy/.env.example` 增服务侧 URL 项 |

## 8. 失败分支与开放项 <a id="edge"></a>

| 场景 | 处置 |
| --- | --- |
| 必需域 Redis 不可用 | 抛 `RedisUnavailableError`（`10012` / 503）；`/readyz` 同时 503 并摘流 |
| 连接池耗尽 / 慢响应 | 受 `socket_timeout_ms`（500）约束快速失败，不拖垮请求 |
| 缓存域 Redis 不可用 | 记 warning，回落来源直连库，业务不失败 |
| `[redis].required = true` 但 provider 配成 `null` | **启动期校验失败**（不静默降级），提示「Redis 为基础能力，provider 应配 redis」 |
| 键前缀 / 租户缺失 | 统一端口校验：键必须以 `{key_prefix}:` 开头；租户域键缺租户不落键（启动期与用例双重把关） |
| 单测误连真 Redis | 夹具强制注入 fakeredis / null，`BMS_TEST_REDIS_URL` 缺失即 skip（沿用现状） |

**口径定稿（2026-10-09 拍板）**：

1. **分布式锁 → fail-closed**：取消降级 `MemoryDistributedLock`（多副本下静默降进程内锁会**真的失去互斥**）。
2. **限流 → 保持降级 `MemoryRateLimiter` + 新增「降级中」指标与告警**：降级后单机计数仍有保护；若 fail-closed，Redis 抖动会把受保护入口**整体拒客**，将缓存故障放大为登录 / 接口全不可用。判据＝「**降级后语义仍正确才允许降级**」。
3. 需同步修订《架构设计 · 性能与安全》：分布式锁条款改 fail-closed；限流条款补「降级中」指标与告警（不再表述为无感降级）。

**其余开放项（按缺省采用，实施中如遇阻碍再报）**：本地 `up` 自动拉起 Redis（`required=false` 仅作应急旁路且需告警）；`redis_client` 作为基座能力对产品服务开放。

## 9. 实施分解（工序先后，数值归阶段计划） <a id="impl"></a>

1. 配置加厚（`RedisSettings` + 三环境 + `.env.example`）与启动校验。
2. 统一能力域 `bms_core/redis/`（端口 / redis / null）+ 装配接线 + 基类清单登记。
3. 十个能力域改造为注入共享 client（逐个替换 `from_url`），同步改各域单测为注入 fake。
4. 口径统一：错误码 `10012` + 异常类 + 幂等 / 屏障 / 锁（限流按开放项 1 结论）改造 + 指标与日志事件。
5. provider 默认翻转与 dev 覆盖调整。
6. 环境前置：本地脚本、CI service 与变量、`tests_support` fake 通道。
7. 文档口径回写（§5 表 + 规范 / 架构 / 知识档案 / 基类清单）。
8. 验证与记录（见 §10）。

## 10. 测试设计与验收映射 <a id="test"></a>

| 验收点（需求 03-5） | 用例 |
| --- | --- |
| 无能力域自建 Redis 客户端 | 静态检索断言（源码扫描 `from_url` 仅出现在 `bms_core/redis/redis.py`） |
| 共享连接池与配置生效 | 单测：解析 `[redis]` 各键；断言同步 / 异步客户端为同一实例 |
| 必需域 fail-closed | 注入不可用 fake client，断言会话 / 验证码 / 幂等 / 锁（限流按结论）抛 `RedisUnavailableError` 且 `code == 10012` / `http_status == 503` |
| 缓存域可降级 | 注入不可用 fake client，断言缓存三域回落来源且不抛错 |
| 缺省即 Redis | 断言缺省配置下幂等 / 屏障 / 缓存 provider 解析为 `redis`；`required=true` + `provider=null` ⇒ 启动校验失败 |
| 短超时与键前缀 | 断言客户端 `socket_timeout` 取配置值；键前缀校验（非法前缀报错） |
| 就绪探针 | 经统一端口 `ping()`；Redis 不可达 ⇒ `/readyz` 503（复用既有集成用例） |
| 环境前置 | 本地脚本 Redis 就绪检查；CI Redis service + `BMS_TEST_REDIS_URL` 下集成用例执行（非 skip） |
| 门禁 | `pytest` / `ruff` / `ruff format --check` / `pyright`（strict）/ 契约与模块校验 / `preflight --fast` 全绿 |

## 11. 登记落点与回写清单 <a id="register"></a>

| 内容 | 落点 |
| --- | --- |
| 强制口径 | 《[后端开发规范](../../../../../../规范/后端开发规范.md)》（「能力实现必须走基座」节补「Redis 一律经统一客户端能力域」；「强一致场景口径」取消屏障 degrade-open） |
| 架构口径 | 《[架构设计 · 后端基础类体系](../../../../../../设计/架构设计/04_架构设计_后端基础类体系.md)》《[架构设计 · 总体架构](../../../../../../设计/架构设计/03_架构设计_总体架构.md)》《[架构设计 · 性能与安全](../../../../../../设计/架构设计/31_架构设计_性能与安全.md)》《[架构设计 · 服务间通信与分布式一致性](../../../../../../设计/架构设计/37_架构设计_子系统_服务间通信与一致性.md)》《[架构设计 · 部署与运维](../../../../../../设计/架构设计/33_架构设计_部署与运维.md)》 |
| 知识档案 | 《[Redis 技术介绍](../../../../../../资料/知识档案/后端核心/Redis技术介绍.md)》《[分布式事务 · 一致性屏障](../../../../../../资料/知识档案/分布式事务/04_分布式事务_一致性屏障.md)》《[分布式事务 · 选型对比（BMS）](../../../../../../资料/知识档案/分布式事务/05_分布式事务_选型对比（BMS）.md)》 |
| 基类清单 | 《[后端基类清单](../../../../../../后端基类清单.md)》（新增 `BaseRedisClient` 与继承链计数） |
| 错误码 | `core/error_codes.py` 增 `10012 REDIS_UNAVAILABLE`；`core/exceptions.py` 增异常类 |
| 配置 | `backend/config.toml` / `config.dev.toml` / `config.test.toml` / `config.prod.toml` / `backend/.env.example` / `deploy/.env.example` |
| 环境 | `scripts/tools/dev/本地全套.sh`、`.gitlab-ci.yml` |
| 需求 / 任务 / 计划 | 需求 03-5、本任务、阶段计划（状态随实施回写） |

## 12. 参考文档 <a id="ref"></a>

- 需求 [03-5](../../../../需求/03_需求_后端基础能力.md#r03-5)；任务 [04](../03_后端基础能力_04_Redis基础能力统一.md)
- 《[后端开发规范](../../../../../../规范/后端开发规范.md)》「能力实现必须走基座」「字典取数与缓存必须走基座」节
- 知识档案《[Redis 技术介绍](../../../../../../资料/知识档案/后端核心/Redis技术介绍.md)》《[部署与运维 · Redis 部署使用说明](../../../../../../资料/开发服务器/linux/Redis部署使用说明.md)》
- 相关能力域落点：`libs/bms_core/{cache,dict,config,idempotency,consistency,lock,ratelimit,session,idp,captcha,health}/`、`core/assembly.py`、`core/config.py`

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》与《[AI开发规范](../../../../../../规范/AI开发规范.md)》编写

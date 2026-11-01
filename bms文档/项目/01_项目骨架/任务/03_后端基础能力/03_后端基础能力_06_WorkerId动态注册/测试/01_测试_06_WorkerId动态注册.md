# 01 测试记录 · WorkerId 动态注册（Redis 租约）

> 项目骨架 · 03 后端基础能力 · 子任务 06（需求 03-7）· 测试记录

[文档首页](../../../../../../文档首页.md) › [03 后端基础能力](../../03_后端基础能力.md) › 测试记录　|　[← 任务](../03_后端基础能力_06_WorkerId动态注册.md)　[实施记录 →](../实施/01_实施_06_WorkerId动态注册.md)

## 1. 测试信息 <a id="info"></a>

| 项 | 值 |
| --- | --- |
| 任务 | 06 WorkerId 动态注册（Redis 租约） |
| 对应需求 | 03-7 |
| 详细设计 | [01 详细设计 · WorkerId 动态注册](../设计/01_详细设计_06_WorkerId动态注册.md) |
| 实施记录 | [01 实施 · WorkerId 动态注册](../实施/01_实施_06_WorkerId动态注册.md) |
| 测试日期 | 2026-11-01 |
| 测试人 | minjian |
| 测试环境 | 本地 Windows / Python 3.14 / SQLite / fakeredis（真 Redis 用例未配置即 skip） |
| Kiwi 用例 | **2397 / 2398**（2026-11-01 登记，平台回读一致） |
| 结论 | 新增用例全绿；新增模块覆盖率 100%（行 + 分支）；真 Redis 双实例待真机复核 |

## 2. 用例登记 <a id="kiwi"></a>

| 用例号 | 标题 | 自动化落点 |
| --- | --- | --- |
| 2397 | 租约算法：探测 / 配置优先占号 / 释放 / TTL / 心跳 / 降级 / 生产拒启 | `libs/bms_core/tests/workerid/test_registry.py` |
| 2398 | 接入与部署：应用装配 / ops 入口覆盖 / compose 注入语义 / 真 Redis 双实例 | `libs/bms_core/tests/workerid/{test_integration,test_workerid_real_redis}.py`、`services/*/tests/**/test_*jobs_entry.py` |

## 3. 覆盖范围与结果 <a id="cases"></a>

### 3.1 租约算法（2397，26 用例）

- **配置值优先**：配 `[app].worker_id=11` → 占 11（`source=config`）、写 TTL、生成器机器段为 11；
- **占不到改分配**：11 已被他人持有 → 随机起点探测到 12（`source=registry`）+ 告警；
- **随机起点 + 跳过占用**：起点 5 被占 → 顺延 6；
- **释放与复用**：CAS 删除后同号可再占；令牌不匹配不误删他人租约；
- **TTL 回收**：键过期（删除模拟）后同号可被重新占用；
- **降级**：Redis 抛连接错误 / 共享客户端未登记 / 探测上限内无空闲号 → 回落 `[app].worker_id`（`source=fallback`）；
- **幂等**：重复 `acquire` 不换号、只占一个键；
- **旁路实现**：`enabled=false` / `provider=null` → 直接用配置值，释放只清标记；
- **生产拒启**：prod 且取号后仍为 0 → `ConfigError`；prod 已配置 / dev → 放行；
- **配置校验**：`[worker_id]` 缺省（启用 / redis / 60 / 20 / 256）；`heartbeat_seconds >= lease_ttl_seconds` → 启动失败；
- **键口径**：env + unit 隔离；unit 空回落 service、再空回落 `default`；`0` 不参与分配、探测上限常量一致；
- **心跳**：续租拉回 TTL；失租后连续失败达 TTL/3 → 重新占号并同步生成器；重新占号失败 / 探测用尽 → 保留原号；无租约时为空操作；循环体随停止事件退出；
- **释放抖动**：Redis 异常只告警不抛错；
- **上下文**：同步 / 异步上下文取号即生效、退出即释放；prod 无号在交出前拒启。

### 3.2 接入与部署（2398，9 用例）

- `worker_id_registry` 属基础能力且排在 `redis_client` 之后；
- 装配即取号（`app.state.worker_id_registry` + 生成器机器段生效），`resources.aclose()` 后租约释放；
- `enabled=false` / `provider=null` 装配走旁路实现，不访问 Redis；
- `ensure_shared_redis_client` 幂等复用；`[redis].provider` 非 redis 时登记 null 实现（fail-closed）；
- **ops 入口覆盖护栏**：调用 `asyncio.run` 的入门须在「已接入 / 排除」清单内，已接入项须确含包装调用；
- **compose 注入语义**：每容器仍注入且互不相同，注释含「显式偏好」口径；
- 作业 worker 入口（平台 / 文件）：租约包裹、单轮 / 长驻分支、声明构造、`python -m` 入口。

### 3.3 真 Redis 双实例（2398，1 用例，本地 skip）

两个独立子进程并发取号 → 号不同且均 > 0、`source=registry`；退出后命名空间内租约键清空。

结果：本地 `1 skipped`（未配置 `BMS_TEST_REDIS_URL`），**待开发服务器注入后复核**。

## 4. 覆盖率 <a id="coverage"></a>

| 模块 | 语句 | 分支 | 覆盖 |
| --- | --- | --- | --- |
| `bms_core/workerid/base.py` | 72 | 2 | 100% |
| `bms_core/workerid/redis.py` | 141 | 24 | 100% |
| `bms_core/workerid/lease.py` | 43 | 6 | 100% |
| `bms_core/workerid/null.py` | 11 | 2 | 100% |
| `bms_core/workerid/__init__.py` | 5 | 0 | 100% |
| `bms_core/redis/bootstrap.py` | 16 | 4 | 100% |

作业入口 `bms_platform.jobs` / `bms_file.jobs` 亦为 100%（行 + 分支，含 `__main__` 入口分支）。

## 5. 定向回归 <a id="regression"></a>

| 范围 | 结果 |
| --- | --- |
| `libs/bms_core/tests/workerid` | 35 passed / 1 skipped |
| `tests/core/test_config.py` + `test_assembly_factories.py` + `tests/redis/test_client.py` + `tests/testing/test_fixtures_worker.py` | 48 passed |
| `tests/ops`（8 文件，含拓扑迁移） | 57 passed / 1 失败（存量：`test_seed_menu::test_platform_seed_counts_drop_by_product_entries` 44≠43） |
| `tests/jobs`（34 用例） | 全过（2 秒） |
| 受影响清单尾段 79 文件（554 用例） | 全过（128 秒） |
| 全仓 `ruff check` / `ruff format --check` | 通过 |

## 6. 问题与处置 <a id="issues"></a>

| # | 现象 | 原因 | 处置 |
| --- | --- | --- | --- |
| 1 | `test_migrate_topology.py::test_full_flow_p1_to_p4_copies_and_verifies` 无限卡死（CPU 60~98%、journal 反复写、pytest 用例目录零新增）；`-n auto` 全量表现为两个 worker 持续刷管道不推进 | 03_05 把雪花 ID 列在 SQLite 改为 38 位补零 TEXT 后，库里混入未补零取值（原生 SQL 直插 int）→ 游标 `column > after` 恒真 → 每批返回同一批 | `db/topology_migration.py` 增 `_ensure_cursor_advanced()`（游标未推进即抛 `ConfigError`）；`ops/migrate_topology.py` 增 `_id_param()`（按方言归一 ID 绑定，同时消除 `OverflowError`）；种子数据补零写入、断言经 `sqlite_int()` 归一。修复后该文件 25 passed / 4.9s |
| 2 | `OverflowError: Python int too large to convert to SQLite INTEGER` | 原生 SQL 直绑真实租户雪花 ID（> 2^63） | 随上条 `_id_param()` 修复 |
| 3 | 拓扑读面查不到默认拓扑行 | 原生 SQL `WHERE tenant_id = :tenant_id` 不走 `SnowflakeId` 类型层，补零值匹配不上 | 测例数据按补零写入 + `_id_param()` 统一绑定 |
| 4 | `test_seed_menu::test_platform_seed_counts_drop_by_product_entries` 失败（44≠43） | 平台种子仍含产品条目（07B / 12_03 遗留） | 登记遗留（04_06 / 07B 归口），本任务不修 |

## 7. 遗留 <a id="gap"></a>

1. **真 Redis 双实例用例待真机复核**（开发服务器注入 `BMS_TEST_REDIS_URL` 后执行并回填）。
2. **全量预检无法跑绿**：`origin/main` 落后 15 个提交，变更集 396 文件里约 65 处 pyright 错误与上述种子用例失败属 03_05 / 07B 存量，归口 03_05 续修与 04_06。
3. **非 SQLite 方言**：`_id_param()` 的整数分支未真库实测（随 test 环境切换复核）。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

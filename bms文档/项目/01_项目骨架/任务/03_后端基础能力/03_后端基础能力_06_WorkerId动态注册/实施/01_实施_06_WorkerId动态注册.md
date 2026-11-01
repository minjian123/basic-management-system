# 01 实施记录 · WorkerId 动态注册（Redis 租约）

> 项目骨架 · 03 后端基础能力 · 子任务 06（需求 03-7）· 实施记录

[文档首页](../../../../../../文档首页.md) › [03 后端基础能力](../../03_后端基础能力.md) › 实施记录　|　[← 任务](../03_后端基础能力_06_WorkerId动态注册.md)　[详细设计 →](../设计/01_详细设计_06_WorkerId动态注册.md)　[测试记录 →](../测试/01_测试_06_WorkerId动态注册.md)

## 1. 实施信息 <a id="info"></a>

| 项 | 值 |
| --- | --- |
| 任务 | 06 WorkerId 动态注册（Redis 租约） |
| 对应需求 | 03-7 WorkerId 动态注册 |
| 详细设计 | [01 详细设计 · WorkerId 动态注册](../设计/01_详细设计_06_WorkerId动态注册.md) |
| 实施日期 | 2026-11-01 |
| 实施人 | minjian |
| 实施环境 | 本地（Windows / Python 3.14） |
| 结论 | 代码 / 配置 / 装配 / 测试完成；新增模块覆盖率 100%（行 + 分支）；本地全量预检受 03_05 未推送存量阻塞（见 §7） |

## 2. 概述 <a id="intro"></a>

按[详细设计](../设计/01_详细设计_06_WorkerId动态注册.md)落地：新增**插件化能力域** `bms_core/workerid/`（端口 `BaseWorkerIdRegistry` + `redis` / `null` 实现），以 Redis 租约（`SET NX EX` + Lua 内循环探测 + 心跳续租 + CAS 释放）为每个进程取唯一 WorkerId，取代「compose 按容器硬编码注入」；配置新增 `[worker_id]` 分区，`[app].worker_id` 降级为「显式偏好 + Redis 不可用兜底」。

## 3. 交付物清单 <a id="deliver"></a>

| # | 交付物 | 落点 |
| --- | --- | --- |
| 1 | 租约能力域（端口 / 键口径 / 40 位池 / 持有者令牌） | `bms_core/workerid/base.py`、`__init__.py` |
| 2 | Redis 实现（Lua 占号 + 心跳线程 + 令牌 CAS 释放 + 降级） | `bms_core/workerid/redis.py` |
| 3 | 旁路实现（`provider=null` / `enabled=false`） | `bms_core/workerid/null.py` |
| 4 | 上下文管理器（应用 / 作业 worker / ops 共用入口） | `bms_core/workerid/lease.py` |
| 5 | 配置分区 `[worker_id]`（开关 / 实现 / TTL / 心跳 / 探测上限 + 心跳< TTL 校验） | `core/config.py`、`backend/config.toml`、`backend/.env.example` |
| 6 | 装配接线（基础能力先行：`redis_client` → `worker_id_registry`） | `core/assembly.py`（`BASE_PLUGIN_KEYS` / `PluginWiring` / 两个工厂） |
| 7 | 应用生命周期取号 + 生产拒启判定 | `application.py`（`assemble_base_plugins` 后、建库引导前）、`core/config.py::validate_startup` |
| 8 | 共享客户端引导（非应用进程零依赖接 Redis） | `bms_core/redis/bootstrap.py`（`ensure_shared_redis_client` / `current_shared_redis_client`、`redis/base.py` 新增只读取用） |
| 9 | 作业 worker 入口包裹（平台 / 文件） | `bms_platform/jobs.py`、`bms_file/jobs.py` |
| 10 | ops 引导包装器 + 全入口覆盖（26 个脚本） | `ops/_worker.py`（`run_with_worker_id` / 清单）、`ops/*.py` |
| 11 | 测试（租约算法 / 接入 / 真 Redis 双实例 / 作业入口） | `tests/workerid/`（3 文件）、`services/platform/tests/jobs/test_jobs_entry.py`、`services/file/tests/test_jobs_entry.py` |
| 12 | 部署编排口径（注入语义改为「显式偏好」） | `deploy/compose/services.yml` |

## 4. 实施要点 <a id="impl"></a>

1. **能力域而非函数库**：遵循「能力实现必须走基座」，WorkerId 取号做成端口 + 实现 + 装配 + 配置选择；`worker_id_registry` 紧跟 `redis_client` 列入 `BASE_PLUGIN_KEYS`——必须早于任何雪花 ID 生成（建库引导 / 声明自举都会写库）。
2. **Redis 实现细节**：占号用单个 Lua 脚本（`SET NX EX` 内循环 256 次 + 取模回绕，一次往返）；键 `{前缀}:{env}:{unit}:worker_id:v2:{id}`（unit 空回落 service，再空回落 `default`，ops 与运行服务共用同一号池）；值为 `{service}|{hostname}|{pid}|{uuid}`，释放与心跳均以令牌 CAS。
3. **心跳用后台线程**（`threading.Thread` + `Event.wait(interval)`），不占用事件循环；连续失败达 `TTL/3` 重新占号并 `reconfigure`，占不到保留原号下轮重试。
4. **兜底与拒启**：配置值先按 `SET NX` 占号 → 占不到走注册分配并告警 → Redis 不可用回落配置值并告警；`validate_startup` 的「prod `worker_id==0` 拒启」改为「取号后仍为 0 即拒启」（`ensure_worker_id_ready`）。
5. **零依赖接入**：非 FastAPI 进程（作业 worker / ops）不启 lifespan，经 `ensure_shared_redis_client(settings)` 自行登记共享客户端，再进 `worker_id_lease(_sync)` 上下文。
6. **测试隔离**：`[worker_id].enabled` 缺省 `true`，公共隔离夹具 `bms_isolate_settings` 置 `false`——既有用例零扰动，需验注册时用专项夹具显式开启。

## 5. 偏差与处置 <a id="deviation"></a>

| # | 偏差 / 事项 | 处置 | 归口 |
| --- | --- | --- | --- |
| 1 | 设计 §5.5 原写「心跳失败仅重试」 | 实施按已确认结论（第 11 项）落实「失败达 TTL/3 重新占号」，设计已回写 | 本任务 |
| 2 | 存量阻断：`backend/tests_support/tenant_sql.py:96` 行宽 122（`beb47dc06` 引入，ruff E501，阻断开发环 / 预检） | 拆行（零语义变更），用户 2026-11-01 授权「顺手修复」 | 本任务 |
| 3 | 存量阻断：全仓 16 个文件未过 `ruff format --check`（03_05 / 01_03 遗留）与 `db/migration.py` 的 isort 双视图互斥 | 统一格式化；`db/migration.py` 的 `from alembic import command` 改为函数内局部导入（两种 ruff 视图均可通过，零语义变更） | 本任务 |
| 4 | 存量阻断：`deploy/boundaries/bare_collections_baseline.json` 为空而现存 15 处违规（01_03 引入） | 按护栏机制 `--update-baseline` 登记为存量（15 条），本次新增代码零违规 | 04_06（递减） |
| 5 | **范围外修复**：`tests/ops/test_migrate_topology.py::test_full_flow_p1_to_p4_copies_and_verifies` 无限卡死（CPU 60~98%、journal 反复写） | 见 §6，用户 2026-11-01 两次授权「直接修」 | 本任务（顺带） |

## 6. 顺带修复：拓扑迁移分页死循环 <a id="bonus"></a>

**现象**：`libs/bms_core/tests/ops/test_migrate_topology.py` 跑到第 2 个用例即无限期挂住——实测量化：单进程 CPU 63~98%、写 8~12 MB/s（SQLite `-journal` 反复写）、pytest 用例目录 6 秒零新增；`-n auto` 全量时表现为「两个 xdist worker 持续刷管道、整体不推进」，与 03_05 测试记录「全量约 93% 处长时间无进展」同源。

**根因**：`db/topology_migration.py` 的三处游标分页（搬数 `:737`、对账 `:861`、多出统计 `:905`）以 `column > after` 推进；03_05 把雪花 ID 列在 SQLite 改为 **38 位补零 TEXT** 后，若库里混入**未补零**取值（原生 SQL 直插 int），补零绑定值与该值比较恒真 → 每批返回同一批 → 死循环。

**修复**：

| 位置 | 改动 |
| --- | --- |
| `db/topology_migration.py` | 新增 `_ensure_cursor_advanced()`：游标未推进即抛 `ConfigError`（显式化数据不规范），三处循环接入；死循环变为明确报错 |
| `ops/migrate_topology.py` | 新增 `_id_param()`：原生 SQL 的雪花 ID 绑定值按平台库方言归一（SQLite → 38 位补零，其它方言 → 整数）；`_topology_rows` 的 `tenant_id` 绑定接入（同时消除 `> 2^63` 绑定 SQLite 的 `OverflowError`） |
| `tests/ops/test_migrate_topology.py` | 种子数据主键 / `tenant_id` 经 `sqlite_id()` 补零写入；断言读回经 `sqlite_int()` 归一 |

**结果**：该文件由「第 2 个用例无限卡死」变为 **25 passed / 4.9s**；`tests/ops` 相邻 8 文件 57 passed / 1 存量失败（见 §7）。

## 7. 验证与遗留 <a id="verify"></a>

**已验证**（本地，2026-11-01）：

| 项 | 命令 / 范围 | 结果 |
| --- | --- | --- |
| 租约算法 + 接入 | `pytest libs/bms_core/tests/workerid` | 35 passed / 1 skipped（真 Redis 用例未配置 URL 即 skip） |
| 新增模块覆盖率 | 同上 + `--cov=bms_core.workerid --cov=bms_core.redis.bootstrap --cov-branch` | **100% 行 + 分支**（288 语句 / 38 分支） |
| 作业 worker 入口 | `services/platform/tests/jobs/test_jobs_entry.py`、`services/file/tests/test_jobs_entry.py` | 15 passed；两模块覆盖率 100% |
| 配置 / 装配 / Redis / 夹具 | `tests/core/test_config.py`、`test_assembly_factories.py`、`tests/redis/test_client.py`、`tests/testing/test_fixtures_worker.py` | 48 passed |
| ops 相邻回归 | `tests/ops` 8 文件 | 57 passed / 1 存量失败 |
| 拓扑迁移修复 | `tests/ops/test_migrate_topology.py` | 25 passed / 4.9s（修复前无限卡死） |
| 静态 | `ruff check` / `ruff format --check`（全仓） | 通过 |
| 类型 | `pyright`（本次新增 / 改动文件） | 0 errors |

**遗留**：

1. **本地全量预检无法跑绿**：`origin/main` 落后 15 个提交（03_05 全部代码未推送），故 `engkit run-changed` / `推送.py` 的变更集含 396 个文件，其中约 65 处 pyright 错误与 `test_seed_menu::test_platform_seed_counts_drop_by_product_entries`（44≠43，产品条目未从平台种子移除）为 03_05 / 07B 存量，与本任务无关。归口：03_05 续修与 04_06 测试体系重写。
2. **真 Redis 双实例用例待真机跑**：`tests/workerid/test_workerid_real_redis.py`（`BMS_TEST_REDIS_URL` 未配置即 skip），需在开发服务器注入后复核并回填测试记录。
3. **达梦 / MySQL / PostgreSQL 方言**：`_id_param` 的非 SQLite 分支按整数绑定，未经真库实测（随 test 环境切换复核）。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

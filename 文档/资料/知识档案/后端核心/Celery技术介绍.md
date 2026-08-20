# Celery 技术介绍

> 分布式任务队列 · BMS 定时与周期性任务

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › Celery 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Celery** 是一个分布式任务队列系统，用于把「耗时、可延迟、需定时」的工作从请求主链路里剥离出去，
交给独立的工作进程（worker）异步执行。它聚焦**实时任务处理**，同时支持**任务调度**（定时任务）。

- **定位**：BMS 的定时任务与周期性任务引擎——孤儿分片清理、日志归档、分片表预创建、过期数据物理清理等。
- **版本**：5.x 系列（截至 2026 年最新 5.6.3），要求 Python 3.8+，本项目用 3.14+。
- **许可**：BSD-3-Clause，OSI 认证开源，商用无限制。
- **broker**：本项目用 **Redis**（Celery 官方支持的 broker），复用现有 Redis 实例。
- **作者/维护**：Ask Solem 等，社区活跃，Open Collective 资助。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| Task（任务） | 用 `@app.task` 装饰器定义的普通 Python 函数，是 Celery 调度的最小单位 |
| Broker（消息代理） | 任务消息的中转站：生产者（beat/接口）把任务投递到 broker，worker 从 broker 取任务，本项目用 Redis |
| Worker（工作进程） | 常驻进程，从 broker 拉取任务并执行；可多实例横向扩展，任务在 worker 间分配，无需额外锁 |
| Beat（定时调度器） | 定时进程：按 cron 表达式到点把任务投递到 broker；BMS 用自研数据库调度器驱动它 |
| Result Backend（结果后端） | 存储任务执行结果（成功/失败/返回值）的后端，本项目执行历史落 `sys_task_log` |
| 任务重试（Retry） | 任务失败后按策略自动重试（可设次数、间隔、退避），提高可靠性 |
| acks_late / ack 确认 | 「执行完才确认」模式：任务真正跑完才向 broker 确认，worker 崩溃时任务不丢、会被重新投递 |
| Queue（任务队列） | 任务路由通道：不同任务可路由到不同队列，由不同 worker 组消费，实现隔离 |
| 自研数据库调度器 | BMS 自研：任务定义入库 `sys_task`，beat 启动时加载、任务变更事件触发重载，页面可动态增删改与启停 |
| 任务序列化 | 任务参数与结果用序列化格式（默认 JSON）在 broker 传输，参数需可序列化 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

Celery 在 BMS 里承担**定时任务与周期性后台任务**，把「不需要即时响应、可以延后批量做」的工作从 API 主链路剥离。

- **任务分配**：任务在多个 worker 间分配执行，多实例无需额外锁，横向扩展即可提升吞吐。
- **broker 用 Redis**：复用现有 Redis 实例作 broker（Celery 官方支持），与事件总线（RocketMQ）解耦（见《[RocketMQ 技术介绍](RocketMQ技术介绍.md)》）。
- **定时任务**：celery beat + 自研数据库调度器——任务定义入库 `sys_task`（定义/cron/启停），beat 启动时加载、任务变更事件触发重载，页面可动态增删改与启停（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节「任务调度」）。
- **执行历史**：每次任务执行的状态、耗时、结果落 `sys_task_log`，页面可查。
- **可靠性**：失败自动重试、`acks_late` 确认，worker 崩溃不丢任务。
- **周期性任务清单**：孤儿分片清理（上传中断遗留的 `.part` 对象回收）、日志归档、分片表预创建（新月份 `yyyyMM` 表提前建）、过期软删除数据物理清理、180 天未登录账号锁定扫描等。

> 关键约束：Celery worker 是**同步进程**。任务内若要执行异步业务（如异步 SQLAlchemy、httpx），
> 必须用 `asyncio.run()` 新建事件循环或独立引擎，**禁止跨事件循环复用连接/会话**。
> 否则会出现「连接绑定的事件循环已关闭」类错误。

典型任务定义：

```python
from celery import Celery

app = Celery("bms", broker="redis://localhost:6379/0")

@app.task(bind=True, max_retries=3, acks_late=True)
def cleanup_orphan_parts(self):
    """清理 MinIO 中上传中断遗留的 .part 孤儿分片。"""
    try:
        # 同步 worker 内执行异步业务：新建事件循环
        import asyncio
        asyncio.run(_do_cleanup())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@app.task
def precreate_shard_table():
    """提前创建下月分片表（sys_operation_log / sys_open_log 的 yyyyMM 表）。"""
    ...
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Celery（选中）** | 最成熟、生态全、Redis broker 官方支持、beat 调度、重试/acks_late 完善 | 契合定时任务 + 周期性任务需求，Redis broker 复用现有设施，首选 |
| RQ（Redis Queue） | 轻量、Redis 原生；但无内置 beat 调度、重试/结果后端较弱、生态小 | 缺定时调度能力，需另配调度器，不如 Celery 一体 |
| APScheduler | 进程内调度、API 简单；但**非分布式**，多实例会重复调度，无 worker 池 | 适合单进程小任务，不满足 BMS 多实例分布式要求 |
| 自研任务队列 | 完全可控；但开发/维护成本高，重试、调度、监控都要自己造 | 成本高，Celery 已成熟，无自研必要 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **worker 是同步进程**：任务内执行异步业务必须 `asyncio.run()` 或独立引擎，禁止跨事件循环复用连接/会话，否则会报「事件循环已关闭」。
- **beat 单副本运行**：celery beat 必须只跑一个实例，否则同一任务会被重复调度；多副本部署时用锁或只在一节点启 beat。
- **任务要幂等**：`acks_late` + 重试可能导致同一任务执行多次，任务逻辑必须幂等（按业务键去重）。
- **参数需可序列化**：任务参数与返回值走 JSON 序列化，不能传数据库会话、连接等不可序列化对象，应传 ID 由 worker 内重建。
- **长任务与内存**：长运行 worker 可能内存泄漏，配置 `worker_max_tasks_per_child` 定期回收子进程。
- **任务超时**：用 `time_limit` / `soft_time_limit` 限制任务最长执行时间，防止卡死占满 worker。
- **结果后端**：本项目执行历史落 `sys_task_log`（业务表），而非 Celery 默认 result backend，注意别混淆两套「结果」。
- **与事件总线解耦**：Celery 只跑任务，事件总线走 RocketMQ，别把事件消费塞进 Celery 任务里。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Celery 官方文档 | https://docs.celeryq.dev/ | 权威文档，含教程、API、定时任务、部署 |
| Celery GitHub | https://github.com/celery/celery | 源码、issue 与 changelog |
| PyPI 包页 | https://pypi.org/project/celery/ | 版本、依赖与安装信息 |
| Celery 定时任务指南 | https://docs.celeryq.dev/en/stable/userguide/timing.html | beat / crontab 用法详解 |
| Redis 技术介绍 | 《[Redis 技术介绍](Redis技术介绍.md)》 | Celery broker 的底层设施 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节 | 功能模块：任务调度（sys_task/sys_task_log、内置周期任务） |
| 《[项目规划说明](../../../规划/项目规划说明.md#datasource)》10 节 | 多数据源策略：分片表预创建（Celery 定时任务） |
| 《[项目规划说明](../../../规划/项目规划说明.md#dbrule)》11.1 节 | 数据规范：过期软删除数据由 Celery 定时物理清理 |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | Celery broker（官方支持） |
| 《[RocketMQ 技术介绍](RocketMQ技术介绍.md)》 | 事件总线：与任务队列解耦 |
| 《[MinIO 技术介绍](MinIO技术介绍.md)》 | 孤儿分片清理的对象存储 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
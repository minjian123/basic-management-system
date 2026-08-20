# python-socketio 技术介绍

> Socket.IO 协议服务端 · BMS 实时推送

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › python-socketio 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**python-socketio** 是 Socket.IO 协议的 Python 实现，提供**服务端**与**客户端**。
Socket.IO 是在 WebSocket 之上封装的实时通信协议，在原生 WebSocket 的基础上补齐了
**自动重连、断线降级（长轮询）、命名事件、房间广播、心跳保活**等能力，
让「服务端主动推消息给浏览器」这件事变得可靠且简单。

- **定位**：BMS 的实时推送通道——待办/通知实时到达、待办角标实时更新、会话失效即时广播。
- **版本**：5.x 系列（截至 2026 年最新 5.16.2），要求 Python 3.8+，本项目用 3.14+。
- **许可**：MIT，OSI 认证开源。
- **集群**：多实例部署用 Redis 适配器（`socketio.RedisManager` / `AsyncRedisManager`）跨实例广播。
- **作者**：Miguel Grinberg（Flask-SocketIO 作者）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| Socket.IO 协议 | 基于 WebSocket 的实时通信协议，带自动重连与降级机制；WebSocket 不可用时自动退回 HTTP 长轮询，保证连通 |
| 事件（Event） | 命名事件：客户端与服务端互相 `emit`（发送）/ 注册回调（接收），比裸 WebSocket 的「字节流」语义更清晰 |
| 命名空间（Namespace） | 逻辑隔离通道：不同业务用不同 namespace，互不干扰（默认 `/`） |
| 房间（Room） | 消息分组：把连接加入某个 room，向该 room 广播即只发给组内成员，BMS 用它按用户/租户定向推送 |
| 心跳（Ping/Pong） | 定期心跳探测连接存活，及时发现断线并触发重连，避免「假连接」 |
| 自动重连 | 断线后客户端自动按退避策略重连，重连成功后可恢复状态，无需业务层手写重连逻辑 |
| 降级（Fallback） | WebSocket 被代理/防火墙拦截时，自动降级到 HTTP 长轮询，保证消息仍能送达 |
| `RedisManager` | Redis 消息队列适配器：多个服务端进程通过 Redis pub/sub 协调，实现跨实例广播（同步 Server 用） |
| `AsyncRedisManager` | 异步版 Redis 适配器：配合 `AsyncServer`（asyncio）使用，BMS FastAPI 异步栈用这个 |
| 握手鉴权 | 连接建立时的 `connect` 事件里校验 token，拒绝未授权连接，BMS 在此校验 access token |
| 连接/断开事件 | `connect` / `disconnect` 生命周期回调，用于登记在线状态、加入/移出房间 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

python-socketio 在 BMS 里承担**服务端实时推送**，让「服务端有变化」能即时到达浏览器，
而不需要前端轮询。前端对应使用 `socket.io-client` 库（见《[知识档案总览](../技术栈知识档案总览.md#frontend)》前端索引）。

- **待办/通知实时到达**：审批待办产生、通知发布时，实时推送给对应用户，待办角标即时更新（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节「通知中心」）。
- **会话失效广播**：管理员强制踢出某会话时，经 Socket.IO 广播「会话失效」，关闭该会话全部实时连接，即时生效（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节「多端会话」）。
- **集群跨实例广播**：BMS 多实例部署，用户连接可能落在任意实例；用 Redis 适配器（`socketio.AsyncRedisManager`）让「实例 A 产生的事件」能广播到「连在实例 B 上的用户」。
- **握手鉴权**：连接建立时校验 access token，未登录/令牌失效的连接直接拒绝，保证推送只发给合法用户。
- **连接数监控**：Socket.IO 连接数纳入系统监控（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节「系统监控」）。

典型服务端代码（FastAPI 异步栈）：

```python
import socketio

# 异步 Server + 异步 Redis 适配器，跨实例广播
sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=socketio.AsyncRedisManager("redis://localhost:6379/0"),
)

@sio.event
async def connect(sid, environ, auth):
    # 握手鉴权：校验 access token，失败返回 False 拒绝连接
    token = (auth or {}).get("token")
    user = await verify_access_token(token)
    if user is None:
        return False
    await sio.enter_room(sid, f"user:{user.id}")

async def push_todo(user_id: int, payload: dict):
    """向指定用户推送待办更新。"""
    await sio.emit("todo.updated", payload, room=f"user:{user_id}")
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **python-socketio（选中）** | Socket.IO 标准、自动重连、降级、房间广播、Redis 适配器成熟 | 功能全、可靠性高、集群方案现成，契合 BMS 实时推送，首选 |
| 原生 WebSocket（websockets 库） | 轻量、无额外协议；但**无自动重连/降级/房间**，这些都要自己造 | 可靠性与工程化不足，重复造轮子成本高 |
| SSE（Server-Sent Events） | 实现简单、走 HTTP；但**单向**（仅服务端→客户端）、无房间、无降级重连语义 | 满足不了双向与房间广播需求 |
| HTTP 轮询 | 实现最简单、穿透性好；但**延迟高、空请求多**，实时性差 | 体验差、开销大，仅作兜底 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **异步栈选对管理器**：FastAPI（asyncio）用 `AsyncServer` + `AsyncRedisManager`；别在异步环境用同步的 `RedisManager`，会阻塞事件循环。
- **Redis 适配器依赖 redis 库**：用 Redis 适配器需安装 `redis` 包，否则初始化报「Redis package is not installed」。
- **握手鉴权别漏**：在 `connect` 事件里校验 token 并返回 `False` 拒绝，否则任何人未登录也能连上并收推送。
- **房间按用户/租户建**：用 `user:{id}`、`tenant:{id}` 等 room 定向推送，避免全量广播造成信息越权（把 A 租户的待办推给 B 租户）。
- **跨实例 channel 要一致**：所有实例的 Redis 适配器 `channel` 参数必须相同，否则跨实例广播收不到。
- **心跳与超时配置**：按网络环境调 `ping_interval` / `ping_timeout`，太短会误判断线、太长发现断线慢。
- **消息体用 JSON**：推送数据保持可 JSON 序列化，别传数据库对象/会话。
- **重连后状态恢复**：客户端重连成功要重新拉取最新待办/通知，避免「断线期间漏掉的推送」造成状态不一致。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| python-socketio 官方文档 | https://python-socketio.readthedocs.io/ | 权威文档，含 Server/Client/Redis 适配器用法 |
| python-socketio GitHub | https://github.com/miguelgrinberg/python-socketio | 源码、issue 与 changelog |
| PyPI 包页 | https://pypi.org/project/python-socketio/ | 版本、依赖与安装信息 |
| Socket.IO 协议文档 | https://socket.io/docs/ | Socket.IO 协议与前端客户端文档 |
| Redis 技术介绍 | 《[Redis 技术介绍](Redis技术介绍.md)》 | 跨实例广播的 pub/sub 底座 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节 | 功能模块：通知中心（待办角标实时推送）、系统监控（连接数） |
| 《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节 | 认证与安全：多端会话、会话失效广播 |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 跨实例广播的 pub/sub 底座 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 异步栈背景，AsyncServer 挂载方式 |
| 《[JWT 与 PBKDF2 技术介绍](JWT与PBKDF2技术介绍.md)》 | 握手阶段校验的 access token |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
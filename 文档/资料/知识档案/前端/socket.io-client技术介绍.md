# socket.io-client 技术介绍

> Socket.IO 协议浏览器客户端 · BMS 待办/通知实时到达

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › socket.io-client 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**socket.io-client**（npm 包名 `socket.io-client`）
是 **Socket.IO** 协议的官方浏览器/Node.js 客户端。
Socket.IO 是构建在 WebSocket 之上的实时通信协议，
在裸 WebSocket 的「字节流」之上提供**命名事件、
自动重连、传输降级（WebSocket → HTTP 轮询）、房间广播**等能力，
断线、代理拦截、老浏览器这些脏活都由客户端兜底。

- **定位**：BMS 前端实时推送客户端——待办/通知实时到达、待办角标实时刷新、会话失效即时生效（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节）。
- **版本**：4.8.3（截至 2026 年，4.x 系列；须与后端 python-socketio 4.x 匹配）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，运行于浏览器。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Engine.IO | Socket.IO 的底层传输层：负责连接建立与数据分帧，支持 WebSocket 与 HTTP 轮询两种传输 |
| 传输降级（fallback） | WebSocket 不可用（企业代理拦截、老浏览器）时自动退回 HTTP 轮询，保证「总能连上」 |
| 自动重连 | 断线后按指数退避自动重连，业务层无需手写重连逻辑；重连成功触发 `connect` 事件 |
| 命名事件 | `emit`/`on` 按事件名通信，比裸 WebSocket 的字节流语义清晰，前后端约定事件名即可 |
| Ack（确认回调） | 发送方传回调函数，接收方处理完调用回调，实现请求-应答语义 |
| 房间（Room） | 服务端把连接加入指定房间，向房间广播即只发给相关用户；BMS 按用户/租户定向推送 |
| 握手鉴权 | 连接时经 `auth` 选项携带 token，后端在握手阶段校验会话（BMS 校验 access token） |
| 连接状态事件 | `connect`/`disconnect`/`connect_error`，用于 UI 状态提示与重连后状态恢复 |
| Sticky Session | 连接升级后必须固定在同一后端实例：nginx 用 ip_hash / Cookie 亲和（见《[项目规划说明](../../../规划/项目规划说明.md#deploy-cluster)》19.2 节） |
| Redis 适配器 | 后端多实例经 Redis 适配器跨实例广播，客户端无感知（见《[python-socketio 技术介绍](../后端核心/python-socketio技术介绍.md)》） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **待办/通知实时到达**：审批待办提醒、通知中心消息实时推送，替代轮询（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节通知中心）。
- **待办角标实时刷新**：顶栏/侧边栏待办角标作为全局元素实时展示，新待办到达即更新（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节首页工作台）。
- **会话失效即时生效**：管理端强制踢出会话时，经 Socket.IO 广播「会话失效」事件，客户端立即关闭实时连接并跳转登录（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节）。
- **与后端配合**：后端用 python-socketio（Redis 适配器跨实例广播），前端用 socket.io-client，协议两端对齐（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节）。
- **重连与降级**：断线自动重连、WebSocket 被拦自动降级轮询；重连成功后重新拉取最新待办/通知，避免断线期间漏推（见《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节）。
- **验收口径**：MVP 验收要求「待办提醒经 Socket.IO 实时触达」（见《[项目规划说明](../../../规划/项目规划说明.md#plan)》20 节）。

最小示例（连接 + 事件订阅 + 鉴权）：

```js
import { io } from 'socket.io-client'

const socket = io('https://bms.example.com', {
  auth: { token: localStorage.getItem('access_token') },
  transports: ['websocket', 'polling'],
})

socket.on('connect', () => {
  // 已连接（含重连成功）：重新拉取最新待办/通知，补齐断线期间漏推
})

socket.on('todo:created', (payload) => {
  // 新待办到达：更新角标与通知列表
})

socket.on('session:invalidated', () => {
  // 会话被踢出：清本地状态，跳转登录页
})

socket.on('disconnect', () => {
  // 断线提示；自动重连由客户端处理，无需手写
})
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **socket.io-client（选中）** | 自动重连 + 传输降级 + 房间 + 命名事件，与后端 python-socketio 天然配套，MIT | 与 BMS「实时推送 + 多实例广播 + 免登场景」诉求完全匹配 |
| 原生 WebSocket | 零依赖、协议简单；但无自动重连、无降级、无房间，断线恢复与鉴权全要自己写 | 基础设施重复造，不选 |
| SSE（Server-Sent Events） | 实现简单、走 HTTP；但单向（仅服务端→客户端）、无房间语义，双向交互难 | 满足不了定向房间与双向需求，不选 |
| MQTT over WebSocket | IoT 场景强；但 Web 应用场景偏重，与后端 Python 栈配套弱 | 场景不符，不选 |
| HTTP 轮询 | 最简单、无协议问题；但延迟高、服务端负载大、体验差 | 仅作兜底（Socket.IO 降级时自动使用），不作主方案 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **版本匹配**：客户端 4.x 必须对服务端 4.x（python-socketio），跨大版本不兼容。
- **token 位置**：经 `auth` 选项传，别拼在 URL query 里（会进访问日志泄露）。
- **重连后恢复**：`connect` 事件里重新拉取最新待办/通知，避免「断线期间漏掉的推送」造成状态不一致。
- **nginx 配置**：`/socket.io` 路径要放行 Upgrade/Connection 头；负载均衡用 ip_hash / Cookie 亲和（sticky session），连接升级后必须固定同一后端实例。
- **连接复用**：全局共享一条连接（模块单例或 Pinia store 管理），别每个页面各建一条。
- **降级别关**：企业网络可能拦 WebSocket，客户端自动降级轮询是兜底，不要强制只走 websocket。
- **移动端内嵌浏览器**：企微/钉钉 WebView 里测一遍连通性与重连表现。
- **多实例广播**：后端经 Redis 适配器跨实例广播，客户端无感知，但部署时 Redis 必须可用（见《[Redis 技术介绍](../后端核心/Redis技术介绍.md)》）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Socket.IO 官方文档 | https://socket.io/docs/ | 协议、客户端与服务端完整文档 |
| Socket.IO 客户端特性 | https://socket.io/docs/v4/client-features/ | 自动重连、降级、ack 等客户端能力说明 |
| Socket.IO GitHub | https://github.com/socketio/socket.io | 源码（含 socket.io-client 包）、Changelog 与 issue |
| socket.io-client npm | https://www.npmjs.com/package/socket.io-client | 安装与版本历史 |
| MDN：WebSocket API | https://developer.mozilla.org/zh-CN/docs/Web/API/WebSocket | 理解 Socket.IO 底层的裸 WebSocket 机制 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（socket.io-client 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：待办/通知实时到达 |
| 《[项目规划说明](../../../规划/项目规划说明.md#deploy-cluster)》19.2 节 | nginx WebSocket 放行与 sticky session 要求 |
| 《[python-socketio 技术介绍](../后端核心/python-socketio技术介绍.md)》 | 服务端协议实现与 Redis 适配器 |
| 《[Redis 技术介绍](../后端核心/Redis技术介绍.md)》 | 跨实例广播的 Redis 底座 |
| 《[Pinia 技术介绍](Pinia技术介绍.md)》 | 全局连接状态与待办角标数据管理 |
| 《[Vant 技术介绍](Vant技术介绍.md)》 | 移动端通知/待办界面（frontend-mobile） |
| 《[命名规范](../../../规范/命名规范.md)》 | 事件名（todo:created 等）命名 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
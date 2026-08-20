# Axios 技术介绍

> Promise 风格的 HTTP 客户端 · BMS 前端统一请求层

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Axios 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Axios** 是一个基于 Promise 的 HTTP 客户端，浏览器与 Node.js 环境都能用，
由 Matt Zabriskie 于 2014 年发布，主打**拦截器**、**自动 JSON 转换**与
**请求取消**。截至 2026 年，Axios（1.19.0）仍是 Vue/React 生态中使用最广的
HTTP 库之一，周下载量过亿。

- **定位**：BMS 前端（PC 管理端 frontend 与移动端 frontend-mobile）的统一 HTTP 客户端，所有接口请求都经它发出。
- **版本**：1.x 系列（1.19.0，截至 2026 年，持续迭代）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，自带类型定义。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Promise API | 所有请求返回 Promise，可用 `async/await` 串写，无需回调地狱 |
| 请求拦截器 | `interceptors.request`：请求发出前的钩子，BMS 用它统一注入 access token |
| 响应拦截器 | `interceptors.response`：响应返回后的钩子，BMS 用它统一解包、处理 401 刷新与错误提示 |
| 自动 JSON 转换 | 请求体对象自动序列化为 JSON、响应 JSON 自动解析为对象，省去手动 `JSON.stringify/parse` |
| 请求取消 | 基于 `AbortController`，组件卸载或重复请求时可取消在途请求，防竞态 |
| 超时控制 | `timeout` 配置毫秒数，超时自动 reject，避免请求长时间挂起 |
| baseURL | 统一前缀（如 `/api/v1`），各接口只写相对路径，便于环境与网关切换 |
| XSRF 防护 | 自动从 cookie 读取 `XSRF-TOKEN` 写入请求头，配合后端双重提交校验 |
| 错误对象 | 失败时抛 `AxiosError`，含 `status`、`data`（后端统一响应体），便于按错误码分支处理 |
| 实例隔离 | `axios.create()` 创建独立实例，各自持有 baseURL、拦截器，BMS 按端（PC/移动）分别封装 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **统一请求封装**：请求拦截器注入 access token、处理 401 刷新；响应拦截器统一错误提示（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **与后端统一响应格式配合**：后端返回固定结构（code/message/data + 5 位错误码），响应拦截器按 code 分支——成功取 data、失败弹 ElMessage 并按错误码跳转（见《[API 接口规范](../../../规范/API接口规范.md)》）。
- **双端复用**：frontend 与 frontend-mobile 各自封装一份 Axios 实例，逻辑一致、配置独立（见《[npm 技术介绍](npm技术介绍.md)》双工程独立约定）。
- **认证链路**：access token 存内存、refresh token 走 httpOnly cookie；401 时静默刷新并重放原请求，用户无感（见《[JWT 与 PBKDF2 技术介绍](../后端核心/JWT与PBKDF2技术介绍.md)》）。
- **上传/下载**：文件分片上传、预签名 URL 下载均经 Axios 发出，统一携带 token 与超时。

最小示例（统一封装骨架）：

```js
import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api/v1', timeout: 15000 })

// 请求拦截器：注入 access token
http.interceptors.request.use((config) => {
  const token = useAuthStore().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：统一解包 + 错误提示
http.interceptors.response.use(
  (res) => res.data,
  async (err) => {
    if (err.response?.status === 401) await refreshAndRetry(err)
    ElMessage.error(err.response?.data?.message ?? '网络异常')
    return Promise.reject(err)
  },
)
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Axios（选中）** | 拦截器成熟、浏览器/Node 通用、生态与资料最全、TS 类型好 | 与 BMS 统一封装、双端复用诉求完全匹配 |
| fetch（浏览器原生） | 零依赖、标准原生；但无拦截器、无自动 JSON、取消与超时需自行封装 | 统一封装成本高，团队习惯 Axios 写法 |
| ky | API 贴近 fetch、体积小；但生态与中文资料少于 Axios | 可选但非生态最优，暂不引入 |
| got / node-fetch | Node 侧能力强；但面向服务端，浏览器场景不占优 | 与前端双端统一目标不符 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **401 并发刷新**：多个请求同时 401 时只能刷新一次 refresh token，其余请求排队等待刷新结果后重放，否则会互相踢下线。
- **token 不落日志**：拦截器里别把 Authorization 头打进 console 或上报，避免泄露。
- **超时与重试要区分**：幂等 GET 可自动重试，写操作（POST/PUT）禁止盲目重试，防重复提交。
- **请求取消防竞态**：列表搜索、页面切换时用 AbortController 取消在途请求，避免旧响应覆盖新数据。
- **表单与 JSON 别混**：文件上传用 `multipart/form-data`（别手动设 Content-Type，交给浏览器带 boundary）。
- **拦截器顺序**：请求拦截器按注册逆序执行、响应拦截器按正序执行，多个拦截器时注意先后。
- **升级注意破坏性变更**：1.x 内个别默认行为调整（如跨域 XSRF 头），升级走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 全量回归。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Axios 官方文档 | https://axios-http.com | 权威文档，含完整 API 与示例 |
| Axios GitHub 仓库 | https://github.com/axios/axios | 源码、Changelog 与 issue 讨论 |
| MDN：fetch API | https://developer.mozilla.org/zh-CN/docs/Web/API/Fetch_API | 对照理解原生 fetch 与 Axios 差异 |
| AbortController | https://developer.mozilla.org/zh-CN/docs/Web/API/AbortController | 请求取消底层机制 |
| 阮一峰：网络请求 | https://www.ruanyifeng.com/blog/ | HTTP 与请求流程通俗讲解 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（Axios 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：统一封装请求/响应拦截器 |
| 《[API 接口规范](../../../规范/API接口规范.md)》 | 统一响应结构、5 位错误码、幂等与限流约定 |
| 《[JWT 与 PBKDF2 技术介绍](../后端核心/JWT与PBKDF2技术介绍.md)》 | access/refresh token 机制，401 刷新链路 |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | 响应拦截器统一错误提示（ElMessage） |
| 《[npm 技术介绍](npm技术介绍.md)》 | 双工程依赖独立、CI 锁定安装 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
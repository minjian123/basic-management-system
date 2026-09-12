# frontend 工程初始化测试记录

> 项目骨架 · 01 工程骨架 · 子任务 04 · 测试记录 01

[文档首页](../../../../../../文档首页.md) › [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) › 01 测试记录　|　[实施记录 →](../实施/04_实施_01_frontend工程初始化.md)　[详细设计 →](../设计/04_详细设计_01_frontend工程初始化.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04 frontend 工程初始化](../01_工程骨架_04_frontend工程初始化.md) |
| 对应需求 | [01-4](../../../../需求/01_需求_工程骨架.md#r01-4) |
| 详细设计 | [04_详细设计_01_frontend工程初始化](../设计/04_详细设计_01_frontend工程初始化.md) |
| 实施记录 | [01 实施记录](../实施/04_实施_01_frontend工程初始化.md) |
| 测试日期 | 2026-09-10 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu）；Node 22.23.2（nvm）、npm 10.9.8；backend 本地 8000；Vitest 5（jsdom） |
| Kiwi 用例 | 本任务新增 Case 19（frontend 默认页与代理链路冒烟）；补充 Case 25/26（Axios 基线单元） |
| 结论 | 2/2 用例通过；lint/build/vue-tsc 通过；覆盖率 100%（已导入文件）；代理链路实测通过 |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：默认页标题与 backend 应用信息渲染（成功/降级两态）、工程门禁（lint/vue-tsc/build）、开发代理链路（`/info` 重写、`/api`、`/healthz`）。不含：真实浏览器 E2E 与视觉断言（随 05-1 重验证层）、业务接口与权限（阶段三）、OpenAPI 生成（随 05 域）。

| Kiwi ID | 用例 | 类型 | 自动化文件 | 结果 |
| --- | --- | --- | --- | --- |
| 19 | frontend 默认页与代理链路冒烟（标题 + 应用名/版本；后端未连通降级） | 单元·冒烟 | `tests/home.spec.ts`（2 条） | 通过 |
| 25 | frontend Axios 基线单元（request 解包/code≠0 拒绝/fetchAppInfo/拦截器 401 与普通错误） | 单元 | `frontend/tests/http.spec.ts`（6 条） | 通过 |
| 26 | frontend-mobile Axios 基线单元（同款） | 单元 | `frontend-mobile/tests/http.spec.ts`（6 条） | 通过 |
| — | 工程门禁：ESLint / vue-tsc / 构建 | 静态·构建 | `npm run lint` / `build` | 通过 |
| — | 开发代理链路（/info、/api、/healthz） | 联调 | `curl`（起 backend + dev） | 通过 |

## 3. 执行记录与结果 <a id="run"></a>

```bash
cd frontend
npm ci
npm run lint     # 通过（--max-warnings 0）
npm run test     # 2 passed
npm run build    # vue-tsc -b && vite build 通过
```

联调实测（backend 8000 + dev 5173）：

| 请求 | 实测 |
| --- | --- |
| `GET /` | `<title>BMS 基础管理系统</title>` |
| `GET /info` | `{"code":0,…,"data":{"name":"BMS 基础管理系统","version":"0.1.0"}}`（代理重写 backend 根） |
| `GET /api/v1/demos` | `{"code":0,…,"data":[]}`（/api 代理） |
| `GET /healthz` | `{"status":"ok"}` |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 首轮 ESLint 启动失败（缺 vue-eslint-parser） | legacy-peer-deps 不装 peer | 显式安装依赖后通过 | [实施记录 §4](../实施/04_实施_01_frontend工程初始化.md#issues) |
| 2 | TS6 `baseUrl` 弃用导致构建失败 | TS 6 迁移口径 | 移除 baseUrl 保留 paths | 同上 |

## 5. 覆盖率 <a id="coverage"></a>

| 范围 | 语句 | 分支 | 函数 | 行 |
| --- | --- | --- | --- | --- |
| 已导入文件（i18n、views 等） | 100% | 100% | 100% | 100% |

口径：`npm run test:cov`（v8）；骨架期仅覆盖被导入文件；前端覆盖率门禁随 05-1 接入（阈值与采集范围届时定案，含 `src/**` 全量采集）。

## 6. 偏差与遗留 <a id="deviations"></a>

- 真实浏览器链路与 375×667 之外的视觉断言随 05-1 Playwright E2E。
- 覆盖率当前口径为「已导入文件」，全量 `src/**` 采集与阈值已补入 05-1 门禁清单。
- Element Plus 构建告警已消除（按需引入，主包 147.34 kB / gzip 53.67 kB，2026-09-10 优化）。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》「测试文档（任务测试记录）」节测试文档结构组织

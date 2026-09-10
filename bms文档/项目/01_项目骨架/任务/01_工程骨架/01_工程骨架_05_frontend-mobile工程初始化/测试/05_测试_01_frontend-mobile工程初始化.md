# frontend-mobile 工程初始化测试记录

> 项目骨架 · 01 工程骨架 · 子任务 05 · 测试记录 01

[文档首页](../../../../../../文档首页.md) › [05 frontend-mobile 工程初始化](../01_工程骨架_05_frontend-mobile工程初始化.md) › 01 测试记录　|　[实施记录 →](../实施/05_实施_01_frontend-mobile工程初始化.md)　[详细设计 →](../设计/05_详细设计_01_frontend-mobile工程初始化.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [05 frontend-mobile 工程初始化](../01_工程骨架_05_frontend-mobile工程初始化.md) |
| 对应需求 | [01-5](../../../../需求/01_需求_工程骨架.md#r01-5) |
| 详细设计 | [05_详细设计_01_frontend-mobile工程初始化](../设计/05_详细设计_01_frontend-mobile工程初始化.md) |
| 实施记录 | [01 实施记录](../实施/05_实施_01_frontend-mobile工程初始化.md) |
| 测试日期 | 2026-09-10 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu）；Node 22.23.2、npm 10.9.8；backend 本地 8000；Vitest 5（jsdom） |
| Kiwi 用例 | 本任务新增 Case 20（frontend-mobile 默认页与连通冒烟） |
| 结论 | 2/2 用例通过；lint/build/vue-tsc 通过；覆盖率 100%（已导入文件）；代理连通实测通过 |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：默认页标题与 backend 连通状态（成功/降级两态）、工程门禁（lint/vue-tsc/build）、开发代理连通（`/info` 重写）。不含：375×667 视口与安全区像素级断言（随 05-1 E2E）、移动端业务交互（后续阶段）、免登（阶段二）。

| Kiwi ID | 用例 | 类型 | 自动化文件 | 结果 |
| --- | --- | --- | --- | --- |
| 20 | frontend-mobile 默认页与连通冒烟（标题 + 连通成功/降级） | 单元·冒烟 | `tests/home.spec.ts`（2 条） | 通过 |
| — | 工程门禁：ESLint / vue-tsc / 构建 | 静态·构建 | `npm run lint` / `build` | 通过 |
| — | 开发代理连通（/info） | 联调 | `curl`（起 backend + dev） | 通过 |

## 3. 执行记录与结果 <a id="run"></a>

```bash
cd frontend-mobile
npm ci
npm run lint     # 通过（--max-warnings 0）
npm run test     # 2 passed
npm run build    # vue-tsc -b && vite build 通过
```

联调实测（backend 8000 + dev 5174）：

| 请求 | 实测 |
| --- | --- |
| `GET /` | `<title>BMS 基础管理系统</title>` |
| `GET /info` | `{"code":0,…,"data":{"name":"BMS 基础管理系统","version":"0.1.0"}}`（代理重写 backend 根） |

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 无失败项；公共依赖问题（peer/parser/baseUrl）同 04 | 同 04 | 同 04 处置 | [04 实施记录 §4](../../01_工程骨架_04_frontend工程初始化/实施/04_实施_01_frontend工程初始化.md#issues) |

## 5. 覆盖率 <a id="coverage"></a>

| 范围 | 语句 | 分支 | 函数 | 行 |
| --- | --- | --- | --- | --- |
| 已导入文件（i18n、views 等） | 100% | 100% | 100% | 100% |

口径：`npm run test:cov`（v8）；前端覆盖率门禁随 05-1 接入（全量 `src/**` 采集与阈值届时定案）。

## 6. 偏差与遗留 <a id="deviations"></a>

- 375×667 视口与安全区断言随 05-1 Playwright E2E（当前默认页简单结构，视口基线配置已就位）。
- 覆盖率口径同 04（已导入文件），全量采集随门禁任务。
- Vant 按需引入与 vw 适配方案已配置，业务组件样式随后续阶段验证。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》第 6 节测试文档结构组织

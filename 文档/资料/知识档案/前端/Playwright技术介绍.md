# Playwright 技术介绍

> 跨浏览器 E2E 测试框架 · BMS 端到端质量门禁

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Playwright 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Playwright** 是微软出品的跨浏览器
端到端（E2E）测试框架，一套 API 驱动
**Chromium、Firefox、WebKit** 三大内核，
内置**自动等待**（元素可见/稳定/可交互才执行动作）、
**代码录制器**（边点边生成测试代码）、
**Trace 查看器**（失败现场全量回放）与
内置测试运行器（并行、重试、报告）。
是当下 E2E 测试的主流开源方案，
直接替代 Selenium 的手工等待与冗长样板。

- **定位**：BMS E2E 测试框架，main 流水线独立 job 运行（见《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节）。
- **版本**：1.6x（截至 2026 年 1.62.x，持续迭代；浏览器版本与 Playwright 版本绑定）。
- **许可**：Apache-2.0，OSI 认证开源。
- **语言**：测试代码用 JS/TS（Node.js 运行），驱动 Chromium/Firefox/WebKit。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 自动等待（Auto-wait） | 每个动作前自动等元素可见、稳定、可交互，无需手写 sleep，从根上减少 flaky |
| Locator | 稳定的元素定位器：`getByRole`/`getByText`/`getByTestId`；每次动作重新查询，避免「元素过期」问题 |
| Codegen 录制器 | `npx playwright codegen` 打开浏览器边操作边生成测试代码，新人上手最快路径 |
| 测试运行器 | `@playwright/test` 内置 runner：并行 worker、失败重试、超时、HTML 报告，开箱即用 |
| Project | 浏览器矩阵配置：同一套用例在 chromium/firefox/webkit 各跑一遍 |
| Browser Context | 每个测试独立的「浏览器档案」（cookie/存储隔离），测试互不污染 |
| Trace Viewer | 全量动作轨迹（DOM 快照、网络请求、console），失败用例一键回放定位 |
| 网络拦截 | `page.route` 拦截/模拟 API 响应，测试不依赖真实后端数据 |
| storageState | 复用登录态（cookie/localStorage），每条用例不必重新登录 |
| 设备模拟 | 内置手机设备参数（视口/UA/触摸），移动端 H5 用例用 iPhone 等模拟跑 |
| Headless | 无界面模式，CI 容器里直接跑，无需 X server |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **E2E 覆盖范围**：登录、主体链 RBAC 权限（含按钮显隐与字段权限）、核心 CRUD 主流程（见《[项目规划说明](../../../规划/项目规划说明.html#test)》16 节）。
- **main 流水线独立 job**：Playwright E2E 在 main 流水线单独成 job 运行，不阻塞 MR 流水线（见《[项目规划说明](../../../规划/项目规划说明.html#sel-ops)》3.4 节 GitLab CI）。
- **E2E 环境**：服务容器起 backend（SQLite）与前端产物，job 内自包含（见《[开发部署规划](../../../规划/开发部署规划.html#workflow)》7 节）。
- **测试报告与归档**：Playwright 生成自动化测试报告（CI 产物归档），结果经官方插件导入 Kiwi TCMS（见《[项目规划说明](../../../规划/项目规划说明.html#test-report)》16.5 节）。
- **移动端兼容基线**：设备模拟覆盖移动端 H5（审批/通知/查询链路），支撑「浏览器与移动端真机兼容基线」验收（见《[项目规划说明](../../../规划/项目规划说明.html#plan)》20 节）。
- **替代 Selenium**：自动等待 + 录制器 + 跨浏览器，替代 Selenium 的手工等待与冗长样板（见《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节）。

最小示例（登录用例 + 浏览器矩阵配置）：

```ts
// e2e/login.spec.ts
import { test, expect } from '@playwright/test'

test('账号密码登录进入工作台', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('账号').fill('admin')
  await page.getByLabel('密码').fill('Test@12345')
  await page.getByRole('button', { name: '登录' }).click()

  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByText('工作台')).toBeVisible()
})

// playwright.config.ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:8080',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
})
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Playwright（选中）** | 跨三大内核、自动等待、录制器、Trace、内置 runner、活跃维护、Apache-2.0 | 与 BMS「跨浏览器 + CI 独立 job + 移动端模拟」诉求完全匹配 |
| Selenium WebDriver | 经典、语言多；但手工等待、稳定性差、样板代码多、生态老化 | 项目规划明确替代对象，不选 |
| Cypress | 开发者体验好、调试直观；但单 tab 限制、无 WebKit、多域名支持弱 | 跨浏览器与多页能力不如 Playwright，不选 |
| WebdriverIO | Node 系、移动端能力有；但社区规模与资料少于 Playwright | 生态与资料不如 Playwright，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **浏览器下载走镜像**：`npx playwright install` 首次下载浏览器体积大，国内环境设 `PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/` 加速。
- **CI 依赖就绪**：main 流水线 E2E job 要等 backend（SQLite）与前端产物容器就绪后再跑，避免连接拒绝误报。
- **测试隔离**：每个测试独立 context，别共享登录态；确需复用用 `storageState` 显式管理。
- **减少 flaky**：优先自动等待与稳定定位器（`getByRole`/`getByTestId`），禁止硬编码 `waitForTimeout` 凑时间。
- **Trace 调试**：配 `trace: 'on-first-retry'`，失败用例用 Trace Viewer 回放，别只盯着截图猜。
- **移动端用例**：用设备模拟（iPhone 等）跑 H5 链路，真机兼容基线另做人工验证（见《[项目规划说明](../../../规划/项目规划说明.html#plan)》20 节）。
- **浏览器版本绑定**：浏览器由 Playwright 版本锁定，别手动装系统浏览器混用，升级走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归。
- **用例与 Kiwi TCMS 关联**：测试代码以用例 ID 标注，执行结果导入平台归档，别只留 CI 日志。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Playwright 官网 | https://playwright.dev | 文档、教程与最佳实践入口 |
| Playwright 入门 | https://playwright.dev/docs/intro | 安装、第一个测试、核心概念 |
| Playwright GitHub | https://github.com/microsoft/playwright | 源码、Releases 与 issue |
| Codegen 录制器 | https://playwright.dev/docs/codegen-intro | 边操作边生成测试代码的用法 |
| Trace Viewer | https://playwright.dev/docs/trace-viewer | 失败用例回放调试 |
| npmmirror Playwright 镜像 | https://npmmirror.com/mirrors/playwright/ | 国内浏览器下载加速源 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节 | 前端技术栈（Playwright 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节 | 选型理由：自动等待、录制器、跨浏览器，替代 Selenium |
| 《[项目规划说明](../../../规划/项目规划说明.html#test)》16 节 | 测试策略：E2E 覆盖范围与报告归档 |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-ops)》3.4 节 | GitLab CI：main 流水线 Playwright 独立 job |
| 《[Vitest 技术介绍](Vitest技术介绍.md)》 | 单元测试（与 E2E 分层互补） |
| 《[Kiwi TCMS 技术介绍](../工程化与质量/KiwiTCMS技术介绍.md)》 | 用例登记与 Playwright 结果导入 |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | 后端对应测试框架 |
| 《[开发部署规划](../../../规划/开发部署规划.html#workflow)》7 节 | E2E 环境：服务容器起 backend 与前端产物 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19
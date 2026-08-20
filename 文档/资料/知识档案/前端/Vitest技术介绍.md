# Vitest 技术介绍

> Vite 同构单元测试框架 · BMS 前端覆盖率门禁

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Vitest 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Vitest** 是 Vite 团队出品的下一代单元测试框架，
与 Vite **同构**：直接复用 `vite.config.ts`
的转换管线（别名、TS、JSX 全部生效），
原生 ESM、多 worker 并行执行，默认**零配置**跑起来。
内置覆盖率统计与阈值门禁，
是 Vue 3 + Vite 技术栈的事实标准测试框架。

- **定位**：BMS 前端单元测试/组件测试框架，内置 coverage 统计前端覆盖率，CI 门禁之一（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节）。
- **版本**：4.x（截至 2026 年稳定线，5.0 处于 RC 阶段）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，测试代码用 JS/TS。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 测试套件 | `describe` 分组 + `it`（test）用例 + `expect` 断言，结构清晰、失败定位准 |
| Vite 同构 | 复用 `vite.config.ts`：别名、TS 转换、环境变量与开发环境一致，测试即「换个入口跑同一套代码」 |
| 原生 ESM | 不走 Babel 转 CJS，启动快、模块语义与 Vite 开发态一致 |
| 并行执行 | 多 worker 并行跑测试文件，大项目提速明显 |
| vi（mock API） | `vi.fn`（假函数）、`vi.mock`（模块级 mock）、`vi.spyOn`、`vi.useFakeTimers`（假时钟），隔离外部依赖 |
| 测试环境 | `node`（默认）/ `happy-dom` / `jsdom`：组件测试需要 DOM 环境，二选一 |
| 组件测试 | 配合 `@vue/test-utils` 的 `mount` 挂载 Vue 组件，断言渲染结果与交互 |
| Coverage | 内置覆盖率统计（`@vitest/coverage-v8` 或 istanbul），支持阈值配置，低于门槛即失败 |
| watch 模式 | 本地默认 watch，改代码即重跑相关用例；CI 用 `vitest run` 跑一次即退出 |
| 快照测试 | `toMatchSnapshot` 记录渲染快照，防回归（适合纯展示组件） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **前端单元测试**：工具函数、API 封装、状态逻辑（Pinia store）的纯逻辑测试（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **组件测试**：关键组件（待办角标、表单设计器控件、审批操作区）的渲染与交互测试，配合 @vue/test-utils。
- **覆盖率门禁**：核心模块（认证/RBAC/工作流/审计/收付款）行覆盖 ≥ 80%、整体 ≥ 70%，CI 门禁——前端由 Vitest coverage 统计，低于门槛流水线失败（见《[项目规划说明](../../../规划/项目规划说明.md#test-exit)》16.4 节）。
- **MR 流水线**：前端 ESLint + Vitest（含 coverage 门禁）+ 双端构建（见《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 GitLab CI）。
- **测试报告**：Vitest 生成自动化测试报告（CI 产物归档），结果经官方插件导入 Kiwi TCMS（见《[项目规划说明](../../../规划/项目规划说明.md#test-report)》16.5 节）。
- **双工程**：frontend 与 frontend-mobile 各自独立 vitest 配置，口径一致、工程独立。

最小示例（单元测试 + 组件测试）：

```ts
// src/utils/amount.spec.ts
import { describe, it, expect } from 'vitest'
import { formatAmount } from './amount'

describe('formatAmount', () => {
  it('千分位格式化金额', () => {
    expect(formatAmount(1234567.89)).toBe('1,234,567.89')
  })

  it('空输入返回空串', () => {
    expect(formatAmount('')).toBe('')
  })
})

// src/components/TodoBadge.spec.ts
import { mount } from '@vue/test-utils'
import TodoBadge from './TodoBadge.vue'

describe('TodoBadge', () => {
  it('有待办时显示角标数字', () => {
    const wrapper = mount(TodoBadge, { props: { count: 3 } })
    expect(wrapper.text()).toContain('3')
  })
})
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Vitest（选中）** | 与 Vite 同构零配置、原生 ESM 快、内置 coverage 与阈值、活跃维护、MIT | 与 BMS「Vite 技术栈 + 覆盖率门禁」诉求完全匹配 |
| Jest | 经典、生态大；但与 Vite 不同构（CJS 为主）、需额外配置，社区重心已转向 Vitest | 同构优势明显，Vitest 更顺 |
| Mocha + Chai | 老牌组合、灵活；但 runner/覆盖率/mock 要手工拼装，配置成本高 | 工程化成本不划算，不选 |
| QUnit | 轻量、JQuery 时代经典；但生态小、与 Vite 不同构 | 生态与同构都不如 Vitest，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **CI 用 run 模式**：CI 里执行 `vitest run`（非 watch），否则流水线挂起不退出。
- **覆盖率 provider 二选一**：`@vitest/coverage-v8`（快）或 istanbul（兼容性好），选定后锁定版本，别混装。
- **组件测试要 DOM 环境**：配置 `environment: 'happy-dom'`（或 jsdom），并在 package.json 装对应依赖。
- **vi.mock 提升**：模块级 mock 会被提升到文件顶部，mock 工厂里引用外部变量会报错，注意写法。
- **阈值配置**：coverage 门槛写进 `vitest.config.ts`（对齐 80%/70% 口径），低于门槛流水线失败，别只出报告不设门槛。
- **双工程独立配置**：frontend 与 frontend-mobile 各自 vitest 配置，别跨工程共享。
- **版本跟踪**：4.x 为当前稳定线，5.0 RC 阶段，升级前看迁移说明，走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归。
- **测试文件命名**：统一 `*.spec.ts`（或 `*.test.ts`）放源码旁，避免散落难找。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Vitest 官方文档 | https://vitest.dev | 入门、API 与配置完整文档 |
| Vitest GitHub | https://github.com/vitest-dev/vitest | 源码、Changelog 与 issue |
| Vitest 覆盖率配置 | https://vitest.dev/config/#coverage | coverage provider 与阈值配置说明 |
| Vue Test Utils | https://test-utils.vuejs.org/ | Vue 组件测试官方工具（mount/断言） |
| happy-dom | https://happy-dom.com/ | 轻量 DOM 实现，组件测试环境选项之一 |
| jsdom | https://github.com/jsdom/jsdom | 另一 DOM 环境选项，兼容性好 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（Vitest 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：与 Vite 同构、内置 coverage |
| 《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节 | 测试策略：覆盖率门槛与测试报告归档 |
| 《[ESLint 与 Prettier 技术介绍](ESLint与Prettier技术介绍.md)》 | 同一 MR 门禁的代码规范部分 |
| 《[Playwright 技术介绍](Playwright技术介绍.md)》 | E2E 测试（与单元测试分层互补） |
| 《[Vite 技术介绍](Vite技术介绍.md)》 | 同构基础：复用 Vite 转换管线 |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | 后端对应工具（测试 + pytest-cov 门禁） |
| 《[Kiwi TCMS 技术介绍](../工程化与质量/KiwiTCMS技术介绍.md)》 | 用例登记与测试结果导入归档 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
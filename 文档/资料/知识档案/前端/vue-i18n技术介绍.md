# vue-i18n 技术介绍

> Vue 官方国际化方案 · BMS 多语言与 RTL 适配基础

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › vue-i18n 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**vue-i18n** 是 Vue.js 的官方国际化（i18n）插件，由 intlify 团队
（kazuya kawaguchi）维护，主打**组件级文案管理**、**复数与格式化**与
**运行时语言切换**。截至 2026 年，vue-i18n（11.4.8）是 Vue 生态事实上的国际化标准，
与 Vue 官方文档、DevTools 深度集成。

- **定位**：BMS 前端（PC 管理端 + 移动端 H5）的国际化方案，承载中英文切换、多语言动态扩展与 RTL 适配。
- **版本**：11.x 系列（11.4.8，截至 2026 年，持续迭代）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，自带类型定义。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Composition API | `legacy: false` 模式下用 `useI18n()` 在组件内取 `t`、`locale`，与 Vue 3 组合式风格一致 |
| 消息编译 | 文案模板（含插值 `{name}`、复数）运行时编译为渲染函数，支持按需加载语言包 |
| locale 响应式 | `locale` 是响应式引用，赋值即全局切换语言，所有组件文案立即重渲染 |
| 回退语言（fallbackLocale） | 当前语言缺某 key 时自动回退到指定语言（如 en），避免界面出现 key 原文 |
| 作用域（scope） | global（全局语言包）与 local（组件内 `messages`）两级，BMS 以 global 为主 |
| 复数与格式化 | 内置复数规则与日期/数字格式化（基于 Intl API），按 locale 本地化 |
| RTL 支持 | 切换语言时可联动 `document.dir`（ltr/rtl），BMS 由 sys_i18n_locale.rtl 标记驱动 |
| 消息函数 | 文案可传函数动态求值（如按权限返回不同提示），适合条件文案 |
| 缺失侦测 | 可监听 `missing` 事件，开发期收集未翻译 key，配合后端 Babel 提取入库 |
| DevTools 集成 | Vue DevTools 中可查看当前 locale 与各作用域消息，排障方便 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **中英文切换**：顶栏语言切换器改 `locale` 即全局生效，偏好写 localStorage 持久化，刷新后保持（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **语言包运行时拉取**：启动时 `GET /api/v1/i18n/messages` 从后端取当前语言文案（后端 Redis 缓存 + 前端 localStorage 二次缓存），避免打进前端包体（见《[Redis 技术介绍](../后端核心/Redis技术介绍.md)》）。
- **文案不硬编码**：前后端固定文案统一存 `sys_i18n_message`，页面在线维护、新增语言免发版；前端模板一律 `t('key')`，禁止写死中文（见《[国际化规范](../../../规范/国际化规范.md)》）。
- **多语言动态扩展**：语言清单 `sys_i18n_locale` 动态扩展，前端按清单渲染语言菜单，无需改代码发版。
- **RTL 适配**：语言带 rtl 标记时切换 `dir` 与布局镜像（阿拉伯语等场景），由数据驱动而非硬编码。
- **组件文案联动**：Element Plus 内置文案（分页、空数据）经 el-config-provider 与 vue-i18n 同步切换（见《[Element Plus 技术介绍](ElementPlus技术介绍.md)》）。

最小示例（初始化 + 组件内使用）：

```js
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false, // Composition API 模式
  locale: localStorage.getItem('bms.locale') ?? 'zh-CN',
  fallbackLocale: 'en',
  messages: {}, // 语言包运行时从后端拉取后合并
})
app.use(i18n)
```

```html
<script setup>
import { useI18n } from 'vue-i18n'
const { t, locale } = useI18n()
</script>
<template>
  <button @click="toggleLocale">切换语言</button>
  <span>{{ t('common.save') }}</span>
</template>
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **vue-i18n（选中）** | Vue 官方方案、组件级文案、复数/格式化齐全、DevTools 集成 | 与 Vue 3 生态天然契合，BMS 首选 |
| i18next | 框架无关、功能强、生态大；但偏 React/通用，Vue 集成需额外适配 | 非 Vue 官方，集成成本高于 vue-i18n |
| react-intl | React 生态成熟；但绑定 React，Vue 项目不适用 | 框架不符，直接排除 |
| 自建字典映射 | 零依赖、简单；但无复数/格式化/作用域，多语言扩展吃力 | 能力不足，BMS 多语言动态扩展诉求下不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **组件文案要同步**：Element Plus 等组件库内置文案默认英文，需 el-config-provider 配 locale 并与 vue-i18n 切换联动，否则切语言后组件文案不变。
- **缺 key 兜底**：务必设 fallbackLocale，并在开发期监听 missing 事件收集未翻译 key，避免线上出现 key 原文。
- **语言包缓存失效**：localStorage 二次缓存要带版本号/哈希，后端文案更新后能感知并拉新，否则用户一直看旧文案。
- **运行时编译开销**：大量文案首次切换会触发编译，语言包按语言懒加载、避免一次全量编译。
- **RTL 布局别硬编码**：用逻辑属性（margin-inline、padding-inline）或 dir 驱动镜像，别写死 left/right。
- **文案不硬编码**：模板与 JS 提示一律走 `t('key')`，代码评审时把写死中文当缺陷处理（见《[国际化规范](../../../规范/国际化规范.md)》）。
- **数字/日期本地化**：用 Intl API 或 vue-i18n 格式化，别手动拼日期字符串，否则各语言格式错乱。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| vue-i18n 官方文档 | https://vue-i18n.intlify.dev | 权威文档，含教程、API 与生态 |
| vue-i18n GitHub 仓库 | https://github.com/intlify/vue-i18n | 源码、Changelog 与 issue 讨论 |
| intlify 官网 | https://intlify.dev | 国际化生态与多项目入口 |
| MDN：Internationalization | https://developer.mozilla.org/zh-CN/docs/Web/JavaScript/Reference/Global_Objects/Intl | Intl API（复数/日期/数字本地化）底层 |
| W3C：ICU MessageFormat | https://unicode.org/icu/icu4c/ | 复数与消息格式标准背景 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（vue-i18n 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：运行时拉取、动态扩展、RTL |
| 《[国际化规范](../../../规范/国际化规范.md)》 | 文案入库、key 命名、回退与 RTL 约定 |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | 组件文案国际化联动（el-config-provider） |
| 《[Redis 技术介绍](../后端核心/Redis技术介绍.md)》 | 语言包后端缓存层 |
| 《[Babel 技术介绍](../后端核心/Babel技术介绍.md)》 | 后端开发期文案 key 提取入库 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
# SCSS 技术介绍

> 最流行的 CSS 预处理器 · BMS 样式定制与主题基础

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › SCSS 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**SCSS**（Sassy CSS）是历史最悠久、使用最广泛的 CSS 预处理器，
在 CSS 之上扩展了**变量、嵌套、mixin、模块化**等能力，编译产物仍是标准 CSS。
当前主流实现是 **dart-sass**（Dart 语言编写、编译为纯 JS 的 npm 包 `sass`），
旧的 node-sass 已停止维护。截至 2026 年，sass（1.101.x 系列）是前端样式预处理的事实标准。

- **定位**：BMS 前端样式预处理与 Element Plus 主题定制的基础，Vite 原生支持。
- **版本**：1.101.x 系列（1.102.0，截至 2026 年，持续迭代）。
- **许可**：MIT，OSI 认证开源。
- **实现**：dart-sass（npm 包 `sass`，纯 JS，跨平台）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 变量 | `$primary: #409eff;` 定义可复用值，改一处全局生效，BMS 主题色板的基础 |
| 嵌套 | 选择器可嵌套书写，编译后展开为后代选择器，贴近组件 DOM 结构 |
| Mixin | `@mixin` 定义可复用样式块，`@include` 调用，支持传参，替代复制粘贴 |
| 函数 | `@function` 自定义计算（如色阶、间距倍数），返回变量值 |
| 模块化（@use/@forward） | 新模块系统，按文件组织样式、命名空间引用，替代已废弃的 `@import` |
| 占位符 | `%placeholder` 定义不直接输出的选择器，`@extend` 复用，减少重复 CSS |
| 运算与条件 | `@if/@else`、`@for`、`@each`，用逻辑生成系列样式（如 12 栅格） |
| 内置函数 | 颜色（`lighten`/`mix`）、数学、字符串等，主题派生色常用 |
| 编译产物 | 输出标准 CSS，浏览器零感知；Vite 构建时自动调用 sass 编译 |
| 与 CSS 变量协作 | SCSS 变量编译期固定，CSS 变量（`--el-color-primary`）运行期可改，BMS 深色模式用后者 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **Element Plus 主题定制**：覆盖主题变量（色板、圆角、字号）实现企业品牌色，见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节与《[Element Plus 技术介绍](ElementPlus技术介绍.md)》。
- **全局样式组织**：按模块拆分 `.scss` 文件，用 `@use` 模块化引入，避免单文件膨胀。
- **组件样式复用**：卡片、表单、表格等重复样式抽 mixin，双端（PC/移动）视觉一致。
- **避免重型 CSS 方案**：不引入 CSS-in-JS 或原子化框架，保持样式体系统一、构建简单（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **Vite 原生支持**：`.vue` 的 `<style lang="scss">` 直接可用，无需额外插件（见《[Vite 技术介绍](Vite技术介绍.md)》）。

最小示例（变量 + 嵌套 + mixin）：

```scss
// theme.scss
$primary: #409eff;
$font-size-base: 14px;

@mixin card-shadow {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.card {
  padding: 16px;
  @include card-shadow;

  .title {
    font-size: $font-size-base;
    color: $primary;
  }
}
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **SCSS（选中）** | 生态最大、资料最全、Element Plus 主题原生基于 SCSS、Vite 原生支持 | 与 BMS 组件库定制、团队习惯完全匹配 |
| Less | 语法略简、Ant Design 系用得多；但生态与资料少于 SCSS | Element Plus 不基于 Less，选它反而别扭 |
| PostCSS + 插件 | 灵活、可做 autoprefixer 等；但无变量/嵌套等语法糖，需配多个插件 | 定位是 CSS 处理而非预处理器，不替代 SCSS |
| CSS-in-JS（styled-components 等） | 运行时样式、作用域强；但运行时开销、与 SSR/构建体系耦合 | BMS 为 SPA 管理端，静态样式足够，不引入 |
| Tailwind CSS | 原子化、开发快；但学习曲线、与组件库主题体系并存成本高 | 与 Element Plus 主题定制目标重叠，暂不引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **@import 已废弃**：dart-sass 会告警，新代码用 `@use/@forward` 模块系统，旧 `@import` 逐步迁移。
- **scoped 样式改组件内部**：在 `<style scoped>` 中改 Element Plus 内部样式需 `:deep()` 选择器（见《[Element Plus 技术介绍](ElementPlus技术介绍.md)》）。
- **嵌套别过深**：超过 3 层选择器特异性高、难维护，BMS 约定嵌套不超过 3 层。
- **SCSS 变量 vs CSS 变量**：SCSS 变量编译期固定、CSS 变量运行期可改；深色模式切换用 CSS 变量，别用 SCSS 变量。
- **node-sass 已退役**：统一用 dart-sass（npm 包 `sass`），别混装 node-sass，避免版本冲突。
- **构建性能**：超大样式文件编译慢，按模块拆分、`@use` 按需引入，避免全量 `@import`。
- **颜色函数弃用**：`lighten/darken` 等已标记弃用，新代码用 `color.scale`/`color.adjust`。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Sass 官方文档 | https://sass-lang.com/documentation/ | 权威语法与函数参考 |
| Sass 指南（入门） | https://sass-lang.com/guide | 安装、语法、模块化教程 |
| dart-sass GitHub | https://github.com/sass/dart-sass | 源码、Changelog 与 issue |
| MDN：CSS 参考 | https://developer.mozilla.org/zh-CN/docs/Web/CSS | 编译产物 CSS 属性权威参考 |
| Element Plus 主题定制 | https://element-plus.org/zh-CN/guide/theming.html | 基于 SCSS/CSS 变量的主题定制实践 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（SCSS 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：Element Plus 主题定制、避免重型 CSS 方案 |
| 《[前端开发规范](../../../规范/前端开发规范.md)》 | 样式组织、嵌套深度、scoped 约定 |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | 主题变量定制（--el-color-primary 等） |
| 《[Vite 技术介绍](Vite技术介绍.md)》 | 构建时 SCSS 编译支持 |
| 《[vue-i18n 技术介绍](vue-i18n技术介绍.md)》 | RTL 布局适配（dir 驱动样式镜像） |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
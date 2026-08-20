# Vant 技术介绍

> 移动端 Vue 组件库 · BMS frontend-mobile 界面基础

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › Vant 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Vant** 是有赞出品的移动端 Vue 组件库，
面向**手机浏览器 / App 内嵌 WebView** 场景，
提供 80+ 组件，组件平均体积约 1KB（min+gzip），
零第三方依赖、TypeScript 编写，支持按需引入、
自定义主题、暗黑模式与 30+ 语言国际化。
截至 2026 年，Vant（4.10.x）是 Vue 移动端组件库中
组件最全、社区最活跃的方案之一。

- **定位**：BMS frontend-mobile 独立工程的 UI 组件库，承载移动端 H5（审批、通知、数据查询）全部界面（见《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节）。
- **版本**：4.10.0（截至 2026 年，持续迭代；4.x 面向 Vue 3）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，Vue 3 组件。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 移动端优先 | 按小屏（375px 设计基准）与触摸交互设计，不是 PC 组件的缩小版 |
| 组件集 | 80+ 组件：导航（Navbar/Tabbar）、反馈（Toast/Dialog/Notify）、表单（Field/Picker/DatePicker）、列表（List/Sticky）等，覆盖移动端常见交互 |
| 按需引入 | 支持 Tree Shaking，用哪个引哪个，包体小；配合 unplugin-vue-components 可自动按需导入 |
| 主题定制 | Less 变量体系，改品牌色、圆角、字号等全局变量即可换肤 |
| 暗黑模式 | 内置暗黑主题，与 PC 端深色模式风格可对齐 |
| 国际化（i18n） | 组件文案内置 30+ 语言；业务文案仍由 vue-i18n 统一管（见《[vue-i18n 技术介绍](vue-i18n技术介绍.md)》） |
| 触摸交互 | 滑动、长按、下拉刷新、上拉加载等触摸手势原生支持 |
| WebView 兼容 | 兼容 Chrome ≥ 51、iOS ≥ 10（与 Vue 3 同口径），企微/钉钉内嵌浏览器可用 |
| SSR | 支持 Nuxt 服务端渲染；BMS 移动端是 SPA，不用 SSR，仅说明能力存在 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **frontend-mobile 独立工程**：Vue 3 + Vant 的移动端 H5 工程，与 PC 端 frontend 各自独立（各自 package-lock.json、ESLint/Prettier/TS 配置，互不共享），复用后端 API 与会话体系（见《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节、《[项目规划说明](../../../规划/项目规划说明.html#structure)》4 节）。
- **移动端 H5 页面**：登录（账号密码/SSO/企业微信/钉钉免登）、首页工作台（待办/通知/公告/快捷入口卡片）、我的待办/已办、审批操作（同意/驳回/评论，附件在线预览）、通知列表（批量已读/全部已读）、公告查看、我发起的、数据查询（报表查看）、帮助中心、个人中心（改密/语言/喜好偏好/退出登录）（见《[项目规划说明](../../../规划/项目规划说明.html#pages)》15 节）。
- **企微/钉钉免登**：企业微信/钉钉工作台内嵌免登，手机浏览器可直接访问；审批链路在移动端闭环（见《[项目规划说明](../../../规划/项目规划说明.html#plan)》20 节验收标准）。
- **跨端一致**：工作台布局配置与 PC 同源跨端同步，移动端按小屏形态呈现（卡片、列表、Tabbar 导航）。
- **与 Element Plus 分工**：PC 端用 Element Plus、移动端用 Vant，两个工程互不混用（见《[Element Plus 技术介绍](ElementPlus技术介绍.md)》）。

最小示例（待办列表 + 审批操作）：

```html
<script setup>
import { ref } from 'vue'
import { showToast } from 'vant'
import { Button, Cell, CellGroup } from 'vant'

const tasks = ref([
  { id: 1, title: '采购申请审批', done: false },
  { id: 2, title: '付款单审批', done: true },
])

function approve(id) {
  // 调后端审批接口（复用 PC 端同一套 API）
  showToast('已提交审批意见')
}
</script>

<template>
  <CellGroup inset>
    <Cell
      v-for="t in tasks"
      :key="t.id"
      :title="t.title"
      :label="t.done ? '已办' : '待办'"
    >
      <template #right-icon>
        <Button v-if="!t.done" size="small" type="primary" @click="approve(t.id)">审批</Button>
      </template>
    </Cell>
  </CellGroup>
</template>
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Vant（选中）** | Vue 3 移动端组件最全、有赞生产验证、活跃维护、MIT、按需引入包体小 | 与 BMS 移动端 H5 + 企微/钉钉内嵌场景完全匹配 |
| Ant Design Mobile | 组件齐全、设计体系好；但绑定 React，Vue 项目不适用 | 框架不符，直接排除 |
| NutUI（腾讯） | 支持 Vue 3、移动端定位；但社区规模与组件生态小于 Vant | 可用但资料与生态弱于 Vant，不选 |
| Element Plus | PC 组件库、团队已用；但面向桌面设计，小屏/触摸体验非一等公民 | 分工不同：PC 用 Element Plus（见《[Element Plus 技术介绍](ElementPlus技术介绍.md)》） |
| Mint UI / iView Mobile | 移动端组件；但面向 Vue 2，基本停止更新 | 版本不符且无维护，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **版本对应**：4.x 面向 Vue 3；2.x 面向 Vue 2，BMS 一律用 4.x，别混装。
- **按需引入**：用 unplugin-vue-components 或手动 import，避免整包引入撑大体积。
- **内嵌浏览器兼容**：企微/钉钉 WebView 版本参差，上线前真机过一遍（触摸、弹窗、滚动）。
- **安全区**：刘海屏底部 Tabbar 要处理安全区（Vant 提供 `safe-area-inset-bottom` 工具类）。
- **i18n 分工**：Vant 管组件文案、vue-i18n 管业务文案，两边语言切换要对齐，别出现「界面中文、按钮英文」。
- **与 Element Plus 不混用**：PC 工程用 Element Plus、移动工程用 Vant，跨端共享的只有 API 与布局配置。
- **暗黑模式**：如启用 Vant 暗黑主题，与 PC 端深色模式保持风格一致。
- **升级走评审**：大版本变更走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归，重点验证审批链路。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Vant 官网（中文文档） | https://vant-ui.github.io/vant/ | 组件文档、示例与主题定制说明 |
| Vant GitHub | https://github.com/vant-ui/vant | 源码、Changelog 与 issue |
| Vant npm | https://www.npmjs.com/package/vant | 安装与版本历史 |
| Vue 3 官方文档 | https://cn.vuejs.org/ | Vant 组件的宿主框架 |
| MDN：移动端 Web 开发 | https://developer.mozilla.org/zh-CN/docs/Web/Performance | 移动端性能与兼容基础 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-frontend)》2.2 节 | 前端技术栈（Vue 3 + Vant 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-frontend)》3.2 节 | 选型理由：移动端独立工程，复用后端 API |
| 《[项目规划说明](../../../规划/项目规划说明.html#pages)》15 节 | 移动端 H5 页面清单（审批/通知/查询/免登） |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | Vant 的宿主框架 |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | PC 端组件库（与 Vant 分工） |
| 《[Axios 技术介绍](Axios技术介绍.md)》 | 移动端 API 请求（复用后端 API 与会话体系） |
| 《[vue-i18n 技术介绍](vue-i18n技术介绍.md)》 | 业务文案国际化（与 Vant 组件文案分工） |
| 《[命名规范](../../../规范/命名规范.html)》 | 移动端路由、接口调用等命名 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19
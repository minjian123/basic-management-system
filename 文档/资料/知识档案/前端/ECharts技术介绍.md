# ECharts 技术介绍

> Apache 开源可视化库 · BMS 报表与大屏渲染引擎

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › ECharts 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**ECharts** 是 Apache 软件基金会旗下的开源可视化库，
主打**声明式配置**、**图表类型全**与**大数据量渲染**，
支持 Canvas/SVG 渲染。截至 2026 年，ECharts（6.1.0）是中文生态最完善、
图表覆盖最广的前端可视化方案，广泛用于管理端报表与数据大屏。

- **定位**：BMS 报表中心与可视化大屏的渲染引擎，工作台数据集图表卡也用它。
- **版本**：6.x 系列（6.1.0，截至 2026 年，持续迭代）。
- **许可**：Apache-2.0，OSI 认证开源（含专利授权）。
- **语言**：TypeScript 编写，框架无关（可嵌入 Vue/React）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| 声明式配置（option） | 整张图用一个 `option` 对象描述（坐标轴/系列/提示/图例），`setOption` 渲染，改配置即更新 |
| 渲染方式 | 默认 Canvas（性能好、适合大数据），可切 SVG（适合打印/缩放不失真） |
| 图表类型 | 折线、柱状、饼、散点、雷达、漏斗、热力、地图、树图等，覆盖管理端全场景 |
| 系列（series） | option.series 数组，一个元素一条数据系列，可混排（如柱线组合图） |
| 坐标轴 | xAxis/yAxis（直角）、radiusAxis（极坐标），支持多轴、双轴 |
| tooltip 与 legend | 悬浮提示与图例开关，内置交互，减少自研 |
| 主题（theme） | 全局配色/字体主题，BMS 深色模式切换用 |
| 大数据渲染 | 渐进渲染（progressive）、采样、GPU（WebGL 扩展），十万级点不卡 |
| resize | 容器尺寸变化需调 `chart.resize()`，否则图形不跟随 |
| Vue 集成 | 无官方 Vue 包，常用 vue-echarts 封装或手动 init/dispose，BMS 按组件生命周期管理 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **报表渲染**：拖拽报表设计器产出的 `rpt_report.chart_config`（ECharts 配置）直接驱动渲染（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **可视化大屏**：大屏设计器 + 轮播播放，图表节点用 ECharts 渲染，配合 vue-flow 自由画布（见《[vue-flow 技术介绍](vue-flow技术介绍.md)》）。
- **工作台图表卡**：数据集图表卡（`rpt_dataset` + `chart_type`）挂接 ECharts 动态渲染（见《[项目规划说明](../../../规划/项目规划说明.md#pages)》首页工作台）。
- **中文生态最全**：图表类型覆盖管理端全场景，资料与示例丰富，团队上手快（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **主题联动**：深色/浅色模式切换时同步 ECharts 主题与系列配色（见《[Element Plus 技术介绍](ElementPlus技术介绍.md)》暗黑模式）。

最小示例（初始化 + 渲染 + 自适应）：

```js
import * as echarts from 'echarts'

const chart = echarts.init(document.getElementById('chart'))
chart.setOption({
  title: { text: '销售趋势' },
  tooltip: {},
  xAxis: { type: 'category', data: ['1月', '2月', '3月'] },
  yAxis: { type: 'value' },
  series: [{ type: 'line', data: [120, 200, 150] }],
})

// 容器尺寸变化时自适应
window.addEventListener('resize', () => chart.resize())
// 组件卸载时释放
// chart.dispose()
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **ECharts（选中）** | 图表类型最全、中文生态最好、大数据渲染强、Apache 许可 | 与 BMS 报表/大屏全场景、中文团队完全匹配 |
| Chart.js | 轻量、API 简单；但图表类型与大数据能力弱于 ECharts | 大屏/复杂图表场景能力不足 |
| Highcharts | 商业成熟、文档好；但收费、中文资料少 | 商业授权成本高，不符 BMS 开源自托管定位 |
| D3.js | 底层灵活、自定义强；但学习曲线陡、开发成本高 | 适合定制可视化，BMS 常规报表用 ECharts 更快 |
| AntV（G2） | 蚂蚁出品、语法优雅；但生态与中文资料少于 ECharts | 可选但非生态最优，暂不引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **忘记 resize**：容器尺寸变化（侧边栏折叠、卡片拖拽）必须调 `chart.resize()`，否则图形错位。
- **内存泄漏**：组件卸载要 `chart.dispose()`，否则 Canvas 实例残留，列表页多图尤甚。
- **大数据量**：上万点开启 progressive/采样，别全量渲染卡死页面。
- **主题同步**：深色模式切换要同步 ECharts 主题与系列色，否则图表与界面配色割裂。
- **配置深拷贝**：`setOption` 默认合并，切换数据集时注意 `notMerge: true` 或先清空，避免残留系列。
- **Vue 集成生命周期**：init 要在 DOM 挂载后（onMounted），dispose 在 onBeforeUnmount，别在 setup 顶层直接 init。
- **版本 6 破坏性变更**：5→6 有 API 调整，升级走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 全量回归。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| ECharts 官方文档（中文） | https://echarts.apache.org/zh/index.html | 权威文档，含示例与 API |
| ECharts 官方文档（英文） | https://echarts.apache.org | 英文版文档 |
| ECharts GitHub | https://github.com/apache/echarts | 源码、Changelog 与 issue |
| vue-echarts | https://github.com/ecomfe/vue-echarts | Vue 封装（按需选用） |
| ECharts 示例画廊 | https://echarts.apache.org/zh/examples.html | 各类图表现成示例，抄作业入口 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（ECharts 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：中文生态最全、覆盖全场景 |
| 《[vue-flow 技术介绍](vue-flow技术介绍.md)》 | 大屏自由画布，ECharts 渲染图表节点 |
| 《[gridstack.js 技术介绍](gridstack技术介绍.md)》 | 工作台卡片网格布局（与 ECharts 图表卡配合） |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | 报表/大屏界面组件与深色模式联动 |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | ECharts 组件的宿主框架 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
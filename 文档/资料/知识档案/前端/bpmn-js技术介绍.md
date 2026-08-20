# bpmn-js 技术介绍

> Web 端 BPMN 2.0 建模组件 · BMS 工作流拖拽设计器

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › bpmn-js 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**bpmn-js** 是 bpmn-io 团队（Camunda 生态）出品的 Web 端
**BPMN 2.0** 建模组件，基于自研渲染引擎 diagram-js，
主打**拖拽绘制流程图**、**导出标准 BPMN XML**与
**只读渲染**。截至 2026 年，bpmn-js（18.x 系列）是浏览器端 BPMN 建模的事实标准，
被 Camunda 等主流工作流引擎采用。

- **定位**：BMS 管理端工作流管理模块的流程建模器，拖拽绘制流程定义并导出 BPMN XML 交给后端执行。
- **版本**：18.x 系列（18.24.0，截至 2026 年，持续迭代）。
- **许可**：MIT，OSI 认证开源。
- **语言**：TypeScript 编写，框架无关（可嵌入 Vue/React）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| BPMN 2.0 | 业务流程建模标准（OMG 制定），用节点/连线描述流程：开始/结束事件、用户任务、网关等 |
| diagram-js | bpmn-io 自研底层渲染引擎，负责画布、缩放、拖拽、元素交互，bpmn-js 在其上实现 BPMN 语义 |
| Moddle | bpmn-io 的 XML 模型框架，把 BPMN 元素与 XML 互转，是导出标准 XML 的基础 |
| Modeler（建模器） | 可编辑模式：拖拽、连线、改属性，BMS 流程建模页用它 |
| Viewer（查看器） | 只读渲染：展示流程定义，BMS 流程实例详情页用它 |
| Palette（元素面板） | 左侧可拖入的元素库（任务、网关、事件等） |
| Context Pad | 选中元素后出现的上下文操作（加连线、加任务、删除） |
| Properties Panel | bpmn-js-properties-panel 插件，右侧属性编辑（名称、办理人、条件） |
| saveXML | 导出标准 BPMN 2.0 XML 字符串，BMS 存 `wf_process.bpmn_xml` 交后端解析 |
| 事件机制 | `element.changed`、`selection.changed` 等，监听建模操作做联动与校验 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **拖拽建模流程定义**：管理端工作流管理模块用 bpmn-js 绘制流程，支持条件分支可视化（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **导出 BPMN XML**：建模完成后 `saveXML()` 导出标准 XML，存 `wf_process.bpmn_xml`，交后端 SpiffWorkflow 解析执行（见《[SpiffWorkflow 技术介绍](../后端核心/SpiffWorkflow技术介绍.md)》）。
- **流程版本管理**：同一 `definition_key` 多版本，建模器加载历史版本 XML 可继续编辑（见《[项目规划说明](../../../规划/项目规划说明.md#pages)》数据规范）。
- **只读展示**：流程实例、待办/已办详情页用 Viewer 渲染流程走向，高亮当前节点。
- **属性与办理人**：用户任务办理人、会签/或签、条件表达式经 Properties Panel 配置，写入 BPMN 扩展属性。

最小示例（建模 + 导出 XML）：

```js
import BpmnModeler from 'bpmn-js/lib/Modeler'
import 'bpmn-js/dist/assets/diagram-js.css'
import 'bpmn-js/dist/assets/bpmn-js.css'

const modeler = new BpmnModeler({ container: document.getElementById('canvas') })

await modeler.createDiagram() // 空白画布

// 建模完成后导出标准 BPMN XML，提交后端存 wf_process.bpmn_xml
const { xml } = await modeler.saveXML()
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **bpmn-js（选中）** | Web 端 BPMN 标准、导出标准 XML、生态成熟（Camunda 采用）、MIT | 与 BMS「拖拽建模 → 标准 XML → 后端执行」链路完全匹配 |
| Signavio | 功能强、企业级；但商业收费、SaaS 为主 | 成本高且非开源自托管，不符 BMS 定位 |
| 自研画布 | 完全可控；但 BPMN 语义、渲染、XML 互转工作量巨大 | 重复造轮子，风险高，不选 |
| jBPM / Activiti 前端 | 绑定 Java 引擎；但 BMS 后端是 Python（SpiffWorkflow） | 引擎栈不符，前端组件也不如 bpmn-js 通用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **无官方 Vue 封装**：bpmn-js 框架无关，需自己包一层 Vue 组件（onMounted 初始化、onBeforeUnmount 调 `modeler.destroy()` 防内存泄漏）。
- **与 SpiffWorkflow 的 BPMN 子集对齐**：SpiffWorkflow 支持 BPMN 子集（用户任务、网关、结束事件），建模时引导用户只用支持元素，避免导出后端跑不了的流程。
- **XML 校验**：提交前做 BPMN 合法性校验（起止事件、连线完整），别把残缺流程存库。
- **大流程性能**：节点很多时渲染/交互变慢，合理分页或用 Viewer 只读展示。
- **样式冲突**：bpmn-js 自带 CSS 可能影响全局，注意作用域隔离（scoped 或独立容器）。
- **属性面板按需引入**：Properties Panel 是独立包，只读场景别引入，减小体积。
- **升级注意 diagram-js 联动**：bpmn-js 依赖 diagram-js 版本，升级看 Changelog，走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| bpmn.io 官网 | https://bpmn.io | bpmn-io 生态入口与示例 |
| bpmn-js GitHub | https://github.com/bpmn-io/bpmn-js | 源码、API、Changelog 与 issue |
| bpmn-js 示例 | https://github.com/bpmn-io/bpmn-js-examples | 各类用法示例（建模/查看/属性） |
| BPMN 2.0 规范 | https://www.omg.org/spec/BPMN/ | OMG 官方 BPMN 标准定义 |
| bpmn-js-properties-panel | https://github.com/bpmn-io/bpmn-js-properties-panel | 属性面板插件说明 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（bpmn-js 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：拖拽建模导出 BPMN XML |
| 《[SpiffWorkflow 技术介绍](../后端核心/SpiffWorkflow技术介绍.md)》 | 后端 BPMN 执行引擎，解析 bpmn-js 导出的 XML |
| 《[命名规范](../../../规范/命名规范.md)》 | 工作流表 wf_ 前缀、definition_key 命名 |
| 《[Vue 3 技术介绍](Vue3技术介绍.md)》 | bpmn-js 组件的宿主框架 |
| 《[Element Plus 技术介绍](ElementPlus技术介绍.md)》 | 建模页工具栏、属性表单等界面组件 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
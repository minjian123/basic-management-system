# SpiffWorkflow 技术介绍

> Python BPMN 2.0 工作流引擎 · BMS 审批流程

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › SpiffWorkflow 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**SpiffWorkflow** 是 Python 生态里最成熟的工作流引擎，核心能力是**解析并执行标准 BPMN 2.0 流程图**。
它用纯 Python 实现，让非开发者也能用图形化流程图描述审批等业务流程，
引擎负责解析 BPMN XML 并按图执行（用户任务、网关、结束事件等）。

- **定位**：BMS 审批流程引擎——解析前端 bpmn-js 导出的 BPMN XML，驱动审批流转。
- **版本**：3.x 系列（截至 2026 年最新 3.1.2 / 3.2.0），要求 Python 3.10+，本项目用 3.14+（有兼容性风险，见下）。
- **许可**：**LGPL-3.0**（GNU 宽通用公共许可证，弱 copyleft）。注意：任务清单与《项目规划说明》2.5 节曾标注为 MIT，经核实 GitHub 仓库与 PyPI 实际为 LGPL-3.0，两者法律含义不同，**建议复核并同步修正规划文档**。
- **依赖**：仅依赖 `lxml`（解析 XML），外部依赖极少。
- **作者/维护**：Sartography（原 Samuel Abels 创建并维护十余年）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| BPMN 2.0 | 业务流程建模标准（OMG 制定）：用图形化流程图描述审批等业务流程，是 SpiffWorkflow 的输入格式 |
| Workflow | 工作流对象：解析一段 BPMN XML 后得到的可执行流程实例 |
| Task（任务） | 流程中的一个执行节点，是流程推进的基本单位 |
| UserTask（用户任务） | 需要「人」来处理的节点，BMS 用它表示审批节点，等待审批人操作 |
| Gateway（网关） | 分支/汇合控制点：排他网关（二选一）、并行网关（同时走多路）、包含网关等 |
| StartEvent / EndEvent | 开始事件（流程入口）与结束事件（流程出口），标记流程的起止 |
| Process | 流程定义：一段 BPMN 里描述的一条完整业务路径 |
| Engine（执行引擎） | 驱动流程按 BPMN 规则推进的核心：解析节点、执行任务、走网关、到结束事件 |
| 序列化（Serialization） | 把流程实例当前状态序列化（存/取），BMS 用它把流程状态落库、跨请求恢复 |
| 脚本引擎 | 支持在流程节点里执行 Python 脚本，灵活但需注意沙箱安全 |
| 不持久化 | 引擎本身**不内置持久化**：流程实例、任务、审批记录的存储由 BMS 自建表维护 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

SpiffWorkflow 在 BMS 里是**审批流程的执行引擎**。
整体分工：前端 `bpmn-js` 负责拖拽绘制流程定义并导出 BPMN XML，
SpiffWorkflow 负责解析这段 XML 并按图执行审批流转。

- **解析执行 BPMN XML**：支持用户任务（审批节点）、网关（分支/并行）、结束事件等标准元素（见《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节）。
- **同步执行 + 线程池**：SpiffWorkflow 是**同步**库，在 FastAPI 异步栈中放入线程池运行（`run_in_executor`），避免阻塞事件循环（见《[FastAPI 技术介绍](FastAPI技术介绍.md)》）。
- **状态由 BMS 自建表维护**：引擎本身不持久化，流程实例、任务、审批记录由 BMS 自建表（如 `wf_process`、流程实例表、审批记录表）存储，经序列化/反序列化跨请求恢复（见《[项目规划说明](../../../规划/项目规划说明.html#tables)》6 节）。
- **流程建模闭环**：管理端用 bpmn-js 拖拽绘制 → 导出 BPMN XML → SpiffWorkflow 执行；流程定义发布新版本、实例启动、节点通过、驳回、结束等经事件总线发布（见《[项目规划说明](../../../规划/项目规划说明.html#integ-event)》9.3 节 `wf.*` 事件）。
- **审批提醒联动**：流程走到用户任务时触发审批提醒邮件（见《[aiosmtplib 技术介绍](aiosmtplib技术介绍.md)》）与待办实时推送（见《[python-socketio 技术介绍](python-socketio技术介绍.md)》）。

> Python 3.14 兼容性风险：SpiffWorkflow 对 Python 3.14 的适配情况待验证。
> 按《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节既定口径，
> 阶段一骨架阶段逐依赖验证，若 SpiffWorkflow 暂未适配 3.14，则整体回退 Python 3.13。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **SpiffWorkflow（选中）** | Python 生态最成熟 BPMN 引擎、纯 Python、依赖仅 lxml、支持 BPMN/DMN | 契合 BPMN 标准与 Python 栈，首选 |
| 自研工作流引擎 | 完全可控；但 BPMN 解析、网关、序列化都要自己造，成本高、易出错 | 成本高、BPMN 支持不全，无自研必要 |
| Java 系引擎（Flowable / Activiti） | BPMN 支持强、生态成熟；但**非 Python**，需跨语言集成或另起 JVM，架构复杂 | 与 Python 栈集成成本高，不契合 |
| 轻量状态机库 | 简单场景够用；但**不支持 BPMN 标准**，无法解析 bpmn-js 导出的 XML | 不满足 BPMN 标准与前端建模闭环需求 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **同步执行要放线程池**：SpiffWorkflow 是同步库，在 `async def` 接口中直接调用会阻塞事件循环，必须用 `run_in_executor` 丢进线程池。
- **引擎不持久化**：SpiffWorkflow 本身不存流程状态，流程实例/任务/审批记录必须由 BMS 自建表维护，靠序列化/反序列化跨请求恢复，别指望引擎自带存储。
- **Python 3.14 兼容性**：若引擎暂未适配 3.14，按既定口径整体回退 Python 3.13，阶段一验证。
- **依赖 lxml**：需安装 `lxml`（解析 XML），注意其在各平台的可用版本。
- **脚本引擎安全**：BPMN 节点里若执行 Python 脚本，需做沙箱限制，防止流程定义里夹带危险代码。
- **BPMN XML 要合规**：前端 bpmn-js 导出的 XML 须符合 BPMN 2.0 标准，非法 XML 会导致解析失败，发布前做校验。
- **许可证注意**：LGPL-3.0 是弱 copyleft，与 MIT 法律含义不同（动态链接场景下义务较轻，但需保留许可证声明），商用前建议法务确认，并修正规划文档中的许可证标注。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| SpiffWorkflow 官方文档 | https://spiffworkflow.readthedocs.io/ | 权威文档，含 BPMN 支持、核心库、序列化 |
| SpiffWorkflow GitHub | https://github.com/sartography/SpiffWorkflow | 源码、issue、release notes 与许可证 |
| PyPI 包页 | https://pypi.org/project/SpiffWorkflow/ | 版本、依赖与安装信息 |
| BPMN 2.0 规范（OMG） | https://www.omg.org/spec/BPMN/ | BPMN 标准规范，理解流程元素语义 |
| SpiffWorkflow 示例应用 | https://github.com/sartography/spiff-example-cli | 官方示例，快速上手流程定义与执行 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节 | 选型说明：SpiffWorkflow 条目与 Python 3.14 兼容口径 |
| 《[项目规划说明](../../../规划/项目规划说明.html#modules)》5 节 | 功能模块：审批（流程建模、流程实例、我的待办/已办） |
| 《[项目规划说明](../../../规划/项目规划说明.html#integ-event)》9.3 节 | 事件总线：`wf.*` 流程事件 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 异步栈背景，同步引擎放线程池运行 |
| 《[Python 技术介绍](Python技术介绍.md)》 | Python 3.14 版本与兼容性口径 |
| 《[aiosmtplib 技术介绍](aiosmtplib技术介绍.md)》 | 审批提醒邮件发送 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19
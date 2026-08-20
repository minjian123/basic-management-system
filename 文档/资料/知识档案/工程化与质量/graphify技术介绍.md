# graphify 技术介绍

> 代码知识图谱工具 · BMS 代码理解与架构分析

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [工程化与质量](../技术栈知识档案总览.md#eng) › graphify 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**graphify** 是一个开源的命令行工具：把任意目录下的代码、文档、论文、图片、视频
构建成一张持久化的**知识图谱**（节点是函数/类/概念，边是调用/导入/继承等关系），
之后用自然语言查询、追路径、解释概念，代替满仓库 grep。
代码解析走 tree-sitter AST，本地、确定性、免费；文档语义抽取可选用 LLM。

- **定位**：BMS 代码理解与架构分析辅助——AI 助手查代码库问题优先走图谱查询，人看架构走可视化图。
- **版本**：0.9.x 系列（迭代快；本项目锁定 0.9.42，Python ≥ 3.10）。
- **许可**：Apache-2.0 或 MIT（双许可）。
- **安装**：官方仓库 [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)；PyPI 包名 `graphifyy`（双 y，其他 `graphify*` 包均非官方），CLI 命令为 `graphify`。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 知识图谱（graph.json） | 核心产物：节点（函数、类、概念）+ 边（calls/imports/inherits 等关系）的 JSON 图，跨会话持久化在 `graphify-out/`，所有查询都基于它 |
| AST 层 | 代码用 tree-sitter 做静态解析：确定性、本地运行、无需 LLM 与 API Key，覆盖函数、类与跨文件调用关系（约 40 种语言） |
| 语义层 | 文档/论文/图片由 LLM 抽取概念、设计理由与跨文档关联；未配置 API 时可由 AI 助手会话代劳，结果带缓存 |
| 置信度标签 | 每条边标注 EXTRACTED（源码中明确存在）/ INFERRED（工具推断）/ AMBIGUOUS（存疑），一眼分清"读到的"和"猜的" |
| God Nodes（枢纽节点） | 连接数最多的节点排行：架构上"所有事都经过它"的核心，评审与重构时优先关注 |
| 社区（Community） | 用 Leiden 算法把图聚成子系统级社区并命名，相当于自动导出的模块地图 |
| query | 自然语言提问 → 返回范围受限的子图（BFS 广度或 DFS 深度），比全文 grep 输出小得多，支持中文问题自动分词 |
| path | 追两个概念之间的最短关联路径，回答"A 是怎么影响到 B 的" |
| explain | 用大白话解释某个节点及其邻居，快速建立对陌生模块的直觉 |
| affected | 反向遍历影响面："改了这个，谁会被波及"，重构前的风险评估 |
| 增量更新 | `graphify update` 依据 manifest 与缓存只重抽新增/变更文件；AST 层免费重抽，已有语义层保留 |
| 非向量索引 | 不做 embedding、不依赖向量库：是真实可遍历的图，查询走图结构而非相似度检索 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 知识图谱辅助**代码理解与架构分析**：AI 助手处理代码库问题时优先 `graphify query`，关系用 `graphify path`，概念用 `graphify explain`（见《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节"知识图谱：graphify"）。
- 图谱索引范围覆盖**代码与「文档」目录**：规划、规范、设计文档的语义层一并入图，文档与代码的关联可查（见《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节）。
- **中文查询分词**：安装 `chinese` 扩展（jieba），中文问题先分词再匹配节点，避免"两字滑动窗口"的降级效果（安装命令见下）。
- **日常维护纪律**：修改代码或文档后运行 `graphify update .` 保持图谱最新（纯 AST，无 API 开销），再跑 `python deploy/tools/graphify/localize-graph.py` 收尾（汉化 graph.html + 生成中文架构图 CALLFLOW.html）。
- **AI 能力输入源**：帮助文档智能维护以功能代码的 graphify 知识图谱为输入之一（见《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节 AI 能力、《[LLM 适配层技术介绍](../后端核心/LLM适配层技术介绍.md)》）。
- 安装与排障细节以《[graphify 部署使用说明](?../../AI/graphify部署使用说明.md》为准（本机 Windows 环境实测）。

常用命令（Windows PowerShell 与 Linux 通用）：

```bash
# 安装（extras 必须一次列全，否则互相顶掉）
uv tool install "graphifyy[chinese,openai]" --force

# 查询 / 路径 / 概念
graphify query "认证流程如何处理 token 刷新？"
graphify path "事件总线" "工作流"
graphify explain "多租户路由"

# 代码变更后增量更新
graphify update .
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **graphify（选中）** | 本地 AST 解析免费离线；结构关系（调用/导入）+ 语义概念兼备；query/path/explain 面向理解而非检索；中文分词支持<br>缺点：项目较新，语义层依赖 LLM 质量 | 与"AI 助手 + 人"双消费方契合，零服务端依赖 |
| RAG / 向量库（Milvus 等） | 语义检索成熟<br>缺点：只有相似度没有结构关系，答不了"A 怎么调到 B"；需向量库与 embedding 管线，BMS 的 Milvus 用于业务语义搜索，不兼作代码索引 | 不用于代码理解场景 |
| grep / IDE 全文搜索 | 零成本、精确匹配<br>缺点：无概念层与跨文件语义，大库下输出爆炸，AI 助手上下文浪费 | 保留作兜底，不作首选 |
| Sourcegraph / CodeSee 等商业代码智能平台 | 索引能力强<br>缺点：商业授权或需自建服务端，与内网单机工具链不匹配 | 不引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **extras 互顶**：`uv tool install` 后装只带部分 extras 会顶掉之前的（如只装 `[chinese]` 后语义抽取报缺 `openai` 包），升级/加装必须一次列全并加 `--force`。
- **语义层不可再生**：`graphify update` 保留语义层；彻底删除 `graphify-out/` 重建会永久丢失语义节点（本项目实测 951 → 139），恢复只能重跑语义抽取或从备份恢复——重建前先整体备份。
- **节点数防缩保护**：update 后节点变少时默认拒绝覆盖；确认是删了代码才加 `--force`。
- **第三方库刷屏**：压缩 JS/CSS 的函数名会灌进图，用项目根目录 `.graphifyignore`（语法同 .gitignore）排除后 `update --force` 修剪。
- **graph.html 固定英文界面**：可视化模板不可配置，跑 `deploy/tools/graphify/localize-graph.py` 汉化并生成 CALLFLOW.html 架构图。
- **API Key 边界**：纯代码目录完全免费离线；只有文档/图片语义抽取需要 LLM（Gemini Key 或 AI 助手会话），不要把 Key 写进脚本。
- **包名是双 y**：`uvx graphify` 会失败（按包名解析），正确写法 `uvx --from graphifyy graphify ...`；PyPI 上其他 `graphify*` 包均非官方。
- **graphify-out/ 变脏属正常**：钩子或增量更新后文件有改动是常态，不要因此跳过图谱查询；仅当图输出确认过期或错误时才考虑重建。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| graphify 官方仓库 | https://github.com/Graphify-Labs/graphify | 源码、issue 与安装说明 |
| PyPI 包页（graphifyy） | https://pypi.org/project/graphifyy/ | 官方包（双 y）、版本与依赖信息 |
| graphify 官网 | https://graphify.com/ | 官方文档与特性介绍 |
| tree-sitter | https://tree-sitter.org/ | AST 解析引擎，理解 AST 层原理 |
| Leiden 算法论文 | https://arxiv.org/abs/1810.08473 | 社区检测（社区划分）所用算法原文 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节 | 工程化与质量技术栈（知识图谱：graphify 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节 | 选型说明：知识图谱辅助代码理解与架构分析 |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节 | AI 能力：帮助文档智能维护以 graphify 知识图谱为输入源 |
| 《[graphify 部署使用说明](?../../AI/graphify部署使用说明.md》 | 本机安装、首次构建、日常使用与维护的完整实录（首选阅读） |
| 《[uv 技术介绍](uv技术介绍.md)》 | `uv tool install` 安装方式与 extras 互顶问题 |
| 《[LLM 适配层技术介绍](../后端核心/LLM适配层技术介绍.md)》 | 知识图谱作为 AI 能力的输入源 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
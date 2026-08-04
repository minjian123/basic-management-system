# AGENTS.md

**注意**：用户是中国人，英文看不懂，尽量使用中文。

## 项目现状

- BMS（基础管理系统）：后端管理用途。当前**尚无源代码**，处于规划阶段；技术栈方向（FastAPI + SQLAlchemy + Redis + JWT / Vue 3 + Vite）见 `文档/规划/项目规划说明.md`，动手写代码前先读该文件。
- 文档目录使用中文名（`文档/`），README 与规划文档均为中文；回复与文档保持中文。
- `.opencode/`（opencode.json、plugins/graphify.js 等）由 graphify 安装脚本生成，勿手动修改。

## graphify

本项目通过知识图谱（graphify-out/）辅助代码理解与架构分析，已启用中文查询分词。

当用户输入 `/graphify` 时，先使用已安装的 graphify skill（`.opencode/skills/graphify/SKILL.md`）或下述规则，再做其他事。

规则：
- 代码库相关问题，当 graphify-out/graph.json 存在时，先运行 `graphify query "<问题>"`（可直接用中文）。关系用 `graphify path "<A>" "<B>"`，概念用 `graphify explain "<概念>"`。返回的是范围受限的子图，通常比 GRAPH_REPORT.md 或原始 grep 输出小得多。
- 钩子或增量更新后 graphify-out/ 文件变脏属正常现象，不应因此跳过 graphify。只有任务涉及过期或错误的图输出、或用户明确不用时，才跳过。
- 若 graphify-out/wiki/index.md 存在，用它做广域导航，避免直接浏览源码。
- 仅在需要宏观架构审查、或 query/path/explain 信息不足时，才读 graphify-out/GRAPH_REPORT.md。
- 修改代码后运行 `graphify update .` 保持图谱最新（纯 AST，无 API 开销）。

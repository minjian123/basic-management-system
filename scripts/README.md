# scripts — 开发期工具链

本目录存放**开发期工具链**（自 `deploy/tools/` 迁入）。以 Python 标准库或 uv 管理依赖为主，Windows / Linux 均可用。

## 工具链清单

| 工具 | 用途 |
| --- | --- |
| `wol/` | WOL 电源控制（远程唤醒 / 关机 mjbk） |
| `bg/` | 后台执行器（长命令后台化 + 秒级轮询状态） |
| `graphify/` | 知识图谱（`localize-graph.py` 汉化 + 生成架构图） |
| `zentao/` | 禅道 API 工具包（CLI + ZentaoClient，文档 ↔ 禅道同步） |
| `defect/` | 缺陷工具链（REPRO 复现包自动上报 / AI 修复 / 一键复现） |
| `multimodal/` | 多模态 MCP（识图 / 无头截图） |
| `backup/` | 开发服务器备份脚本（版本管理源） |
| `gitlab/` | GitLab 流水线盯守（`watch_pipeline.py`） |
| `reorder-design/` | 设计文档节点编号重排 |

## 职责边界

- `scripts/` 只放开发期工具链，**不放**产品运维脚本（见 `ops/`），**不放**部署产物（见 `deploy/`）。
- 凭据统一存 `deploy/.env`（不入库），各工具自动读取，不硬编码密码。

> 各工具的详细用法见其自带 `README.md` 或 docstring，以及 `文档/` 下对应的使用说明。

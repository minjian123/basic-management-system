# basic-management-system

基础管理系统，主要用作后端管理，简称BMS。

支持分布式、集群部署；多租户 SaaS 架构（租户独立库），支持 SSO 单点登录，内置报表 BI 与移动端 H5。后端基于 FastAPI + SQLAlchemy，前端基于 Vue 3 + Vite（PC 管理端 + 移动端 H5 双工程）。

## 当前状态

阶段一（项目骨架）已完成并通过验收，详见 [阶段一_实施记录](文档/项目/阶段一/阶段一_实施记录.html) 与 [阶段一_验收报告](文档/项目/阶段一/阶段一_验收报告.html)。下一步：阶段二（认证与安全）。

## 快速开始

完整步骤见 [阶段一_启动指南](文档/项目/阶段一/阶段一_启动指南.html)，本地环境要求：uv（Python 3.14 自动管理）、Node ≥ 20.19、pnpm。

```powershell
# 后端
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
# 验证：http://localhost:8000/healthz、/readyz（需 Redis，可用 docker compose -f deploy/compose.yml up -d）
```

```bash
# 前端
pnpm install
pnpm --filter frontend dev
pnpm --filter frontend-mobile dev
```

## 目录结构

```
bms/
├── backend/          # FastAPI 后端（uv 管理，Python 3.14）
│   ├── app/          # core/db/models/schemas/api/services/repositories/migrations
│   ├── alembic_*.ini # 平台库/租户库双套迁移环境
│   ├── scripts/      # 运维脚本（如 migrate_tenants.py 批量迁移租户库）
│   └── tests/        # unit + integration
├── frontend/         # Vue 3 + Vite（PC 管理端）
├── frontend-mobile/  # Vue 3 + Vant（移动端 H5）
├── pnpm-workspace.yaml
├── deploy/           # Docker Compose（Redis 等依赖服务）
├── scripts/          # 顶层运维脚本（阶段三起补充）
├── .github/workflows/ci.yml
├── 文档/             # 规划、规范、项目阶段文档
└── graphify-out/     # 知识图谱输出
```

## 文档导航

- [项目规划说明](文档/规划/项目规划说明.md)：技术栈、功能模块、数据表、权限模型、开发计划与验收标准
- [阶段一_项目骨架说明](文档/项目/阶段一/阶段一_项目骨架说明.html)：阶段一设计与实施依据
- [阶段一_实施记录](文档/项目/阶段一/阶段一_实施记录.html)：实施过程与现状
- [阶段一_验收报告](文档/项目/阶段一/阶段一_验收报告.html)：完成标准逐项验收结论
- 规范：[文档生成规范](文档/规范/文档生成规范.html)、[命名规范](文档/规范/命名规范.html)、[后端开发规范](文档/规范/后端开发规范.html)、[前端开发规范](文档/规范/前端开发规范.html)

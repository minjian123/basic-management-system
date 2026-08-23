# monorepo 仓库根骨架详细设计

> BMS · 阶段一 / 01-1 任务 · 任务级详细设计（可落地、可逐项验收）

[文档首页](../../../../../文档首页.md) › [01-1 任务文档](../01_工程骨架_01-1_monorepo仓库骨架.md) › 01-1 详细设计　|　[← 01 工程骨架](../../01_工程骨架.md)

## 1. 概述 <a id="overview"></a>

本文档是任务 [01-1 monorepo 仓库根骨架](../01_工程骨架_01-1_monorepo仓库骨架.md) 的**详细设计**，粒度到「按序落地、逐条验收」，是任务级执行设计，位于 `文档/设计/` 全局粗设计之下一级。两者不一致时，以本文档为 01-1 的执行依据；所有不一致点已逐项对齐并记录于 [第 9 节](#align)。

上游依据（可追溯）：

- 《[项目规划说明](../../../../../规划/项目规划说明.md)》§2 技术选型、§4 项目目录结构（权威目录基线）
- 《[架构设计 · 总体架构](../../../../../设计/架构设计/03_架构设计_总体架构.md)》§5 monorepo 布局、§6 技术栈
- 《[架构设计 · 前端架构](../../../../../设计/架构设计/28_架构设计_前端架构.md)》双工程结构
- 《[后端开发规范](../../../../../规范/后端开发规范.md)》§2 目录分层、《[前端开发规范](../../../../../规范/前端开发规范.md)》§2 目录约定
- 《[命名规范](../../../../../规范/命名规范.md)》§3 项目与目录命名

与后续任务的关系：01-1 只交付「仓库根骨架 + 三工程最小可启动占位」；三工程的完整骨架与分层在 01-2（backend 工程初始化）、01-3（backend 分层）、01-4（frontend 工程初始化）、01-5（frontend-mobile 工程初始化）细化，01-6 做依赖锁定与 Python 3.14 兼容性验证。职责边界见 [7.4 节](#boundary)。

## 2. 现状与差距 <a id="gap"></a>

落地前已核实的仓库现状（`git status` 干净、`git ls-files node_modules` 为 0、`scripts/` 为空目录）与差距清单：

| 项 | 现状 | 01-1 目标 | 动作 |
| --- | --- | --- | --- |
| `backend/` | 缺失 | 最小可启动占位（FastAPI + `/healthz`） | 新建 |
| `frontend/` | 缺失 | 最小 Vite + Vue + TS 占位（端口 5173） | 新建 |
| `frontend-mobile/` | 缺失 | 最小 Vite + Vue + TS 占位（端口 5174） | 新建 |
| `scripts/` | 空目录（未入库） | 补目录说明 `README.md` | 新增文件 |
| `.github/` | 缺失 | 补 GitHub 归档说明 `README.md` | 新建 |
| `graphify-out/README.md` | 缺失（`graphify-out/` 整目录被忽略） | 提交 `README.md`，产物忽略 | 新增 + 调 .gitignore |
| `README.md` | 缺「快速启动」章节、无技术栈概览表；Python 徽标为 3.12+；文档目录树漏 `测试/`、`项目/` | 按四章节重写 | 重写 |
| `.gitignore` | 无 Node 规则；编辑器规则为注释态；无 `*.local` | 补 Node / 编辑器 / `*.local`；调整 graphify-out | 修改 |
| `.editorconfig` | 缺失 | 新建 | 新建 |
| `.gitlab-ci.yml` | 存在（内容非 01-1 范围） | 保留 | — |
| `deploy/`、`文档/` | 存在 | 保留 | — |
| `LICENSE`、`AGENTS.md`、`.graphifyignore`、`renovate.json` | 存在 | 保留 | — |

> **已知 git 现象**：`git status` 干净，但告警 `could not open directory 'node_modules/.pnpm/node_modules/frontend/'`。根因为根目录 `node_modules/`（`.opencode` 的 pnpm store）残留的陈旧 untracked 缓存条目，该目录实际未被跟踪（`git ls-files node_modules` 为 0）。处理：本任务加入 `node_modules/` 忽略规则后重跑 `git status` 验证告警消失；若仍在，执行 `git update-index --again` 清理索引缓存。

## 3. 目标目录树与交付物清单 <a id="tree"></a>

01-1 落地后的仓库顶层结构（即根 README「目录结构」章节内容）：

```text
bms/
├── README.md                 # 本仓库说明（简介 / 快速启动 / 目录结构 / 文档导航）
├── LICENSE                   # MIT 许可
├── AGENTS.md                 # AI 协作约定
├── .gitignore                # Python / Node / 环境与凭据 / 编辑器 / 图谱产物
├── .editorconfig             # 编辑器统一配置（UTF-8 / LF / 缩进）
├── .gitlab-ci.yml            # CI 流水线定义（GitLab CE，内容非 01-1 范围）
├── .graphifyignore           # graphify 索引排除规则
├── renovate.json             # Renovate 依赖升级配置
├── backend/                  # FastAPI 后端（01-1 最小占位，01-2 / 01-3 细化）
│   ├── .python-version       # 固定 Python 版本（3.14）
│   ├── pyproject.toml        # uv 项目声明
│   ├── uv.lock               # 依赖锁定（必须提交）
│   ├── README.md             # 四章节简化版
│   └── app/                  # 应用包（core / api / … / i18n，01-2 / 01-3 细化）
│       ├── __init__.py
│       └── main.py           # FastAPI 最小应用 + /healthz
├── frontend/                 # Vue 3 + Vite（01-1 最小占位，01-4 细化）
│   ├── .nvmrc                # 固定 Node 版本（22）
│   ├── package.json
│   ├── package-lock.json     # 依赖锁定（必须提交）
│   ├── vite.config.ts        # 固定开发端口 5173
│   ├── tsconfig.json
│   ├── index.html
│   ├── README.md             # 四章节简化版
│   └── src/
│       ├── main.ts
│       ├── App.vue           # 占位页面
│       └── vite-env.d.ts
├── frontend-mobile/          # Vue 3 + Vant 移动端 H5（01-1 最小占位，01-5 细化）
│   └── …                     # 结构同 frontend，端口固定 5174
├── deploy/                   # 部署配置与工具链
│   ├── .env.example          # 凭据模板
│   ├── compose/              # Docker Compose（base / gitlab / kiwi）
│   ├── setup/                # 环境安装脚本
│   └── tools/                # backup / bg / defect / graphify / multimodal / reorder-design / wol / zentao
├── scripts/                  # 运维脚本（种子数据、备份恢复等，按阶段补充）
│   └── README.md             # 目录说明
├── .github/                  # GitHub 归档镜像辅助文件
│   └── README.md             # GitHub 只读归档说明
├── 文档/                     # 项目文档
│   ├── 文档首页.md            # 全量导航
│   ├── 规划/
│   ├── 规范/
│   ├── 设计/
│   ├── 项目/                 # 需求 / 计划 / 任务（00_准备期、01_项目骨架 …）
│   ├── 测试/
│   ├── 资料/
│   ├── 用户文档/              # 本地资源（已 gitignore）
│   └── 资源/
├── graphify-out/             # 知识图谱产物（产物 gitignore，仅 README.md 入库）
│   └── README.md             # 目录说明
└── temp/                     # 本地临时目录（gitignore）
```

交付物清单（01-1 新建 / 修改的文件）：

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `backend/`（6 个文件，见 7.1） | 新建 | 最小可启动占位 |
| `frontend/`（10 个文件，见 7.2） | 新建 | 最小 Vite 占位 |
| `frontend-mobile/`（10 个文件，见 7.3） | 新建 | 最小 Vite 占位 |
| `scripts/README.md` | 新建 | 目录说明 |
| `.github/README.md` | 新建 | GitHub 归档说明 |
| `graphify-out/README.md` | 新建 | 图谱产物目录说明 |
| `README.md` | 重写 | 四章节 |
| `.gitignore` | 修改 | 补 Node / 编辑器 / `*.local`，调整 graphify-out |
| `.editorconfig` | 新建 | 编辑器统一配置 |

## 4. 根 README 设计 <a id="readme"></a>

四章节结构，替换现有「简介 / 文档 / 目录结构 / 使用指南」四段：

| 章节 | 内容要求 |
| --- | --- |
| 1. 项目简介 | 顶部徽标行（修正后，见下）+ 一段简介（沿用现有两段）+ **技术栈概览表**（新增，取自《项目规划说明》§2） |
| 2. 快速启动 | 前置条件（Python 3.14 + uv、Node 22）+ 三工程启动命令块 + 预期结果（端口与访问地址） |
| 3. 目录结构 | [第 3 节](#tree) 的目标目录清单 |
| 4. 文档导航 | 合并现有「文档」段说明 + 「使用指南」表（全部行保留，指向 `文档/` 各入口） |

**徽标修正**：`Python 3.12+` → `Python 3.14+`；新增 `Node 22` 徽标；其余徽标（FastAPI / SQLAlchemy / Vue / Vite / TypeScript / Element Plus / Vant / Redis / MySQL / PostgreSQL / Docker / GitLab / MIT）保留。

**技术栈概览表**（新增，置于简介段之后）：

| 层面 | 技术 |
| --- | --- |
| 后端 | Python 3.14+ · FastAPI · uvicorn · Pydantic v2 · SQLAlchemy 2.0+（异步）· Alembic · Celery · SpiffWorkflow |
| 数据库 / 中间件 | SQLite（开发/测试）· MySQL 8.x · PostgreSQL 16+ · 达梦 DM8（信创选配）· Redis · RocketMQ 5.x · ElasticSearch 8.x · MinIO |
| 前端 | Vue 3.5+ · Vite 7 · TypeScript · Element Plus（PC）/ Vant 4（移动端 H5）· Pinia |
| 工程与质量 | uv（Python 依赖）· npm（前端依赖）· GitLab CI · Renovate · pytest / Vitest / Playwright · structlog |
| 部署与运维 | Docker 27+ · Docker Compose 2.33+ · nginx · GitLab CE 18+ · Prometheus / Grafana / Jaeger（监控与链路） |

**快速启动**（三工程命令，均可复制执行）：

```powershell
# 前置：Python 3.14（uv 管理）、Node 22（nvm 管理）

# 后端（端口 8000）
cd backend
uv sync
uv run uvicorn app.main:app --port 8000
# 验证：访问 http://127.0.0.1:8000/healthz 返回 {"status":"ok"}

# PC 前端（端口 5173）
cd frontend
npm ci
npm run dev
# 验证：访问 http://127.0.0.1:5173 看到占位页

# 移动端（端口 5174）
cd frontend-mobile
npm ci
npm run dev
# 验证：访问 http://127.0.0.1:5174 看到占位页
```

> 凭据统一存 `deploy/.env`（已 gitignore，模板见 `deploy/.env.example`）——沿用现有说明，置于「目录结构」章节末尾。

## 5. .gitignore 最终规则 <a id="gitignore"></a>

保留现有 Python 模板主体不动，做以下**追加与替换**（不删除既有规则）：

**追加**（Node 与本地覆盖）：

```gitignore
# Node
node_modules/

# 本地覆盖文件（如 .env.local、*.local）
*.local
```

**替换**——把现有注释态的 `# .idea/`（189 行）与 `# .vscode/`（202 行）改为生效规则：

```gitignore
# JetBrains
.idea/

# VS Code（放行可共享的 settings.json / extensions.json）
.vscode/*
!.vscode/settings.json
!.vscode/extensions.json
```

**替换**——把现有 `graphify-out/`（226 行）改为「产物忽略、保留说明文件」：

```gitignore
# graphify 运行产物（图谱可随时重建，含本机绝对路径，不入库；保留目录说明文件）
graphify-out/*
!graphify-out/README.md
```

**锁定文件口径**：`uv.lock`、`package-lock.json` 在 .gitignore 中**不出现**（现有 `# uv.lock` 保持注释态即可），即两者必须提交。

落地后 `git check-ignore -v` 抽查（预期结果）：

| 路径 | 预期 |
| --- | --- |
| `node_modules/foo` | 被忽略 |
| `.venv/x` | 被忽略 |
| `.env` | 被忽略 |
| `.idea/x.xml` | 被忽略 |
| `.vscode/settings.json` | **不**被忽略 |
| `.vscode/extensions.json` | **不**被忽略 |
| `.vscode/xxx.code-workspace` | 被忽略 |
| `backend/.env.local` | 被忽略（`*.local`） |
| `graphify-out/graph.json` | 被忽略 |
| `graphify-out/README.md` | **不**被忽略 |
| `backend/uv.lock` | **不**被忽略 |
| `frontend/package-lock.json` | **不**被忽略 |
| `文档/用户文档/本地资源.md` | 被忽略 |

## 6. .editorconfig <a id="editorconfig"></a>

新建，全文如下：

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4

[*.{ts,tsx,js,jsx,json,vue,scss,css,html,yml,yaml,toml,ini}]
indent_style = space
indent_size = 2

[Makefile]
indent_style = tab

[*.md]
trim_trailing_whitespace = false
```

覆盖任务要求：UTF-8、LF、尾行空格去除、末尾空行；Python 4 空格、TS/JS/JSON 2 空格缩进。

## 7. 三工程占位工程设计 <a id="projects"></a>

### 7.1 backend <a id="backend"></a>

文件清单与内容：

- `.python-version`：`3.14`
- `pyproject.toml`：

```toml
[project]
name = "bms-backend"
version = "0.1.0"
description = "BMS 后端服务（阶段一占位，01-2 / 01-3 细化）"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]
```

- `uv.lock`：执行 `uv lock` 生成并提交（依赖 `fastapi`、`uvicorn`）
- `app/__init__.py`：

```python
"""BMS 后端应用包（阶段一占位，01-2 / 01-3 细化）。"""
```

- `app/main.py`：

```python
"""BMS 后端占位入口：最小 FastAPI 应用，提供 /healthz 存活检查。"""

from fastapi import FastAPI

app = FastAPI(title="BMS 后端", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """存活检查端点。

    Returns:
        dict: 服务状态，固定返回 {"status": "ok"}。
    """
    return {"status": "ok"}
```

- `README.md`：四章节简化版（见 7.5）
- 启动验证：`uv sync` → `uv run uvicorn app.main:app --port 8000` → `GET /healthz` 返回 `{"status":"ok"}`

### 7.2 frontend <a id="frontend"></a>

以 `npm create vite@latest frontend -- --template vue-ts` 生成的 Vite + Vue + TS 工程为基，做以下调整（版本号以模板为准，记录在 `package-lock.json`，不在此硬编码）：

- `package.json`：`name` 字段改为 `bms-frontend`，`version` 为 `0.1.0`，保留 `dev` / `build` / `preview` 脚本与 `vue` 依赖、`vite` / `@vitejs/plugin-vue` / `typescript` / `vue-tsc` 开发依赖
- `vite.config.ts`：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// BMS PC 管理端占位：固定开发端口，避免与 frontend-mobile 冲突
export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, strictPort: true },
})
```

- `index.html`：标题 `BMS PC 管理端`，保留 `<div id="app">` 与 `<script type="module" src="/src/main.ts">`
- `src/main.ts`：

```ts
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
```

- `src/App.vue`：

```vue
<script setup lang="ts">
// BMS PC 管理端占位（01-4 细化为完整工程）
</script>

<template>
  <main>
    <h1>BMS PC 管理端占位</h1>
    <p>阶段一 · 01-1 最小可运行占位，01-4 细化为完整工程。</p>
  </main>
</template>
```

- `src/vite-env.d.ts`、`tsconfig.json`：沿用模板
- `.nvmrc`：`22`
- `package-lock.json`：`npm install` 生成并提交
- `README.md`：四章节简化版（见 7.5）
- 启动验证：`npm ci` → `npm run dev` → 访问 `http://127.0.0.1:5173` 看到占位页

### 7.3 frontend-mobile <a id="mobile"></a>

文件结构与 7.2 完全一致，仅以下差异：

- 目录名 `frontend-mobile/`，`package.json` 的 `name` 为 `bms-frontend-mobile`
- `vite.config.ts` 的 `server.port` 为 `5174`
- `index.html` 标题、`App.vue` 文案改为「BMS 移动端 H5 占位」
- 组件库（Vant）与完整骨架由 01-5 引入，01-1 不引入

### 7.4 职责边界（01-1 vs 01-2 ~ 01-6）<a id="boundary"></a>

| 事项 | 归属 | 说明 |
| --- | --- | --- |
| 仓库根骨架、三工程目录、根 README / .gitignore / .editorconfig、最小可启动占位 | **01-1（本文档）** | 本任务交付 |
| backend 完整分层（app 下 core/api/models/schemas/services/repositories/db/tasks/ws/i18n）、config.toml、alembic、tests | 01-2 / 01-3 | 在 01-1 占位之上细化 |
| frontend 完整工程（Element Plus、Router、Pinia、ESLint / Prettier、SCSS、i18n） | 01-4 | 在 01-1 占位之上细化 |
| frontend-mobile 完整工程（Vant、移动端骨架） | 01-5 | 在 01-1 占位之上细化 |
| 依赖锁定复核、Python 3.14 兼容性逐依赖验证（不兼容整体回退 3.13） | 01-6 | 复核 01-1 生成的 lock 与 `.python-version` |
| CI 流水线内容 | 后续任务 | 01-1 仅保留既有 `.gitlab-ci.yml`，不改内容 |

> 原则：01-1 只做「能启动的最小占位」，不引入任何业务依赖与完整分层；占位文件均可被 01-2 ~ 01-5 直接扩展，不返工。

### 7.5 三工程 README（简化四章节）<a id="proj-readme"></a>

`backend/README.md`、`frontend/README.md`、`frontend-mobile/README.md` 统一四章节简化结构：

| 章节 | 内容 |
| --- | --- |
| 项目简介 | 1~2 句定位 + 技术栈一行（取自对应规范） |
| 快速启动 | 前置条件 + 该工程启动命令 + 预期结果（端口 / 访问地址） |
| 目录结构 | 该工程文件清单（等宽目录清单） |
| 文档导航 | 链接根 README 与对应规范（backend → 《后端开发规范》；frontend → 《前端开发规范》+《架构设计 · 前端架构》；frontend-mobile → 《架构设计 · 前端架构》移动端节） |

## 8. 其他新增文件 <a id="others"></a>

| 文件 | 内容要点 |
| --- | --- |
| `scripts/README.md` | 目录用途：种子数据、备份恢复等运维脚本，按阶段补充；01-1 仅保留目录说明，脚本在后续任务添加 |
| `.github/README.md` | GitHub 为只读归档镜像（GitLab CE 为主仓库，push mirror 单向同步 main；GitHub 侧不承载协作；Renovate 全本地运行，零 GitHub 依赖） |
| `graphify-out/README.md` | 知识图谱产物目录（graph.json / graph.html / wiki / GRAPH_REPORT.md 等），可由 graphify 随时重建；因含本机绝对路径，产物不入库（见《graphify 部署使用说明》），本目录仅保留此说明文件 |

## 9. 与全局设计的对齐记录 <a id="align"></a>

01-1 与 `文档/设计/` 全局设计对照后，发现 6 处矛盾 / 缺口，已逐项确认并定稿：

| # | 事项 | 定稿口径 | 落点 |
| --- | --- | --- | --- |
| 1 | Python 版本 | **钉 3.14**（01-6 逐依赖验证，不兼容整体回退 3.13，既定口径） | `backend/.python-version`=3.14、根 README 徽标 3.12+→3.14+ |
| 2 | graphify-out 入库策略 | **产物忽略 + 提交 README.md**（含本机绝对路径，不入库） | `.gitignore` 改 `graphify-out/*` + `!graphify-out/README.md`；新增 `graphify-out/README.md` |
| 3 | 占位工程范围 | **最小可启动**（非完整骨架），完整骨架归 01-2 ~ 01-5 | 本文档 §7；无空目录、无 `.gitkeep` |
| 4 | 编辑器忽略规则 | `.idea/` 全忽略；`.vscode/*` 忽略但放行 `settings.json` / `extensions.json` | `.gitignore`（§5） |
| 5 | Node 版本 | **Node 22 LTS** | `frontend/.nvmrc`、`frontend-mobile/.nvmrc`、根 README 技术栈表 / 徽标 |
| 6 | 三库 / 双库口径 | **统一三库**（MySQL / PostgreSQL / 达梦 DM8），对齐 03_总体架构与测试规范 §7 | 全库订正「双库」旧表述：《后端开发规范》§2、§10，《项目规划说明》§3.4，知识档案 3 处（GitLab / pytest 技术介绍）；概要设计07「双库引用」为平台库/租户库概念，非方言口径，不改 |

> 第 6 项为跨文档口径订正，不属于 01-1 仓库改动，单独执行并核对。

## 10. 实施步骤 <a id="steps"></a>

按序执行，每步附验证点（依赖：无）：

1. **backend 占位**：建 `backend/`，写 `.python-version`、`pyproject.toml`、`app/__init__.py`、`app/main.py`、`README.md` → `uv lock`（网络慢切国内 PyPI 镜像）→ `uv sync` → `uv run uvicorn app.main:app --port 8000`。验证：`GET http://127.0.0.1:8000/healthz` 返回 `{"status":"ok"}`。
2. **frontend 占位**：`npm create vite@latest frontend -- --template vue-ts`，按 7.2 调整（name、端口 5173、`.nvmrc`=22、`App.vue` 文案、`README.md`）→ `npm install` 生成 lock。验证：`npm run dev` 访问 `http://127.0.0.1:5173` 看到占位页。
3. **frontend-mobile 占位**：同步骤 2，端口 5174、name `bms-frontend-mobile`、文案改移动端。验证：访问 `http://127.0.0.1:5174`。
4. **其余说明文件**：建 `scripts/README.md`、`.github/README.md`、`graphify-out/README.md`（内容见 §8）。
5. **根 .gitignore**：按 §5 追加 / 替换规则；保留现有 Python 模板主体。
6. **根 .editorconfig**：按 §6 新建。
7. **根 README**：按 §4 重写四章节、修正徽标、补技术栈概览表、补全目录树（含 `测试/`、`项目/`）。
8. **整体验证**：
   - `git status` 干净、无 `.venv` / `node_modules` / `.env` 等应忽略产物出现（验证 §2 已知告警消失）；
   - `git check-ignore -v` 按 §5 抽查表逐项核对；
   - 模拟 fresh clone（`git clone` 到临时目录）后按根 README「快速启动」逐条执行三工程启动，确认照做可通；
   - 目录结构与《项目规划说明》§4 逐项一致。
9. **提交**：经用户明确指令后再 `git commit`（遵循 AGENTS.md 提交纪律）。

## 11. 验收映射 <a id="accept-map"></a>

01-1 任务文档「完成标准」逐条映射到本设计与验证方法：

| 完成标准 | 设计落点 | 验证方法 |
| --- | --- | --- |
| `git clone` 后目录结构与《项目规划说明》§4 逐项一致 | §3 目标目录树 | 对照《项目规划说明》§4 目录清单逐项核对 + fresh clone |
| 三工程最小占位均可启动 | §7.1 / 7.2 / 7.3 | 三工程分别启动并访问占位页 / `/healthz` |
| README 快速启动命令照做可通 | §4 快速启动 | fresh clone 后逐条执行 §10 步骤 8 的启动验证 |
| `git status` 不出现应忽略产物（.venv、node_modules、.env） | §5 .gitignore | `git status` + `git check-ignore -v` 抽查表 |

## 12. 风险与开放项 <a id="risk"></a>

| 风险 / 开放项 | 说明 | 处置 |
| --- | --- | --- |
| Python 3.14 兼容性未知（dmPython / Celery / SpiffWorkflow 等） | 01-1 占位仅用 fastapi / uvicorn，风险低 | 01-6 逐依赖验证，不兼容整体回退 3.13（`.python-version` 与 README 徽标同步改） |
| `uv` / `npm` 下载慢 | 国内网络 | 切换国内镜像（PyPI 用阿里云 / 清华源，npm 用淘宝 npmmirror 源），命令注明 |
| Vite / 依赖版本漂移 | 占位版本随模板 | 以 `package-lock.json` / `uv.lock` 锁定，提交后复现 |
| 根 `node_modules` 陈旧索引告警 | 见 §2 已知现象 | 加 `node_modules/` 忽略规则后验证，仍在则 `git update-index --again` |
| 三库口径跨文档旧表述 | 已全库订正并复核 | 订正《后端开发规范》§2、§10，《项目规划说明》§3.4，知识档案 3 处；复核 grep 仅剩概要设计07「双库引用」（平台库/租户库概念，非方言口径，不改） |

> 本文档依《文档生成规范》编写 · 生成日期：2026-08-23 · 对齐全局设计：2026-08-23

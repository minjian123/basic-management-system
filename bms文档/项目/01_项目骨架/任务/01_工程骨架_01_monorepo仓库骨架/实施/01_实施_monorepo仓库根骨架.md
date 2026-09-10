# 01 monorepo 仓库根骨架实施记录

> 项目骨架 · 01 工程骨架 · 子任务 01 · 实施记录（实做内容、问题与处置、验证与遗留）

[文档首页](../../../../../文档首页.md) › [01 任务文档](../01_工程骨架_01_monorepo仓库骨架.md) › 01 实施记录　|　[← 01 工程骨架](../../01_工程骨架.md)　[详细设计 →](../设计/01_详细设计_monorepo仓库根骨架.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 monorepo 仓库根骨架](../01_工程骨架_01_monorepo仓库骨架.md) |
| 对应需求 | [01-1](../../../需求/01_需求_工程骨架.md#r01-1)（三工程占位为 01-2 ~ 01-6 的前置） |
| 详细设计 | [01 详细设计](../设计/01_详细设计_monorepo仓库根骨架.md) |
| 实施日期 | 2026-09-10 |
| 实施人 | minjian |
| 实施环境 | 开发机（Ubuntu）；Python 3.14.4（uv 0.12.7）；Node 22.23.2（nvm 管理）；npm 11.19.0；依赖镜像：阿里云 PyPI、淘宝 npmmirror |
| 提交 | `e470985`（设计定案修正）、`2390527`（三工程占位与根文件）、`1dfeaf8`（实施记录与规范口径）；已于 2026-09-10 推送远端 |
| 结论 | 三工程最小占位与根文件完成；本地与 fresh clone 全流程验证全部通过，提交已推送远端 |

## 2. 实施概览 <a id="overview"></a>

```mermaid
flowchart LR
    A[设计定案修正] --> B[backend 占位]
    B --> C[frontend 占位]
    C --> D[frontend-mobile 占位]
    D --> E[根文件与说明文件]
    E --> F[本地验证]
    F --> G[分两条提交]
```

| 步骤 | 内容 | 结果 |
| --- | --- | --- |
| 1 | 设计定案修正（4 处） | 完成并单独提交 `e470985` |
| 2 | backend 最小占位 + 依赖锁定 | `uv lock`/`uv sync` 通过；`/healthz` 200 |
| 3 | frontend 最小占位 | `npm run build` 与 dev 5173 通过 |
| 4 | frontend-mobile 最小占位 | `npm run build` 与 dev 5174 通过 |
| 5 | 根文件（.editorconfig / .gitignore / README）与 `scripts`、`ops` 说明核对 | 完成 |
| 6 | 本地验证（启动、构建、忽略、端口） | 全部通过 |
| 7 | 提交 | `e470985`、`2390527`（分两条，未推送） |

## 3. 实施过程 <a id="process"></a>

### 3.1 设计定案修正

实施前对详细设计做最后核对，修正 4 处与磁盘/现行模型不一致的地方，单独提交 `e470985`：

1. 快速启动代码块 `powershell` → `bash`（开发机为 Ubuntu）。
2. 风险表「根 node_modules 陈旧索引告警」改为「已随工作区模型消除（`.opencode` 移至工作区根）」。
3. §3 目录树补 `基座文档清单.md`、删除磁盘上不存在的 `测试/`。
4. §2 现状表 README 行、§10 实施步骤第 7 步同步上述目录树口径。

### 3.2 backend 占位

新建文件：`.python-version`（3.14）、`pyproject.toml`（`fastapi>=0.115`、`uvicorn[standard]>=0.30`）、`app/__init__.py`（`__version__ = "0.1.0"`）、`app/main.py`（应用工厂 `create_app()` + `/healthz`）、`README.md`（四章节）。

```bash
cd backend
uv lock   # 使用系统 CPython 3.14.4；Resolved 20 packages
uv sync   # 安装 fastapi 0.141.1 / uvicorn 0.52.4 等 20 个包
uv run uvicorn app.main:create_app --factory --port 8000
```

验证：`GET /healthz` → `{"status":"ok"}`；`GET /docs` → HTTP 200；验证后停止服务。

### 3.3 frontend 占位

脚手架（Node 22 + npmmirror 源）：

```bash
npm create vite@latest frontend -- --template vue-ts
```

create-vite 9.2.0 生成：Vue 3.5.41 / Vite 8.2.2 / TypeScript 6.0.2 / vue-tsc 3.3.11 / @vitejs/plugin-vue 6.0.8。按设计调整：

- `package.json`：`name`=`bms-frontend`、`version`=`0.1.0`
- `vite.config.ts`：固定端口 `5173` + `strictPort`
- `index.html`：标题「BMS PC 管理端」、`lang="zh-CN"`
- `src/App.vue` 改为占位页；`src/main.ts` 去掉 `style.css` 引入
- 删除模板演示文件（`src/style.css`、`src/components/`、`src/assets/`、`public/icons.svg`）
- 新增 `.nvmrc`（22）；README 重写为四章节

```bash
npm install   # npmmirror 源，added 48 packages in 5s
npm run build # ✓ 11 modules transformed；dist/index.html 0.39 kB + js 59.88 kB
npm run dev   # 5173 返回占位页 HTML（title=BMS PC 管理端）
```

### 3.4 frontend-mobile 占位

以调整后的 `frontend/` 为基复制，差异：`name`=`bms-frontend-mobile`、端口 `5174`、标题与 `App.vue` 文案改移动端。`npm install`（48 包）、`npm run build` 通过、dev 5174 可访问占位页。

### 3.5 根文件与说明文件

- `.editorconfig`（新建）：UTF-8 / LF / 去行尾空格 / 文件末尾空行；Python 4 空格、前端与配置类 2 空格、Makefile tab、`*.md` 保留行尾空格。
- `.gitignore`：启用 `.idea/`、`.vscode/*`（放行 `settings.json` / `extensions.json`），新增 `*.local`；保留 Python 模板主体、`node_modules/`、`graphify-out/`、凭据忽略等既有规则。
- `README.md` 重写：徽标 Python 3.12+ → 3.14+ 并新增 Node 22；技术栈概览表；快速启动（bash）；目录结构按磁盘实际（含三工程、`基座文档清单.md`，并注明 AGENTS/opencode/图谱在工作区根）；文档导航合并原使用指南并补《平台可扩展性规划》行。
- `scripts/README.md` 工具表补 `base-check` / `winrm` / `vision` / `dsh`；`ops/README.md` 的 scripts 清单补 `base-check`。

### 3.6 验证与提交

按 [§5 验证结果](#verify) 逐项验证后，分两条提交：`e470985 docs(设计)`（定案修正）、`2390527 feat(项目)`（占位与根文件，39 文件）。另按设计 §10 步骤 8 补做 fresh clone 模拟：本地克隆 → `uv sync` / `npm ci` → 三工程启动，全部通过（见 §5）；随后连同实施记录提交一并推送远端（至 `1dfeaf8`）。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | 设计文与实际偏离：快速启动代码块标 `powershell`；目录树含不存在的 `测试/` 且漏 `基座文档清单.md`；风险表残留已消除的 node_modules 告警 | 设计编写早于 R1/R2 工作区改造，未随磁盘核对 | 实施前定案修正 4 处，单独提交 | `e470985` |
| 2 | 机器默认 `node -v` 为 v24.20.0，项目口径为 Node 22 LTS，且 fnm 未安装 | 环境默认版本与项目口径不一致 | 使用 nvm 已装的 v22.23.2（命令前置 PATH 指向该版本），不改机器默认版本 | 本记录「实施信息」 |
| 3 | create-vite 9.2.0 模板文件多于设计 §3 树（`tsconfig.app/node.json`、`public/favicon.svg`、`.vscode/extensions.json`，另有演示文件） | 设计树为最小示意、未逐一列模板产物 | 保留构建必需文件、删除演示文件；README 目录树按实际编写 | 根 `README.md` |
| 4 | 停止 dev 后台任务后 5173/5174 仍被占用 | `npm run dev` 经 npm 包装，停止任务只杀了主进程，vite 子进程残留 | 按端口定位 PID 精确 kill，确认端口释放 | 本记录 |
| 5 | `git check-ignore -v` 对否定规则（`!`）会打印该模式，易误判为「已忽略」 | 命令输出语义（最后命中的模式） | 以 `git status` / 实际跟踪状态为准 | 本记录 |

## 5. 验证结果 <a id="verify"></a>

| 验证点 | 方法 | 结果 |
| --- | --- | --- |
| 本地起服务 | `uv run uvicorn ...` 启动、访问 `/docs` | 通过（`/docs` 200） |
| 健康检查占位 | `GET /healthz` | 通过（`{"status":"ok"}`） |
| PC 前端可启动 | `npm run build` + dev 5173 | 通过（build 11 modules；dev 返回占位页） |
| 移动端可启动 | `npm run build` + dev 5174 | 通过（同上） |
| README 快速启动照做可通 | 按「快速启动」三工程命令逐条执行 | 通过 |
| fresh clone 照做可通 | 本地克隆 → `uv sync` / `npm ci` → 三工程启动 | 通过（`/healthz` 200；5173/5174 返回占位页；构建产物哈希与工作区一致） |
| `git status` 无应忽略产物 | `git status` + `git check-ignore -v` 抽查 | 通过（无 `.venv` / `node_modules` / `dist` / `.env` 入库） |
| 目录结构与《项目规划说明》§4 一致 | 对照 §4 目录清单 | 通过（模板额外文件已在 README 树列明） |
| 测试端口释放 | `ss -ltn` 检查 | 通过 |

## 6. 偏差与遗留 <a id="deviations"></a>

- 首次安装用 `npm install` 生成锁文件；README 快速启动按设计写 `npm ci`（锁文件就位后可用）。
- 前端子工程保留模板拆分的 `tsconfig.app/node.json`、`public/favicon.svg`、`.vscode/extensions.json`；设计 §3 树为简化示意，根 README 目录树按实际列明。
- 子工程 `.vscode/settings.json` 忽略差异：**已处理**——`frontend/.gitignore`、`frontend-mobile/.gitignore` 放行 `settings.json`（保留 `extensions.json` 放行），与设计 §9 第 4 条及根 `.gitignore` 一致。
- fresh clone 验证与提交推送均已完成（§5，推送至 `1dfeaf8`）；本任务无待办遗留。

> 本文档依《文档生成规范》编写 · 按《任务文档规范》第 5 节实施文档结构组织

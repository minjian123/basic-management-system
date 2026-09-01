# npm 技术介绍

> Node.js 官方包管理器 · BMS 前端依赖与构建入口

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › npm 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**npm**（Node Package Manager）是 Node.js 官方自带的包管理器，
随 Node.js 一起安装，无需额外依赖。它负责**依赖安装、版本锁定、脚本运行**，
并运营全球最大的开源包注册表 `npmjs.com`。截至 2026 年，npm（11.x 系列，
Node 24/26 自带；Node 22 自带 10.x）是 Node 生态默认包管理器。

- **定位**：BMS 前端双工程（frontend、frontend-mobile）的依赖管理与构建命令入口。
- **版本**：11.x 系列（Node 24/26 自带；Node 22 自带 10.x，持续迭代）。
- **许可**：Artistic-2.0（npm CLI 本体）。
- **语言**：JavaScript 编写，随 Node.js 发行。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| package.json | 工程清单：依赖、脚本、元信息，每个工程一份，BMS 双工程各自独立 |
| package-lock.json | 锁定文件：记录精确依赖树与校验和，`npm ci` 据此复现安装，必须入库 |
| node_modules | 依赖安装目录，体积大、不入库（.gitignore 排除） |
| npm install | 按 package.json 安装依赖并更新 lock 文件，开发期加依赖用 |
| npm ci | 严格按 lock 文件干净安装（先删 node_modules），CI 专用，保证可复现 |
| 依赖树（扁平化） | npm 尽量把依赖平铺到顶层 node_modules，版本冲突时嵌套子目录 |
| Registry | 包注册表，默认 npmjs.com；国内可换 npmmirror 镜像加速 |
| Scripts | package.json 的 scripts 字段定义 `npm run dev/build/test` 等命令 |
| Workspaces | npm 原生 monorepo 支持，BMS 双工程未用（保持独立） |
| Semver | 语义化版本（主.次.修订），依赖范围（^/~）决定自动升级边界 |
| .npmrc | 配置镜像、认证等，团队可共享，BMS 用于指向国内镜像 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **双工程依赖管理**：frontend 与 frontend-mobile 各自独立 package.json 与 package-lock.json，ESLint/Prettier/TS 配置互不共享（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **CI 可复现安装**：流水线用 `npm ci` 锁定安装，保证每次构建依赖完全一致（见《[GitLab 技术介绍](../部署与运维/GitLab技术介绍.md)》CI 流水线）。
- **构建命令入口**：`npm run dev/build/test/lint` 驱动 Vite、ESLint、Vitest 等工具（见《[Vite 技术介绍](Vite技术介绍.md)》）。
- **Node 版本管理**：`.nvmrc` 固定 Node 版本（22 LTS），配合 nvm/volta/fnm 切换，npm 随 Node 自带（见《[项目规划说明](../../../规划/项目规划说明.md#pages)》部署约定）。
- **依赖升级**：Renovate 自动提 MR 升级依赖，npm lock 文件随之更新（见《[Renovate 技术介绍](../部署与运维/Renovate技术介绍.md)》）。

最小示例（日常命令）：

```bash
# 开发期：安装依赖（会更新 lock 文件）
npm install

# 加一个依赖
npm install element-plus

# CI：严格按 lock 干净安装（可复现）
npm ci

# 运行脚本
npm run dev
npm run build
npm run test
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **npm（选中）** | Node 官方自带、零额外依赖、不生成额外配置、CI 生态成熟 | 与 BMS 双工程独立、CI 可复现诉求完全匹配 |
| yarn | 安装快、workspaces 成熟；但需额外安装、多一套 lock 与配置 | 非官方自带，引入成本高于收益 |
| pnpm | 硬链接省空间、依赖严格隔离；但需额外安装、团队需学习 | 能力优秀但非默认，BMS 规模下 npm 足够 |
| Bun | 快、集成运行时；但生态与 Node 兼容性仍在演进 | 稳定性与兼容性风险，暂不引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **CI 用 npm ci 而非 npm install**：install 可能改 lock 文件导致构建漂移，ci 严格按 lock 安装。
- **lock 文件必须入库**：package-lock.json 提交到仓库，否则 CI 与本地依赖不一致。
- **双工程别共享配置**：frontend 与 frontend-mobile 各自 package.json/lock/ESLint/TS 配置，互不引用（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **Node 版本一致**：`.nvmrc` 固定版本，本地与 CI 用同一 Node，避免 npm 大版本差异。
- **国内镜像**：访问 npmjs.com 慢时配 npmmirror 镜像（`.npmrc` 或 `--registry`），别长时间等待。
- **依赖范围注意**：`^` 允许次版本升级，安全/破坏性变更要 Renovate 提 MR 评审，别盲目自动合入。
- **node_modules 不入库**：体积大且平台相关，.gitignore 排除，靠 lock 文件复现。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| npm 官网 | https://www.npmjs.com | 包注册表与包搜索 |
| npm 官方文档 | https://docs.npmjs.com | 命令、配置、脚本权威参考 |
| npm CLI GitHub | https://github.com/npm/cli | 源码、Changelog 与 issue |
| npmmirror（淘宝镜像） | https://npmmirror.com | 国内镜像加速，.npmrc 配置入口 |
| Node.js 官网 | https://nodejs.org | Node 与自带 npm 版本对应关系 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（npm 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：官方自带、双工程独立、CI 锁定 |
| 《[命名规范](../../../规范/命名规范.md)》 | 工程、依赖与脚本命名约定 |
| 《[Vite 技术介绍](Vite技术介绍.md)》 | 构建工具，经 npm scripts 驱动 |
| 《[ESLint + Prettier 技术介绍](ESLint与Prettier技术介绍.md)》 | 代码规范工具，双工程各自配置 |
| 《[Renovate 技术介绍](../部署与运维/Renovate技术介绍.md)》 | 依赖自动升级，更新 npm lock |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
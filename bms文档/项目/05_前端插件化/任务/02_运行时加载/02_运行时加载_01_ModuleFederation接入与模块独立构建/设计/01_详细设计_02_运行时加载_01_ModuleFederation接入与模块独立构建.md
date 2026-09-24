# 01 详细设计 · Module Federation 接入与模块独立构建

> 前端插件化 · 02 运行时加载 · 子任务 01（需求 05-3）· 详细设计

[文档首页](../../../../../../文档首页.md) › [02 运行时加载](../02_运行时加载_01_ModuleFederation接入与模块独立构建.md) › 详细设计　|　[← 任务](../02_运行时加载_01_ModuleFederation接入与模块独立构建.md)

## 1. 设计目标与范围 <a id="goal"></a>

在 [01_02](../../../01_扩展点与装配/01_扩展点与装配_02_宿主加载器运行时化与模块契约远端对接/01_扩展点与装配_02_宿主加载器运行时化与模块契约远端对接.md)（**前置契约已交付**：`ModuleLoader` 接口、清单驱动加载器 `ManifestModuleLoader`、清单结构（名称 / 入口 / 版本）与「清单为唯一来源、拒绝不挂载」口径、宿主装配与消费接线、卸载逆序清理）之上：

1. **Module Federation 接入**——宿主接入 `@module-federation/vite` 作**纯 host**（只声明 `name` 与 `shared`，不声明静态 `remotes` / `exposes`），运行时经 `@module-federation/runtime` 的 `registerRemotes` + `loadRemote` 按清单加载远端；模块独立工程作 **remote**，以 `remoteEntry.js` + 暴露键 `./module` 暴露自身**模块定义**（注册声明 + 页面）；
2. **模块独立构建**——模块工程落 `frontend/modules/<模块名>/`（自有依赖清单 / 锁文件 / 构建配置 / 产物目录），产物**不并入主应用产物**，独立构建、独立归档；
3. **清单对接**——清单条目扩展 `mode`（`local` 缺省 / `remote`）显式区分构建期合并与运行时远端；`ModuleLoader` 接口不变，`ManifestModuleLoader` 的入口来源由「懒加载表」改为**入口解析器注入**（本地表解析器落 core、远端 MF 解析器落宿主）；
4. **动态导入分包**——远端入口运行期按需加载，模块页面在模块产物内为独立异步分包，**不进宿主首屏**；模块产物纳入体积预算计量（**模块工程自带预算配置与脚本，单独计量**）；
5. **两形态共存**——构建期合并（`mode: local`）与运行时加载（`mode: remote`）并存，由清单显式区分并成文，共用同一加载器与装配 / 卸载路径；
6. **演示验证**——演示模块**整体迁出**为独立工程 `frontend/modules/demo/`，以构建产物（`vite preview`，端口 5002）供宿主（5173）运行时加载并注册路由（**仅开发态进菜单**）。

**不在本期**：`shared` 版本偏斜治理与升级契约（`02_02`）、样式与运行时隔离护栏（`03_01`）、清单唯一来源与发布 / 灰度 / 回滚（`03_02`）、按模块可观测与失败兜底增强（`03_03`）、首个模块样例的独立发布与接入指南（`04_01`）。

### 1.1 现状与缺口 <a id="gap"></a>

```text
frontend/
├── packages/core/src/module/
│   ├── manifest.ts            # 清单契约与严格解析（三字段）              ← 本期 +mode
│   ├── loader.ts              # LocalModuleLoader + ManifestModuleLoader  ← 本期 改解析器注入、删 LocalModuleLoader
│   └── types.ts               # 模块契约 / 上下文 / 加载器接口              ← 本期 +mode 相关导出
├── apps/desktop/
│   ├── vite.config.ts         # 纯 Vite（无 MF）                          ← 本期 +federation（纯 host）
│   ├── public/modules.json    # 演示模块（entry=demo，本地标识）           ← 本期 改远端 URL + mode
│   └── src/
│       ├── module/
│       │   ├── entries.ts     # 入口懒加载表（import.meta.glob）           ← 本期 改为本地解析器
│       │   ├── federation.ts  # （本期新增）远端入口解析器（MF 运行时）
│       │   └── host.ts        # 清单驱动装载                            ← 本期 按 mode 分派解析器
│       └── modules/demo/      # 演示模块（宿主内，构建期合并）              ← 本期 整体迁出
└── modules/demo/              # （本期新增）模块独立工程（MF remote，独立构建）
```

缺口：① 宿主无 MF 能力，清单 `entry` 只能解析「模块源码标识」，远端形态无处落脚；② 模块产物随主应用构建，无法独立构建 / 独立发布；③ 构建期合并与运行时加载两形态无显式判据，叠加后加载路径易混；④ 模块产物体积无处计量（并入宿主即污染宿主阈值）；⑤ `01_02` 遗留：`entry` 语义为模块源码标识、`LocalModuleLoader` 去留未定。

## 2. 交付物清单 <a id="deliver"></a>

| # | 交付物 | 落点 |
| --- | --- | --- |
| 1 | 清单契约扩展：`mode`（`local` / `remote`）与 `remote` 入口绝对 URL 校验 | `core/src/module/manifest.ts`、`core/src/index.ts` |
| 2 | 入口解析器抽象：`ModuleEntryResolver` + `createModuleEntryTableResolver`；`ManifestModuleLoader` 改解析器注入 | `core/src/module/loader.ts` |
| 3 | 删除 `LocalModuleLoader`（连同入口导出与既有用例） | `core/src/module/loader.ts`、`core/src/index.ts`、`core/tests/module-loader.spec.ts` |
| 4 | 宿主 MF 接入（纯 host：`name` + `shared`） | `apps/desktop/vite.config.ts`、`apps/desktop/package.json` |
| 5 | 远端入口解析器（`registerRemotes` + `loadRemote`） | `apps/desktop/src/module/federation.ts`（新增） |
| 6 | 本地入口表改本地解析器；宿主按清单 `mode` 分派解析器 | `apps/desktop/src/module/entries.ts`、`host.ts` |
| 7 | 演示清单改远端条目（绝对 URL + `mode: remote`） | `apps/desktop/public/modules.json` |
| 8 | **模块独立工程**（remote）：构建 / 预览 / 预算 / 类型 / Lint / 单测配置与源码 | `frontend/modules/demo/`（`package.json`、`pnpm-lock.yaml`、`vite.config.ts`、`vitest.config.ts`、`tsconfig*.json`、`eslint.config.js`、`budget.json`、`scripts/check-bundle-budget.mjs`、`index.html`、`src/`） |
| 9 | 演示模块源码迁移（模块定义 + 页面 + 独立预览壳） | `frontend/modules/demo/src/{index.ts,standalone.ts,views/}` |
| 10 | 宿主侧清理：删除 `src/modules/demo/**`，菜单仍取注册表快照 | `apps/desktop/src/modules/`、`App.vue` |
| 11 | 核心用例（清单 `mode` / 解析器注入 / 校验链） | `core/tests/module-manifest.spec.ts`、`module-loader.spec.ts` |
| 12 | 宿主用例（远端解析器替身、两形态分派、远端不可达处置） | `apps/desktop/tests/module-federation.spec.ts`（新增）、`module-hosting.spec.ts`、`module-manifest.spec.ts` |
| 13 | 模块工程用例与产物断言 | `frontend/modules/demo/tests/module-definition.spec.ts`、`scripts/check-bundle-budget.mjs` |
| 14 | CI 接线：镜像预装模块工程依赖 + 模块构建 / 预算 / 测试 job + 模块产物归档 | `deploy/ci/Dockerfile.frontend`、`deploy/ci/build-base.sh`、`.gitlab-ci.yml` |
| 15 | 登记回写（契约 / 架构 / 概要 / 基类清单 / 规范 / 计划 / 任务 / README） | 《前端模块契约》§4 / §6、《前端架构》§9、《扩展点与插件化》§7.2、《概要设计 · 前端插件化》§5.2、《前端基类清单》§9、《前端开发规范》「构建体积预算」、`项目/05_前端插件化/` |
| 16 | 任务实施记录 / 测试记录 | 本目录 `实施/`、`测试/` |

## 3. 接口 / 契约与边界 <a id="contract"></a>

### 3.1 清单契约扩展：加载形态 <a id="manifest"></a>

清单条目由「严格三字段」扩为「三必填 + 一可选形态」，字段口径与 `01_02` 一致（不重复定义两套），落 `core/src/module/manifest.ts`：

```ts
/** 模块加载形态（`local`＝构建期合并；`remote`＝运行时远端加载）。 */
export type ModuleLoadMode = 'local' | 'remote'

/** 模块清单项（宿主 `modules.json` 条目）。 */
export interface ModuleManifestEntry {
  /** 模块名（`MODULE_NAME_PATTERN`）。 */
  name: string
  /** 入口：`local` 为模块源码标识（本地入口表键）；`remote` 为远端入口 URL。 */
  entry: string
  /** 版本（与模块自报 `manifest.version` 严格相等）。 */
  version: string
  /** 加载形态（缺省 `local`；解析后恒有值）。 */
  mode: ModuleLoadMode
}
```

| 校验 | 口径 | 处置 |
| --- | --- | --- |
| 整份形态 | 须为数组 | 非数组 / `null` → 抛 `BaseError(CAPABILITY_VIOLATION)`（宿主捕获为「空清单 + 错误状态」，不阻塞启动） |
| 三字段 | `name` / `entry` / `version` 齐全且非空（`name` 另须合 `MODULE_NAME_PATTERN`） | 缺字段该项**拒绝加载**并记入 `rejected` |
| `mode` 取值 | 缺省按 `local` 归一；出现时须为 `local` / `remote` | 非法值该项**拒绝加载**并记入 `rejected`（原因含非法取值） |
| `remote` 入口形态 | `mode: 'remote'` 时 `entry` 须为**绝对 URL**（`http://` / `https://` 开头） | 非绝对 URL（相对路径 / 源码标识）该项**拒绝加载**并记入 `rejected`——远端入口不做隐式推断 |
| 单项重名 | 同一 `name` 多次出现（前项校验通过） | 保留先通过项，后续项拒绝（沿用 `01_02` 口径） |

- 解析产物中 `mode` **恒有值**（缺省填 `local`），调用方无需再做缺省处理；
- 字段语义与《[前端模块契约](../../../../../../设计/架构设计/35_架构设计_前端模块契约.md)》§4 / §6 对齐：`entry` 的语义**由 `mode` 决定**，不再由字符串形态推断。

### 3.2 加载器入口解析器 <a id="loader"></a>

`ModuleLoader` 接口**不变**；`ManifestModuleLoader` 的第二参由「入口懒加载表」改为**入口解析器**，把「入口从哪来」这一唯一变量抽离（本地表 / 远端容器各一个实现），校验链与装配语义完全复用（`core/src/module/loader.ts`）：

```ts
/** 模块入口模块（约定**默认导出**模块定义）。 */
export interface ModuleEntryModule {
  /** 默认导出（`defineModule` 产物）。 */
  default?: unknown
}

/** 模块入口懒加载表（本地形态：入口标识 → 入口加载器）。 */
export type ModuleEntryTable = Record<string, () => Promise<ModuleEntryModule>>

/** 模块入口解析器（按清单条目解析入口模块；本地 / 远端各一个实现）。 */
export type ModuleEntryResolver = (entry: ModuleManifestEntry) => Promise<ModuleEntryModule>

/** 本地入口解析器（构建期合并形态；入口标识未登记即拒绝）。 */
export function createModuleEntryTableResolver(table: ModuleEntryTable): ModuleEntryResolver

/** 清单驱动模块加载器（入口来源由解析器注入）。 */
export class ManifestModuleLoader implements ModuleLoader {
  constructor(entries: readonly ModuleManifestEntry[], resolveEntry: ModuleEntryResolver)
}
```

`load(name, context)` 执行序（与 `01_02` 一致，仅第 2 步来源可换；任一校验不过即**拒绝加载**、抛错、不挂载）：

| 步 | 动作 | 失败处置 |
| --- | --- | --- |
| 1 | 查清单条目（按名） | 无 → `BaseError(PROVIDER_NOT_REGISTERED)` |
| 2 | 调 `resolveEntry(entry)` 取入口模块 | 本地：入口标识未登记 → `PROVIDER_NOT_REGISTERED`；远端：容器不可达 / 未暴露 → **原样上抛**（宿主记错误状态） |
| 3 | 取入口**默认导出**并校验模块定义形状（`manifest` + `setup`） | 缺默认导出 / 形状非法 → `BaseError(CAPABILITY_VIOLATION)` |
| 4 | **清单 ↔ 模块自报一致性**：`manifest.name` 一致、`manifest.version` **严格相等** | 不一致 → `BaseError(CAPABILITY_VIOLATION)`（发布错位立即暴露） |
| 5 | 冻结上下文快照后调 `setup`（`Object.freeze({ ...context })`） | `setup` 抛错 → 原样上抛 |
| 6 | 返回 `LoadedModule`（`manifest` 以清单为准补 `entry`） | — |

- **删除 `LocalModuleLoader`**：其为「清单出现之前的本地定义表」实现，能力已被「`ManifestModuleLoader` + 本地入口解析器」完全覆盖；去留结论回写 `01_02` 实施记录遗留 5 与决策记录（`01_02` 决策 12「MF 实现另取名」相应修订为「入口解析器注入，实现收敛为一套」）；
- **不隐式回退**：加载器只认清单与解析器——形态缺失按 `local`，`remote` 入口非绝对 URL 在解析期即拒绝，不做「按约定猜地址」的兜底。

### 3.3 宿主 MF 接入与运行时远端解析 <a id="host"></a>

**宿主构建配置**（`apps/desktop/vite.config.ts`）：新增 `federation({ name: 'bms-desktop', shared: SHARED_DEPS })`——**纯 host**，不声明 `remotes` / `exposes`；插件注入宿主初始化（发布 share scope、`shared` 声明的依赖由宿主提供），远端在运行期注册。

| 项 | 口径 |
| --- | --- |
| 宿主容器名 | `bms-desktop`（宿主标识，与模块名不同名空间） |
| `shared` 集合 | **框架三件** `vue` / `vue-router` / `pinia`，均 `singleton: true`；**本任务不写 `requiredVersion`**（版本偏斜治理归 `02_02`）。**2026-09-21 实测修订**（详见 §7）：宿主共享 `element-plus` 时插件会生成「整库 share provider 块」并由宿主入口**静态引入**（首屏 660.7 KB、单块 334.5 KB，超预算 2.5 倍；显式 `eager: false` 实测无效），故本任务收窄为框架三件；`@bms/core` / `@bms/ui-ep` 因宿主以 `resolve.alias` 源码直出消费、MF **探测不到而进不了共享面**（无对应 provider 块），按 §7 回退为双侧各自打包 |
| 静态 `remotes` | **不声明**——远端地址来自清单，改清单不必重构建 |
| 测试环境 | 插件在 Vitest 环境**自动空转**（插件内 `isTestEnv()` 直接返回空插件数组），测试下 MF 运行时不参与，宿主用例须以**替身远端解析器**覆盖远端分支 |

**远端入口解析器**（`apps/desktop/src/module/federation.ts`，新增；`resolveEntry` 的远端实现，走 `@module-federation/runtime`）：

```ts
/** 远端入口解析器（MF 运行时：登记远端容器并加载其暴露的模块定义）。 */
export function createFederationEntryResolver(): ModuleEntryResolver
```

实现要点：

1. `registerRemotes([{ name: entry.name, entry: entry.entry }], { force: true })`——**容器名取清单 `name`**，同名以清单为准重登记（`installModules` 可重入）；
2. `await loadRemote(\`${entry.name}/${MODULE_EXPOSE_KEY}\`)`——暴露键固定 `./module`；
3. 返回入口模块对象，**不做形状 / 版本校验**（校验在加载器内统一执行，保证两条通路校验一致）。

**约定常量**（`core/src/module/loader.ts` 导出，供宿主与模块工程共用，成文落《前端模块契约》）：

| 常量 | 值 | 语义 |
| --- | --- | --- |
| `MODULE_REMOTE_ENTRY_FILE` | `remoteEntry.js` | 远端容器入口文件名（模块构建产物固定文件名） |
| `MODULE_EXPOSE_KEY` | `module` | 暴露键（`loadRemote('<模块名>/module')`；模块定义默认导出） |
| `MODULE_REMOTE_ORIGIN`（宿主侧） | `http://localhost:5002` | 本地演示远端 origin（生产清单地址替换归 `03_02`） |

**宿主装配改造**（`apps/desktop/src/module/`）：

```text
entries.ts     # import.meta.glob('../modules/*/index.ts') → createModuleEntryTableResolver（未迁移模块通路，当前无存量模块）
federation.ts  # createFederationEntryResolver（远端通路）
host.ts        # 构造「按 mode 分派」的解析器：local → 本地表解析器；remote → 远端解析器
```

```ts
// host.ts（示意）：单加载器实例 + 形态分派，装配 / 卸载路径不变
const resolvers: Record<ModuleLoadMode, ModuleEntryResolver> = {
  local: createModuleEntryTableResolver(MODULE_ENTRIES),
  remote: createFederationEntryResolver(),
}
function resolveEntry(entry: ModuleManifestEntry): Promise<ModuleEntryModule> {
  const byMode = resolvers[entry.mode]
  return byMode(entry)
}
loader = new ManifestModuleLoader(manifest.entries, resolveEntry)
```

清单（`apps/desktop/public/modules.json`）：

```json
[{ "name": "demo", "entry": "http://localhost:5002/remoteEntry.js", "version": "0.1.0", "mode": "remote" }]
```

### 3.4 模块独立工程与独立构建 <a id="module"></a>

**落点与结构**（`frontend/modules/demo/`，与 `apps/desktop` 同构；`frontend/modules/` 为模块工程集合）：

```text
frontend/modules/demo/
├── package.json                  # @bms/module-demo（私有；scripts: dev / build / preview / budget / test / typecheck / lint）
├── pnpm-lock.yaml
├── vite.config.ts                # federation({ name:'demo', filename:'remoteEntry.js', exposes:{ './module':'./src/index.ts' }, shared })
├── vitest.config.ts
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── eslint.config.js
├── budget.json                   # 模块产物体积阈值（单独计量）
├── scripts/check-bundle-budget.mjs
├── index.html                    # 模块工程独立预览壳
└── src/
    ├── index.ts                  # 默认导出模块定义（注册声明：路由 / 组件 / 卡片 / 区域 / 令牌 / 文案包）
    ├── standalone.ts             # 独立预览（挂载演示页的最小应用，供模块自身 dev / preview）
    └── views/                    # DemoHome.vue / DemoToolbox.vue（自宿主迁入）
```

| 项 | 口径 |
| --- | --- |
| MF 角色 | **remote**：`name: 'demo'`（= 清单 `name`）、`filename: 'remoteEntry.js'`、`exposes: { './module': './src/index.ts' }` |
| `shared` | 与宿主**同一集合**（`vue` / `vue-router` / `pinia` / `element-plus` / `@bms/core` / `@bms/ui-ep`，单例、不写 `requiredVersion`） |
| `@bms/*` 解析 | 以 **`file:` 依赖**声明（`file:../../packages/core`、`file:../../packages/ui-ep`）——`pnpm install` 生成 `node_modules` 软链，**保留裸标识符**（不走 vite alias），便于 MF 共享面直接生效 |
| 其余依赖 | `vue` / `vue-router` / `pinia` / `element-plus` 为常规依赖；构建链路 `vite` / `vue-tsc` / `vitest` / `eslint` / `sass` 自带（与宿主同版本区间） |
| 构建 | `pnpm run build` → `vite build`，产物 `dist/`（`remoteEntry.js` + 模块页面异步分包），**不并入主应用产物** |
| 服务 | `preview` 固定端口 **5002**、放开 CORS（`server.origin` / `preview.cors`），供宿主跨端口加载 |
| 独立预览 | `index.html` + `src/standalone.ts`：模块可脱离宿主独立开发与预览（模块自身页面路由与样式自洽） |
| 页面分包 | 模块路由的 `component` **一律为 `() => import(...)`**（懒加载），构建后被拆为独立异步块 |
| 迁移 | 宿主 `apps/desktop/src/modules/demo/**` **整体删除**（避免同一示例两处维护、样例绕开机制）；宿主菜单 `demo` 分组仍由 `moduleMenuNodes()`（路由·菜单注册表快照）派生、**仅开发态可见** |

### 3.5 模块产物计量与归档 <a id="budget"></a>

模块产物**单独计量**（不并入宿主阈值）：模块工程自带 `budget.json` 与 `scripts/check-bundle-budget.mjs`（口径与宿主预算脚本同源，但按 MF 产物特征定义「入口块」）。

| 项 | 口径 |
| --- | --- |
| 入口块闭包 | 从 `dist/remoteEntry.js` 出发解析**引用闭包**：种子块追「静态引用（`from`）+ 动态引用（`import()`，即暴露键指向的暴露块）」，其余块只追静态引用——页面 / 工具块经动态 `import()` 引用，**不进闭包**（实测闭包 6 块 / 8.8 KB gzip；暴露模块块仅 0.8 KB，证明共享与分包生效） |
| 阈值 | `budget.json`：`entryGzipKb`（入口闭包 gzip 合计上限，取「实测基线 + 20%」）、`largestGzipKb`（单块上限）、`maxEntryFiles`（入口块数上限，防「分包退化、页面并入入口」） |
| 页面分包断言 | ① 入口闭包**文件名**不得命中 `pageChunkHints`（模块页面块命名特征，如 `DemoHome` / `DemoToolbox`）；② 入口外异步块数 ≥ `minAsyncChunks`（= 模块声明路由数）——页面确实独立分包、未被并入容器入口 |
| 观察输出 | 打印入口闭包与入口外块清单（gzip），供 `03_03` 按模块体积归因复用 |
| 归档 | CI 以 artifact 归档模块产物目录 `frontend/modules/demo/dist/`（模块产物单独归档，不随宿主产物） |

### 3.6 两形态共存口径 <a id="coexist"></a>

| 形态 | 清单判据 | `entry` 语义 | 加载通路 | 适用 |
| --- | --- | --- | --- | --- |
| 构建期合并 | `mode: 'local'`（缺省） | 模块源码标识（宿主本地入口表键） | 宿主构建期打包（`import.meta.glob` 表 + 本地入口解析器） | 平台自身页面与未迁移模块（当前无存量模块） |
| 运行时远端 | `mode: 'remote'` | 远端入口 URL（`remoteEntry.js`） | MF 运行期注册 + 加载（`registerRemotes` + `loadRemote`） | 新业务页面 / 独立构建发布的模块 |

- 两形态**共用**：同一 `ModuleLoader` 接口、同一校验链（默认导出形状 / 名称与版本一致性 / 上下文冻结）、同一统一装配与卸载逆序清理路径；
- **由清单显式区分**（`mode`），加载器只认清单，不做隐式回退（对齐计划风险对策「构建期合并与运行时加载共存配置歧义」）；
- **迁移路径**：模块源码迁出为独立工程并独立发布后，清单条目由 `local` 改 `remote`（清单侧无需改代码）；生产清单来源与替换、版本发现与回滚归 `03_02`。

### 3.7 CI 接线 <a id="ci"></a>

| 项 | 口径 |
| --- | --- |
| CI 基础镜像 | `deploy/ci/Dockerfile.frontend` 增 `COPY frontend/modules/ /opt/ci/frontend/modules/` 并 `pnpm install --frozen-lockfile`；`deploy/ci/build-base.sh` 的哈希输入追加模块锁文件、构建上下文补模块清单与锁文件 |
| 模块 job | 新增 `module-check`（`lint` + `typecheck` + `test`）与 `module-build`（`build` + `budget`，artifacts 归档 `frontend/modules/demo/dist/`），触发路径与前后端 job 同口径（`frontend/**/*` 等） |
| 宿主 job | `desktop-check` / `desktop-build` 路径规则已覆盖 `frontend/**/*`，无需改；宿主新增 MF 依赖后**镜像按锁文件哈希自动重建**（`ci-base-build` 已守 `frontend/apps/desktop/pnpm-lock.yaml`） |
| 远端可达性 | 宿主构建不依赖远端（远端仅运行期加载）；宿主 Vitest 中插件空转 + 远端解析器以替身覆盖，故 CI **无需启动远端服务** |

## 4. 失败分支与边界 <a id="edge"></a>

| 边界 / 失败场景 | 处置 | 错误码 |
| --- | --- | --- |
| 清单 `mode` 取值非法 | 该项拒绝加载并记入 `rejected` | — |
| `mode: 'remote'` 而 `entry` 非绝对 URL | 该项拒绝加载（原因明示「远端入口须为绝对 URL」） | — |
| 远端容器不可达（网络 / 404 / CORS 拒绝） | `loadRemote` 抛错**原样上抛** → 宿主记错误状态（带模块名与版本）、该项不挂载、菜单无该项、其余项照常 | 原始错误 |
| 远端容器可加载但未暴露 `./module` | 加载失败（默认导出缺失）→ 拒绝加载 | `CAPABILITY_VIOLATION`（形状校验） |
| 远端模块自报名称 / 版本与清单不一致 | 拒绝加载（发布错位） | `CAPABILITY_VIOLATION` |
| 远端模块 `setup` 抛错 | 原样上抛，宿主记错误状态，回滚该项已产生的接线 | 原始错误 |
| 同一远端重复登记（重入 `installModules`） | `registerRemotes(..., { force: true })`：同名以清单为准覆盖，幂等 | — |
| 本地形态入口标识未登记 | 拒绝加载 | `PROVIDER_NOT_REGISTERED` |
| 清单整体不可用（获取失败 / 非数组） | 空清单继续，平台页面照常渲染（沿用 `01_02`） | `CAPABILITY_VIOLATION`（清单层） |
| 模块产物超体积阈值 | 模块构建门禁阻断（`pnpm run budget` 退出码 1，CI 红） | — |
| 宿主首屏 | 远端代码不进宿主产物（仅运行期 URL 引用），首屏预算口径不变 | — |
| 卸载 | 沿用 `01_02` 逆序清理（路由 → 文案 → 令牌 → 注册表 → 加载器），远端容器加载结果不驻留注册表 | — |

## 5. 测试设计与验收映射 <a id="test"></a>

| 验收点（需求 05-3 完成标准） | 用例 |
| --- | --- |
| 1 演示模块**独立构建**产出独立产物、宿主**运行时加载**成功（非构建期合并） | 手工全链路验证（模块 `build` → `preview:5002` → 宿主 `dev:5173` 经清单加载）：路由生效、页面渲染、区域插槽 / 令牌 / 文案随挂载生效；证据（构建产物清单 + 加载实录）落实施记录；模块侧 `scripts/check-bundle-budget.mjs` 断言产物形态（含独立 `remoteEntry.js` 与暴露块） |
| 2 动态路由生效、挂载与卸载正常、卸载无残留 | `apps/desktop/tests/module-hosting.spec.ts`（`mode: remote` 条目经**替身远端解析器**装载 → 路由注册 → 菜单派生 → 卸载后路由 / 注册项 / 令牌 / 文案 / 区域项全部还原） |
| 1′ / 3 清单形态判据与远端失败处置 | `core/tests/module-manifest.spec.ts`（`mode` 缺省归一、非法值拒绝、`remote` 非绝对 URL 拒绝、重名口径不变）、`core/tests/module-loader.spec.ts`（解析器注入：本地解析器未登记拒绝、解析器抛错原样上抛、校验链不因解析器而变） |
| 4 MF 配置与清单字段成文、`01_02` 加载器同接口复用 | `apps/desktop/tests/module-federation.spec.ts`（远端解析器：`registerRemotes` 入参名 / 入口、`loadRemote` 调用形为 `<name>/module`、加载错误上抛；以 `vi.mock('@module-federation/runtime')` 覆盖）；核心用例断言 `LocalModuleLoader` 已移除、`ModuleLoader` 接口断言（`load` / `mount` / `unmount` / `isMounted` / `mountedNames`） |
| 模块页面不进首屏、独立分包 | 模块 `budget`（异步块数 ≥ 路由数）+ 模块契约用例（路由 `component` 均为函数）+ 宿主 `budget`（宿主首屏预算不变） |
| 模块 contract（模块定义形状与声明键） | `frontend/modules/demo/tests/module-definition.spec.ts`（默认导出、清单名称与版本、路由懒加载与路径前缀、八类声明键前缀与区域标识） |
| 5 `vue-tsc`、ESLint、Vitest、构建与体积预算全通过 | 根 `pnpm run check`；宿主 `pnpm exec vue-tsc -b` + `lint` + `test:cov` + `build` + `budget`；模块工程 `typecheck` + `lint` + `test` + `build` + `budget`；核心护栏 `guard-core-framework-agnostic`（新增 core 件不触 DOM / 不依赖框架与 MF 运行时） |
| 两形态共存 | `apps/desktop/tests/module-hosting.spec.ts` 增「`local` 与 `remote` 条目同批装载各走各的通路」用例 |
| Kiwi 用例关联 | 一任务一条，**先登记取号（以平台回读编号为准）**再回填代码标注 |

文档门禁：`scripts/tools/base-check/check-base.py`、`check-links.py`、`check-docs/check-status.py --stage 05_前端插件化 --strict`。

## 6. 登记落点 <a id="register"></a>

| 内容 | 落点 |
| --- | --- |
| 清单字段（`mode`）与形态判据、远端入口绝对 URL 要求 | 《[前端模块契约](../../../../../../设计/架构设计/35_架构设计_前端模块契约.md)》§4 / §6 |
| 远端命名与暴露键约定（容器名 / `remoteEntry.js` / `./module`） | 《前端模块契约》§6 |
| 运行时组合（宿主 host / 模块 remote）、独立构建与独立计量 | 《[前端架构](../../../../../../设计/架构设计/08_架构设计_前端架构.md)》§9、《[扩展点与插件化](../../../../../../设计/架构设计/10_架构设计_子系统_扩展点与插件化.md)》§7.2「模块来源与合并方式」 |
| 清单字段与加载形态语义 | 《[概要设计 · 前端插件化](../../../../../../设计/概要设计/38_概要设计_前端插件化.md)》§5.2 |
| core 加载器改造（解析器注入、删 `LocalModuleLoader`、形态常量）与模块工程落点 | 《[前端基类清单](../../../../../../前端基类清单.md)》§9「目录与依赖」 |
| 模块产物单独计量口径 | 《[前端开发规范](../../../../../../规范/前端开发规范.md)》「构建体积预算」节 |
| `01_02` 遗留闭环（`entry` 语义、`LocalModuleLoader` 去留、决策 12 修订） | `01_02` 实施记录 §6、本任务实施记录 |
| 需求 / 任务 / README / 计划表现（工时与状态） | `需求/02_需求_运行时加载.md`（如需口径补充）、`任务/02_运行时加载/…`、`README.md`、`计划/01_计划_前端插件化.md` |
| 任务 / 计划状态 | 任务信息表 + 父任务子任务清单 + 计划 §2 / §3 |

## 7. 边界与开放项 <a id="open"></a>

- **`shared` 版本偏斜治理**：`requiredVersion`、版本唯一来源、生产构建无重复实例验证、CI 依赖实例数断言、框架大版本升级契约——全部归 `02_02`（本任务只落「能跑起来的最小 singleton 声明」）；
- **UI 组件库与平台基座包的共享（实测修订）**：本任务 `shared` 收窄为**框架三件**（`vue` / `vue-router` / `pinia`），实测依据与归口如下——
  - **`element-plus` 不能由宿主共享**：实测宿主共享它时，插件为「宿主未静态引入的共享库」生成整库 share provider 块并由**宿主入口静态引入**（首屏 660.7 KB / 单块 334.5 KB gzip，超预算 2.5 倍；显式 `eager: false` 与 `hostInitInjectLocation: 'entry'` 均不改变下载量——后者只是把块从 HTML 移到入口，属指标失真）；归 `02_02` 评估（`treeShaking.runtime-infer`、provider 懒加载、`@module-federation/runtime` 手工 init 等，前提是解决插件启动期静态拉取）；
  - **平台基座包共享不成立**：`@bms/core` / `@bms/ui-ep` 为**源码直出、版本 `0.0.0` 的内部包**，宿主以 `resolve.alias` 消费 → MF 探测不到模块请求、无 provider 块，本任务按此**回退为双侧各自打包**（模块工程以 `file:` 依赖自带副本；装配器按键重建注册项、不做 `instanceof` 判定，跨副本类实例安全）；基座包**发布版本化 / 共享 scope 化**随基座包发布治理评估；
- **清单治理**：清单唯一来源、版本发现、灰度 / 回滚、**生产远端入口地址替换**归 `03_02`（本任务清单地址为本地演示值）；
- **可观测**：远端入口缓存 / 版本化 URL、sourcemap 口径、按模块错误与性能归因归 `03_03`；
- **隔离**：模块样式前缀、Shadow DOM / 沙箱评估归 `03_01`；
- **模块工程脚手架定位**：本任务落的工程结构（`shared` 清单、预算脚本、`file:` 依赖、预览壳）为 `04_01` 首个模块样例的基座，样例实施时可能据实调整（届时回写）。

## 8. 决策记录 <a id="decision"></a>

| # | 决策项 | 结论 |
| --- | --- | --- |
| 1 | MF 工具链 | `@module-federation/vite` + `@module-federation/runtime`（官方 MF 2.0，peer 支持 vite `^5~^8`；宿主与模块两侧同套配置） |
| 2 | 远端声明方式 | **运行时动态注册**（`registerRemotes` + `loadRemote`）；宿主不声明静态 `remotes`，清单外置、改清单不必重构建 |
| 3 | 清单形态判据 | 新增 `mode: 'local' \| 'remote'`（缺省 `local`）；`mode: 'remote'` 时 `entry` 须为绝对 URL |
| 4 | 远端命名约定 | 容器名 = 清单 `name`；入口文件名固定 `remoteEntry.js`；暴露键固定 `./module`；三者以 core 常量成文，清单保持三字段 |
| 5 | 演示模块落点 | **整体迁出**为独立模块工程 `frontend/modules/demo/`；宿主删除 `src/modules/demo/**`；构建期合并形态由平台自身页面承载 |
| 6 | 模块工程形态 | `frontend/modules/<模块名>/` **独立安装**（自有 `package.json` / 锁文件 / `vite.config.ts` / `tsconfig`），依赖隔离、独立构建与独立发布 |
| 7 | 加载器结构 | **入口解析器注入**（`ModuleEntryResolver`）；本地表解析器落 core、远端 MF 解析器落宿主；**删除 `LocalModuleLoader`**，加载实现收敛为一套（修订 `01_02` 决策 12） |
| 8 | 演示 remote 运行方式 | 模块 `build` 后用 **`vite preview`**（端口 5002、放开 CORS）提供产物，宿主 dev server 经清单 URL 加载——验证对象即独立构建产物 |
| 9 | 体积计量 | 模块工程**自带** `budget.json` + 校验脚本（入口块**引用闭包**阈值 + 入口文件数上限 + 页面分包断言），模块产物单独计量、不牵连宿主阈值 |
| 10 | `shared` 深度 | **最小 singleton 声明**，不写 `requiredVersion`；完整治理归 `02_02`。**2026-09-21 实测修订**：集合由六件收窄为**框架三件**（`vue` / `vue-router` / `pinia`）——`element-plus` 由宿主共享会把整库拉入首屏（+334.5 KB gzip）、`@bms/core` / `@bms/ui-ep` 经 alias 消费时 MF 探测不到；两者共享方案归 `02_02`（见 §7） |
| 11 | CI 接线 | **本次接线**：镜像预装模块工程依赖 + 新增 `module-check` / `module-build`（含产物归档）；宿主 job 免改（路径规则已覆盖） |
| 12 | 演示入口 URL | 清单 `entry` 用**绝对 URL** `http://localhost:5002/remoteEntry.js`（不涉内网 IP，符合公开文档红线）；生产清单归 `03_02` |
| 13 | 宿主插件角色 | **纯 host**（仅 `name` + `shared`；无 `remotes` / `exposes`） |
| 14 | 模块工程解析 `@bms/*` | **`file:` 依赖**链接（`node_modules` 软链、保留裸标识符），不走 vite alias——为共享面留通路 |
| 15 | 模块独立预览 | 模块工程自带 `index.html` + `src/standalone.ts`，可脱离宿主独立开发与预览 |
| 16 | 测试中 MF | 插件在 Vitest 环境自动空转 → 宿主用例以**替身远端解析器**覆盖远端分支，CI 不需起远端服务 |

## 9. 参考文档 <a id="ref"></a>

- [需求 05-3](../../../../需求/02_需求_运行时加载.md#r05-3)
- 《[架构设计 · 前端模块契约](../../../../../../设计/架构设计/35_架构设计_前端模块契约.md)》§4 / §6
- 《[架构设计 · 前端架构](../../../../../../设计/架构设计/08_架构设计_前端架构.md)》§9「运行时组合」与 §7 性能
- 《[架构设计 · 扩展点与插件化](../../../../../../设计/架构设计/10_架构设计_子系统_扩展点与插件化.md)》§7.2
- 《[概要设计 · 前端插件化](../../../../../../设计/概要设计/38_概要设计_前端插件化.md)》§5.2
- 《[前端基类清单](../../../../../../前端基类清单.md)》§9「目录与依赖」
- 《[前端开发规范](../../../../../../规范/前端开发规范.md)》「构建体积预算」节
- 知识档案《[微前端](../../../../../../资料/知识档案/微前端/01_微前端_总览.md)》与《[微前端 · 03 技术方案对比](../../../../../../资料/知识档案/微前端/03_微前端_技术方案对比.md)》
- 本域 [01_01 扩展点注册表补齐与统一装配](../../../01_扩展点与装配/01_扩展点与装配_01_扩展点注册表补齐与统一装配/01_扩展点与装配_01_扩展点注册表补齐与统一装配.md)（前置契约已交付）
- 本域 [01_02 宿主加载器运行时化与模块契约远端对接](../../../01_扩展点与装配/01_扩展点与装配_02_宿主加载器运行时化与模块契约远端对接/01_扩展点与装配_02_宿主加载器运行时化与模块契约远端对接.md)（**前置契约已交付**：加载器接口 / 清单结构与拒绝口径 / 宿主装配与消费接线；本任务只替换入口通路，接口与清单结构不变）+ 其[实施记录](../../../01_扩展点与装配/01_扩展点与装配_02_宿主加载器运行时化与模块契约远端对接/实施/01_实施_01_扩展点与装配_02_宿主加载器运行时化与模块契约远端对接.md) §6 遗留
- 后续任务 [`02_02` 依赖共享与版本偏斜治理](../../02_运行时加载_02_依赖共享与版本偏斜治理/02_运行时加载_02_依赖共享与版本偏斜治理.md)（`shared` 治理边界）
- 《[微前端 · Module Federation 官方文档](https://module-federation.io/)》与 `@module-federation/vite` 仓库 README（Vite 8 / Rolldown 适配与 `hostInitInjectLocation`、动态远端能力）
- 《[测试规范](../../../../../../规范/测试规范.md)》§5「用例管理」、《[Kiwi TCMS 部署使用说明](../../../../../../资料/开发服务器/linux/KiwiTCMS部署使用说明.md)》§5.3

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

# 01 测试 · Module Federation 接入与模块独立构建

> 前端插件化 · 02 运行时加载 · 子任务 01（需求 05-3）· 测试记录

[文档首页](../../../../../../文档首页.md) › [02 运行时加载](../02_运行时加载_01_ModuleFederation接入与模块独立构建.md) › 测试记录　|　[← 实施记录](../实施/01_实施_02_运行时加载_01_ModuleFederation接入与模块独立构建.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 Module Federation 接入与模块独立构建](../02_运行时加载_01_ModuleFederation接入与模块独立构建.md) |
| 对应需求 | [05-3](../../../../需求/02_需求_运行时加载.md#r05-3) |
| 详细设计 | [01 详细设计](../设计/01_详细设计_02_运行时加载_01_ModuleFederation接入与模块独立构建.md) |
| 实施记录 | [01 实施](../实施/01_实施_02_运行时加载_01_ModuleFederation接入与模块独立构建.md) |
| 测试日期 | 2026-09-21 |
| 测试人 | minjian |
| 测试环境 | 本地开发机（Node v24.20.0 / Vitest 5.0.1 / jsdom；模块与宿主构建产物经 `vite preview` 实跑验证） |
| Kiwi 用例 | **978**（分类「平台骨架」/ P2 / CONFIRMED / 标签「自动化」；一任务一条） |
| 结论 | 通过（core 93 文件 / 1158 用例、vue 2 / 5、ui-ep 61 / 901、宿主 13 / 53、模块工程 1 / 4 全绿；宿主与模块构建 + 体积预算、端到端运行时加载、基座与链接校验、CI 配置校验全部通过） |

## 2. 测试范围与用例 <a id="scope"></a>

| 用例组 | 类型 | 自动化文件 | 覆盖点 |
| --- | --- | --- | --- |
| 清单加载形态（新增） | 单元 | `core/tests/module-manifest.spec.ts` | 形态缺省归一为 `local`；显式 `local` / `remote` 保留；形态取值非法该项拒绝；`mode: remote` 而入口为相对路径 / 源码标识**该项拒绝**（原因明示）；重名口径与既有断言不变 |
| 入口解析器注入（改造） | 单元 | `core/tests/module-loader.spec.ts` | 同一 `ManifestModuleLoader` 承接本地与远端两类解析器（调用序列同结果）；本地入口标识未登记抛 `PROVIDER_NOT_REGISTERED`；**解析器抛错原样上抛**（远端不可达不吞错、不自造错误）；校验链不因解析器而变（缺默认导出 / 名称或版本不一致拒绝加载）；挂载 / 卸载幂等与重复挂载拒重；远端约定常量与入口 URL 拼接成文 |
| 本地入口解析器（承接替代旧加载器） | 单元 | `core/tests/module.spec.ts` | `defineModule` 校验与冻结（不变）；`createModuleEntryTableResolver` 命中返回入口模块（懒加载表按次调用）、未登记报未注册不可用（原 `LocalModuleLoader` 断言改写为解析器断言） |
| 远端入口解析器（新增） | 单元 | `apps/desktop/tests/module-federation.spec.ts` | 按清单条目登记容器（`name` / `entry` / `type: module`，`{ force: true }`）并按 `<模块名>/module` 加载；重复解析幂等（重登记覆盖）；**远端不可达错误原样上抛**；容器返回空时返回空模块对象（形状校验交加载器）；远端约定常量（入口文件名 / 暴露键 / 演示 origin） |
| 宿主按形态分派与全链路（改造） | 集成 | `apps/desktop/tests/module-hosting.spec.ts` | 清单未装载时挂载拒绝；按清单挂载远端模块 → **运行期登记与加载调用契约** → 动态路由生效 → 菜单取注册表快照 → 卸载无残留；消费接线成对（令牌 / 文案 / 区域项）；**两形态共存**（`remote` 走 MF 运行时、`local` 走本地入口表且未登记即拒绝）；版本不匹配 / 远端不可达 / 清单缺字段项拒绝加载并记错误状态；装配冲突回滚本次接线 |
| 统一装配通道（承接 976，改造） | 集成 | `apps/desktop/tests/module-registration.spec.ts` | 装配前不可解析 → 装配后可用（八类，含字段渲染器）→ 卸载后回到不可解析；命名空间越权拒绝；校验失败零登记与登记键可逆序清理；路由声明（无标题不登记） |
| 清单获取（承接 977，扩写） | 集成 | `apps/desktop/tests/module-manifest.spec.ts` | 三字段齐全按清单序返回并**归一形态**；远端形态条目按绝对入口 URL 通过、相对路径被拒；HTTP 失败 / 非数组 / 网络异常按空清单与原因返回；获取失败不阻塞启动 |
| 模块定义契约（新增） | 单元 | `modules/demo/tests/module-definition.spec.ts` | 默认导出模块定义并冻结、清单名与版本与宿主清单条目一致；路由一律懒加载（`component` 为函数）、路径前缀与标题；**八类声明通道齐全**且键带模块命名空间前缀；区域标识点分、文案包语言标识小写、令牌使用 `--bms-*` 变量 |
| 模块产物计量与分包（脚本断言） | 构建产物 | `modules/demo/scripts/check-bundle-budget.mjs` | 容器入口 `remoteEntry.js` 存在；入口块**引用闭包** gzip 合计 / 单块不超阈值；入口块数不超上限（防分包退化）；入口闭包**不命中**页面块命名特征（`DemoHome` / `DemoToolbox`）；入口外异步块数不少于声明路由数 |
| 端到端运行时加载（需求完成标准 1 / 2） | 实跑 | 模块 `vite build` + `vite preview`（5002）与宿主 `vite build` + `vite preview`（4173） | 宿主经清单 `http://localhost:5002/remoteEntry.js` **运行期**加载独立构建产物；`/demo` 直连渲染远端模块页面、页头区域插槽渲染远端区域项、无 404；宿主产物内不含模块页面代码（**非构建期合并**） |

## 3. 执行记录与结果 <a id="run"></a>

```bash
# 根（core + vue + ui-ep：typecheck / lint / test）
cd bms && npm run check

# 宿主（PC）
cd frontend/apps/desktop && npx vue-tsc -b && npm run lint && npm run test:cov && npm run build && npm run budget

# 模块工程（独立构建 / 独立计量）
cd frontend/modules/demo && npm run typecheck && npm run lint && npm run test && npm run build && npm run budget

# 端到端（构建产物）：模块 preview 5002 提供独立产物，宿主 preview 4173 经清单运行期加载
cd frontend/modules/demo && npm run preview          # 5002
cd frontend/apps/desktop && npm run preview          # 4173
# 浏览器渲染 http://localhost:4173/demo（无头 Chromium dump-dom 取证）

# 文档与基座校验 / CI 配置
python3 scripts/tools/base-check/check-base.py
python3 scripts/tools/base-check/check-links.py
python3 scripts/tools/check-docs/check-status.py --stage 05_前端插件化 --strict
sh -n deploy/ci/build-base.sh   # 另以 YAML 解析校验 .gitlab-ci.yml 新增 job
```

```text
> core    93 files / 1158 tests passed
> vue      2 files /    5 tests passed
> ui-ep   61 files /  901 tests passed
> host    13 files /   53 tests passed；vue-tsc / lint / build 通过
> cov     host 语句 88.47% / 分支 80.19% / 函数 81.69% / 行 89.07%（module/federation.ts 100%，module/ 语句 100%）
> budget  宿主首屏合计 172.7 KB（预算 260 KB）；首屏最大单文件 76.6 KB（预算 150 KB）；宿主产物内不含模块页面代码
> module   1 file / 4 tests passed；typecheck / lint 通过
> module budget  容器入口闭包 8.8 KB / 6 块（预算 12 KB / 8 块 / 上限 8）；页面异步块命中 DemoHome / DemoToolbox
> e2e     模块产物（5002）+ 宿主产物（4173）实跑：/demo 渲染远端模块页面与页头区域项，404 计数 0
> base    清单一致 171 / 171；跨文档编号引用 0 处
> links   断链 0 / 失效锚点 0
> status  检查 95 项；硬规则不合规 0，软提示 0
> ci      build-base.sh 语法通过；.gitlab-ci.yml 解析通过（module-check / module-build 就位）
> kiwi    978 新建 1 / 跳过 0 / 失败 0
```

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 宿主共享 `element-plus` 后首屏超预算 2.5 倍（660.7 KB / 单块 334.5 KB） | 拍板收窄 `shared` 为框架三件并复跑预算（177.5 KB → 删除宿主内演示模块后 172.7 KB）；UI 组件库共享归 `02_02`，实施记录 §4 问题 1 留痕 |
| 2 | 远端加载报 `#RUNTIME-001 Failed to get remoteEntry exports` | 运行期登记补 `type: 'module'`；用例断言登记入参含该类型，常量成文 |
| 3 | 首屏直连 `/demo` 落兜底 404 | `main.ts` 路由安装后移至模块装载之后；端到端复测直连可命中（404 计数 0） |
| 4 | 宿主用例「按清单挂载远端模块」断言登记入参失败（缺 `type`） | 补断言字段（与 `module-federation.spec.ts` 同口径），用例全绿 |
| 5 | 模块工程用例首次类型检查失败（`bpmn-moddle` 悬空声明） | 模块工程补 `src/env.d.ts`（与 ui-ep / 宿主同口径）后通过 |
| 6 | 宿主测试环境无 MF 运行时常量 | MF 插件在测试环境**自动空转**（源码 `isTestEnv()` 直接返回空插件数组），用例以 `vi.mock('@module-federation/runtime')` 替身覆盖（并因此可断言登记与加载调用契约） |

## 5. 覆盖率 <a id="coverage"></a>

| 侧 | 语句 | 分支 | 函数 | 行 | 口径 |
| --- | --- | --- | --- | --- | --- |
| 宿主（`apps/desktop` `test:cov`） | 88.47% | 80.19% | 81.69% | 89.07% | 高于《测试规范》前端 70% 阈值；`src/module/` 语句与行 **100%**（`federation.ts` 四维 100%；`host.ts` 分支 81.81%，余为防御性回退分支） |
| 核心（`packages/core`） | — | — | — | — | 核心包门禁为 `core:check`（typecheck / lint / test），不含覆盖率采集（包内未安装 coverage 依赖），与既有口径一致 |
| 模块工程（`modules/demo`） | — | — | — | — | 模块侧门禁为 `typecheck` / `lint` / `test` + 构建产物断言脚本（`budget`）；未配覆盖率采集，用例覆盖模块定义契约与产物形态（覆盖率门禁如需，随 `04_01` 首个样例统一口径） |

## 6. 偏差与遗留 <a id="deviations"></a>

- **未覆盖项**：`shared` 版本偏斜与重复实例（`requiredVersion` / CI 实例数断言 / 升级契约）与 UI 组件库、平台基座包共享归 `02_02`（已完成）；清单唯一来源、版本发现、灰度 / 回滚归 `03_02`（已完成，生产部署侧清单归部署阶段）；远端入口缓存与 sourcemap、按模块归因归 `03_03`；模块样式隔离护栏归 `03_01`；远端不可达的网络级超时与降级 UI 由 `03_03` 承接（本任务只断言「错误原样上抛 + 拒绝加载 + 错误状态」）。
- **后续任务接收项**：① `02_02` 在框架三件 `shared` 之上补 `requiredVersion` 与实例数断言，并评估 `element-plus` 与基座包共享（实测结论见实施记录 §4 / §6）；② `03_02` 替换生产清单来源与远端入口地址（本任务为本地演示地址），加载器与清单结构不变（**已完成**：清单唯一来源 / 版本发现 / 发布回滚就位、演示清单指向版本目录；生产远端入口地址调整为部署阶段——部署侧清单）；③ `03_01` 补模块样式前缀与全局污染护栏；④ `04_01` 复用本任务落的模块工程脚手架（独立安装 / 独立构建 / 预算脚本 / 预览壳）开发首个样例模块。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》与《[测试规范](../../../../../../规范/测试规范.md)》编写

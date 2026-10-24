# RBAC 基础模块阶段测试报告

> BMS 基础管理系统 · 阶段七（RBAC 基础模块 · 权限与多租户可用）· 阶段末测试报告

[文档首页](../../文档首页.md) › [RBAC 基础模块总览](需求/00_需求_RBAC基础模块.md) › 测试报告　|　[需求 07-8](需求/05_需求_阶段验收.md#r07-8)　[05_01 任务](任务/05_阶段验收/05_阶段验收_01_阶段验收门禁核对与测试报告/05_阶段验收_01_阶段验收门禁核对与测试报告.md)

| 项 | 值 |
| --- | --- |
| 报告日期 | 2026-10-24 |
| 阶段范围 | 阶段七 17 条需求（域 01 插件化挂接 1 / 域 02 用户与角色 6 / 域 03 菜单与权限 3 / 域 04 租户与平台超管 1 / 域 05 阶段验收 1 / 域 06 布局样式 1 / 域 07 原型对照结论补齐 3 / 域 08 字典页布局对齐 1） |
| 阶段任务 | 18 项任务（含 11 个嵌套子任务，合计 29 个交付单元）全部完成（实际 2026-10-04 ~ 2026-10-24） |
| 数据来源 | 各任务测试记录与实施记录、本地收口当日命令快照、GitLab 流水线（项目 `bms/bms`）、Kiwi TCMS 平台、mdm 仓阶段一记录 |
| 编制方式 | 命令采集 + 文档断言用例（`backend/libs/bms_core/tests/crosscut/test_m7_closure.py`，Kiwi 2349）+ 人工汇总 |
| 依据 | 《[测试规范](../../规范/测试规范.md)》「测试报告」节、《[项目管理规范](../../规范/项目管理规范.md)》、《[RBAC 基础模块计划](计划/01_计划_RBAC基础模块.md)》 |

> **本轮特别说明**：收口核对发现**跨仓口径漂移**——mdm 于 2026-10-23 完成服务标识归并（`org` → `mdm`，mdm 阶段一 `01_05`，Kiwi 2348），bms 侧消费方仍按旧标识，导致主体链组织角色解析、分配写链、服务身份白名单与前端组织数据源在真实部署下**全部断链**。经 2026-10-24 拍板在本任务内**全量对齐修复**（含测试种子口径），门禁第 1 / 2 / 4 行以**修复后实测**下结论。详见 §2 与[实施记录](任务/05_阶段验收/05_阶段验收_01_阶段验收门禁核对与测试报告/实施/01_实施_01_阶段验收门禁核对与测试报告.md#issues)。

## 1. 用例执行统计 <a id="run"></a>

| 层次 | 工具 | 用例数 | 结果 | 说明 |
| --- | --- | --- | --- | --- |
| 后端收口断言（本任务） | pytest | 5 个断言函数 | 通过 | `test_m7_closure.py`：门禁 7 行结论与证据 / 计划收口自洽 / 报告归档节齐备 / 任务与域总览状态一致 / mdm 口径锁定（Kiwi 2349） |
| 后端口径修复定向（本任务） | pytest（SQLite 轻量库） | **837 passed / 1 skipped** | 通过 | `services/platform/tests` 全量 + `libs/bms_core/tests/ops`；含服务身份白名单、分配编排、种子与模块目录对账 |
| 后端各任务全量快照 | pytest | 见下「分域执行」 | 通过 | 各任务收口当日快照（`--cov-branch` 门禁同批输出） |
| 前端各包快照 | Vitest | core 1317 / ui-ep 987 / desktop 634（08_02 收口） | 通过 | 各任务收口快照；本轮复跑 ui-ep **72 文件全绿** |
| 前端宿主本轮复跑 | Vitest | **868 例（818 passed / 50 failed）** | 部分失败 | 失败集中在 3 份记录页 spec（`user-record-tab` / `menu-record-tab` / `user-assign-slot`），均为 Element Plus `ElTabPane` 运行时断言（`HEAD` 同样失败，非本轮引入），见 §4 第 45 项 |
| 模块工程（demo / sample） | Vitest | 15 / 25 | 通过 | 阶段六收口快照，本阶段无改动 |
| E2E（浏览器主流程） | Playwright | 未激活 | — | 前置为完整登录链路的应用账号与前端全页面（阶段十五）；本阶段以**原型逐页对照 + 真机截图**代偿（见 §5） |
| 文档校验（收口） | `check-status` / `check-links` / `check-base` / `preflight --fast` | 172 项 / 全绿 | 通过 | `check-status --stage 07_RBAC基础模块`：硬规则不合规 0、软提示 0 |

**分域执行（后端各任务收口快照）**：

| 域 | 任务 | 执行结果 |
| --- | --- | --- |
| 01 插件化挂接 | 01_01 | 具名插槽三文件 26 例 + 闭环段 4 判据真机通过（无代码交付） |
| 02 用户与角色 | 02_01 | 1990 passed / 50 skipped；合计覆盖率 95%（`users_admin` 93% / `user_sessions` 84%） |
| | 02_01_01 | `tests/users` 20 passed（契约快照 / 类型 / 基线三处 `dept_id` 零残留） |
| | 02_02 / 02_02_01 / 02_02_02 | desktop 296 passed / 49 文件；ui-ep 946 passed；mdm 37 passed；编排 4 passed；platform 454 passed / 1 skipped |
| | 02_03 / 02_03_01 / 02_03_02 | platform 404 / 1 skipped + 基座 1199；前端 ui-ep 944 / desktop 275 / core 1277；定向 7 passed；desktop 301 passed / 1 failed（既有，归阶段五 `05_14`） |
| | 02_04 | 23 例（引擎 / 端到端 / 字段权限 / 数据范围 / 种子）；后端全量 2113 passed / 51 skipped；平台 440 passed |
| | 02_04_01 ~ _04 | 三套件 2790 → 2911 → 2926 → 2947 passed（跳过 52~53）；定向 101 → 50 → 135 → 231 passed；覆盖率均 100% |
| | 02_05 | 基座 1200 / 48、platform+org 404 / 1、identity 288 / 1；搬迁脚本 9 passed |
| | 02_06 | `tests/users` 14 passed（`dept_id` 口径已由 2275 修订） |
| 03 菜单与权限 | 03_01 | 后端 1526 passed / 38 skipped；ui-ep 933 / desktop 243 / core 1274 |
| | 03_02 | 520 passed（含异常全量参数化 100 例）；种子 5 passed；覆盖率 100%（1784 语句 / 416 分支） |
| | 03_03_01 / 03_03_02 | 前端各 8 / 10 文件全通过；后端定向 60 passed；覆盖率四项 100% |
| 04 租户与平台超管 | 04_01 | 后端 3275 passed / 57 skipped；前端 680 passed；后端 100%（46 模块）、前端四项 100% |
| 06 布局样式 | 06_01 | ui-ep 931 / desktop 235 / core 1274；补修后 935 / 261 / 1277 |
| 07 原型对照补齐 | 07_01 / 07_02 / 07_03 | 纯文档交付；门禁命中 58 份全部补齐，末批**零命中**且 `preflight` 该项**首次转绿** |
| 08 字典页布局对齐 | 08_01 / 08_02 | 后端 8 passed；host 634 例 / 77 文件；ui-ep 987；后端聚合 2651 passed / 51 skipped |

**Kiwi 策展用例（本阶段新增与复用，均已回读核验存在）**：

| 域 | Kiwi 编号 | 覆盖 |
| --- | --- | --- |
| 01 插件化挂接 | 不新增（引用阶段五 2260 / 2280） | 具名插槽消费与依赖登记、mdm 插件真挂接与缺失即隐藏 |
| 02 用户与角色 | 2270 / 2275 / 2276 / 2277 / 2278 / 2248 / 2267 / 2283 / 2284 / 2269 / 2320 / 2321 / 2323 / 2324 / 2247 / 2257 | 用户完整域、出口字段收口、用户管理前端与分配页签、保存编排端点、角色管理与角色码可改、角色分配插件编排、主体链权限引擎与四项沉子任务、账号归口平台、平台用户只读出口 |
| 03 菜单与权限 | 2242 / 2314 / 2338 / 2339 | 菜单/表单/按钮/字段挂接与动态菜单、三权分立与平台超管边界、菜单表单维护页、业务/动作/权限码与图标维护页 |
| 04 租户与平台超管 | 2325 | 租户开通 / 停用 / 配额 / 模块开关 / 平台租户登录 |
| 05 阶段验收 | 2349 | 本任务：门禁核对 / 报告归档 / 状态一致 / mdm 口径锁定 |
| 06 布局样式 | 2241 | 布局族 18 件样式与令牌消费 |
| 07 原型对照补齐 | 不登记（纯文档交付，需求 07-12 ~ 07-14 口径） | 58 份记录补「原型对照结论」 |
| 08 字典页布局对齐 | 2293 / 2294 | 清单显式 `kind` 与按 `kind` 套骨架、现有记录页对齐 |

**CI 侧执行**：阶段七推送窗口（2026-10-03 ~ 2026-10-23）流水线 **#562 ~ #1240 共 278 条**——**skipped 168**（推送带 `-o ci.skip` 的免跑条目）/ success 40 / failed 62 / canceled 8。失败岗位分布（62 条失败流水线内）：`backend-test` 15、`desktop-check` 9、`base-integrity` 9、`core-check` 8、`desktop-build` 7、`backend-typecheck` 7、`txn-2pc` 5、`module-check` 4、`contract-smoke-tenant` / `contract-gate` / `integration-dm8` 各 3、`contract-smoke-identity` / `contract-smoke-platform` 各 2、`dependency-scan` / `contract-smoke-file` / `integration-mysql` / `shared-deps-check` / `ci-queue-acquire` / `api-types-check` / `module-build` / `backend-lint` 各 1。失败均为**实施期中间推送并在同一任务内转绿**；收口阶段以本地预检为唯一放行依据（推送默认 `-o ci.skip`）。

## 2. 缺陷统计 <a id="defect"></a>

| 项 | 数量 | 说明 |
| --- | --- | --- |
| 新增缺陷（自动捕获，累计） | **124**（`defect-auto`） | 阶段七窗口内新增 **62** 条（iid **64 ~ 132**，含跳号） |
| 开放缺陷（自动捕获，累计） | **77** | 收口查询 `state=all` 得 124 条，其中 opened 77 / closed 47 |
| 新增缺陷（人工 / UAT） | 0 | 阶段内无人工上报缺陷（UAT 未进入） |
| 新增缺陷（收口核对发现并当天修复） | **3** | ① 跨仓口径漂移（mdm `org` → `mdm` 后 bms 侧未同步，主体链 / 分配链 / 白名单 / 前端出口四处断链）——已修；② 平台测试种子未含产品清单行（接库对账「库中缺登记行：mdm」致平台用例整批 setup 失败）——已修；③ 模块目录用例写死 17 行与旧 `org` 键——已改为按登记清单断言 |
| 过程问题处置 | 若干 | 均在任务实施 / 测试记录 §4 留痕，非产品缺陷 |

**代表性过程问题**（详见各任务实施记录）：

| 问题 / 现象 | 落点 |
| --- | --- |
| 权限计算实现落在服务包，其余服务 `require_permission` 恒放行 → 立项需求 `07-16` 下沉基座 | 02_04/_01 ~ _04；04_01 前置 |
| 数据权限值列表 `IN` 在百万级集合下不可承受 → 集合按规则物化共享 + 容量淘汰 | 02_04/_03 |
| 角色码可改与内置判定脱钩（内置判定改按 `role_type` 列） | 02_03/_01 |
| 用户/角色分配须与宿主「单一保存」同帧提交 → platform 编排端点（`provider=xa` 走 TM、`null` 走顺序提交） | 02_02/_02、02_03/_02 |
| `ui-ep` 布局族 18 件无样式（阶段四~六漏检）→ 补需求 `07-9` 先行交付 | 06_01 |
| 原型对照结论机器门禁命中 58 份历史记录 → 补需求 `07-12` ~ `07-14` 分批补齐 | 07_01 ~ 07_03 |
| 菜单/表单/业务码/动作码/权限码/图标维护页长期未立项（入口兜底占位）→ 补需求 `07-17` | 03_03/_01、_02 |
| 用户-部门关系归 mdm 且需「主要项」语义 → 补需求 `07-11`；`sys_user` 不落组织字段 | 02_01/_01、mdm 01_02/_02 |
| 跨仓口径漂移（本轮）：mdm `01_05` 服务标识归并后 bms 侧未同步 | 本任务（§4 第 44 项） |

> 自动缺陷单不随修复自动关闭（`defect-capture` 只建单 / 追加评论，关闭须人工，《测试规范》§9）；依本任务决策项 13，**只登记计划 §7 归口，不擅自处置**。

## 3. 覆盖率 <a id="coverage"></a>

| 口径 | 数值 | 说明 |
| --- | --- | --- |
| 本轮变更源文件（定向门禁） | **100%（行 + 分支）** | `services/platform`：`permission_subject` 58 语句 / 14 分支、`user_assignments` 327 / 122、`role_assignments` 274 / 106、`api/internal_users` 48 / 2、`api/internal_config` 14 / 0 全部 100%；`ops/seed_menu` / `ops/seed_module` 变更行全覆盖（`ops/seed_module` 98%，余 1 行为 `__main__` 守卫，与 02_05 同口径） |
| 后端（02_04_01 ~ _04） | **100%** | 每文件逐项列出（5 ~ 7 文件，行 + 分支） |
| 后端（03_02） | **100%**（1784 语句 / 416 分支） | 10 模块逐个 100% |
| 后端（04_01） | **100%**（46 模块） | 3275 passed 同批输出 |
| 后端（03_03_01 / _02、08_01、08_02） | **100% ×4 项** | 行 / 分支 / 函数 / 语句 |
| 前端（宿主 `@bms/desktop`、07_03 / 08_01 / 08_02） | **100% ×4 项** | 77 文件 628 ~ 634 例同批输出 |
| 后端（02_01） | **95%**（`users_admin` 93% / `user_sessions` 84%） | 任务内快照；剩余缺口为分支防御与可选参数展开，未在后续任务纳入（**口径差异**，见下注） |
| 后端（02_05 搬迁脚本） | **99%**（158 语句） | 余 1 行为 `__main__` 守卫 |
| 未量化的任务 | 02_01_01 / 02_02 / 02_02_01 / 02_02_02 / 02_03 / 02_03_01 / 02_03_02 / 02_04 / 02_06 / 03_01 / 06_01 | 收口时按定向执行、未产出全量数值；02_03 明示「全量覆盖率报表随阶段收口产出」，本轮按决策项 3 以「变更源文件定向 100% + 引用既有快照」呈现，**未现场重跑全量** |

> **口径说明（决策项 3）**：本轮不现场重跑全量后端 / 前端覆盖率（《AI开发规范》「本地不缺省跑全量」），只对本次变更源文件跑 100% 门禁；其余引用各任务已归档快照。**存量差异**（02_01 的 95% 与 10 个未量化任务）如实登记为遗留口径差异，不折算为「已达标」；如需全量报表，另行显式发起一次全量档。

## 4. 风险与遗留项 <a id="risk"></a>

以[计划 §7「后续阶段待办」](计划/01_计划_RBAC基础模块.md#followup)为**唯一台账**（46 行，编号保持既有口径、不重编号，决策项 9）。按去向分组汇总：

| 去向 | 条数 | 代表事项 |
| --- | --- | --- |
| 已交付 / 已闭环 | 14 | mdm 组织域实施、自定义图标管理、布局族样式、具名插槽上下文注入、用户与账号表迁归 platform、权限配置内容件、菜单管理维护页、角色码可改、用户-部门多分配、`session.codes` 根因、权限计算下沉基座、mdm 前置（`01_02/_04`）、跨仓口径对齐、测试种子口径 |
| 后续阶段（阶段八 / 十 / 十五 / 十七 / 品牌化 / 工作流 / 审计 / 开放平台 / 可观测性） | 22 | 会话管理页与个人中心、操作与登录日志、字段展示类组件回补、Excel 导入导出、日志归档执行器、开放接口调用量计数、进行中流程与模块停用关系、平台业务页权限消费、深色适配、模块服务白名单、事件总线订阅、可观测性出口 |
| 各业务模块 / 各服务按需接入 | 4 | 数据范围消费侧 `scope_columns` 接线、其余服务仍走 `null` 占位、`/form-keys` 不含 `menu`/`form`、菜单树键盘调序 |
| 部署联调 / 运维窗口 | 4 | 三库真库建库与迁移、已部署库重跑种子（含模块目录 / RBAC / 菜单）、网关与真机联调、前端切址联合验收 |
| 设计口径（无动作） | 2 | `item_code` 存量不批量迁移、阈值改动需重启并重建缓存仓 |

**本轮新增 / 调整**：

| # | 事项 | 处置 |
| --- | --- | --- |
| 44 | **跨仓口径漂移**：mdm `01_05` 归并服务标识 `org` → `mdm` 后，bms 侧解析器服务键 / 只读出口路径、分配内部写通道与 XA 分支 `op`、服务身份白名单、权限码种子、前端产品命名空间仍按旧口径 | **已闭环（2026-10-24）**：全量对齐 + `test_m7_closure.py` 口径锁定断言；真实联调仍归部署窗口 |
| 45 | 平台测试种子未含产品清单行（`ops.seed_module` 只播种平台静态清单）→ 装配含产品行时接库对账报「库中缺登记行」 | **已闭环（2026-10-24）**：种子改为「平台清单 + 已装载产品清单」合并视图；`test_modules.py` 改按登记清单断言 |
| 46 | 前端宿主 3 份记录页 spec（50 例）因 Element Plus `ElTabPane` 运行时断言失败（`HEAD` 同样失败） | 登记归口：前端组件库 / 依赖版本核对（CI Linux 口径为准） |

**台账说明**：46 行逐条给出影响与去向，**无「无归口」条目**；闭环项标注闭环时间与落点；同号重复项按既有编号保留并在计划 §7「台账说明」消歧。

## 5. 界面交付 ↔ 原型 / 布局一致性 <a id="ui"></a>

阶段七含大量界面交付，按《[测试规范](../../规范/测试规范.md)》§12 与《[原型审查规范](../../规范/原型审查规范.md)》§4.9 单列核对结论（原型即验收基准）：

| 任务 | 界面范围 | 原型依据 | 对照方式与结论 |
| --- | --- | --- | --- |
| 06_01 | 主框架外壳与布局族 18 件样式 | `设计/布局设计/` + `设计/原型设计/02_公共原型/` | 件族截图逐件对照；**通过**（令牌消费无硬编码色值；标签栏形态差异登记为「不逐像素一致，不修」） |
| 02_02 / _01 / _02 | 用户列表 / 记录页（详细信息、用户分配、系统信息）/ 账号锁定页 | `设计/原型设计/08_用户管理/`（2026-10-09 迭代） | 真机 dev server + Playwright 视口 1440×900 逐页比对；**通过**（空态文案缺口已补并闭环） |
| 02_03 / _01 / _02 | 角色列表 / 角色表单 / 角色记录页（权限配置、角色分配） | `设计/原型设计/09_角色管理/` | 逐页截图对照；**通过**（权限配置空态偏离 1 项已由 `08_04` 闭环） |
| 03_03_01 / _02 | 菜单表单维护页、业务码 / 动作码 / 权限码 / 图标页 | 原型迭代两页（2026-10-21 补） | 逐页对照（含树拖拽、补生成、SVG 上传）；**通过**（6 项增强为原型未覆盖的补生成，已登记） |
| 04_01 | 租户列表 / 租户记录 / 开通弹窗 / 平台租户登录 / 配额与模块开关 | `设计/原型设计/25_租户管理/` | **真机截图 5 页逐页对照**；**通过**（2026-10-20 闭环） |
| 08_01 / 08_02 | 字典记录页骨架（角色 / 用户记录页对齐） | `设计/布局设计/17_布局设计_字典页.html` | 骨架件挂载断言 + 首行三字段与系统信息区核对；**通过**（`State` 下拉差异按 17 §3 三选判定为非偏离） |
| 07_02 / 07_03 | 58 份历史测试记录的「原型对照结论」补齐 | 组件设计自带原型 / 页面原型 | 组件类 11 份 + 页面类 8 份补节；**末批零命中、门禁首次转绿**；4 项实现偏离就地修复（分类列枚举键 / 空态英文 / 端点权限码串 / 雪花 ID 精度） |
| 01_01 | mdm 插件经 `sys.user.detail.tabs` 真挂接 | 用户管理页原型「用户分配」页签 | 缺失即隐藏 + 在场渲染两态真机验证；**通过**（2026-10-09 闭环） |

**结论**：界面类交付**无缺失页面、无裸骨架、无实现命名泄漏**；全部界面任务均有原型依据与对照结论，机器门禁 `check-prototype-review.py` 在 `preflight --fast` 中通过。

## 6. 复盘与经验教训 <a id="retro"></a>

| # | 经验 / 教训（已发生的事实） | 已固化的改进项 |
| --- | --- | --- |
| 1 | **跨仓标识变更必须双向核对**：mdm 归并服务标识只改了自身仓，bms 侧四类消费点（服务键 / 路径 / `op` / 白名单 / 前端命名空间）全部静默断链，且因降级路径存在，**运行时表现为「权限少一半」而非报错**——直到阶段收口才暴露 | 本任务补 `test_m7_closure.py::test_mdm_alignment_lockdown` 口径锁定断言（源码文本级护栏）；产品标识变更纳入跨仓验收清单，接收方须在同一批次内对齐 |
| 2 | **测试种子要与装配视图同源**：种子只播种平台静态清单，而装配视图含产品清单行，接库对账直接拒启；此类缺口在「推送不跑 CI」的节奏下可潜伏很久 | `ops.seed_module` 改为「平台清单 + 已装载产品清单」合并视图；模块目录用例不再写死行数，改按登记清单断言 |
| 3 | **门禁结论必须落在计划、报告只做汇总**：门禁表由计划承载（`check-status` 可校验），报告引用证据索引，避免两处维护漂移 | 本轮沿用阶段六口径：计划 §5 内联结论 + 门禁对照表；`test_m7_closure.py` 断言「需求总览不承载门禁表」 |
| 4 | **界面漏检会被机器门禁补回来**：布局族 18 件无样式一路通过阶段四 / 五 / 六验收，直到 `03_01` 前置排查才暴露 | 原型对照结论成为测试记录固定节 + `check-prototype-review.py` 机器门禁；58 份历史记录补齐后门禁转绿 |
| 5 | **高风险能力的「可证」比「有实现」更重要**：权限、数据范围、字段权限、三权、配额均以「从严拒绝 + 越界永假 + 前置校验」写用例，而不是只测正路径 | 各域用例覆盖拒绝路径与降级路径；本报告门禁每行均给可复现用例文件与 Kiwi 编号 |
| 6 | **降级路径会掩盖断链**：`OrgRoleResolver` 对跨服务异常一律降级为空集（仅告警），断链不报错 | 严格模式 `require_roles` 保留；口径锁定断言在 CI 侧显式失败，不依赖运行期告警 |
| 7 | **收口核对要「以平台与代码为准」而非以文档为准**：本轮以 mdm 仓实际契约（`deploy/contracts/mdm.json`、`branch_handlers.py`）对照 bms 代码，才发现四处漂移 | 收口动作清单固定为「外部契约对照 + 本仓代码扫描」，结论写进报告 §2 与计划台账 |

## 附录 A 数据采集命令与原始输出 <a id="appendix"></a>

```bash
# 1) 后端收口断言用例（本任务；Kiwi 2349）
$ cd backend && uv run pytest libs/bms_core/tests/crosscut/test_m7_closure.py -q
5 passed

# 2) 后端口径修复定向（含服务身份白名单 / 分配编排 / 种子与目录对账）
$ python ../scripts/tools/preflight/run-once.py -- uv run pytest services/platform/tests libs/bms_core/tests/ops \
    --cov=bms_platform --cov=ops --cov-branch --cov-report=term-missing -q
837 passed, 1 skipped in 179.40s
services/platform/src/bms_platform/services/permission_subject.py     58      0     14      0   100%
services/platform/src/bms_platform/services/user_assignments.py      327      0    122      0   100%
services/platform/src/bms_platform/services/role_assignments.py      274      0    106      0   100%
services/platform/src/bms_platform/api/internal_users.py              48      0      2      0   100%
services/platform/src/bms_platform/api/internal_config.py             14      0      0      0   100%
ops/seed_module.py                                                    97      1     28      1    98%   # 余 __main__ 守卫

# 3) 静态检查（变更文件定向）
$ uv run ruff check ops libs/bms_core/tests/crosscut/test_m7_closure.py services/platform
All checks passed!
$ uv run ruff format --check ops libs/bms_core/tests/crosscut/test_m7_closure.py services/platform
225 files already formatted
$ uv run pyright ops/seed_module.py ops/seed_menu.py libs/bms_core/tests/crosscut/test_m7_closure.py \
    services/platform/src/bms_platform/api services/platform/src/bms_platform/services/permission_subject.py \
    services/platform/src/bms_platform/services/user_assignments.py \
    services/platform/src/bms_platform/services/role_assignments.py services/platform/tests/api/test_modules.py
0 errors, 0 warnings, 0 informations

# 4) 契约与模块清单
$ uv run python -m ops.contract_snapshot export    # 重导出（platform.json 描述串随白名单口径变更）
$ uv run python -m ops.contract_snapshot check
[contract_snapshot] 通过：9 个启用服务快照与公开契约一致
$ uv run python -m ops.check_contracts
[契约] 校验通过（9 个服务：实现路由全部进入契约，不可见路由均在白名单，公开契约无空 schema 且引用型响应 schema 可解析）
$ uv run python -m ops.gateway_config check
[gateway_config] 通过：deploy/gateway/apisix.yaml 与服务目录一致、服务发现无硬编码 IP、请求体上限三方一致
$ uv run python -m ops.check_modules
[服务目录] 库中无登记行（种子未执行？）→ 校验失败（1 项）   # 本地开发库未执行 seed_module，归部署窗口（计划 §7 第 35 项）

# 5) 前端（受影响包）
$ pnpm --filter @bms/ui-ep run typecheck      → Done
$ pnpm --filter @bms/ui-ep run test           → 72 文件全通过
$ pnpm --filter @bms/desktop run test         → 868 例 / 818 passed / 50 failed（3 份记录页 spec，ElTabPane 断言，HEAD 同样失败）

# 6) 文档与基座自检（仓库根）
$ python scripts/tools/check-docs/check-status.py --stage 07_RBAC基础模块
[07_RBAC基础模块] 检查 172 项：硬规则不合规 0，软提示 0
$ python scripts/tools/base-check/check-base.py        # base-integrity：通过
$ python scripts/tools/base-check/check-links.py       # 断链 0 处 / 失效锚点 0 处
$ python scripts/tools/base-check/check-docs-scope.py  # 违规 0 处
# 注：preflight 的 `{python}` 占位符取**运行 preflight 的解释器**——用仓内 venv 解释器运行方全通过；
#     系统 Python 缺 `sqlalchemy` 时「网关」步骤误报（环境类，计划 §7 第 36 项）
$ backend/.venv/Scripts/python.exe scripts/tools/preflight/check-preflight.py --fast
全部通过

# 7) 流水线（GitLab 项目 bms/bms，阶段七窗口 2026-10-03 ~ 2026-10-23）
#   #562 ~ #1240 共 278 条：skipped 168 / success 40 / failed 62 / canceled 8
#   失败岗位：backend-test 15、desktop-check 9、base-integrity 9、core-check 8、desktop-build 7、
#             backend-typecheck 7、txn-2pc 5、module-check 4、contract-smoke-tenant/gate/dm8 各 3、
#             contract-smoke-{identity,platform} 各 2，其余 8 岗位各 1

# 8) 缺陷查询（GitLab API，项目 2，labels=defect-auto）
$ python tmp/gl_evidence.py
defect-auto 总数 124，阶段七窗口内新增 62（iid 64 ~ 132），累计开放 77

# 9) Kiwi 平台用例核对（阶段七引用编号）
$ python tmp/kiwi_check.py
MISSING []   # 2241 / 2242 / 2247 / 2248 / 2257 / 2267 / 2268 / 2269 / 2270 / 2272~2278 / 2283 / 2284 /
             # 2293 / 2294 / 2314 / 2320 / 2321 / 2323 / 2324 / 2325 / 2338 / 2339 / 2340 / 2348 / 2349 均在平台
```

> 本报告依《[文档生成规范](../../规范/文档生成规范.md)》与《[测试规范](../../规范/测试规范.md)》「测试报告」节编写 · 数据快照 2026-10-24

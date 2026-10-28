# 01 实施记录 · engkit 产品字面量规则

> 跨产品协同 · 04 护栏与 CI · 子任务 01（需求 04-1）

[文档首页](../../../../../../文档首页.md) › [01 engkit 产品字面量规则](../04_护栏与CI_01_engkit产品字面量规则.md) › 实施记录　|　[详细设计 →](../设计/01_详细设计_01_engkit产品字面量规则.md)　[测试记录 →](../测试/01_测试记录_01_engkit产品字面量规则.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 engkit 产品字面量规则](../04_护栏与CI_01_engkit产品字面量规则.md) |
| 对应需求 | [04-1 产品字面量护栏](../../../../需求/04_需求_护栏与CI.md#r04-1) |
| 详细设计 | [01 详细设计_01 engkit 产品字面量规则](../设计/01_详细设计_01_engkit产品字面量规则.md)（定稿含 10 项决策与 12 条对齐记录） |
| 实施日期 | 2026-10-28 |
| 实施人 | minjian |
| 实施环境 | Windows 开发机；Python 3.14 + uv；engkit 以路径探测 / 平级克隆接入 bms |
| Kiwi 用例 | **2362**（一条用例承载 20 条断言，用例文本列覆盖范围） |
| 涉及仓 | `engkit`（规则与自测）、`bms`（配置 / 薄包装 / 首版基线 / 预检与 CI 接入 / 需求回写） |
| 结论 | 规则交付完成：engkit **547 项用例全绿、覆盖率 100%（行 + 分支）**；bms 预检秒级档全通过；首版基线 149 条 |

## 2. 决策确认 <a id="decisions"></a>

实施前逐项确认 **10 项**（结论已回写设计 §7 决策记录），实施期又因实测数据补 **2 项**：

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 注释 / docstring 是否计入 | 计入，独立开关 `include_comments`（缺省 true） |
| 2 | 标识清单来源 | 配置静态清单；**本期只配 `mdm`**（见 §5 第 1 项） |
| 3 | 能力名等契约级标识放行 | 路径白名单（`allow_globs` 含 `platform/capabilities.py`） |
| 4 | 基线落点与形态 | `deploy/boundaries/product_literals_baseline.json`，路径 + 内容指纹 + 计数 |
| 5 | 接入档位 | 预检秒级档 + CI `base-integrity` 作业 |
| 6 | 基线递减约束 | 机器断言只减不增（`--baseline-ref origin/main`） |
| 7 | 扫描面 | 前后端源码，排除生成物（`exclude_globs`） |
| 8 | 子命令与产品仓用法 | `engkit base product-literals`；本期只服务平台仓 |
| 9 | 配置段位置 | `[rules.product_literals]`（与既有校验器一致） |
| 10 | 匹配大小写 | **区分大小写**（见 §5 第 2 项） |
| 11 | 命令挂载（实施期修正） | 由设计初稿的顶层命令改挂 `base` 下，复用 `require()` / `--self-test` / `--update-baseline` |
| 12 | 基线形态（实施期确认） | 首版基线 149 条，生成物零命中，排除面生效 |

## 3. 交付内容 <a id="delivered"></a>

### 3.1 engkit <a id="engkit"></a>

| # | 文件 | 内容 |
| --- | --- | --- |
| 1 | `src/engkit/base/product_literals.py` | 规则本体：glob 编译 / 扫描根派生 / 注表面掩码（Python `tokenize` + `ast`；TS / JS / Vue 状态机）/ 词边界与组合后缀判定 / 基线读写 / 只减不增比较 / 20 条断言的内置自测 |
| 2 | `src/engkit/config.py` | `ProductLiteralsRules` 数据类 + `_parse_product_literals_rules`（严格键校验、`literals` 非空）+ `[rules]` 键集登记 |
| 3 | `src/engkit/cli.py` | `base` 子命令表登记 `product-literals`，新增 `--baseline-ref`，复用 `--self-test` / `--update-baseline` / `--json` |
| 4 | `src/engkit/gitutil.py` | 新增 `read_at(root, ref, rel)`：读某引用下的文件（基线只减不增断言用） |
| 5 | `tests/test_product_literals.py` | 42 项用例：配置解析正反、glob 形态、注表面、基线格式、只减不增、`run` 各分支、`read_at` 真实 git 仓 |
| 6 | `tests/test_cli.py` | CLI 分派用例（命中退 1 / 自检退 0） |
| 7 | `engkit文档/概述/工程化工具包说明.md` | 子命令表、`[rules.product_literals]` 字段全表、规则口径段 |

### 3.2 bms <a id="bms"></a>

| # | 文件 | 内容 |
| --- | --- | --- |
| 1 | `engkit.toml` | `[rules.product_literals]` 段（禁入 / 允许 / 排除面、`literals = ["mdm"]`、基线 + 基准 ref）+ 预检步骤 + 自测步骤 |
| 2 | `scripts/tools/base_check/check_product_literals.py` | 薄包装（参数转发 + 退出码透传，无推导逻辑） |
| 3 | `deploy/boundaries/product_literals_baseline.json` | 首版基线 149 条（110 个文件） |
| 4 | `.gitlab-ci.yml` | `base-integrity` 作业增加规则与自测两行 |
| 5 | `需求/04_需求_护栏与CI.md` | 需求 04-1 第 2~4 条措辞回写（注释计入、区分大小写、基线只减不增） |

## 4. 验证结果 <a id="verify"></a>

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| engkit 用例 + 覆盖率 | `uv run python -m pytest -q --cov=src/engkit --cov-branch --cov-fail-under=100` | **547 passed**；覆盖率 **100%**（行 6713 / 分支 2578，均 0 缺失） |
| engkit 静态 | `uv run ruff check .` / `ruff format --check .` / `pyright` | 全通过 / 64 文件已格式化 / 0 error |
| engkit 自举 | `engkit preflight --fast` | 通过（随 bms 预检同批验证） |
| bms 预检（秒级档） | `run_once -- check_preflight.py --fast` | **全部通过**（含新增步骤与自测） |
| 规则实跑 | `check_product_literals.py .` | 通过：检查 1533 个文件（排除 12 / 允许 908），命中 149 处全部在基线；`origin/main` 上尚无基线文件故只减不增断言告警跳过（见 §6） |

## 5. 问题与处置 <a id="issues"></a>

| # | 问题 | 处置 |
| --- | --- | --- |
| 1 | 首版基线按 `mdm` + `biz` + `cw` 生成得 326 条，其中 `biz` 命中 164 处**全是 `biz_type` / `biz_id` / `biz_error` 等通用命名** | 上报用户确认：**本期只配 `mdm`**；`biz` / `cw` 随产品真正接入时登记（接入流程已要求登记 `literals`）；基线重生成 149 条 |
| 2 | 大小写不敏感把 `frontend/packages/ui_ep/src/assets/maps/china.ts` 地图坐标串里的 `Cw` 判成产品标识 | 上报用户确认：改为**区分大小写**（产品键恒小写）；补用例 `test_scan_source_case_sensitive` |
| 3 | 首次预检 3 项失败：`engkit.toml` 被追加内容写入 CRLF；设计文档出现进度类字段字样（违反「进度只落计划表」口径）；以节号引用《AI开发规范》被 `check_base` 判跨文档编号引用 | `engkit eol --fix` 修行尾；设计文档改写为「与计划表登记值一致」「实施时…」；引用改为章节名「编号对齐」 |
| 4 | 只减不增断言在首版基线提交前必然告警（`origin/main` 上还没有该文件） | 按设计「ref 或文件不可解析即告警不跳过失败」处理；推送后自然生效，已在 §6 登记 |
| 5 | `uv run pytest` 在嵌套调用时报 uv 缓存目录拒绝访问（`sdists-v9/.git`） | 改用 `uv run --no-sync python -m pytest` 执行，功能等价且不改仓库文件；属本机环境问题，不入文档 |
| 6 | 覆盖率首轮 99.75%：`scan_roots` 循环正常退出、`iter_target_files` 已访问 / 不匹配分支、`emit` 失败路径、自测失败分支未触达 | 补 8 条用例（字面 glob、嵌套扫描根、右侧边界、基线缺失、基准比对、失败分支、CLI 分派），覆盖率 100% |

## 6. 偏差与遗留 <a id="open"></a>

| # | 偏差 / 遗留 | 归口 |
| --- | --- | --- |
| 1 | 首版基线 149 条存量（注释 + 真实代码面），需随收编递减 | `03_02`（前端目录消费）、`03_03`（平台种子去产品化）与本任务之后的注释回写 |
| 2 | 「基线清空 → 硬门禁」为专项收口条件之一 | `05_01`（验收以「基线为空且全仓零命中」为准） |
| 3 | `biz` / `cw` 尚未纳入 `literals` | 产品仓接入时登记（《项目规划说明》接入步骤 + `04_02` 清单对账） |
| 4 | 首个推送前只减不增断言会告警「基准不可解析」 | 推送后自愈，无需处理；新克隆浅仓同样告警（按设计不阻断） |
| 5 | 基线里注释类命中占比高（约八成），注释回写未单独立项 | 随 `03_02` / `03_03` 顺带处理；如量仍大，由 `05_01` 评估是否单独立项 |
| 6 | engkit 版本号未升（新增能力为加性变更，各仓以 rev / 路径依赖取用） | 下次发版时随 `pyproject.toml` 版本一并登记 |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》与《[AI开发规范](../../../../../../规范/AI开发规范.md)》编写

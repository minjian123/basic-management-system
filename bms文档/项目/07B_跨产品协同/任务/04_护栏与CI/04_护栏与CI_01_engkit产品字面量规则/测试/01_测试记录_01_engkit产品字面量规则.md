# 01 测试记录 · engkit 产品字面量规则

> 跨产品协同 · 04 护栏与 CI · 子任务 01（需求 04-1）

[文档首页](../../../../../../文档首页.md) › [01 engkit 产品字面量规则](../04_护栏与CI_01_engkit产品字面量规则.md) › 测试记录　|　[← 实施记录](../实施/01_实施记录_01_engkit产品字面量规则.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 engkit 产品字面量规则](../04_护栏与CI_01_engkit产品字面量规则.md) |
| 依据 | [详细设计](../设计/01_详细设计_01_engkit产品字面量规则.md) §5 + [实施记录](../实施/01_实施记录_01_engkit产品字面量规则.md) |
| Kiwi 用例 | **2362**（一条用例承载 20 条断言，覆盖清单见用例文本） |
| 测试日期 | 2026-10-28 |
| 被测范围 | engkit 规则本体（匹配 / 注表面 / 基线 / 只减不增 / CLI）与 bms 侧接入（配置解析、薄包装、预检步骤、首版基线） |

## 2. 用例与断言 <a id="cases"></a>

| # | 用例 | 落点 | 断言 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 裸标识命中 | 自测 + `test_run_json_and_exit_codes` | 报违规、退出码 1、含路径 / 行号 / 建议 | 通过 |
| 2 | 组合形态（`_` / `.` / `:` / `-`） | `test_accept_right` + 自测 | 四种后缀均命中 | 通过 |
| 3 | 词边界 | `test_scan_source_case_sensitive`、自测夹具 `web/boundary.ts` | `mdma` / `xmdm` 类长串不命中 | 通过 |
| 4 | 注释命中（`include_comments = true`） | 自测「命中注释」 | Python `#` 注释与 docstring 均计入 | 通过 |
| 5 | 注释不判（`false`） | 自测「关闭后注释不判定」 | 注释跳过、代码面仍命中 | 通过 |
| 6 | 允许面 | 自测「允许面（测试 / 能力声明文件）」 | `tests/**`、`capabilities.py` 不报并计入允许计数 | 通过 |
| 7 | 排除面 | 自测「排除面（生成物）」 | `gen/**` 不扫描；bms 实跑 `api_types` / `releases` / `modules.json` 零命中 | 通过 |
| 8 | 行内豁免（有理由） | 自测豁免用例 | 不报 | 通过 |
| 9 | 行内豁免（空理由） | 自测豁免用例 | 按违规报 | 通过 |
| 10 | 基线抑制 | 自测「基线吸收后无新增违规」 | 存量不报、退出码 0 | 通过 |
| 11 | 基线外新增 | 自测「新增违规即失败」 | 报并退 1 | 通过 |
| 12 | 只减不增（条目增加） | `test_compare_baseline_growth_and_shrink` | 断言失败 | 通过 |
| 13 | 只减不增（条目减少） | 同上 | 通过（递减合法） | 通过 |
| 14 | 基准不可解析 | `test_run_json_and_exit_codes`、自测 | 告警不失败；bms 实跑打印「基准 `origin/main` 不可解析」 | 通过 |
| 15 | `--update-baseline` | `test_run_update_baseline` | 写回基线并退 0 | 通过 |
| 16 | 配置错误 | `test_parse_missing_literals` / `test_parse_empty_literals` / `test_parse_unknown_key` / `test_parse_wrong_type` | `ConfigError`；运行期缺段退 2 | 通过 |
| 17 | 关闭开关 | `test_run_disabled` | `enabled = false` 退 0 | 通过 |
| 18 | `--self-test` | `test_run_self_test_entry`、`test_base_product_literals_cli`、bms 包装 | 全通过（含包内零命中断言） | 通过 |
| 19 | 降级路径 | 自测「语法错误文件降级后仍命中」 | 语法错误文件全文扫描并告警 | 通过 |
| 20 | 性能 | bms 预检实跑 | 1533 个文件扫描在秒级档预算内完成 | 通过 |

## 3. 执行结果 <a id="result"></a>

| 项 | 命令 | 结果 |
| --- | --- | --- |
| engkit 全量用例 | `uv run python -m pytest -q`（含新增 43 例） | **547 passed / 0 failed** |
| 覆盖率门禁 | `--cov=src/engkit --cov-branch --cov-fail-under=100` | 行 6713 / 分支 2578，**100%**，0 缺失 |
| 静态 | `ruff check` / `ruff format --check` / `pyright` | 0 error / 已格式化 / 0 error |
| bms 预检（秒级档） | `run_once -- check_preflight.py --fast` | 全部通过（含 `check_product_literals` 与其自测） |
| bms 规则实跑 | `check_product_literals.py .` | 通过：命中 149 处全部在基线（检查 1533 / 排除 12 / 允许 908） |

## 4. 与详细设计的对照 <a id="design"></a>

| 设计项 | 结论 |
| --- | --- |
| §3.2 配置字段（10 个键） | 全部落地并有解析用例；`exclude_globs` 与 `include_extensions` 为实施期新增（对齐记录第 4 / 12 条） |
| §3.3 匹配口径 | 词边界 + 组合后缀 + 区分大小写 + 注表面开关，20 条用例覆盖 |
| §3.4 基线与递减 | JSON（路径 + 指纹 + count + samples）+ `--baseline-ref` 断言，均有用例 |
| §3.5 CLI | `engkit base product-literals`（`--self-test` / `--update-baseline` / `--baseline-ref` / `--json`），CLI 分派用例通过 |
| §3.7 自测与元校验 | 自测矩阵 20 条断言；包内零命中断言通过（engkit 自身用例门禁 100% 覆盖） |
| §5.2 验收映射 | 需求 04-1 四条完成标准逐条达成（见下表） |

| 需求 04-1 完成标准 | 证据 |
| --- | --- |
| 规则自带正反用例并通过自测 | 20 条用例 + `--self-test` 全通过 |
| 平台仓启用后命中给出可操作提示 | 实跑输出含路径 / 行号 / 建议文案（改用能力名或登记产品自持声明） |
| 收编完成后全仓零命中且纳入预检（`--fast` 即可拦截） | 预检秒级档已含该步骤；基线 149 条待随 `03_02` / `03_03` 递减至 0 |
| 包内无任何仓名 / 目录字面量 | engkit 既有包内断言 + 本规则自测哨兵断言 |

## 5. 偏差与遗留 <a id="open"></a>

| # | 事项 | 归口 |
| --- | --- | --- |
| 1 | 基线 149 条存量未在本次清零（按设计以基线递减推进） | `03_02` / `03_03` / `05_01` |
| 2 | 只减不增断言在基准 ref 上无基线文件时告警跳过（首个推送前） | 推送后自愈，无需处理 |
| 3 | 注释类命中占比高，注释回写未单独立项 | `05_01` 评估 |

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》与《[测试规范](../../../../../../规范/测试规范.md)》编写

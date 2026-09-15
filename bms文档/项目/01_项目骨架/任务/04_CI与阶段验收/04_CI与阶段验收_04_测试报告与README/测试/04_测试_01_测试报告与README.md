# 测试报告与 README 测试记录

> 项目骨架 · 04 CI 与阶段验收 · 04 测试报告与 README · 测试记录

[文档首页](../../../../../../文档首页.md) › [04 测试报告与 README](../04_CI与阶段验收_04_测试报告与README.md) › 测试　|　[← 父任务](../04_CI与阶段验收_04_测试报告与README.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [04 测试报告与 README](../04_CI与阶段验收_04_测试报告与README.md) |
| 对应需求 | [04-4](../../../../需求/04_需求_CI与阶段验收.md#r04-4) |
| 详细设计 | [04_详细设计_01_测试报告与README](../设计/04_详细设计_01_测试报告与README.md) |
| 实施记录 | [04 实施记录](../实施/04_实施_01_测试报告与README.md) |
| 测试日期 | 2026-09-15 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu；Python 3.14.4 / uv；Node 22）；GitLab API 与 Kiwi TCMS 位于 mjbk |
| Kiwi 用例 | 69（测试报告与 README） |
| 结论 | 5 项断言全部成立；复盘清单 8/8 通过；阶段一 54/54 收口 |

## 2. 测试范围与用例 <a id="scope"></a>

**范围**：阶段测试报告齐备性与数据可追溯性、两个治理脚本可运行性、阶段末复盘清单、门禁第 10 行转达标与 54/54 收口、四份 README 与现状一致性。不含：各任务级功能核对（由各任务测试记录与 04-3 门禁核对承担）。

**用例清单**（先登记 Kiwi TCMS、后写核对命令）：

| Kiwi ID | 用例 | 类型 | 自动化 / 核对文件 | 结果 |
| --- | --- | --- | --- | --- |
| 69 | 测试报告与 README（阶段一收口）：① 报告四章节 + 复盘 + 附录齐备且数据可追溯；② `collect_metrics.py` 输出三项度量与用例统计；③ `review_stage.py` 复盘清单逐项通过；④ 门禁第 10 行转「达标」、54/54；⑤ 四份 README 与现状一致 | 验收核对（脚本 + 人工） | `scripts/tools/governance/collect_metrics.py`、`review_stage.py`、`check-docs/check-status.py`、`base-check/check-base.py` | 通过 |

**等价复现命令**：

```bash
cd <bms 根>
python3 scripts/tools/governance/collect_metrics.py --with-frontend     # 三项度量 + 用例统计
python3 scripts/tools/governance/review_stage.py                        # 复盘清单 8 项
python3 scripts/tools/check-docs/check-status.py && python3 scripts/tools/base-check/check-base.py
cd backend && uv run pytest -q --cov=app --cov-branch --cov-fail-under=70
```

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ python3 scripts/tools/governance/collect_metrics.py --with-frontend --out /tmp/bms_metrics.json
== 阶段度量采集（01_项目骨架，2026-09-15）==
[1/4] 阶段工期偏差（基线：《项目骨架计划》里程碑对照 M1）
  基线 2026-09-28 / 排期起点 2026-09-14（工期 14 天） / 实际 2026-09-15 / 偏差 -13 天（92.9%） / 超 20% 阈值：是
[2/4] 缺陷分布与收敛（GitLab Issue）
  总数 1 / 打开 0 / 已闭环 1 / 自动缺陷 1 / 手工缺陷 0 / P0-P1 未清零：0
    #1 [closed] [自动缺陷] main pipeline failure @ 7ef8a345 | ['defect-auto']
[3/4] 覆盖率（后端行 / 分支；前端行 / 分支）
  后端：行/语句 99.75%、分支覆盖 已启用（用例 417 passed / 7 skipped / 0 failed，1.59s） → 门禁 ≥ 70%：达标
  frontend：行 100%、分支 100%（产物日期 2026-09-15） → 门禁 ≥ 70%：达标
  frontend-mobile：行 100%、分支 100%（产物日期 2026-09-15） → 门禁 ≥ 70%：达标
[4/4] 用例执行统计
  frontend：Test Files 4 passed / Tests 18 passed
  frontend-mobile：Test Files 4 passed / Tests 18 passed
  Playwright E2E：本阶段未启用（tests/e2e 待建，重验证层随 verify-enabled 开关；2026-09-15 改分档 `verify/e2e` 守门，见 04-01 实施 02）
已写入 JSON：/tmp/bms_metrics.json

$ python3 scripts/tools/governance/review_stage.py
== 阶段末复盘清单（01_项目骨架）==
[1/8] 通过 三类文档状态一致：check-status.py 退出码 0；末行：汇总：检查 374 项；硬规则不合规 0，软提示 0
[2/8] 通过 基座自检通过：check-base.py 退出码 0
[3/8] 通过 验收门禁表结论齐备：10 行（期望 10）
[4/8] 通过 阶段残留为 0（需求 / 任务全部已完成）：残留 0 项
[5/8] 通过 遗留项已登记：计划「后续阶段待办」52 条（后补登核心模块覆盖率 / 前端覆盖率扩面两项，现为 55 条）
[6/8] 通过 报告与 README 就位：报告章节齐备；四份 README 关键命令与导航齐备
[7/8] 通过 记录齐备（已完成任务有实施记录）：缺 0 项
[8/8] 通过 Kiwi 用例编号引用齐备：缺 0 份
汇总：8/8 通过（全部通过）

$ python3 scripts/tools/base-check/check-base.py
1. 链接自洽：断链 0 处，失效锚点 0 处
2. 基座跨层引用：0 处    3. 项目专属措辞残留：0 处
4. 清单一致：登记 146 个，磁盘 146 个，缺失 0 个
5. 跨文档编号引用：0 处
[base-integrity] 通过

$ cd backend && uv run pytest -q --cov=app --cov-branch --cov-fail-under=70
417 passed, 7 skipped in 1.59s
Required test coverage of 70% reached. Total coverage: 99.75%
```

**结果汇总**：报告与 README 交付物齐备，脚本与自检全绿，门禁第 10 行转「达标」、**阶段一 54/54 闭环**；收口推送流水线 **177**（`70d6434`，12 job）全绿；本任务未产生缺陷 Issue。

## 4. 问题与处置 <a id="issues"></a>

| # | 问题 / 现象 | 原因 | 处置与落点 |
| --- | --- | --- | --- |
| 1 | 采集脚本首次运行报 `ValueError: too many values to unpack` | 前端分支误写为 `strip_ansi(run(...)[1])` | 改为先取 `(code, raw)` 再 `strip_ansi(raw)`；复跑通过 |
| 2 | 复盘清单初次 6/8 | 门禁表结论带括注未识别、README 期望串写错（后端不应含 `npm run`） | 解析取前导结论词、期望串改正；复跑 8/8（实施记录 §4 第 3 / 4 项） |
| 3 | 报告数字一度只能取到取整 `99%` | `pytest -q --cov` 无 `--cov-fail-under` 时不打印精确汇总 | 采集命令补 `--cov-fail-under=70` 取 99.75%，并顺带校验门禁 |

## 5. 覆盖率 <a id="coverage"></a>

| 项 | 实测 | 门禁口径 | 结论 |
| --- | --- | --- | --- |
| 后端全量覆盖率 | **99.75%**（语句 3668 未覆盖 3；分支 392 未覆盖 7） | 整体 ≥ 70%（核心模块 ≥ 80% 待模块路径确定后接入） | 达标 |
| 前端双端覆盖率 | frontend / frontend-mobile 各 **100%**（行 / 分支 / 函数） | ≥ 70% | 达标 |
| 用例通过率 | 后端 417 passed / 7 skipped；前端各 18 用例（双端 4 文件） | 冒烟层全绿 | 达标 |

> 数据同《[项目骨架阶段测试报告](../../../../测试报告_项目骨架.md)》§3；覆盖率只作本任务快照，阈值以《测试规范》§6 与流水线为准。

## 6. 偏差与遗留 <a id="deviations"></a>

- **偏差**：报告章节超需求「四章节」（增复盘与附录）、脚本解析口径三处细化——均已在设计 §14 与实施记录 §6 登记。
- **未覆盖项**：门禁各功能项的复现由 04-3 实施 / 测试记录承担；重验证层就绪项（E2E / 三库真库 / Trivy / Allure 接线）随 `verify-enabled` 激活，前置见计划 §3.1（2026-09-15 改分档 `verify/*` 并开 P1 + P2，见 04-01 实施 02）。
- **遗留**：无新增（阶段一收口）。

> 本文档依《文档生成规范》编写

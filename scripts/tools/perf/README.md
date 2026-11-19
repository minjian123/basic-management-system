# perf — 全量耗时测量（13_08 T1）

> 分批全量跑 / 最慢项 / 锁与写微基准的可复跑资产，产出三张表 + 基线 JSON。口径见任务 13_08 详细设计 §13。

## 为什么要有它

任务书 §2 的基线数字（749s、第 5 批 477.6s、微基准 0.30ms / 6.91ms / 7.29ms / 3.33ms）当时是一次性人工测的：不能复跑、不能 diff、也无法回答「这次改完比上次慢多少」。本目录把三项测量固化成脚本，供 T5 后半（并行配额）、T7 验收（全量 ≤300s、卡点定位）和后续回归共用。

## 用法

在 `bms` 仓根、用**仓内 venv** 的解释器（PATH 上的 `python` 不是本仓运行时）：

```bash
backend\.venv\Scripts\python.exe scripts\tools\perf\test_perf_baseline.py all
backend\.venv\Scripts\python.exe scripts\tools\perf\test_perf_baseline.py batch --coverage
backend\.venv\Scripts\python.exe scripts\tools\perf\test_perf_baseline.py micro --micro-count 200
backend\.venv\Scripts\python.exe scripts\tools\perf\test_perf_baseline.py slow --run-dir <运行目录>
backend\.venv\Scripts\python.exe scripts\tools\perf\test_perf_baseline.py --self-test
```

| 子命令 | 作用 |
| --- | --- |
| `all`（缺省） | 分批全量跑 + 最慢项 + 微基准，一次出三张表 |
| `batch` | 只跑分批（阶段记录仍落盘，`slow` 可复用） |
| `slow` | 从运行目录复算最慢项（不重跑用例） |
| `micro` | 只跑六项锁与写微基准 |

常用参数：`--jobs auto|off|N`、`--batch-budget 6000`、`--timeout 秒`、`--top N`、`--micro-count N`、`--coverage`、`--save`、`--baseline <文件>`、`--no-compare`、`--fail-over <百分比>`、`--run-dir <目录>`。

## 三张表的口径

| 表 | 口径 |
| --- | --- |
| 分批耗时 | 每批 = 显式 `.py` 文件清单起一次独立 pytest 会话；**每批含一次会话建库的固定成本**（约 3.4s），不扣除 |
| 最慢项 | 按阶段计：setup / call / teardown 各算一条（与任务书 §2.2「最慢项几乎全在 setup」同口径），附各阶段合计与 ≥1s 段数 |
| 锁与写微基准 | 六项：原 §2.3 四项（文件写锁取放 / 建表写一行不持锁 / 持写门 / `BEGIN IMMEDIATE`）+ 当前实现两项（`gate_scope` 写门取放含记账、OS 原生锁取放）；各 N 次，p50 / p95 用最近秩法 |

## 守卫合规（重要）

- **不需要任何逃生开关**：重命令守卫对「位置参数全是 `.py` 文件」放行，全量测试守卫对 `.py` 目标放行。每批显式列文件，批间**串行**——两个 pytest 会话并发会互相删共享测试库。
- **覆盖率只走 engkit 采集插件**：`--coverage` 只设 `BMS_COVERAGE_DATA` / `BMS_COVERAGE_SOURCE`，不传 `--cov`、不设 `COVERAGE_FILE`（否则 `coverage_guard` 直接 `exit(2)`）。查缺口仍用 `coverage_report.py`。
- **门采样另算**：`BMS_TEST_GATE_HOLD=1` 的八列日志本脚本不解析（T7 定位时另行读取）。

## 输出与基线

- 运行目录：`<bms>/backend/.cache/perf/<时间戳>/`，含 `batch-NN.log`（完整输出）、`phase-<worker>.jsonl`（逐用例阶段记录）。**不能放 `.cache/test/`**：测试会话启动会递归删除那里的目录，实测整轮日志被删光。终端只打三张表与摘要。
- `all` 的次序是**先微基准、后分批**：全量跑完机器处在 IO / CPU 高位，微基准会慢约 1.7 倍，与历史空闲态口径不可比。
- 基线：`deploy/perf/test_perf_baseline.json`（入库、可 `git diff`）。**只存本次实测**；任务书 §2 的历史数字留在文档里（分批口径与改动阶段不同，不能逐格相减）。
- 覆盖基线是**显式动作**：`all --save` 才写；默认只读基线并追加「本次 / 基线 / 增减」对比列。
- `--fail-over <百分比>`：任一指标涨幅超过该值返回退出码 1（默认只提示，不做门禁）。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 测量完成（用例失败数如实入表，不算脚本失败） |
| 1 | `--fail-over` 判定超阈值 |
| 2 | 参数 / 配置 / 会话冲突（已有测量会话在跑） |
| 3 | 批执行中断（超时被杀等） |

## 自测

`--self-test` 只覆盖纯函数（分批切分 / pytest 摘要解析 / 分位统计 / 基线对比 / 表格渲染 / 环境指纹），不启动 pytest、不碰锁与数据库；已登记进 `engkit.toml` 的 `[[preflight.self_tests]]`，只在脚本改动时触发。

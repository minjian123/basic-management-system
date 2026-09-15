# BaseProviderRegistry 收敛测试记录

> 后端插件化 · 03 契约与收敛提取 · 03 BaseProviderRegistry 收敛 · 测试记录

[文档首页](../../../../../../文档首页.md) › [03 BaseProviderRegistry 收敛](../03_契约与收敛提取_03_BaseProviderRegistry收敛.md) › 01 测试　|　[← 父任务](../03_契约与收敛提取_03_BaseProviderRegistry收敛.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [03 BaseProviderRegistry 收敛](../03_契约与收敛提取_03_BaseProviderRegistry收敛.md) |
| 对应需求 | [03-3](../../../../需求/03_需求_契约与收敛提取.md#r03-3) |
| 详细设计 | [01_详细设计_01_BaseProviderRegistry收敛](../设计/01_详细设计_01_BaseProviderRegistry收敛.md) |
| 实施记录 | [01 实施记录](../实施/01_实施_01_BaseProviderRegistry收敛.md) |
| 测试日期 | 2026-09-15 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7） |
| Kiwi 用例 | 655（所属契约套件既有用例 568 回归） |
| 结论 | 通过 |

## 2. 测试范围与用例 <a id="scope"></a>

自动化文件：`backend/tests/contracts/test_domain_registry_contracts.py`（新增 5 条，`@pytest.mark.kiwi_id(655)`；文件级 568 标记并存）+ 3 域既有用例回归。

| Kiwi | 用例（函数） | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 655 | `test_uniqueness_registries_reject_duplicates` | 单元（参数化 4） | 4 域独立清单：同键二次登记 → `ConflictError`（重名拒重与插件注册表一致） |
| 655 | `test_null_registry_registers_really` | 单元 | 3 域 `Null` 登记后 `keys()` / `get` 反映；聚合模板仍恒过 / 固定映射 / 空映射 |
| 568 | `test_null_registry_variants_empty` | 单元（参数化 4） | 空集变体语义（回归，未改） |
| 568 | 其余域用例（聚合模板 / 自动纳入 / 健康） | 单元 / 集成 | 回归全绿 |

同时回归 3 域单测更新的 3 条 Null 断言（登记改真实后语义对齐）。

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ uv run pytest tests/contracts tests/fieldtype tests/query tests/dashboard tests/health -q
通过

$ uv run pytest --cov=app --cov-branch -q
537 passed, 7 skipped

$ uv run pytest --cov=app --cov-branch --cov-report=term-missing -q  # 关键模块口径
app/core/provider.py       29   0  2   0  100%
app/fieldtype/base.py      38   0  4   0  100%
app/fieldtype/null.py      12   0  0   0  100%
app/query/base.py          32   0  2   0  100%
app/dashboard/base.py      34   0  4   0  100%
app/dashboard/null.py      12   0  0   0  100%

$ uv run ruff check . && uv run ruff format --check . && uv run pyright
All checks passed! / 272 files already formatted / 0 errors, 0 warnings, 0 informations

$ uv run python -m ops.check_plugins
[插件装配] 校验通过（36 项）   # 退出码 0
```

结果汇总：唯一性口径 4 域对齐（3 域 `Null` 真实登记 + 健康真实注册表）；3 域 Null 登记与聚合语义用例通过；全量 **537 passed、7 skipped**；收敛后 3 域基类 / Null 覆盖率 **100%**。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 原因 | 处置与落点 |
| --- | --- | --- |
| 3 条既有 Null 断言需迁移 | 登记口径变更（已确认） | 断言改「登记后可解析 / 可枚举」（实施记录 §4 已记） |

## 5. 覆盖率 <a id="coverage"></a>

- `app/core/provider.py` / 3 域 `base.py` / `null.py`：**100%**。
- `app/query/null.py` 中 `NullQueryProvider.describe` 补断言覆盖；全量快照 TOTAL 99%（4286 语句 / 8 缺失）。

## 6. 偏差与遗留 <a id="deviations"></a>

- Kiwi 655 与文件级 568 标记并存（同文件新增用例，双标记属预期）。
- 3 域真实注册实现与唯一性实测（真实提供者）随对应能力阶段。

> 本文档依《文档生成规范》编写

# BaseProvider 提取测试记录

> 后端插件化 · 03 契约与收敛提取 · 02 BaseProvider 提取 · 测试记录

[文档首页](../../../../../../文档首页.md) › [02 BaseProvider 提取](../03_契约与收敛提取_02_BaseProvider提取.md) › 01 测试　|　[← 父任务](../03_契约与收敛提取_02_BaseProvider提取.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [02 BaseProvider 提取](../03_契约与收敛提取_02_BaseProvider提取.md) |
| 对应需求 | [03-2](../../../../需求/03_需求_契约与收敛提取.md#r03-2) |
| 详细设计 | [01_详细设计_01_BaseProvider提取](../设计/01_详细设计_01_BaseProvider提取.md) |
| 实施记录 | [01 实施记录](../实施/01_实施_01_BaseProvider提取.md) |
| 测试日期 | 2026-09-15 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7） |
| Kiwi 用例 | 651 / 652 |
| 结论 | 通过 |

## 2. 测试范围与用例 <a id="scope"></a>

自动化文件：`backend/tests/crosscut/test_provider_contracts.py`（2 条，均标注 `@pytest.mark.kiwi_id`）；另以全量回归验证既有契约套件（03-1，57 条）与 4 域用例不破。

| Kiwi | 用例（函数） | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 651 | `test_provider_contract_semantics` | 单元 | 4 类端口均 `issubclass(BaseProvider)`；实现类 `key` 非空、`describe` 非空且含键名；健康 `name == key` |
| 652 | `test_provider_composition_track_boundary` | 单元 | 4 类端口非 `BasePluggable` 子类；提供者实现类与插件快照条目互斥（组合轨不由继承混入） |

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ uv run pytest tests/crosscut/test_provider_contracts.py -q
2 passed

$ uv run pytest --cov=app --cov-branch -q
533 passed, 7 skipped

$ uv run pytest --cov=app --cov-branch --cov-report=term-missing -q  # 关键模块口径
app/core/provider.py     29   0  2   0  100%
app/core/registry.py      2   0  0   0  100%
app/health/base.py       66   0  2   0  100%
app/health/registry.py    8   0  0   0  100%

$ uv run ruff check . && uv run ruff format --check . && uv run pyright
All checks passed! / 272 files already formatted / 0 errors, 0 warnings, 0 informations

$ uv run python -m ops.check_plugins
[插件装配] 校验通过（36 项）   # 退出码 0
```

结果汇总：契约与边界用例通过；全量 **533 passed、7 skipped**；`app/core/provider.py` 覆盖率 **100%**；健康真实探针 `check()` 两行未覆盖（不连真实依赖，属既有口径）。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 原因 | 处置与落点 |
| --- | --- | --- |
| 首次全量回归需适配健康替身 | 抽象 `name` → `key` | 9 个健康测试替身切 `key`（实施记录 §4 已记） |

## 5. 覆盖率 <a id="coverage"></a>

- `app/core/provider.py` / `app/core/registry.py` / `app/health/base.py` / `app/health/registry.py`：**100%**。
- `app/health/checks.py` 95%（43 / 87 为真实探针执行体，不连外部服务）；全量快照 TOTAL 99%（4310 语句 / 8 缺失）。

## 6. 偏差与遗留 <a id="deviations"></a>

- Kiwi 实际编号 651 / 652（CI 导入推进自增）；3 域注册表唯一性翻转与 `_provider_key` 切换随 03-3。

> 本文档依《文档生成规范》编写

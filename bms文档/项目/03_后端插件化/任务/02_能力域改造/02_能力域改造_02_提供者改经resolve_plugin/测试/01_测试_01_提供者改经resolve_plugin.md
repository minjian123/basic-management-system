# 提供者改经 resolve_plugin 测试记录

> 后端插件化 · 02 能力域改造 · 02 提供者改经 resolve_plugin · 测试记录

[文档首页](../../../../../../文档首页.md) › [02 提供者改经 resolve_plugin](../02_能力域改造_02_提供者改经resolve_plugin.md) › 01 测试　|　[← 父任务](../02_能力域改造_02_提供者改经resolve_plugin.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [02 提供者改经 resolve_plugin](../02_能力域改造_02_提供者改经resolve_plugin.md) |
| 对应需求 | [02-2](../../../../需求/02_需求_能力域改造.md#r02-2) |
| 详细设计 | [01_详细设计_01_提供者改经resolve_plugin](../设计/01_详细设计_01_提供者改经resolve_plugin.md) |
| 实施记录 | [01 实施记录](../实施/01_实施_01_提供者改经resolve_plugin.md) |
| 测试日期 | 2026-09-15 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14.4 / uv 0.12.7） |
| Kiwi 用例 | 565 |
| 结论 | 通过 |

## 2. 测试范围与用例 <a id="scope"></a>

自动化文件：`backend/tests/crosscut/test_plugin_providers.py`（5 条，均标注 `@pytest.mark.kiwi_id(565)`）；masking / permission / health / api 既有用例回归：

| Kiwi | 用例（函数） | 类型 | 断言要点 |
| --- | --- | --- | --- |
| 565 | `test_provider_resolves_from_registry` | 集成 | 路由依赖 / `resolve_plugin` / `app.state` 三处同一实例（默认 null） |
| 565 | `test_config_switch_with_no_consumer_change` | 集成 | `storage.provider=custom` 后既有路由返回自定义实现（消费方零改动） |
| 565 | `test_health_registry_pluginized` | 集成 | `local` 真实注册表（`redis` / `database` 检查项）接入 `/readyz`；`null` 仍登记；解析同实例 |
| 565 | `test_provider_registry_base_semantics` | 单元 | 重名 `ConflictError` / 未命中 `None` / `keys` 保序 / `values` 对应 |
| 565 | `test_providers_have_no_direct_state_bypass` | 单元 | 34 个能力域提供者均含 `resolve_plugin(`、无 `app.state.<能力属性>` 直读 |

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ uv run pytest tests/crosscut/test_plugin_providers.py -q
5 passed

$ uv run pytest --cov=app --cov-branch -q
469 passed, 7 skipped

$ uv run pytest --cov=app --cov-branch --cov-report=term-missing -q  # 关键模块口径
app/core/registry.py    22   0   2   0  100%
app/core/assembly.py   119   0  12   0  100%
app/core/plugin.py     162   0  58   0  100%
app/health/registry.py   8   0   0   0  100%

$ uv run ruff check . && uv run ruff format --check . && uv run pyright
All checks passed! / 262 files already formatted / 0 errors, 0 warnings

$ uv run python -m ops.check_plugins
[插件装配] 校验通过（36 项）   # 退出码 0
```

结果汇总：提供者解析 / 配置切换 / 健康插件化 / 基类语义 / 直连护栏用例全部通过；全量 469 passed、7 skipped；关键模块覆盖率 100%。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 原因 | 处置与落点 |
| --- | --- | --- |
| 最小应用测试注入方式需迁移 | 提供者不再读 `app.state.<能力属性>` | 改经隔离注册表 + `app.state.settings`（实施记录 §4 已记） |

## 5. 覆盖率 <a id="coverage"></a>

- `app/core/registry.py` / `assembly.py` / `plugin.py` / `app/health/registry.py`：**100%**。
- 全量快照：TOTAL 99%（4257 语句 / 5 缺失；门禁阈值以《测试规范》与流水线为准）。

## 6. 偏差与遗留 <a id="deviations"></a>

- 其余 3 个域注册表的基类收敛用例随域三 03-3 补登 Kiwi。
- 平台内建存储实现（`local` / `minio`）切换用例随域四 04-1 补登。

> 本文档依《文档生成规范》编写

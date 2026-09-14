# 开放接口 OAuth2 服务端与 scope 基座测试记录

> 项目骨架 · 02 后端基座 · 03 core 横切基座 · 13 开放接口OAuth2服务端与scope基座 · 测试记录

[文档首页](../../../../../../../文档首页.md) › [02-3-13 开放接口OAuth2服务端与scope基座](../02_后端基座_03_core横切基座_13_开放接口OAuth2服务端与scope基座.md) › 01 测试　|　[← 父任务](../02_后端基座_03_core横切基座_13_开放接口OAuth2服务端与scope基座.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [13 开放接口OAuth2服务端与scope基座](../02_后端基座_03_core横切基座_13_开放接口OAuth2服务端与scope基座.md) |
| 对应需求 | [02-41](../../../../../需求/02_需求_后端基座.md#r02-41) |
| 详细设计 | [13_详细设计_01_开放接口OAuth2服务端与scope基座](../设计/13_详细设计_01_开放接口OAuth2服务端与scope基座.md) |
| 实施记录 | [13 实施记录](../实施/13_实施_01_开放接口OAuth2服务端与scope基座.md) |
| 测试日期 | 2026-09-14 |
| 测试人 | minjian |
| 测试环境 | 开发机（Ubuntu，Python 3.14 / uv；ASGI 内存客户端，免启服务器） |
| Kiwi 用例 | 46（平台：分类「平台骨架」、P2、CONFIRMED、标签「自动化」） |
| 结论 | 通过 |

## 2. 测试范围与用例 <a id="scope"></a>

| Kiwi | 用例 | 类型 | 自动化文件 | 断言要点 |
| --- | --- | --- | --- | --- |
| 46 | 服务端契约继承与能力域标识 | 单元 | `tests/oauth/test_oauth.py::test_oauth_server_inheritance_and_key` | `NullOAuthServer → BaseOAuthServer → BaseCapability → BaseObject`；`placeholder` / `describe()`；`key == "oauth_server"` |
| 46 | scope 契约继承与能力域标识 | 单元 | `…::test_scope_checker_inheritance_and_key` | `NullScopeChecker → BaseScopeChecker → BaseCapability → BaseObject`；`key == "scope_checker"` |
| 46 | 授权类型与令牌类型常量 | 单元 | `…::test_grant_types_and_token_type_constants` | `GRANT_TYPES` 三项无重复；`TOKEN_TYPE_BEARER == "Bearer"` |
| 46 | 数据契约默认值与不可变 | 单元 | `…::test_data_contracts_defaults_and_frozen` | `ClientCredentials.scopes == ()`；`OAuthToken` 默认 `Bearer` / `0` / `()`；frozen（`FrozenInstanceError`） |
| 46 | 占位服务端固定返回（不签发） | 单元 | `…::test_null_server_returns_fixed_token` | 不同 `ClientCredentials` 入参返回同一占位令牌（`null-access-token` / 有效期 0 / 空 scope） |
| 46 | 占位撤销空操作 | 单元 | `…::test_null_server_revoke_is_noop` | `revoke` 返回 `None`、不抛错 |
| 46 | 占位 scope 恒定允许 | 单元 | `…::test_null_scope_checker_always_allows` | 任意 `granted` / `required` 组合均返回 `True` |
| 46 | 两提供者依赖解析 | 集成（ASGI） | `…::test_dependency_providers_resolve` | `create_app()` 装配两占位单例；路由经 `Depends(get_oauth_server)` / `Depends(get_scope_checker)` 取到同一实例 |

回归范围：全量用例（含接口冒烟）。

## 3. 执行记录与结果 <a id="run"></a>

```bash
$ uv run pytest -q
271 passed, 2 skipped in 0.93s

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
162 files already formatted

$ uv run pyright
0 errors, 0 warnings, 0 informations
```

结果汇总：新增 Kiwi 46 用例 8 条全部通过；既有用例无回归（装配两单例后接口冒烟仍全绿）；全量 271 passed，2 skipped（真实 Redis 集成用例，环境未配置，随 04_02 重验证层启用）。

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 原因 | 处置与落点 |
| --- | --- | --- |
| `ruff format` 首轮 1 文件待格式化 | 新增用例多行调用换行 | `uv run ruff format .` 后复跑全绿（详见[实施记录](../实施/13_实施_01_开放接口OAuth2服务端与scope基座.md)「问题与处置」） |
| Kiwi 46 平台登记 | 本地无 mjbk Kiwi 管理凭据 | 已于 2026-09-14 在 mjbk Kiwi TCMS 登记（用例号 46 与 `@pytest.mark.kiwi_id(46)` 一致） |

## 5. 覆盖率 <a id="coverage"></a>

`uv run pytest --cov=app -q`：**TOTAL 2582 语句，覆盖率 99%**。

- 本任务新增 / 改动模块**均 100% 覆盖**：`app/oauth/base.py`（49 语句）、`app/oauth/__init__.py`。
- 未覆盖 3 行均为既有代码占位分支：`app/repositories/base_memory_repository.py:25,30`、`app/repositories/base_repository.py:109`（本任务未改动，随落库阶段回补）。任务级快照；门禁阈值以《[测试规范](../../../../../../../规范/测试规范.md)》与流水线为准。

## 6. 偏差与遗留 <a id="deviations"></a>

- 未覆盖项（已登记闭环，随对应阶段补用例）：真实 authlib 服务端（OIDC Provider / Client Credentials 自签 JWT / scope 分配回收 / 撤销黑名单 / `sys_open_log` 审计）、`/api/open` 路由与 ingress 防护 → **系统集成 / 认证 / 落库阶段**（计划「后续阶段待办」表「开放接口 OAuth2 服务端 / scope 真实实现」行）。
- Kiwi 平台登记：已完成（2026-09-14 于 mjbk Kiwi TCMS 登记用例 46）。
- **处理偏差与遗留（2026-09-14 闭环）**：真实签发 / scope 校验 / 撤销用例去向已在计划 §3.1「开放接口 OAuth2 服务端 / scope 真实实现」行与需求 02-41 `> 注：` 块登记；消费方 / 边界标注见[实施记录](../实施/13_实施_01_开放接口OAuth2服务端与scope基座.md)「处理偏差与遗留」；Kiwi 46 平台登记已完成。
- 结论：本任务遗留已全部登记去向，偏差与遗留处理完成。

> 本文档依《文档生成规范》编写

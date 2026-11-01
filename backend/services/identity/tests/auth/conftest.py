"""认证测试包说明（04-6-2 单库叠加口径）。

**不再逐例清空 `sys_session`**：会话表落共享租户库、全 worker 共用，整表 `delete` 会删掉并行
worker 正在断言的会话（历史现象：踢出 404、登出后存储标记仍在、列表 total 偏小）。
改由用例自己划命名空间——用户主键 / 会话主键按 `session_helpers.uid()` / `sid()` 派生，
断言按 `user_id` 精确筛选（见 `session_helpers` 模块 docstring）。

共享租户库的接线已上收到套件级 autouse 夹具（`tests/conftest.py` 的 `tenant_db`），本目录不再单列。
"""

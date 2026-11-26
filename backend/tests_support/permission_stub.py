"""权限放行的统一入口（测试支持）：把**本应用**的权限 provider 回落占位实现。

为什么不再走 `setup_min_tenant`（写共享租户库）：共享库是全进程 / 全 worker 共用的，把测试主体
置为内置系统管理员后，同进程其它服务的「无权限即 403」用例会全部放行（实测 platform 的
`job:*` / `archive:*` 断言从 403 变 200）。

为什么改配置而不是改装配结果：装配结果（检查器实例、数据来源工厂）由系统装配器唯一决定，
用例直接写 `app.state` 属 P5 禁止项；而 `get_permission_checker` 每请求读
`app.state.settings.permission.provider`，改配置即可让本应用解析到 `null` 占位检查器（恒放行），
且 `monkeypatch` 退出自动还原、只影响本应用。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

__all__ = ["stub_permission_provider"]


def stub_permission_provider(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """把指定应用的权限 provider 置空（解析到恒放行的占位实现）。

    Args:
        app: 应用实例（读 `app.state.settings.permission`）。
        monkeypatch: pytest 补丁夹具（用例结束自动还原）。
    """
    monkeypatch.setattr(app.state.settings.permission, "provider", "")

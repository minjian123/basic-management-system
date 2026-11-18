"""直连写门夹具用例（Kiwi 2508）：`platform_db_write` / `tenant_db_write` 的升级语义。

13_08 起「整条用例持锁」与「声明机制」已删除：写门由会话入口按一次写操作取放；
本文件只验证保留下来的两个升级夹具（供直连共享引擎的用例使用）。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from bms_core.testing import gates, plugin, rwlock

pytestmark = pytest.mark.kiwi_id(2508)


@pytest.fixture(autouse=True)
def _isolate_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例用独立门目录，并在前后清空单例。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest 补丁夹具。

    Yields:
        None: 用例运行期。
    """
    def _gate_path(name: str) -> Path:
        """替身门路径（固定到本用例的临时目录）。"""
        return tmp_path / f"db-gate-{name}.lock"

    monkeypatch.setattr(gates, "gate_path", _gate_path)
    gates.reset_gates()
    yield
    gates.reset_gates()


def test_upgrade_fixtures_registered() -> None:
    """两个升级夹具在插件导出面注册（`-p` 加载后可直接请求）。"""
    assert "platform_db_write" in plugin.__all__
    assert "tenant_db_write" in plugin.__all__


async def test_platform_db_write_holds_write_gate(platform_db_write: None) -> None:
    """请求夹具后处于平台库写门内。"""
    del platform_db_write

    assert gates.gate(gates.PLATFORM_GATE).mode == rwlock.WRITE


async def test_tenant_db_write_holds_write_gate(tenant_db_write: None) -> None:
    """请求夹具后处于租户库写门内。"""
    del tenant_db_write

    assert gates.gate(gates.TENANT_GATE).mode == rwlock.WRITE

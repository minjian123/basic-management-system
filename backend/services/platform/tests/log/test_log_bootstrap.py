"""审计分片启动预热护栏（06_01）：当月 + 次月建表 / 关闭跳过 / 失败只告警。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.config import AuditLogSettings
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION
from bms_platform.domains.log.services import shard_bootstrap
from bms_platform.domains.log.services.shard_bootstrap import bootstrap_audit_shards, ensure_audit_shards

pytestmark = pytest.mark.kiwi_id(2407)

_NOW = datetime(2026, 11, 15, 12, 0, 0)


def _settings(*, enabled: bool = True) -> AuditLogSettings:
    """构造审计日志参数。"""
    return AuditLogSettings.model_validate({"enabled": enabled, "precreate_months_ahead": 1})


async def test_ensure_audit_shards_idempotent(log_session: AsyncSession) -> None:
    """当月 + 未来一月两类日志分片齐备；重复执行不重复建表 / 台账。"""
    months = await ensure_audit_shards(log_session, months_ahead=1, clock=lambda: _NOW)
    assert list(months) == ["202611", "202612"]
    repo = LogShardRepository(log_session)
    for month in months:
        assert month in await repo.months(LOG_TYPE_OPERATION)
        assert month in await repo.months(LOG_TYPE_LOGIN)
    await ensure_audit_shards(log_session, months_ahead=1, clock=lambda: _NOW)
    assert list(await repo.months(LOG_TYPE_OPERATION)) == ["202611", "202612"]


async def test_bootstrap_skips_when_disabled() -> None:
    """关闭审计：不建表 / 不告警。"""
    settings = SimpleNamespace(audit_log=_settings(enabled=False))
    app = cast("FastAPI", SimpleNamespace(state=SimpleNamespace(settings=settings)))
    await bootstrap_audit_shards(app)  # 不抛错即通过


async def test_bootstrap_success_and_failure_paths(log_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动钩子：成功建表；会话异常只告警不抛。"""

    @asynccontextmanager
    async def _scope(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs
        yield log_session

    monkeypatch.setattr(shard_bootstrap, "session_scope", _scope)
    app = cast(
        "FastAPI",
        SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(audit_log=_settings(enabled=True)),
                engine_registry=object(),
                session_factory=object(),
            )
        ),
    )
    await bootstrap_audit_shards(app)
    repo = LogShardRepository(log_session)
    assert list(await repo.months(LOG_TYPE_OPERATION)) == ["202611", "202612"]

    @asynccontextmanager
    async def _broken(*args: object, **kwargs: object) -> AsyncGenerator[Any]:
        del args, kwargs
        raise RuntimeError("db down")
        yield  # pragma: no cover - 不可达（保持异步生成器形态）

    monkeypatch.setattr(shard_bootstrap, "session_scope", _broken)
    await bootstrap_audit_shards(app)  # 异常被吞掉

"""安全专项用例 · 基座侧（Kiwi 2235）：脱敏泄露 / 上传绕过 / 限流爆破 / 认证注入。

七类专项按被测物归属分处承载（见任务详细设计 §3.1）：本文件覆盖 `bms_core` 基座横切的四类；
认证链路侧（限流爆破 IP 维度 / 会话劫持 / 越权 / 注入边界）见
`services/identity/tests/auth/test_auth_security_special.py`；XSS 见前端
`frontend/packages/ui-ep/tests/guard-vhtml-sanitize.spec.ts`。

本套件以**补缺口 + 专项断言**为主，复用既有替身与夹具，不重复既有用例（既有覆盖见测试记录矩阵）。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from pydantic import Field, ValidationError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import reset_current_masker, set_current_masker
from bms_core.core.exceptions import RateLimitError
from bms_core.core.logging import (  # pyright: ignore[reportPrivateUsage]
    _SENSITIVE_KEYS,  # pyright: ignore[reportPrivateUsage]
    _SENSITIVE_SUFFIXES,  # pyright: ignore[reportPrivateUsage]
    _build_redact_processor,  # pyright: ignore[reportPrivateUsage]
)
from bms_core.masking.default import DefaultMasker
from bms_core.permission.null import NullPermissionChecker
from bms_core.ratelimit.base import RateLimitRule, build_rate_limit_key
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.ratelimit.null import NullRateLimiter
from bms_core.schemas.base import BaseSchema
from bms_core.storage.local import LocalObjectStorage
from bms_core.transfer.masking import mask_rows

TENANT_ID = "1001"
"""演示租户主键（雪花 id 字符串；限流键租户位口径）。"""


class _ProbeResponse(BaseSchema):
    """响应契约：声明 `phone` 敏感字段（集合写法＝字段名同名内置策略）。"""

    masked_fields = ConcurrentStableSet({"phone"})

    id: int
    phone: str
    note: str = ""


class _ProbeInput(BaseSchema):
    """入参契约：非空 + 长度上限（认证注入的契约层边界）。"""

    name: str = Field(min_length=1, max_length=64)


def _masker() -> DefaultMasker:
    """真实脱敏实现（占位权限检查器 → 明文判定 fail-closed）。

    Returns:
        DefaultMasker: 掩码器实例。
    """
    return DefaultMasker(checker=NullPermissionChecker())


@pytest.mark.kiwi_id(2235)
def test_masking_leak_export_rows_masked_and_others_untouched() -> None:
    """脱敏泄露（导出）：声明列按策略掩码、未声明列原样、不改入参。"""
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
        [ConcurrentStableDict({"phone": "13812345678", "mail": "zhangsan@example.com", "note": "ok"})]
    )
    fields = ConcurrentStableDict({"phone": "phone", "mail": "email"})

    masked = mask_rows(rows, fields, _masker())

    row = masked[0]
    assert row["phone"] == "138****5678"
    assert row["mail"] == "z***@example.com"
    assert row["note"] == "ok"
    assert "13812345678" not in str(row)
    # 掩码不改入参（导出取数侧数据不被就地改写）
    assert rows[0]["phone"] == "13812345678"


@pytest.mark.kiwi_id(2235)
def test_masking_leak_export_empty_fields_short_circuits() -> None:
    """脱敏泄露（导出）：未声明任何掩码列时原样返回入参（不复制、不改写）。"""
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList(
        [ConcurrentStableDict({"phone": "13812345678"})]
    )
    assert mask_rows(rows, ConcurrentStableDict(), _masker()) is rows


@pytest.mark.kiwi_id(2235)
def test_masking_leak_response_and_log_have_no_secret_plaintext() -> None:
    """脱敏泄露（响应 / 日志）：响应序列化按声明掩码；日志对敏感键与连接串密码脱敏。"""
    token = set_current_masker(_masker())
    try:
        dumped = _ProbeResponse(id=1, phone="13812345678", note="ok").model_dump()
    finally:
        reset_current_masker(token)
    assert dumped["phone"] == "138****5678"
    assert "13812345678" not in str(dumped)

    redact = _build_redact_processor(
        ConcurrentStableSet(_SENSITIVE_KEYS),
        ConcurrentStableList([*_SENSITIVE_SUFFIXES]),
    )
    event = {
        "event": "login",
        "password": "secret",
        "user_password": "secret",
        "refresh_token": "tok",
        "phone": "13812345678",
        "email": "zhangsan@example.com",
        "id_card": "110101199001011234",
        "bank_card": "6222021234567890",
        "dsn": "mysql+aiomysql://bms:pw@10.0.0.1:3306/bms",
        "nested": {"client_secret": "s3cr3t", "mobile": "13900001111"},
    }
    redacted = redact(None, "bms", event)
    assert redacted["password"] == "***"
    assert redacted["user_password"] == "***"
    assert redacted["refresh_token"] == "***"
    assert redacted["phone"] == "***"
    assert redacted["email"] == "***"
    assert redacted["id_card"] == "***"
    assert redacted["bank_card"] == "***"
    assert redacted["nested"]["client_secret"] == "***"
    assert redacted["nested"]["mobile"] == "***"
    assert ":pw@" not in redacted["dsn"] and "***@10.0.0.1" in redacted["dsn"]
    # PII 明文不得随日志事件残留
    assert not any(
        plaintext in str(redacted)
        for plaintext in ("13812345678", "zhangsan@example.com", "110101199001011234", "6222021234567890")
    )


@pytest.mark.kiwi_id(2235)
def test_injection_contract_boundaries_and_literal_payload() -> None:
    """认证注入（契约层）：边界值被校验拦截、注入样本按字面透传（参数化在数据访问层）。"""
    assert _ProbeInput(name="  甲  ").name == "甲"

    with pytest.raises(ValidationError):
        _ProbeInput(name="   ")
    with pytest.raises(ValidationError):
        _ProbeInput(name="x" * 65)

    for payload in ("' OR '1'='1", "1; DROP TABLE sys_user; --", "<script>alert(1)</script>"):
        assert _ProbeInput(name=payload).name == payload


@pytest.mark.kiwi_id(2235)
async def test_upload_path_traversal_rejected(tmp_path: Path) -> None:
    """上传绕过（存储层）：空 / 绝对路径 / `..` 键被拒；合法键正常读写（原子写）。"""
    storage = LocalObjectStorage(root=tmp_path)
    for bad_key in ("", "/etc/passwd", "../escape.txt", "a/../../b"):
        with pytest.raises(ValueError, match="非法对象 key"):
            await storage.put(bad_key, b"x")

    stored = await storage.put("tenant/1001/a.txt", b"hello")
    assert stored.size == 5
    assert stored.content_type is None
    assert await storage.exists("tenant/1001/a.txt") is True
    assert await storage.get("tenant/1001/a.txt") == b"hello"


@pytest.mark.kiwi_id(2235)
async def test_rate_limit_window_expiry_and_key_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """限流爆破（基座）：键租户位为雪花 id；窗口内超限拒绝，窗口过期后计数重置。"""
    key = build_rate_limit_key(dimension="ip", target="10.0.0.1", tenant=TENANT_ID)
    assert key == f"bms:{TENANT_ID}:rate:ip:10.0.0.1"

    limiter = MemoryRateLimiter()
    rule = RateLimitRule(limit=1, window=1)

    first = await limiter.check(key, rule)
    assert first.allowed is True and first.remaining == 0
    second = await limiter.check(key, rule)
    assert second.allowed is False
    with pytest.raises(RateLimitError):
        await limiter.require(key, rule)

    base = time.monotonic()
    monkeypatch.setattr("time.monotonic", lambda: base + 2.0)
    refreshed = await limiter.check(key, rule)
    assert refreshed.allowed is True and refreshed.remaining == 0
    assert await limiter.peek(key) == 1
    await limiter.reset(key)
    assert await limiter.peek(key) == 0


@pytest.mark.kiwi_id(2235)
async def test_ratelimit_placeholder_allows_and_real_implementation_blocks() -> None:
    """限流爆破（基座）：占位实现恒放行；真实实现的 `require` 返回决策、超限抛 10005 / 429。"""
    rule = RateLimitRule(limit=1, window=60)
    key = build_rate_limit_key(dimension="account", target="admin", tenant=TENANT_ID)
    assert key == f"bms:{TENANT_ID}:rate:account:admin"

    placeholder = NullRateLimiter()
    assert (await placeholder.require(key, rule)).allowed is True
    assert (await placeholder.require(key, rule)).allowed is True

    limiter = MemoryRateLimiter()
    assert (await limiter.require(key, rule)).allowed is True
    with pytest.raises(RateLimitError) as excinfo:
        await limiter.require(key, rule)
    assert excinfo.value.code == 10005
    assert excinfo.value.http_status == 429

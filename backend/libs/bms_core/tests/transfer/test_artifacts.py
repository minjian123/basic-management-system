"""导出产物 key 与存储端口测试。"""

from __future__ import annotations

import pytest

from bms_core.core.exceptions import ParamError
from bms_core.storage.null import NullObjectStorage
from bms_core.transfer.artifacts import (
    EXPORT_ARTIFACT_EXTS,
    ObjectStorageExportArtifactStore,
    build_export_object_key,
)

pytestmark = pytest.mark.kiwi_id(2402)


def test_build_export_object_key() -> None:
    """路径风格：租户段 + exports + 业务 + token + 扩展名。"""
    assert build_export_object_key("demo", "users", "abc", "xlsx") == "demo/exports/users/abc.xlsx"
    assert build_export_object_key(None, "roles", "abc", "pdf") == "global/exports/roles/abc.pdf"
    assert EXPORT_ARTIFACT_EXTS == ("xlsx", "pdf")


def test_build_export_object_key_rejects_unknown_ext() -> None:
    """扩展名不在白名单拒绝（10001）。"""
    with pytest.raises(ParamError):
        build_export_object_key("demo", "users", "abc", "zip")


def test_key_is_windows_safe() -> None:
    """key 不含冒号等 Windows 非法字符。"""
    key = build_export_object_key("demo", "users", "abc", "xlsx")
    for char in (":", "*", "?", '"', "<", ">", "|"):
        assert char not in key


async def test_store_put_presign_delete() -> None:
    """端口包装对象存储：写入 / 取址 / 删除均成功。"""
    store = ObjectStorageExportArtifactStore(NullObjectStorage())
    await store.put("demo/exports/users/abc.xlsx", b"payload", content_type="application/octet-stream")
    url = await store.presign("demo/exports/users/abc.xlsx", expires_in=60)
    assert url.expires_in == 60
    await store.delete("demo/exports/users/abc.xlsx")

"""导入源文件端口测试：对象存储读写删与 key 口径。"""

from pathlib import Path

import pytest

from bms_core.core.exceptions import NotFoundError
from bms_core.storage.local import LocalObjectStorage
from bms_core.transfer.source import ObjectStorageImportSourceStore, build_import_source_key

pytestmark = pytest.mark.kiwi_id(2401)


def test_key() -> None:
    """对象 key 口径。"""
    assert build_import_source_key("demo", "abc") == "demo/imports/source/abc.xlsx"
    assert build_import_source_key(None, "abc") == "global/imports/source/abc.xlsx"


async def test_store_round_trip(tmp_path: Path) -> None:
    """写入 / 读取 / 删除（幂等）。"""
    store = ObjectStorageImportSourceStore(LocalObjectStorage(root=tmp_path))
    key = build_import_source_key("demo", "abc")
    await store.put(key, b"hello")
    assert await store.get(key) == b"hello"
    await store.delete(key)
    await store.delete(key)
    with pytest.raises(NotFoundError):
        await store.get(key)

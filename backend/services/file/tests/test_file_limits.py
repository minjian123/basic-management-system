"""文件域参数测试（Kiwi 2374）：默认回落 / 参数覆盖 / 非法值回落 / 白名单解析。"""

from pathlib import Path

import pytest
from file_fixtures import StubConfigSource

from bms_core.core.concurrent import ConcurrentStableDict
from bms_file.domains.file.limits import (
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_MAX_UPLOAD_SIZE,
    DEFAULT_PRESIGN_TTL,
    MAX_FILE_SIZE_KEY,
    MAX_UPLOAD_SIZE_KEY,
    PRESIGN_TTL_KEY,
    WHITELIST_KEY,
    FileLimits,
)
from bms_file.domains.file.rules import DEFAULT_WHITELIST

pytestmark = pytest.mark.kiwi_id(2374)


async def test_load_without_source_uses_code_defaults() -> None:
    """未接线参数源（None）：全部回落代码默认（与平台默认清单同值）。"""
    limits = await FileLimits.load(None)

    assert limits.max_upload_size == DEFAULT_MAX_UPLOAD_SIZE == 20 * 1024 * 1024
    assert limits.max_file_size == DEFAULT_MAX_FILE_SIZE == 2 * 1024 * 1024 * 1024
    assert limits.presign_ttl == DEFAULT_PRESIGN_TTL == 3600
    assert limits.whitelist_raw == DEFAULT_WHITELIST
    assert limits.whitelist["pdf"].mime == "application/pdf"


async def test_load_reads_all_keys_and_overrides_defaults() -> None:
    """参数源命中：四个键全部生效（上限 / 单文件上限 / 预签名 TTL / 白名单）。"""
    source = StubConfigSource(
        ConcurrentStableDict(
            {
                MAX_UPLOAD_SIZE_KEY: "1024",
                MAX_FILE_SIZE_KEY: "2048",
                PRESIGN_TTL_KEY: "60",
                WHITELIST_KEY: "text/plain:txt",
            }
        )
    )

    limits = await FileLimits.load(source)

    assert limits.max_upload_size == 1024
    assert limits.max_file_size == 2048
    assert limits.presign_ttl == 60
    assert set(limits.whitelist) == {"txt"}


async def test_load_falls_back_on_invalid_values() -> None:
    """非法值回落：非整数 / 非正数各自回落代码默认（不阻断请求）。"""
    source = StubConfigSource(
        ConcurrentStableDict({MAX_UPLOAD_SIZE_KEY: "abc", MAX_FILE_SIZE_KEY: "-1", PRESIGN_TTL_KEY: "0"})
    )

    limits = await FileLimits.load(source)

    assert limits.max_upload_size == DEFAULT_MAX_UPLOAD_SIZE
    assert limits.max_file_size == DEFAULT_MAX_FILE_SIZE
    assert limits.presign_ttl == DEFAULT_PRESIGN_TTL


def test_whitelist_parses_multi_extension_entries(tmp_path: Path) -> None:
    """白名单同 MIME 的多扩展名（`jpg|jpeg`）都指向同一条目；大小写不敏感。"""
    del tmp_path
    limits = FileLimits(whitelist_raw="image/jpeg:jpg|JPEG")

    assert limits.whitelist["jpg"] is limits.whitelist["jpeg"]
    assert limits.whitelist["jpeg"].mime == "image/jpeg"

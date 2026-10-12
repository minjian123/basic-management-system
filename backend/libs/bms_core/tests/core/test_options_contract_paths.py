"""`BaseOptionsContract` 选项读取补齐用例（`bms_core/core/objects/options.py`）。

补齐 `_str_option`：非空字符串取用、缺失回落缺省、非字符串 / 空串拒启。
"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import PluginError
from bms_core.core.objects.options import BaseOptionsContract


def test_str_option_valid_default_and_invalid_values() -> None:
    """字符串选项：非空字符串取用；缺失回落缺省；非字符串 / 空串即拒（`PluginError`）。"""
    options: ConcurrentStableDict[str, object] = ConcurrentStableDict({"k": "v"})
    assert BaseOptionsContract._str_option(options, "k", "d") == "v"  # pyright: ignore[reportPrivateUsage]
    assert BaseOptionsContract._str_option(options, "missing", "d") == "d"  # pyright: ignore[reportPrivateUsage]

    not_string: ConcurrentStableDict[str, object] = ConcurrentStableDict({"bad": 1})
    with pytest.raises(PluginError):
        BaseOptionsContract._str_option(not_string, "bad", "d")  # pyright: ignore[reportPrivateUsage]

    empty: ConcurrentStableDict[str, object] = ConcurrentStableDict({"bad": ""})
    with pytest.raises(PluginError):
        BaseOptionsContract._str_option(empty, "bad", "d")  # pyright: ignore[reportPrivateUsage]

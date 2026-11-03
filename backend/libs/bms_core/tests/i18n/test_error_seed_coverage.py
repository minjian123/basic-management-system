"""错误码文案种子完整性（Kiwi 2404）：`error.*` 与 `ErrorCode` 一一对应。

护栏口径：新增错误码而未补中英文案时本用例直接失败（不允许「错误提示裸奔」）。
排除 1~9：段位枚举值（`ErrorSegment`）不是业务码。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.error_codes import ErrorCode
from bms_core.i18n.error_seed import ERROR_MESSAGES
from bms_core.i18n.seed import MESSAGE_SEEDS

pytestmark = [pytest.mark.kiwi_id(2404)]


def test_error_codes_have_bilingual_seeds() -> None:
    """每个业务错误码都有 `error.{code}` 的中英两行。"""
    declared = ConcurrentStableDict(
        (int(member.value), member.name) for member in ErrorCode if int(member.value) >= 10000
    )
    seeded = ConcurrentStableDict((code, (zh, en)) for code, zh, en in ERROR_MESSAGES)
    missing: ConcurrentStableList[str] = ConcurrentStableList(
        f"{code}({name})" for code, name in declared.items() if code not in seeded
    )
    assert not missing, f"缺少错误码文案种子：{list(missing)}"
    extra: ConcurrentStableList[str] = ConcurrentStableList(str(code) for code in seeded if code not in declared)
    assert not extra, f"种子中存在未登记错误码：{list(extra)}"


def test_error_messages_unique_and_non_empty() -> None:
    """错误码种子不重复且中英文非空。"""
    seen: ConcurrentStableSet[int] = ConcurrentStableSet()
    for code, zh, en in ERROR_MESSAGES:
        assert code not in seen, f"错误码文案重复：{code}"
        seen.add(code)
        assert zh.strip(), f"错误码 {code} 中文为空"
        assert en.strip(), f"错误码 {code} 英文为空"


def test_message_seeds_include_error_keys_without_duplicates() -> None:
    """固定文案种子含全部 `error.*` 且无重复 key。"""
    counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    for key, _zh, _en in MESSAGE_SEEDS:
        counts.set(key, (counts.get(key) or 0) + 1)
    duplicated: ConcurrentStableList[str] = ConcurrentStableList(key for key, count in counts.items() if count > 1)
    assert not duplicated, f"固定文案 key 重复：{list(duplicated)}"
    for code, _zh, _en in ERROR_MESSAGES:
        assert f"error.{code}" in counts, f"缺少固定文案 key：error.{code}"

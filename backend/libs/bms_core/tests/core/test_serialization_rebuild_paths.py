"""序列化重建助手回落分支补齐用例（`bms_core/core/serialization.py`）。

补齐：类型不可按可迭代构造时回落内置 `list`；内置 `set` / `frozenset` 保持原样的识别分支。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from bms_core.core.serialization import (
    normalize_collections,
    rebuild_mapping,
    rebuild_sequence,
    stringify_ids,
)


class _OddMapping(Mapping[object, object]):
    """仅接受无参构造的映射替身（重建时抛 `TypeError`）。"""

    def __getitem__(self, key: object) -> object:
        """取键值（恒缺失）。

        Args:
            key: 键。

        Raises:
            KeyError: 恒缺失。
        """
        raise KeyError(key)

    def __iter__(self) -> Iterator[object]:
        """键遍历（恒空）。

        Returns:
            Iterator[object]: 空迭代器。
        """
        return iter(())

    def __len__(self) -> int:
        """条目数。

        Returns:
            int: 0。
        """
        return 0


def test_rebuild_helpers_fall_back_to_builtin_list() -> None:
    """重建助手：类型不可按可迭代构造时回落内置 `list`。"""
    assert rebuild_sequence(range(3), [1, 2, 3]) == [1, 2, 3]
    assert rebuild_mapping(_OddMapping(), [(1, 2)]) == {1: 2}


def test_stringify_and_normalize_keep_builtin_sets() -> None:
    """`stringify_ids` / `normalize_collections` 对内置 `set` / `frozenset` 保持原样。"""
    builtin_set = {1, 2}
    assert stringify_ids(builtin_set) is builtin_set
    frozen = frozenset({1, 2})
    assert normalize_collections(frozen) is frozen

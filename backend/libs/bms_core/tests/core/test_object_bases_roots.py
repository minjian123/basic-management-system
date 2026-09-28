"""框架对象 / 数据契约体系归位测试（Kiwi 2217）。

冻结台账 `OBJECT_BATCH` 即 09_05「框架对象与数据契约存量归位」的归位清单，按批次追加：
批次 ① 数据契约 3 → 批次 ② `bms_core` 框架类 30 → 批次 ③ 服务侧 17。
后续批次只允许「台账条目继续改挂」，不得把已归位对象改回 `BaseObject`。
"""

import ast
import dataclasses
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from bms_core.audit.base import FieldChange
from bms_core.events.base import EventEnvelope
from bms_core.sharding.base import ShardBinding

_BACKEND = Path(__file__).resolve().parents[4]
_ROOT = _BACKEND.parent
_BASELINE = _ROOT / "deploy" / "boundaries" / "direct_base_object_baseline.json"

OBJECT_BASES = frozenset(
    {
        "BaseDataContract",
        "BaseFrameworkObject",
        "BaseValueObject",
        "BaseProviderRegistry",
        "BaseSorted",
        "BaseScopedRepository",
        "BaseRepository",
        "BaseHttpClient",
        "BaseServiceClient",
        "CacheRegion",
        "BaseMiddleware",
    }
)
"""允许的归位父基类（体系根 + 既有能力域基类）；新增基类须扩入本集合并在《后端基类清单》§10 登记。"""

OBJECT_BATCH: tuple[tuple[str, str, str], ...] = (
    ("backend/libs/bms_core/src/bms_core/audit/base.py", "FieldChange", "BaseDataContract"),
    ("backend/libs/bms_core/src/bms_core/events/base.py", "EventEnvelope", "BaseDataContract"),
    ("backend/libs/bms_core/src/bms_core/sharding/base.py", "ShardBinding", "BaseDataContract"),
)
"""已归位台账（批次 ①）——（源文件, 类名, 拟归位父基类）。"""

BASELINE_REMAINING = 47
"""基线剩余条目数（每批次递减：批次 ① 后 50 → 47，目标 0）。"""


def _class_bases(rel: str, name: str) -> Sequence[str]:
    """取指定类声明的父类名列表（源码内 `class X(...)` 的括号内容）。

    Args:
        rel: 相对仓库根的源文件路径。
        name: 类名。

    Returns:
        Sequence[str]: 父类名（按声明顺序）；未找到该类时为空。
    """
    tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return [ast.unparse(base) for base in node.bases]
    return []


def _baseline_entries() -> Sequence[tuple[str, str, str]]:
    """读取直继承存量基线快照（`(文件, 类名, 拟归位体系)`）。

    Returns:
        Sequence[tuple[str, str, str]]: 基线条目。
    """
    payload = json.loads(_BASELINE.read_text(encoding="utf-8"))
    return [(str(entry["file"]), str(entry["class"]), str(entry["target_system"])) for entry in payload["entries"]]


@pytest.mark.kiwi_id(2217)
def test_object_batch_declares_expected_base() -> None:
    """归位完整性：台账条目均声明**单一**目标父基类（体系根 / 能力域基类），且不再直继承 `BaseObject`。"""
    offenders: list[str] = []
    for rel, name, expected in OBJECT_BATCH:
        bases = _class_bases(rel, name)
        if bases != [expected] or expected not in OBJECT_BASES:
            offenders.append(f"{rel}::{name} → {bases}（期望 {expected}）")
    assert not offenders, "台账条目须挂目标体系根 / 能力域基类；违规：\n" + "\n".join(offenders)


@pytest.mark.kiwi_id(2217)
def test_object_batch_removed_from_baseline() -> None:
    """基线即台账：台账条目已不在基线快照中，且基线条目数随批次递减。"""
    baseline = {(rel, name) for rel, name, _system in _baseline_entries()}
    still_present = [f"{rel}::{name}" for rel, name, _expected in OBJECT_BATCH if (rel, name) in baseline]
    assert not still_present, "已归位条目仍留在基线快照（须用 --update-baseline 递减）：\n" + "\n".join(still_present)
    assert len(baseline) == BASELINE_REMAINING, f"基线条目数应为 {BASELINE_REMAINING}，实际 {len(baseline)}"


@pytest.mark.kiwi_id(2217)
def test_data_contract_batch_is_mutable_dataclass() -> None:
    """数据类体系语义：`BaseDataContract` 归位项为**可变** dataclass（非 frozen）。"""
    offenders: list[str] = []
    for cls in (FieldChange, EventEnvelope, ShardBinding):
        params = getattr(cls, "__dataclass_params__", None)
        if not dataclasses.is_dataclass(cls) or params is None or params.frozen:
            offenders.append(cls.__name__)
    assert not offenders, "数据契约体系成员须为可变 dataclass（非 frozen）：\n" + "\n".join(offenders)

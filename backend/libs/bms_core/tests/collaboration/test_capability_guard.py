"""无声明降级护栏（07B `02_02` 用例 9；Kiwi 编号归 `05_01` 统一登记）。

护栏口径：`except` 处理器体只有 `pass`、直接返回空集合、或出现 `x or <空集合>` 兜底，即视为
「无声明降级」——降级必须经 `call_capability()` 按 `CapabilityUsage` 声明执行（有日志、有指标、理由留痕）。

基线：平台现存 3 处命中（与能力寻址无关的存量写法）登记为基线，`03_01` 收编后逐项递减；
新增文件 / 新增写法即失败（防「到处 try/except 吞掉」回潮）。
"""

from collections.abc import Iterable
from pathlib import Path

from bms_core.collaboration import find_undeclared_degradations
from bms_core.core.concurrent import ConcurrentStableFrozenSet, ConcurrentStableSet

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
"""后端工程根（`backend/`；用例文件位于 `backend/libs/bms_core/tests/collaboration/`）。"""

_BASELINE: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    {
        "libs/bms_core/src/bms_core/core/base.py:except-pass",
        "services/platform/src/bms_platform/domains/menu_form/services/menu.py:except-pass",
        "services/platform/src/bms_platform/domains/user/services/credentials.py:except-empty-return",
    }
)
"""存量基线（相对后端工程根；随消费方收编递减，不得新增）。"""


def _relative(findings: Iterable[str]) -> ConcurrentStableFrozenSet[str]:
    """把 `文件:行号:类别` 命中归一为 `相对路径:类别`（去掉行号，避免无关改动导致基线抖动）。

    Args:
        findings: 扫描命中清单。

    Returns:
        ConcurrentStableFrozenSet[str]: 归一后的命中集合。
    """
    normalized: ConcurrentStableSet[str] = ConcurrentStableSet()
    for item in findings:
        location, _lineno, kind = item.rsplit(":", 2)
        normalized.add(f"{Path(location).resolve().relative_to(_BACKEND_ROOT).as_posix()}:{kind}")
    return ConcurrentStableFrozenSet(normalized)


def test_scanner_detects_undeclared_degradations(tmp_path: Path) -> None:
    """扫描器识别三类写法（`except: pass` / 处理器内返回空集合 / 处理器内 `or []`）。"""
    module = tmp_path / "demo_consumer.py"
    module.write_text(
        "def swallow():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "def empty():\n"
        "    try:\n"
        "        return [1]\n"
        "    except Exception:\n"
        "        return []\n"
        "\n"
        "def or_empty(values):\n"
        "    try:\n"
        "        return values()\n"
        "    except Exception:\n"
        "        return values() or []\n",
        encoding="utf-8",
    )

    findings = find_undeclared_degradations([module])

    assert sorted(item.rsplit(":", 2)[2] for item in findings) == [
        "except-empty-return",
        "except-or-empty",
        "except-pass",
    ]


def test_scanner_ignores_declared_degradation(tmp_path: Path) -> None:
    """声明式降级与「字典取值兜底」不算违规（护栏只拦吞异常）。"""
    module = tmp_path / "demo_consumer.py"
    module.write_text(
        "def declared(entries):\n"
        "    try:\n"
        "        return entries()\n"
        "    except Exception:\n"
        "        return entries() or ('fallback',)\n"
        "\n"
        "def mapping_default(mapping):\n"
        "    return mapping.get('key') or []\n",
        encoding="utf-8",
    )

    assert find_undeclared_degradations([module]) == []


def test_scanner_covers_collection_forms_and_dedupes(tmp_path: Path) -> None:
    """空字典 / 集合构造（含属性形式）与无法识别的调用形式均按口径处理；重复路径只扫一次。"""
    module = tmp_path / "demo_consumer.py"
    module.write_text(
        "import bms_core\n"
        "\n"
        "def empty_mapping():\n"
        "    try:\n"
        "        return {'a': 1}\n"
        "    except Exception:\n"
        "        return {}\n"
        "\n"
        "def empty_factory():\n"
        "    try:\n"
        "        return [1]\n"
        "    except Exception:\n"
        "        return ConcurrentStableList()\n"
        "\n"
        "def empty_attribute_factory():\n"
        "    try:\n"
        "        return [1]\n"
        "    except Exception:\n"
        "        return bms_core.ConcurrentStableList()\n"
        "\n"
        "def unrecognized_call():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        return (lambda: [])()\n",
        encoding="utf-8",
    )

    findings = find_undeclared_degradations([module, module])

    kinds = [item.rsplit(":", 2)[2] for item in findings]
    assert kinds.count("except-empty-return") == 3
    assert len(findings) == 3


def test_collaboration_package_has_no_undeclared_degradation() -> None:
    """能力寻址包自身零命中（基座不得自写降级）。"""
    assert (
        find_undeclared_degradations([_BACKEND_ROOT / "libs" / "bms_core" / "src" / "bms_core" / "collaboration"]) == []
    )


def test_platform_source_matches_baseline() -> None:
    """平台源码（基座 + 平台服务）命中不得超出基线（新增吞异常即失败）。"""
    findings = find_undeclared_degradations(
        [_BACKEND_ROOT / "libs" / "bms_core" / "src", _BACKEND_ROOT / "services" / "platform" / "src"]
    )

    assert _relative(list(findings)) == _BASELINE

"""回收站规格完整性护栏：表 / 模型 / 列 / 归属 / 级联 / 可见性。"""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from dataclasses import replace

import pytest

import bms_core.models.platform as platform_models
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.recycle.engine import model_for_table
from bms_core.recycle.registry import (
    RECYCLE_TABLES,
    recycle_spec_of,
    register_recycle_tables,
    reset_recycle_tables,
    validate_recycle_specs,
    visible_recycle_specs,
)
from bms_core.recycle.spec import RecycleCascade, RecycleField, RecycleTableSpec

pytestmark = [pytest.mark.kiwi_id(2530)]

# 规格校验读 Base.metadata；本文件独立运行时也要把平台模型全部登记进元数据。
for _module in platform_models.MODEL_MODULES:
    importlib.import_module(_module)


def test_recycle_specs_are_valid() -> None:
    """首批规格全部通过完整性校验（模型 / 列 / 归属 / 级联 / 可见性）。"""
    assert validate_recycle_specs() == []
    assert model_for_table("sys_help_article") is not None
    assert model_for_table("not_exists") is None


def test_visible_and_hidden_specs() -> None:
    """可见表 12 张；隐藏子表不可单独恢复；辅助表在规格内可清理。"""
    specs = visible_recycle_specs()
    assert len(specs) == 12
    assert all(spec.restorable for spec in specs)
    hidden = [spec for spec in RECYCLE_TABLES if not spec.visible]
    assert len(hidden) == 6
    assert all(not spec.restorable for spec in hidden)
    assert recycle_spec_of("sys_help_article_i18n") is not None
    assert recycle_spec_of("sys_recycle_log") is None


def test_register_recycle_specs_is_idempotent_and_rejects_conflict() -> None:
    """追加注册同值幂等、异值即拒；reset 清空追加项。"""
    existing = recycle_spec_of("sys_help_feedback")
    assert existing is not None
    register_recycle_tables((existing,))
    with pytest.raises(ValueError):
        register_recycle_tables((replace(existing, label="改名"),))
    probe = replace(existing, table="sys_recycle_probe")
    other = replace(existing, table="sys_recycle_other")
    register_recycle_tables((probe, other))
    register_recycle_tables((other,))
    assert recycle_spec_of("sys_recycle_probe") == probe
    assert recycle_spec_of("sys_recycle_other") == other
    reset_recycle_tables()
    assert recycle_spec_of("sys_recycle_probe") is None
    assert len(RECYCLE_TABLES) == 18


def _errors_of(monkeypatch: pytest.MonkeyPatch, specs: Iterable[RecycleTableSpec]) -> ConcurrentStableList[str]:
    """在指定规格集上跑校验（不改平台首批）。"""
    monkeypatch.setattr(
        "bms_core.recycle.registry.recycle_table_specs",
        lambda: ConcurrentStableList(specs),
    )
    return ConcurrentStableList(validate_recycle_specs())


def test_validate_recycle_specs_reports_each_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    """规格校验覆盖重复 / 缺模型 / 缺列 / 空名 / 归属 / 级联 / 可见性等分支。"""
    base = recycle_spec_of("sys_help_feedback")
    assert base is not None
    base_errors = _errors_of(monkeypatch, (base, base))
    assert any("表规格重复登记" in error for error in base_errors)
    missing_model = _errors_of(monkeypatch, (replace(base, table="not_exists"),))
    assert any("ORM 模型不存在" in error for error in missing_model)
    no_deleted_at = _errors_of(monkeypatch, (replace(base, table="sys_archive_record", title_field="id"),))
    assert any("缺少 deleted_at" in error for error in no_deleted_at)
    empty_label = _errors_of(monkeypatch, (replace(base, label=""),))
    assert any("中文名 / 模块名不能为空" in error for error in empty_label)
    no_record = _errors_of(monkeypatch, (base,))
    assert no_record == []
    planned = _errors_of(
        monkeypatch,
        (replace(base, table="demo", title_field="id", visible_fields=ConcurrentStableFrozenList(())),),
    )
    assert any("表归属未启用" in error for error in planned)
    bad_title = _errors_of(monkeypatch, (replace(base, title_field="missing"),))
    assert any("标题列不存在" in error for error in bad_title)
    bad_visible = _errors_of(
        monkeypatch,
        (
            replace(
                base,
                visible_fields=ConcurrentStableFrozenList(
                    (RecycleField(column="missing", label="缺列"), RecycleField(column="feedback", label=""))
                ),
            ),
        ),
    )
    assert any("展示列不存在" in error for error in bad_visible)
    assert any("展示列缺少中文标签" in error for error in bad_visible)
    bad_keyword = _errors_of(monkeypatch, (replace(base, keyword_fields=ConcurrentStableFrozenList(("missing",))),))
    assert any("关键字列不存在" in error for error in bad_keyword)
    no_keyword = _errors_of(monkeypatch, (replace(base, keyword_fields=ConcurrentStableFrozenList(())),))
    assert any("可见表必须登记关键字列" in error for error in no_keyword)
    missing_child = _errors_of(
        monkeypatch,
        (replace(base, cascades=ConcurrentStableFrozenList((RecycleCascade("not_exists", "id"),))),),
    )
    assert any("级联子表不存在" in error for error in missing_child)
    assert any("级联子表未登记规格" in error for error in missing_child)
    bad_cascade_column = _errors_of(
        monkeypatch,
        (
            replace(
                base,
                cascades=ConcurrentStableFrozenList((RecycleCascade("sys_help_article_i18n", "missing"),)),
            ),
        ),
    )
    assert any("级联列不存在" in error for error in bad_cascade_column)
    visible_not_restorable = _errors_of(monkeypatch, (replace(base, restorable=False),))
    assert any("可见表必须可恢复" in error for error in visible_not_restorable)
    hidden_restorable = _errors_of(monkeypatch, (replace(base, visible=False, restorable=True),))
    assert any("隐藏子表不可单独恢复" in error for error in hidden_restorable)


def test_validate_reports_missing_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    """表归属缺失单独覆盖（其余字段保持合法）。"""
    base = recycle_spec_of("sys_help_feedback")
    assert base is not None

    def _no_record(table: str) -> None:
        del table
        return None

    monkeypatch.setattr("bms_core.recycle.registry.table_record", _no_record)
    errors = _errors_of(monkeypatch, (base,))
    assert any("未登记表归属" in error for error in errors)

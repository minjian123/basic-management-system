"""i18n 附表登记台账（Kiwi 2405）：台账与模型层一致。

台账是「逐项登记、不全表附挂」的机器可读事实源（`bms_core/i18n/attachments.py`），
本用例锁死三件事：**已落库行必须在模型层存在且文案列一致**、**待落地行不得已在模型层出现**、
**模型层新增 `*_i18n` 表未登记即失败**（护栏思路同 `error.*` 种子覆盖用例）。
"""

import ast
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.i18n.attachments import (
    ATTACHMENT_LANDED,
    ATTACHMENT_PENDING,
    I18N_ATTACHMENTS,
    landed_attachments,
    pending_attachments,
)
from bms_core.models.base import BaseModel
from bms_core.models.platform import catalog, icon, menu_form, permission_meta

pytestmark = pytest.mark.kiwi_id(2405)

_MODELS_ROOT = Path(__file__).resolve().parents[2] / "src" / "bms_core" / "models"

_MODEL_MODULES = (catalog, icon, menu_form, permission_meta)
"""已落库附表所属模型模块（导入即注册 `BaseModel.metadata`，供列名一致性校验）。"""


def _ensure_models_registered() -> None:
    """触发模型模块导入副作用（元数据注册）。"""
    for module in _MODEL_MODULES:
        assert module is not None


def _iter_model_tables() -> ConcurrentStableSet[str]:
    """扫模型层源码里的 `__tablename__` 字面量（AST，不 import）。

    Returns:
        ConcurrentStableSet[str]: 模型层声明的表名集合。
    """
    tables: ConcurrentStableSet[str] = ConcurrentStableSet()
    for path in _MODELS_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                    continue
                target = item.targets[0]
                if not isinstance(target, ast.Name) or target.id != "__tablename__":
                    continue
                if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                    tables.add(item.value.value)
    return tables


def test_attachment_counts() -> None:
    """台账行数与状态分布（6 张已落库 + 5 张待落地）。"""
    assert len(I18N_ATTACHMENTS) == 11
    assert len(landed_attachments()) == 6
    assert len(pending_attachments()) == 5
    assert {item.status for item in I18N_ATTACHMENTS.values()} == {ATTACHMENT_LANDED, ATTACHMENT_PENDING}


def test_landed_tables_exist_in_models() -> None:
    """已落库的附表都必须在模型层声明（漏建模型即失败）。"""
    model_tables = _iter_model_tables()
    for item in landed_attachments():
        assert item.table in model_tables, f"台账登记为已落库但模型层无此表：{item.table}"


def test_pending_tables_not_in_models() -> None:
    """待落地附表不得已在模型层出现（建表后须改状态）。"""
    model_tables = _iter_model_tables()
    for item in pending_attachments():
        assert item.table not in model_tables, f"附表已建但台账仍标 pending：{item.table}"


def test_model_tables_all_registered() -> None:
    """模型层每张 `*_i18n` 表都必须在台账内（新增未登记即失败）。"""
    model_tables = _iter_model_tables()
    i18n_tables = {name for name in model_tables if name.endswith("_i18n")}
    assert i18n_tables <= set(I18N_ATTACHMENTS), f"存在未登记的 i18n 附表：{i18n_tables - set(I18N_ATTACHMENTS)}"


def test_landed_text_columns_match_models() -> None:
    """已落库行的文案列 / 关联列与模型列名一致。"""
    _ensure_models_registered()
    model_tables = _iter_model_tables()
    for item in landed_attachments():
        assert item.owner_table in model_tables, f"主表未在模型层声明：{item.owner_table}"
        table = BaseModel.metadata.tables.get(item.table)
        assert table is not None, f"模型元数据缺表：{item.table}"
        assert item.key_column in table.c, f"{item.table} 缺关联列：{item.key_column}"
        for column in item.text_columns:
            assert column in table.c, f"{item.table} 缺文案列：{column}"


def test_pending_tables_unique() -> None:
    """待落地行不与任何登记行重名（表名唯一）。"""
    names = list(I18N_ATTACHMENTS.keys())
    assert len(names) == len(set(names))

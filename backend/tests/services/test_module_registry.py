"""模块注册服务测试（Kiwi 28）：占位清单 / 筛选 / 唯一性与格式校验。"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.platform import SysModule, SysModuleI18n
from app.services.module_registry import PLATFORM_MODULES, ModuleRecord, ModuleRegistry


def _record(module_key: str = "pur", **overrides: str) -> ModuleRecord:
    """构造测试注册记录。"""
    values: dict[str, str] = {
        "module_key": module_key,
        "name": "采购",
        "table_prefix": f"{module_key}_",
        "errcode_segment": "10",
        "event_domain": module_key,
        "status": "enabled",
    }
    values.update(overrides)
    return ModuleRecord(**values)


@pytest.mark.kiwi_id(28)
def test_platform_seed_list_and_filter() -> None:
    """占位清单：平台域 4 行固定；status 筛选正确。"""
    registry = ModuleRegistry()
    keys = [module.module_key for module in registry.list_modules()]
    assert keys == ["sys", "wf", "rpt", "ai"]
    assert [m.module_key for m in registry.list_modules(status="enabled")] == keys
    assert registry.list_modules(status="planned") == []
    assert len(PLATFORM_MODULES) == 4


@pytest.mark.kiwi_id(28)
def test_validate_accepts_legal_registry() -> None:
    """合法清单：平台域占位与业务模块均通过。"""
    assert ModuleRegistry().validate() == []
    assert ModuleRegistry([_record(), _record("sale", name="销售", errcode_segment="11")]).validate() == []


@pytest.mark.kiwi_id(28)
def test_validate_detects_duplicates() -> None:
    """唯一性：四要素重复均检出。"""
    registry = ModuleRegistry(
        [
            _record("pur"),
            _record("pur", name="采购2"),
            _record("sale", table_prefix="pur_", name="销售", event_domain="pur", errcode_segment="10"),
        ]
    )
    errors = registry.validate()
    assert any("module_key 重复" in e for e in errors)
    assert any("table_prefix 重复" in e for e in errors)
    assert any("errcode_segment 重复" in e for e in errors)
    assert any("event_domain 重复" in e for e in errors)


@pytest.mark.kiwi_id(28)
def test_validate_detects_bad_format() -> None:
    """格式：前缀 / 段号 / 事件域非法均检出。"""
    registry = ModuleRegistry(
        [
            _record("Bad", table_prefix="Bad", errcode_segment="0", event_domain="Bad-Domain"),
        ]
    )
    errors = registry.validate()
    assert any("table_prefix 非法" in e for e in errors)
    assert any("errcode_segment 非法" in e for e in errors)
    assert any("event_domain 非法" in e for e in errors)


@pytest.mark.kiwi_id(28)
def test_models_declared_and_persistable(tmp_path: Path) -> None:
    """模型声明：建表 / 字段 / 唯一约束可用（SQLite 临时库）。"""
    assert {"sys_module", "sys_module_i18n"} <= set(Base.metadata.tables)
    engine: Engine = create_engine(f"sqlite:///{tmp_path / 'module.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        module = SysModule(
            module_key="pur",
            name="采购",
            table_prefix="pur_",
            errcode_segment="10",
            event_domain="pur",
        )
        session.add(module)
        session.commit()
        i18n = SysModuleI18n(module_id=module.id, locale="zh-CN", name="采购")
        session.add(i18n)
        session.commit()
        assert module.id > 0
        assert i18n.id > 0
    engine.dispose()

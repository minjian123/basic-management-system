"""工厂基座契约与迁移回归（Kiwi 778）：BaseFactory / 四域工厂基类 / 关键工厂解析。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bms_core.core.exceptions import PluginError
from bms_core.core.factory import (
    BaseApplicationFactory,
    BaseDbFactory,
    BaseFactory,
    BaseIdFactory,
    BasePluginFactory,
    register_factory,
    resolve_factory,
)
from bms_core.core.id import IdGeneratorFactory, SnowflakeGenerator
from bms_core.db.engine import EngineFactory
from bms_core.db.session import SessionFactory


class _Product:
    """示例产出物。"""

    def __init__(self, value: int = 0) -> None:
        """初始化。

        Args:
            value: 值。
        """
        self.value = value


class _SampleFactory(BaseFactory[int, _Product]):
    """示例工厂（覆写 validate / create）。"""

    key = "sample"

    def validate(self, options: int) -> None:
        """校验非负。

        Args:
            options: 值。

        Raises:
            ValueError: 负值。
        """
        if options < 0:
            raise ValueError("options 不能为负")

    def create(self, options: int = 0) -> _Product:
        """创建产出物。

        Args:
            options: 值。

        Returns:
            _Product: 产出物。
        """
        self.validate(options)
        return _Product(options)


class _SamplePluginFactory(BasePluginFactory[_Product]):
    """示例插件实现工厂（零参可调用）。"""

    key = "sample_plugin"

    def create(self, options: None = None) -> _Product:
        """创建产出物。

        Args:
            options: 未使用。

        Returns:
            _Product: 产出物。
        """
        return _Product(42)


@pytest.mark.kiwi_id(778)
def test_base_factory_contract() -> None:
    """工厂基类：抽象不可实例化、validate 默认空实现、子类生效。"""
    with pytest.raises(TypeError):
        BaseFactory()  # type: ignore[abstract]

    factory = _SampleFactory()
    assert factory.create().value == 0
    assert factory.create(7).value == 7
    with pytest.raises(ValueError):
        factory.create(-1)


@pytest.mark.kiwi_id(778)
def test_domain_factory_bases() -> None:
    """四域工厂基类：均继承 BaseFactory 且键就位。"""
    assert issubclass(BaseApplicationFactory, BaseFactory)
    assert issubclass(BaseDbFactory, BaseFactory)
    assert issubclass(BaseIdFactory, BaseFactory)
    assert issubclass(BasePluginFactory, BaseFactory)
    assert BaseApplicationFactory.key == "application_factory"
    assert BaseDbFactory.key == "db_factory"
    assert BaseIdFactory.key == "id_factory"
    assert BasePluginFactory.key == "plugin_factory"


@pytest.mark.kiwi_id(778)
def test_plugin_factory_is_zero_arg_callable() -> None:
    """插件实现工厂：零参可调用（兼容 PluginImpl 口径）。"""
    produced = _SamplePluginFactory()()
    assert produced.value == 42


@pytest.mark.kiwi_id(778)
def test_factory_registry_register_and_resolve() -> None:
    """工厂专用注册表：登记 / 解析按次新建 / 重名拒 / 未登记拒。"""
    register_factory("sample", "default", _SampleFactory)
    first = resolve_factory("sample")
    second = resolve_factory("sample")
    assert isinstance(first, _SampleFactory)
    assert first is not second  # 按次新建，不复用实例
    with pytest.raises(PluginError):
        register_factory("sample", "default", _SamplePluginFactory)  # 重名（不同实现）拒
    with pytest.raises(PluginError):
        resolve_factory("sample", "ghost")


@pytest.mark.kiwi_id(778)
def test_engine_and_session_factory_migration() -> None:
    """迁移回归：引擎 / 会话工厂经工厂链产出可用（SQLite）。"""
    register_factory("engine_factory", "default", EngineFactory)
    register_factory("session_factory", "default", SessionFactory)
    factory = resolve_factory("engine_factory")
    assert isinstance(factory, EngineFactory)
    assert issubclass(EngineFactory, BaseDbFactory)
    engine = factory.create("platform")
    assert isinstance(engine, AsyncEngine)
    session_factory = SessionFactory().create(engine)
    assert isinstance(session_factory, async_sessionmaker)
    assert issubclass(SessionFactory, BaseDbFactory)


@pytest.mark.kiwi_id(778)
def test_id_generator_factory() -> None:
    """迁移回归：ID 生成器工厂 create / validate 与重设。"""
    factory = IdGeneratorFactory()
    assert issubclass(IdGeneratorFactory, BaseIdFactory)
    generator = factory.create(3)
    assert isinstance(generator, SnowflakeGenerator)
    assert generator.next_id() > 0
    generator.reconfigure(5)
    assert generator.next_id() > 0
    with pytest.raises(ValueError):
        factory.create(9999)

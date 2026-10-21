"""选项集注册与校验基座契约测试（Kiwi 2336）：契约 / 标识 / 合并 / 冲突 / 引用 / 占位 / 真实注册表 / 依赖解析。"""

from collections.abc import Iterable, Iterator
from dataclasses import FrozenInstanceError
from typing import Annotated, cast

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from support_app import ApplicationFactory, lifespan

from bms_core.api.deps import get_option_set_registry
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import NotFoundError, PluginError
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.core.provider import BaseProvider
from bms_core.optionset.base import (
    OPTION_SET_KEY_PATTERN,
    OPTION_SET_KEY_SEPARATOR,
    OPTION_SET_ORIGIN_PLATFORM,
    OPTION_SET_ORIGIN_PRODUCT,
    PLATFORM_NAMESPACE,
    BaseOptionSet,
    BaseOptionSetRegistry,
    OptionItem,
    OptionSetInfo,
    check_registered_references,
    unused_option_sets,
    validate_option_set_key,
)
from bms_core.optionset.local import PLATFORM_OPTION_SETS, LocalOptionSetRegistry
from bms_core.optionset.null import NullOptionSetRegistry

pytestmark = pytest.mark.kiwi_id(2336)


@pytest.fixture(autouse=True)
def force_null_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """占位用例固定 null 实现（避免其他套件把配置改成 local 影响断言）。"""
    monkeypatch.setenv("BMS_OPTION_SET_REGISTRY__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _OptionSet(BaseOptionSet):
    """测试用选项集提供者（条目 / 名称 / 版本由构造指定）。"""

    def __init__(
        self,
        key: str,
        items: Iterable[OptionItem],
        *,
        name: str | None = None,
        version: int | None = None,
    ) -> None:
        """初始化。

        Args:
            key: 选项集标识。
            items: 选项项清单。
            name: 名称（None 用基类缺省）。
            version: 内容版本（None 用基类缺省）。
        """
        self._key = key
        self._items = ConcurrentStableList(items)
        self._name = name
        self._version = version

    @property
    def key(self) -> str:
        """选项集标识。

        Returns:
            str: 标识。
        """
        return self._key

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 描述。
        """
        return f"选项集 {self._key}"

    def items(self) -> ConcurrentStableList[OptionItem]:
        """选项项清单。

        Returns:
            ConcurrentStableList[OptionItem]: 条目。
        """
        return ConcurrentStableList(self._items)

    def get(self, value: str) -> OptionItem | None:
        """按值取选项项。

        Args:
            value: 选项值。

        Returns:
            OptionItem | None: 命中项。
        """
        for item in self._items:
            if item.value == value:
                return item
        return None

    def validate_value(self, value: str) -> ConcurrentStableList[str]:
        """值域判定。

        Args:
            value: 选项值。

        Returns:
            ConcurrentStableList[str]: 违规原因。
        """
        if self.get(value) is None:
            return ConcurrentStableList((f"{self._key} 不含选项值 {value!r}",))
        return ConcurrentStableList(())

    @property
    def name(self) -> str:
        """名称（未指定回退基类缺省）。

        Returns:
            str: 名称。
        """
        return self._key if self._name is None else self._name

    @property
    def version(self) -> int:
        """内容版本（未指定回退基类缺省）。

        Returns:
            int: 版本。
        """
        return 1 if self._version is None else self._version


class _BareOptionSet(BaseOptionSet):
    """最小实现：只用基类缺省的 namespace / name / version / info。"""

    def __init__(self, key: str) -> None:
        """初始化。

        Args:
            key: 选项集标识。
        """
        self._key = key

    @property
    def key(self) -> str:
        """选项集标识。

        Returns:
            str: 标识。
        """
        return self._key

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 描述。
        """
        return f"选项集 {self._key}"

    def items(self) -> ConcurrentStableList[OptionItem]:
        """选项项清单（空）。

        Returns:
            ConcurrentStableList[OptionItem]: 空清单。
        """
        return ConcurrentStableList()

    def get(self, value: str) -> OptionItem | None:
        """按值取选项项（恒定未命中）。

        Args:
            value: 选项值。

        Returns:
            OptionItem | None: 恒 None。
        """
        del value
        return None

    def validate_value(self, value: str) -> ConcurrentStableList[str]:
        """值域判定（空值域恒定违规）。

        Args:
            value: 选项值。

        Returns:
            ConcurrentStableList[str]: 违规原因。
        """
        return ConcurrentStableList((f"{self._key} 不含选项值 {value!r}",))


_ITEMS = (
    OptionItem(value="enabled", label="启用", color="success", sort=2),
    OptionItem(value="disabled", label="停用", label_key="status.disabled", sort=1),
)


def _registry() -> BaseOptionSetRegistry:
    """构造空注册表（继承基座解析 / 校验模板）。

    Returns:
        BaseOptionSetRegistry: 空注册表。
    """
    return LocalOptionSetRegistry()


def test_contract_inheritance_and_identity() -> None:
    """契约继承与能力域标识：提供者 → BaseProvider；注册表 → BaseProviderRegistry / 占位 → BaseNullObject。"""
    assert issubclass(BaseOptionSet, BaseProvider)
    assert issubclass(BaseOptionSetRegistry, BasePluggable)
    assert issubclass(BaseOptionSetRegistry, BaseCapability)
    assert BaseOptionSetRegistry.key == "option_set_registry"
    assert BaseOptionSetRegistry.plugin_key == "option_set_registry"
    assert issubclass(NullOptionSetRegistry, BaseNullObject)
    assert issubclass(LocalOptionSetRegistry, BaseOptionSetRegistry)

    registry = NullOptionSetRegistry()
    assert registry.placeholder is True
    assert "占位实现" in registry.describe()
    assert "option_set_registry" in LocalOptionSetRegistry().describe()


def test_key_constants_and_validation() -> None:
    """标识常量与校验：合法标识通过；非法格式 / 未登记命名空间抛 PluginError 40002。"""
    assert OPTION_SET_KEY_SEPARATOR == "."
    assert PLATFORM_NAMESPACE == "bms"
    assert OPTION_SET_KEY_PATTERN.startswith("^")

    validate_option_set_key("bms.user.status")
    validate_option_set_key("biz.order.status")
    validate_option_set_key("bms.user.status", namespaces=ConcurrentStableList(("bms", "biz")))
    validate_option_set_key("biz.order.status", namespaces=("bms", "biz"))

    for invalid in ("status", "BMS.user.status", "bms..status", "", "bms.user-status", "bms.user.status."):
        with pytest.raises(PluginError) as exc:
            validate_option_set_key(invalid)
        assert exc.value.code == ErrorCode.PLUGIN

    with pytest.raises(PluginError):
        validate_option_set_key("cw.novel.status", namespaces=ConcurrentStableList(("bms", "biz")))


def test_data_contract_defaults_and_frozen() -> None:
    """数据契约：缺省值、只读语义与信息汇总（排序 / 名称 / 版本）。"""
    item = OptionItem(value="enabled")
    assert (item.label, item.label_key, item.color, item.disabled, item.sort) == ("", None, None, False, 0)
    with pytest.raises(FrozenInstanceError):
        cast("object", item).__setattr__("value", "disabled")

    empty = OptionSetInfo(option_set_key="bms.user.status")
    assert list(empty.items) == []
    assert (empty.name, empty.namespace, empty.version) == ("", "", 1)
    with pytest.raises(FrozenInstanceError):
        cast("object", empty).__setattr__("name", "用户状态")

    provider = _OptionSet("bms.user.status", _ITEMS, name="用户状态", version=2)
    assert provider.namespace == "bms"
    assert (provider.name, provider.version) == ("用户状态", 2)
    info = provider.info()
    assert info.option_set_key == "bms.user.status"
    assert [entry.value for entry in info.items] == ["disabled", "enabled"]
    assert isinstance(info.items, ConcurrentStableFrozenList)

    default = _BareOptionSet("bms.user.status")
    assert (default.namespace, default.name, default.version) == ("bms", "bms.user.status", 1)
    assert list(default.info().items) == []


def test_register_merge_and_origins() -> None:
    """登记：同 value 同 label 合并、同标识异义拒绝、来源标记可查。"""
    registry = _registry()
    registry.register(_OptionSet("bms.user.status", _ITEMS))
    assert list(registry.keys()) == ["bms.user.status"]
    assert registry.origin_of("bms.user.status") == OPTION_SET_ORIGIN_PLATFORM
    assert registry.origin_of("bms.user.absent") is None

    # 同一标识、内容一致 → 合并（不重复登记、不抛错）
    registry.register(_OptionSet("bms.user.status", tuple(reversed(_ITEMS))))
    assert list(registry.keys()) == ["bms.user.status"]

    # 同标识、内容不一致 → 同标识异义
    with pytest.raises(PluginError) as exc:
        registry.register(_OptionSet("bms.user.status", (OptionItem(value="locked", label="锁定"),)))
    assert exc.value.code == ErrorCode.PLUGIN

    # 产品来源：自有命名空间可登记；基座命名空间禁止占用
    registry.register(_OptionSet("biz.order.status", _ITEMS), origin=OPTION_SET_ORIGIN_PRODUCT)
    assert registry.origin_of("biz.order.status") == OPTION_SET_ORIGIN_PRODUCT
    with pytest.raises(PluginError):
        registry.register(_OptionSet("bms.order.status", _ITEMS), origin=OPTION_SET_ORIGIN_PRODUCT)


def test_register_conflicts() -> None:
    """装载期冲突：同 value 异义 / 异属性 / 同 label 异值 / 空值 / 缺展示文本均 40002。"""
    registry = _registry()
    cases = (
        (OptionItem(value="enabled", label="启用"), OptionItem(value="enabled", label="可用")),
        (OptionItem(value="enabled", label="启用"), OptionItem(value="enabled", label="启用", color="danger")),
        (OptionItem(value="enabled", label="启用"), OptionItem(value="disabled", label="启用")),
        (OptionItem(value="", label="空值"),),
        (OptionItem(value="enabled"),),
    )
    for items in cases:
        with pytest.raises(PluginError) as exc:
            registry.register(_OptionSet("bms.user.status", items))
        assert exc.value.code == ErrorCode.PLUGIN

    with pytest.raises(PluginError):
        registry.register(_OptionSet("bms.user.status", _ITEMS), origin="unknown")


def test_duplicate_identical_item_and_same_count_different_content() -> None:
    """同一次声明内重复条目合并；同标识同条目数但内容不同 → 同标识异义。"""
    registry = _registry()
    registry.register(
        _OptionSet(
            "bms.dedup.status",
            (
                OptionItem(value="a", label="甲"),
                OptionItem(value="a", label="甲", sort=5),
                OptionItem(value="b", label="", label_key="status.b"),
            ),
        )
    )
    assert [entry.value for entry in registry.resolve("bms.dedup.status").items] == ["a", "b"]

    registry.register(
        _OptionSet("bms.user.status", (OptionItem(value="a", label="甲"), OptionItem(value="b", label="乙")))
    )
    with pytest.raises(PluginError):
        registry.register(
            _OptionSet("bms.user.status", (OptionItem(value="a", label="甲"), OptionItem(value="b", label="丙")))
        )


def test_resolve_and_validate() -> None:
    """解析与值域：条目按 sort 升序；未登记抛 NotFoundError；校验委托提供者返回违规元组。"""
    registry = _registry()
    registry.register(_OptionSet("bms.user.status", _ITEMS))
    info = registry.resolve("bms.user.status")
    assert [entry.value for entry in info.items] == ["disabled", "enabled"]
    assert info.namespace == "bms"
    assert info.version == 1

    with pytest.raises(NotFoundError) as exc:
        registry.resolve("bms.user.absent")
    assert exc.value.code == ErrorCode.NOT_FOUND

    assert list(registry.validate("enabled", option_set_key="bms.user.status")) == []
    violations = registry.validate("locked", option_set_key="bms.user.status")
    assert len(violations) == 1
    assert "locked" in violations[0]
    with pytest.raises(NotFoundError):
        registry.validate("enabled", option_set_key="bms.user.absent")


def test_reference_checks() -> None:
    """双向引用校验：未注册引用报错；注册未引用进死项清单；模块函数薄封装同口径。"""
    registry = _registry()
    registry.register(_OptionSet("bms.user.status", _ITEMS))
    registry.register(_OptionSet("bms.role.status", _ITEMS))

    registry.check_references(ConcurrentStableList(("bms.user.status",)))
    with pytest.raises(PluginError) as exc:
        registry.check_references(ConcurrentStableList(("bms.user.status", "bms.absent", "bms.absent")))
    assert exc.value.code == ErrorCode.PLUGIN
    assert "bms.absent" in str(exc.value)

    assert list(registry.unused_sets(ConcurrentStableList(("bms.user.status",)))) == ["bms.role.status"]
    assert list(registry.unused_sets(ConcurrentStableList(("bms.user.status", "bms.role.status")))) == []

    check_registered_references(registry, ConcurrentStableList(("bms.user.status",)))
    with pytest.raises(PluginError):
        check_registered_references(registry, ConcurrentStableList(("bms.absent",)))
    assert list(unused_option_sets(registry, ConcurrentStableList(("bms.user.status",)))) == ["bms.role.status"]


def test_null_registry_semantics() -> None:
    """占位语义：登记真实、解析恒定空集（version 0）、校验恒定通过。"""
    registry = NullOptionSetRegistry()
    registry.register(_OptionSet("bms.user.status", _ITEMS))
    assert list(registry.keys()) == ["bms.user.status"]

    info = registry.resolve("bms.user.status")
    assert info.option_set_key == "bms.user.status"
    assert list(info.items) == []
    assert (info.name, info.namespace, info.version) == ("", "bms", 0)
    assert registry.resolve("bms.absent").version == 0

    assert list(registry.validate("anything", option_set_key="bms.absent")) == []


def test_local_registry_semantics() -> None:
    """真实注册表：内建清单本期为空；注入项按产品来源登记；改写基座项 40002。"""
    assert list(PLATFORM_OPTION_SETS) == []

    product = _OptionSet("biz.order.status", _ITEMS)
    registry = LocalOptionSetRegistry(injected=(product,))
    assert registry.origin_of("biz.order.status") == OPTION_SET_ORIGIN_PRODUCT
    assert [entry.value for entry in registry.resolve("biz.order.status").items] == ["disabled", "enabled"]

    platform = _OptionSet("bms.user.status", _ITEMS)
    builtin_registry = LocalOptionSetRegistry(builtin=(platform,))
    assert builtin_registry.origin_of("bms.user.status") == OPTION_SET_ORIGIN_PLATFORM
    with pytest.raises(PluginError):
        LocalOptionSetRegistry(builtin=(platform,), injected=(_OptionSet("bms.user.status", _ITEMS),))


def test_product_cannot_override_platform_injected_item() -> None:
    """产品覆盖基座：基座项（非 bms 命名空间）被产品同名改写 → 40002（含来源优先判定）。"""
    platform = _OptionSet("acme.user.status", _ITEMS)
    registry = LocalOptionSetRegistry(builtin=(platform,))
    with pytest.raises(PluginError) as exc:
        registry.register(_OptionSet("acme.user.status", _ITEMS), origin=OPTION_SET_ORIGIN_PRODUCT)
    assert exc.value.code == ErrorCode.PLUGIN
    registry.register(_OptionSet("acme.user.status", _ITEMS), origin=OPTION_SET_ORIGIN_PLATFORM)


async def test_dependency_provider_resolves() -> None:
    """依赖解析：基座测试应用装配占位注册表；提供者取到同一实例；local 插件键可解析。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.option_set_registry, NullOptionSetRegistry)
        assert resolve_plugin("option_set_registry", "local") is not None
        assert isinstance(resolve_plugin("option_set_registry", "local"), LocalOptionSetRegistry)

        @app.get("/optionset-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            registry: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
        ) -> dict[str, object]:  # bare-collections:allow（FastAPI 端点返回注解）
            return {
                "key": registry.key,
                "type": type(registry).__name__,
                "violations": list(registry.validate("any", option_set_key="bms.any.value")),
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/optionset-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "option_set_registry", "type": "NullOptionSetRegistry", "violations": []}

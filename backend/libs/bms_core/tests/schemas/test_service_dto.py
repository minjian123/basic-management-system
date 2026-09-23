"""跨服务读出口契约测试（Kiwi 2169）：契约 DTO 基类与只读投影沿用查询提供者。"""

import pytest

from bms_core.core.provider import BaseProvider, BaseProviderRegistry
from bms_core.query.base import BaseQueryProvider, BaseQueryProviderRegistry
from bms_core.schemas.base import BaseSchema
from bms_core.schemas.service import ServiceDto


class _DemoDto(ServiceDto):
    """测试用跨服务 DTO（模拟契约响应体）。"""

    id: int
    name: str


@pytest.mark.kiwi_id(2169)
def test_service_dto_inherits_response_base() -> None:
    """跨服务 DTO 基类继承响应基类，复用统一序列化口径。"""
    assert issubclass(ServiceDto, BaseSchema)


@pytest.mark.kiwi_id(2169)
def test_service_dto_serializes() -> None:
    """契约 DTO 可实例化并序列化（ID 字符串化口径生效）。"""
    dto = _DemoDto(id=123, name="演示")
    assert dto.model_dump() == {"id": "123", "name": "演示"}


@pytest.mark.kiwi_id(2169)
def test_readonly_projection_uses_query_provider() -> None:
    """只读投影出口沿用既有数据查询提供者基座（不新建平行出口）。"""
    assert issubclass(BaseQueryProvider, BaseProvider)
    assert issubclass(BaseQueryProviderRegistry, BaseProviderRegistry)
    assert BaseQueryProviderRegistry.key == "query_provider_registry"

"""导入导出基座契约测试（Kiwi 56）：契约 / 标识 / 列契约 / 结果契约 / 占位空结果与空流 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_exporter, get_importer
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import create_app, lifespan
from app.transfer.base import ColumnSpec
from app.transfer.exporter import BaseExporter
from app.transfer.importer import BaseImporter, ImportResult, RowError
from app.transfer.null import NullExporter, NullImporter

_COLUMNS = (ColumnSpec(key="name", title="姓名", required=True),)


@pytest.mark.kiwi_id(56)
def test_inheritance_and_keys() -> None:
    """两契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseImporter, BaseCapability)
    assert issubclass(NullImporter, BaseImporter)
    assert issubclass(NullImporter, BaseNullObject)
    assert BaseImporter.key == "importer"

    assert issubclass(BaseExporter, BaseCapability)
    assert issubclass(NullExporter, BaseExporter)
    assert issubclass(NullExporter, BaseNullObject)
    assert BaseExporter.key == "exporter"

    for placeholder in (NullImporter(), NullExporter()):
        assert placeholder.placeholder is True
        assert "占位实现" in placeholder.describe()


@pytest.mark.kiwi_id(56)
def test_column_spec() -> None:
    """列定义契约默认值与不可变。"""
    column = ColumnSpec(key="name", title="姓名")
    assert column.required is False

    field = "title"
    with pytest.raises(FrozenInstanceError):
        setattr(column, field, "名")


@pytest.mark.kiwi_id(56)
def test_result_contracts_defaults_and_frozen() -> None:
    """`RowError` / `ImportResult` 默认值与不可变。"""
    error = RowError(row=1, message="必填缺失")
    assert error.field is None
    assert ImportResult(rows=()).errors == ()

    field = "row"
    with pytest.raises(FrozenInstanceError):
        setattr(error, field, 2)


@pytest.mark.kiwi_id(56)
async def test_null_importer_empty() -> None:
    """占位导入器：解析空行、校验空结果。"""
    importer = NullImporter()
    assert await importer.parse(b"data", columns=_COLUMNS) == ()
    assert await importer.validate([{"name": "甲"}], columns=_COLUMNS) == ImportResult(rows=(), errors=())


@pytest.mark.kiwi_id(56)
async def test_null_exporter_empty_stream() -> None:
    """占位导出器：空流（无分块）。"""
    exporter = NullExporter()
    chunks = [chunk async for chunk in exporter.export([{"name": "甲"}], columns=_COLUMNS)]
    assert chunks == []
    assert b"".join(chunks) == b""


@pytest.mark.kiwi_id(56)
async def test_dependency_providers_resolve() -> None:
    """依赖解析：应用装配两占位单例；路由经两提供者取到同一实例。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.importer, NullImporter)
        assert isinstance(app.state.exporter, NullExporter)

        @app.get("/transfer-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            importer: Annotated[BaseImporter, Depends(get_importer)],
            exporter: Annotated[BaseExporter, Depends(get_exporter)],
        ) -> dict[str, object]:
            parsed = await importer.parse(b"", columns=())
            chunks = [chunk async for chunk in exporter.export([], columns=())]
            return {
                "importer_key": importer.key,
                "rows": len(parsed),
                "exporter_key": exporter.key,
                "chunks": len(chunks),
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/transfer-probe")

        assert resp.status_code == 200
        assert resp.json() == {"importer_key": "importer", "rows": 0, "exporter_key": "exporter", "chunks": 0}

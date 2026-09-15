"""国际化翻译基座契约测试（Kiwi 60）：契约 / 标识 / 常量 / 占位原样返回与默认 locale / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_translator
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES, BaseTranslator
from app.i18n.null import NullTranslator
from app.main import create_app


@pytest.mark.kiwi_id(60)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseTranslator, BaseCapability)
    assert issubclass(NullTranslator, BaseTranslator)
    assert issubclass(NullTranslator, BaseNullObject)
    assert BaseTranslator.key == "translator"

    translator = NullTranslator()
    assert translator.placeholder is True
    assert "占位实现" in translator.describe()


@pytest.mark.kiwi_id(60)
def test_constants() -> None:
    """默认语言与种子语言清单常量。"""
    assert DEFAULT_LOCALE == "zh-CN"
    assert SUPPORTED_LOCALES == ("zh-CN", "en-US")
    assert len(set(SUPPORTED_LOCALES)) == len(SUPPORTED_LOCALES)


@pytest.mark.kiwi_id(60)
async def test_null_translator_fixed() -> None:
    """占位翻译器：原样返回 key、默认 locale、空语言包。"""
    translator = NullTranslator()
    assert await translator.translate("user.form.username") == "user.form.username"
    assert await translator.translate("common.confirm", locale="en-US", params={"x": 1}) == "common.confirm"
    assert translator.resolve_locale("en-US,en;q=0.9") == DEFAULT_LOCALE
    assert await translator.load_messages("zh-CN") == {}


@pytest.mark.kiwi_id(60)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位翻译器；路由经 get_translator 取到同一实例。"""
    app = create_app()
    assert isinstance(app.state.translator, NullTranslator)

    @app.get("/i18n-probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        translator: Annotated[BaseTranslator, Depends(get_translator)],
    ) -> dict[str, object]:
        text = await translator.translate("common.confirm")
        return {"key": translator.key, "type": type(translator).__name__, "text": text}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/i18n-probe")

    assert resp.status_code == 200
    assert resp.json() == {"key": "translator", "type": "NullTranslator", "text": "common.confirm"}

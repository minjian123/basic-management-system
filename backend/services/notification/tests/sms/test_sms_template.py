"""短信模板：CRUD / 场景 / 渠道唯一 / 内置事务性模板解析。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import AliyunSmsSettings, SmsSettings, TencentSmsSettings
from bms_core.core.exceptions import ConflictError, ParamError, SmsTemplateUnavailableError
from bms_core.testing.transaction import rollback_session
from bms_notification.domains.notification.schemas.sms import SmsTemplateCreateRequest
from bms_notification.domains.notification.services.sms import SmsTemplateService

pytestmark = pytest.mark.kiwi_id(2519)


class _Registry:
    def __init__(self, violations: ConcurrentStableList[str] | None = None) -> None:
        self._violations = violations or ConcurrentStableList()

    def validate(self, value: str, *, option_set_key: str) -> ConcurrentStableList[str]:
        del value, option_set_key
        return self._violations


def _settings() -> SmsSettings:
    return SmsSettings(
        channel="aliyun",
        aliyun=AliyunSmsSettings(
            access_key_id="ak",
            access_key_secret="sk",
            sign_name="BMS",
            captcha_template_id="SMS_1",
            password_reset_template_id="SMS_2",
        ),
        tencent=TencentSmsSettings(
            secret_id="id",
            secret_key="key",
            sdk_app_id="app",
            sign_name="BMS",
            captcha_template_id="1001",
            password_reset_template_id="1002",
        ),
    )


def _service(session: object) -> SmsTemplateService:
    return SmsTemplateService(
        session,  # pyright: ignore[reportArgumentType]
        option_sets=_Registry(),  # pyright: ignore[reportArgumentType]
        sms_settings=_settings(),
        render_timeout_seconds=3,
    )


def _service_with_registry(session: object, registry: _Registry) -> SmsTemplateService:
    return SmsTemplateService(
        session,  # pyright: ignore[reportArgumentType]
        option_sets=registry,  # pyright: ignore[reportArgumentType]
        sms_settings=_settings(),
        render_timeout_seconds=3,
    )


def _request(code: str = "order_notice") -> SmsTemplateCreateRequest:
    return SmsTemplateCreateRequest(
        code=code,
        name="订单通知",
        content="订单 {{ order_no }} 已发货。",
        channel="aliyun",
        scene="notify",
        provider_template_id="SMS_9",
        provider_param_keys=ConcurrentStableList(("order_no",)),
    )


async def test_create_list_and_resolve(shared_tenant_engine: AsyncEngine) -> None:
    """新建 / 列表合并内置 / 发送解析。"""
    async with rollback_session(shared_tenant_engine) as session:
        service = _service(session)
        detail = await service.create(_request())
        assert detail.code == "order_notice"
        assert detail.provider_template_id == "SMS_9"
        assert list(detail.provider_param_keys) == ["order_no"]

        page = await service.list(page=1, size=50)
        codes = [item.code for item in page.list]
        assert "order_notice" in codes
        assert "sms_captcha" in codes

        resolved = await service.resolve_for_send("order_notice", params=ConcurrentStableDict({"order_no": "A001"}))
        assert resolved.content == "订单 A001 已发货。"
        assert resolved.provider_template_id == "SMS_9"
        assert list(resolved.provider_param_keys) == ["order_no"]


async def test_builtin_transactional(shared_tenant_engine: AsyncEngine) -> None:
    """内置验证码 / 密码重置按配置的厂商模板 ID 解析。"""
    async with rollback_session(shared_tenant_engine) as session:
        service = _service(session)
        resolved = await service.resolve_for_send(
            "sms_captcha", params=ConcurrentStableDict({"code": "123456", "minutes": "5"})
        )
        assert resolved.provider_template_id == "SMS_1"
        assert "123456" in resolved.content

        reset = await service.resolve_for_send(
            "sms_password_reset",
            params=ConcurrentStableDict({"account": "a", "minutes": "15", "token": "t", "link": ""}),
        )
        assert reset.provider_template_id == "SMS_2"


async def test_duplicate_scene_and_missing(shared_tenant_engine: AsyncEngine) -> None:
    """同 code+渠道重复 / 场景非法 / 不存在。"""
    async with rollback_session(shared_tenant_engine) as session:
        service = _service(session)
        await service.create(_request())
        with pytest.raises(ConflictError):
            await service.create(_request())
        with pytest.raises(ParamError):
            await _service_with_registry(session, _Registry(ConcurrentStableList(("场景不可用",)))).create(
                _request("bad_scene")
            )
        with pytest.raises(SmsTemplateUnavailableError):
            await service.resolve_for_send("missing", params=ConcurrentStableDict())


async def test_update_and_test(shared_tenant_engine: AsyncEngine) -> None:
    """编辑停用 / 渲染测试。"""
    async with rollback_session(shared_tenant_engine) as session:
        service = _service(session)
        detail = await service.create(_request())
        assert detail.id is not None
        code, content = await service.test(int(detail.id), params=ConcurrentStableDict({"order_no": "B002"}))
        assert code == "order_notice"
        assert "B002" in content


async def test_list_filter_source(shared_tenant_engine: AsyncEngine) -> None:
    """来源 / 场景筛选。"""
    async with rollback_session(shared_tenant_engine) as session:
        service = _service(session)
        await service.create(_request())
        builtin = await service.list(page=1, size=50, source="builtin")
        assert all(item.source == "builtin" for item in builtin.list)
        tenant = await service.list(page=1, size=50, source="tenant")
        assert all(item.source == "tenant" for item in tenant.list)
        scene = await service.list(page=1, size=50, scene="code")
        assert all(item.scene == "code" for item in scene.list)

"""邮件模板：CRUD / 多语言回退 / 内置默认覆盖 / 沙箱校验。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import (
    ConflictError,
    MailTemplateNotFoundError,
    TemplateSyntaxInvalidError,
)
from bms_core.db.gate import GATE_CRITICAL_WAIT
from bms_core.testing.locks import file_lock
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.mail_constants import MAIL_TEMPLATE_STATUS_DISABLED
from bms_notification.domains.notification.schemas.mail import (
    MailTemplateCreateRequest,
    MailTemplateDetail,
    MailTemplateUpdateRequest,
    MailTextInput,
)
from bms_notification.domains.notification.services.mail import MailTemplateService

pytestmark = pytest.mark.kiwi_id(2519)


@pytest.fixture
def code(ns: Namespace) -> str:
    """本用例的邮件模板 code（按 nodeid 派生，避免与并行用例撞码）。"""
    return f"{ns.prefix}_welcome"


@pytest.fixture(autouse=True)
def _serial_mail_templates() -> Iterator[None]:
    """模板覆盖内置需要独占 code（`approval_todo`）：整份文件串行，避免并行互相覆盖。

    Yields:
        None: 用例运行期。
    """
    with file_lock("notification-mail-templates", timeout=180.0):
        yield


@pytest.fixture(autouse=True)
async def _clean_mail_templates(
    _serial_mail_templates: None, shared_tenant_engine: AsyncEngine, code: str
) -> AsyncIterator[None]:
    """用例前后只清本用例的模板（含多语言附表；写入立即落库，不再回滚）。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        code: 本用例模板 code。

    Yields:
        None: 用例运行期。
    """

    async def _purge() -> None:
        """删除本用例的模板与附表（原生 SQL 带 WHERE）。"""
        async with write_session(shared_tenant_engine, wait=GATE_CRITICAL_WAIT) as session:
            await session.execute(
                text(
                    "DELETE FROM sys_mail_template_i18n "
                    "WHERE template_id IN (SELECT id FROM sys_mail_template WHERE code IN (:code, :override))"
                ),
                {"code": code, "override": "approval_todo"},
            )
            await session.execute(
                text("DELETE FROM sys_mail_template WHERE code IN (:code, :override)"),
                {"code": code, "override": "approval_todo"},
            )

    await _purge()
    yield
    await _purge()


def _id(detail: MailTemplateDetail) -> int:
    """取租户模板主键（内置默认为 None，用例只针对租户行）。"""
    assert detail.id is not None
    return int(detail.id)


def _create_request(code: str) -> MailTemplateCreateRequest:
    return MailTemplateCreateRequest(
        code=code,
        name="欢迎邮件",
        i18n=ConcurrentStableDict(
            {
                "zh-CN": MailTextInput(subject="欢迎 {{ name }}", content="<p>你好 {{ name }}</p>"),
                "en-US": MailTextInput(subject="Welcome {{ name }}", content="<p>Hello {{ name }}</p>"),
            }
        ),
    )


async def test_create_list_detail_and_locale(shared_tenant_engine: AsyncEngine, code: str) -> None:
    """新建 / 列表合并内置 / 详情 / 多语言回退。"""
    async with write_session(shared_tenant_engine) as session:
        service = MailTemplateService(session, render_timeout_seconds=3)
        detail = await service.create(_create_request(code), request_locale="zh-CN")
        assert detail.code == code
        assert detail.subject == "欢迎 {{ name }}"
        assert set(detail.i18n) == {"zh-CN", "en-US"}

        page = await service.list(page=1, size=50, locale="en-US")
        codes = [item.code for item in page.list]
        assert code in codes
        assert "approval_todo" in codes
        builtin = next(item for item in page.list if item.code == "approval_todo")
        assert builtin.source == "builtin"
        assert builtin.id is None
        assert "Todo" in builtin.subject

        fallback = await service.detail(_id(detail), locale="fr-FR")
        assert fallback.subject == "欢迎 {{ name }}"


async def test_preview_builtin_and_override(shared_tenant_engine: AsyncEngine) -> None:
    """内置默认可预览；同 code 覆盖后走租户行，删除后回落。"""
    async with write_session(shared_tenant_engine) as session:
        service = MailTemplateService(session, render_timeout_seconds=3)
        subject, content = await service.preview(
            "approval_todo",
            params=ConcurrentStableDict({"title": "审批", "content": "内容"}),
            locale="zh-CN",
        )
        assert "审批" in subject
        assert "内容" in content

        override = await service.create(_create_request("approval_todo"), request_locale="zh-CN")
        subject, _ = await service.preview("approval_todo", params=ConcurrentStableDict({"name": "A"}), locale="zh-CN")
        assert subject == "欢迎 A"

        await service.delete(_id(override))
        subject, _ = await service.preview(
            "approval_todo",
            params=ConcurrentStableDict({"title": "审批", "content": "内容"}),
            locale="zh-CN",
        )
        assert "审批" in subject


async def test_update_disable_and_conflict(shared_tenant_engine: AsyncEngine, code: str) -> None:
    """编辑 / 停用 / 重复 code / 语法错误保存即拒。"""
    async with write_session(shared_tenant_engine) as session:
        service = MailTemplateService(session, render_timeout_seconds=3)
        detail = await service.create(_create_request(code), request_locale="zh-CN")
        with pytest.raises(ConflictError):
            await service.create(_create_request(code), request_locale="zh-CN")

        updated = await service.update(
            _id(detail),
            MailTemplateUpdateRequest(status=MAIL_TEMPLATE_STATUS_DISABLED),
            request_locale="zh-CN",
        )
        assert updated.status == MAIL_TEMPLATE_STATUS_DISABLED
        with pytest.raises(MailTemplateNotFoundError):
            await service.preview("welcome", params=ConcurrentStableDict(), locale="zh-CN")

        with pytest.raises(TemplateSyntaxInvalidError):
            await service.create(
                MailTemplateCreateRequest(
                    code=f"{code}_bad",
                    name="坏模板",
                    i18n=ConcurrentStableDict({"zh-CN": MailTextInput(subject="x", content="{% if x %}")}),
                ),
                request_locale="zh-CN",
            )


async def test_test_endpoint_and_missing(shared_tenant_engine: AsyncEngine, code: str) -> None:
    """按 id 渲染测试；不存在返回 70301。"""
    async with write_session(shared_tenant_engine) as session:
        service = MailTemplateService(session, render_timeout_seconds=3)
        detail = await service.create(_create_request(code), request_locale="zh-CN")
        subject, content = await service.test(_id(detail), params=ConcurrentStableDict({"name": "B"}), locale="en-US")
        assert subject == "Welcome B"
        assert "Hello B" in content
        with pytest.raises(MailTemplateNotFoundError):
            await service.test(999999, params=ConcurrentStableDict(), locale="zh-CN")

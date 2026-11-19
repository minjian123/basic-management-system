"""公告业务服务（Kiwi 2518）：状态机 / 可见性 / 多语言 / 事件 / 回执统计 / 过期下线。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    NoticeAudienceUnavailableError,
    NoticeContentInvalidError,
    NoticeNotFoundError,
    NoticeNotVisibleError,
    NoticeStatusConflictError,
    NoticeTimeInvalidError,
    ParamError,
)
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.models.notice import SysNotice, SysNoticeI18n, SysNoticeRead
from bms_notification.domains.notification.notice_constants import (
    NOTICE_ACTION_OFFLINE,
    NOTICE_ACTION_PUBLISHED,
    NOTICE_ACTION_UPDATED,
    NOTICE_STATUS_DRAFT,
    NOTICE_STATUS_OFFLINE,
    NOTICE_STATUS_PUBLISHED,
)
from bms_notification.domains.notification.schemas.notice import (
    NoticeCreateRequest,
    NoticeTextInput,
    NoticeUpdateRequest,
)
from bms_notification.domains.notification.services.notice import NoticeService
from notice._support import (
    FakeAudience,
    FakeOptionSets,
    Outbox,
    add_notice,
    add_receipt,
    reset_user,
    use_user,
    utc_now,
)

pytestmark = pytest.mark.kiwi_id(2518)


def _service(
    session: AsyncSession, *, outbox: Outbox | None = None, option_sets: FakeOptionSets | None = None
) -> NoticeService:
    """构造公告服务（替身注入）。

    Args:
        session: 回滚会话。
        outbox: 发件箱替身。
        option_sets: 选项集替身。

    Returns:
        NoticeService: 服务实例。
    """
    return NoticeService(
        cast("object", session),  # pyright: ignore[reportArgumentType]
        option_sets=cast("object", option_sets or FakeOptionSets()),  # pyright: ignore[reportArgumentType]
        outbox=cast("object", outbox or Outbox()),  # pyright: ignore[reportArgumentType]
    )


def _texts(
    *, zh: str = "标题", en: str | None = None, content: str = "<p>正文</p>"
) -> ConcurrentStableDict[str, NoticeTextInput]:
    """构造多语言入参。

    Args:
        zh: 中文标题。
        en: 英文标题（None 不传）。
        content: 正文。

    Returns:
        ConcurrentStableDict[str, NoticeTextInput]: 多语言映射。
    """
    result: ConcurrentStableDict[str, NoticeTextInput] = ConcurrentStableDict(
        {"zh-CN": NoticeTextInput(title=zh, content=content)}
    )
    if en is not None:
        result.set("en-US", NoticeTextInput(title=en, content=f"<p>{en}</p>"))
    return result


async def _i18n_rows(session: AsyncSession, notice_id: int) -> ConcurrentStableDict[str, str]:
    """取公告附表语言 → 标题。

    Args:
        session: 回滚会话。
        notice_id: 公告主键。

    Returns:
        ConcurrentStableDict[str, str]: 语言 → 标题。
    """
    rows = (
        (
            await session.execute(
                select(SysNoticeI18n).where(SysNoticeI18n.notice_id == notice_id, SysNoticeI18n.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    return ConcurrentStableDict({row.locale: row.title for row in rows})


async def test_create_published_with_i18n_and_event(shared_tenant_engine: AsyncEngine) -> None:
    """直接发布：主表派生中文、附表两种语言、发 published 事件。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            outbox = Outbox()
            service = _service(session, outbox=outbox)
            detail = await service.create(
                NoticeCreateRequest(i18n=_texts(zh="中文标题", en="English title"), is_top=True),
                now=utc_now(),
                request_locale="zh-CN",
                tenant_id="1001",
            )
            assert detail.title == "中文标题"
            assert detail.is_top is True
            assert detail.status == NOTICE_STATUS_PUBLISHED
            assert detail.i18n is not None and set(detail.i18n) == {"zh-CN", "en-US"}
            assert await _i18n_rows(session, detail.id) == ConcurrentStableDict(
                {"zh-CN": "中文标题", "en-US": "English title"}
            )
            assert [event.event_type for event in outbox.events] == ["sys.notice.published"]
            payload = outbox.events[0].payload
            assert payload["action"] == NOTICE_ACTION_PUBLISHED
            assert payload["type"] == "system"
            assert payload["priority"] == "normal"
            assert payload["notice_id"] == str(detail.id)
        finally:
            reset_user(tokens)


async def test_create_draft_then_publish(shared_tenant_engine: AsyncEngine) -> None:
    """草稿不发布事件；PUT publish=true 发布并写 published 事件。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            outbox = Outbox()
            service = _service(session, outbox=outbox)
            detail = await service.create(
                NoticeCreateRequest(i18n=_texts(content=""), publish=False),
                now=utc_now(),
                request_locale="zh-CN",
                tenant_id="1001",
            )
            assert detail.status == NOTICE_STATUS_DRAFT
            assert outbox.events == []
            updated = await service.update(
                detail.id,
                NoticeUpdateRequest(i18n=_texts(), publish=True),
                now=utc_now(),
                request_locale="zh-CN",
                tenant_id="1001",
                can_manage=True,
            )
            assert updated.status == NOTICE_STATUS_PUBLISHED
            assert [event.payload["action"] for event in outbox.events] == [NOTICE_ACTION_PUBLISHED]
        finally:
            reset_user(tokens)


async def test_update_published_emits_updated(shared_tenant_engine: AsyncEngine) -> None:
    """编辑已发布公告：标题 / 置顶更新并写 updated 事件。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            row = add_notice(session, title="旧标题")
            await session.flush()
            outbox = Outbox()
            service = _service(session, outbox=outbox)
            detail = await service.update(
                int(row.id),
                NoticeUpdateRequest(i18n=_texts(zh="新标题"), is_top=True),
                now=utc_now(),
                request_locale="zh-CN",
                tenant_id="1001",
                can_manage=True,
            )
            assert detail.title == "新标题" and detail.is_top is True
            assert [event.payload["action"] for event in outbox.events] == [NOTICE_ACTION_UPDATED]
        finally:
            reset_user(tokens)


async def test_update_conflicts_and_offshelf(shared_tenant_engine: AsyncEngine) -> None:
    """已下线不可编辑；不支持撤回草稿；不存在 70201。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            offline = add_notice(session, title="下线", status=NOTICE_STATUS_OFFLINE)
            await session.flush()
            service = _service(session)
            with pytest.raises(NoticeStatusConflictError):
                await service.update(
                    int(offline.id),
                    NoticeUpdateRequest(),
                    now=utc_now(),
                    request_locale="zh-CN",
                    tenant_id="1001",
                    can_manage=True,
                )
            published = add_notice(session, title="发布中")
            await session.flush()
            with pytest.raises(NoticeStatusConflictError):
                await service.update(
                    int(published.id),
                    NoticeUpdateRequest(publish=False),
                    now=utc_now(),
                    request_locale="zh-CN",
                    tenant_id="1001",
                    can_manage=True,
                )
            with pytest.raises(NoticeNotFoundError):
                await service.update(
                    999999,
                    NoticeUpdateRequest(),
                    now=utc_now(),
                    request_locale="zh-CN",
                    tenant_id="1001",
                    can_manage=True,
                )
        finally:
            reset_user(tokens)


async def test_delete_soft_deletes_i18n(shared_tenant_engine: AsyncEngine) -> None:
    """软删除公告并连带软删附表。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            service = _service(session)
            detail = await service.create(
                NoticeCreateRequest(i18n=_texts()), now=utc_now(), request_locale="zh-CN", tenant_id="1001"
            )
            assert await service.delete(detail.id) is True
            row = (await session.execute(select(SysNotice).where(SysNotice.id == detail.id))).scalars().one()
            assert row.deleted_at is not None
            i18n = (
                (await session.execute(select(SysNoticeI18n).where(SysNoticeI18n.notice_id == detail.id)))
                .scalars()
                .all()
            )
            assert all(item.deleted_at is not None for item in i18n)
        finally:
            reset_user(tokens)


async def test_content_time_and_option_errors(shared_tenant_engine: AsyncEngine) -> None:
    """内容 / 时间 / 选项集 / 语言映射的失败分支。"""
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            service = _service(session)
            with pytest.raises(NoticeTimeInvalidError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts(), publish_at=now, expire_at=now),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(NoticeTimeInvalidError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts(), expire_at=now - timedelta(seconds=1)),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(NoticeContentInvalidError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts(content="")),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(NoticeContentInvalidError):
                service._clean_title("长" * 257)  # pyright: ignore[reportPrivateUsage]
            with pytest.raises(NoticeContentInvalidError):
                service._clean_content("<p>" + "中" * 21000 + "</p>")  # pyright: ignore[reportPrivateUsage]
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=ConcurrentStableDict()),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=ConcurrentStableDict({"en-US": NoticeTextInput(title="en")})),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=ConcurrentStableDict({"bad locale": NoticeTextInput(title="x")})),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts(), type="unknown"),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts(), priority="unknown"),
                    now=now,
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts()), now=now, request_locale="zh-CN", tenant_id=None
                )
        finally:
            reset_user(tokens)


async def test_content_byte_limit(shared_tenant_engine: AsyncEngine) -> None:
    """正文 UTF-8 字节超限 70205。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            service = _service(session)
            with pytest.raises(NoticeContentInvalidError):
                await service.create(
                    NoticeCreateRequest(i18n=_texts(content="中" * 21000)),
                    now=utc_now(),
                    request_locale="zh-CN",
                    tenant_id="1001",
                )
        finally:
            reset_user(tokens)


async def test_list_detail_visibility_and_locale(shared_tenant_engine: AsyncEngine) -> None:
    """普通用户只看发布中；管理侧看全部；显式 locale 命中附表。"""
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(2)
        try:
            published = add_notice(session, title="中文标题")
            draft = add_notice(session, title="草稿", status=NOTICE_STATUS_DRAFT)
            await session.flush()
            session.add(
                SysNoticeI18n(notice_id=int(published.id), locale="en-US", title="English title", content="<p>en</p>")
            )
            await session.flush()
            service = _service(session)
            page = await service.list_published(page=1, size=10, now=now, locale="en-US")
            assert page.total == 1 and page.list[0].title == "English title"
            page = await service.list_manage(
                page=1,
                size=10,
                now=now,
                locale="zh-CN",
                keyword=None,
                status=None,
                notice_type=None,
                can_manage=False,
            )
            assert page.total == 1 and page.list[0].title == "中文标题"
            page = await service.list_manage(
                page=1,
                size=10,
                now=now,
                locale="zh-CN",
                keyword=None,
                status=None,
                notice_type=None,
                can_manage=True,
            )
            assert page.total == 2
            with pytest.raises(NoticeNotFoundError):
                await service.detail(int(draft.id), now=now, locale="zh-CN", can_manage=False)
            detail = await service.detail(int(draft.id), now=now, locale="zh-CN", can_manage=True)
            assert detail.title == "草稿"
            detail = await service.detail(int(published.id), now=now, locale="en-US", can_manage=False)
            assert detail.title == "English title" and detail.i18n is None
            detail = await service.detail(int(published.id), now=now, locale="zh-CN", can_manage=True)
            assert detail.i18n is not None and "en-US" in detail.i18n
            with pytest.raises(ParamError):
                await service.list_manage(
                    page=1,
                    size=10,
                    now=now,
                    locale="zh-CN",
                    keyword=None,
                    status="bad",
                    notice_type=None,
                    can_manage=True,
                )
            with pytest.raises(ParamError):
                await service.list_manage(
                    page=1,
                    size=10,
                    now=now,
                    locale="zh-CN",
                    keyword=None,
                    status=None,
                    notice_type="unknown",
                    can_manage=True,
                )
        finally:
            reset_user(tokens)


async def test_mark_read_idempotent_and_errors(shared_tenant_engine: AsyncEngine) -> None:
    """回执幂等；不可见 70202；不存在 70201。"""
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(3)
        try:
            row = add_notice(session, title="阅读")
            draft = add_notice(session, title="草稿", status=NOTICE_STATUS_DRAFT)
            await session.flush()
            service = _service(session)
            first = await service.mark_read(int(row.id), now=now)
            second = await service.mark_read(int(row.id), now=now)
            assert first.read_at == second.read_at
            receipts = (
                (await session.execute(select(SysNoticeRead).where(SysNoticeRead.notice_id == int(row.id))))
                .scalars()
                .all()
            )
            assert len(receipts) == 1
            with pytest.raises(NoticeNotVisibleError):
                await service.mark_read(int(draft.id), now=now)
            with pytest.raises(NoticeNotFoundError):
                await service.mark_read(999999, now=now)
        finally:
            reset_user(tokens)


async def test_read_stats_and_unavailable(shared_tenant_engine: AsyncEngine) -> None:
    """统计：应读 / 已读 / 未读与读>应读边界；应读不可用 70206。"""
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            row = add_notice(session, title="统计")
            await session.flush()
            add_receipt(session, notice_id=int(row.id), user_id=1)
            add_receipt(session, notice_id=int(row.id), user_id=2)
            await session.flush()
            service = _service(session)
            stats = await service.read_stats(int(row.id), audience_reader=cast("object", FakeAudience(5)))  # pyright: ignore[reportArgumentType]
            assert (stats.audience_count, stats.read_count, stats.unread_count) == (5, 2, 3)
            stats = await service.read_stats(int(row.id), audience_reader=cast("object", FakeAudience(1)))  # pyright: ignore[reportArgumentType]
            assert (stats.audience_count, stats.read_count, stats.unread_count) == (1, 2, 0)
            with pytest.raises(NoticeAudienceUnavailableError):
                await service.read_stats(
                    int(row.id),
                    audience_reader=cast("object", FakeAudience(error=NoticeAudienceUnavailableError("x"))),  # pyright: ignore[reportArgumentType]
                )
            with pytest.raises(NoticeNotFoundError):
                await service.read_stats(999999, audience_reader=cast("object", FakeAudience(1)))  # pyright: ignore[reportArgumentType]
        finally:
            reset_user(tokens)


async def test_expire_batches_and_events(shared_tenant_engine: AsyncEngine) -> None:
    """过期扫描：批量下线、发 offline 事件、已下线不重复。"""
    now = utc_now()
    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            first = add_notice(session, title="到期1", expire_at=now - timedelta(minutes=2))
            second = add_notice(session, title="到期2", expire_at=now - timedelta(minutes=1))
            add_notice(session, title="未到期", expire_at=now + timedelta(hours=1))
            await session.flush()
            outbox = Outbox()
            service = _service(session, outbox=outbox)
            assert await service.expire(now=now, limit=10, tenant_id="1001") == 2
            assert {event.payload["action"] for event in outbox.events} == {NOTICE_ACTION_OFFLINE}
            assert first.status == NOTICE_STATUS_OFFLINE and second.status == NOTICE_STATUS_OFFLINE
            assert await service.expire(now=now, limit=10, tenant_id="1001") == 0
        finally:
            reset_user(tokens)


async def test_no_user_context(shared_tenant_engine: AsyncEngine) -> None:
    """无登录用户上下文：列表 / 详情取当前用户失败 10001。"""
    async with write_session(shared_tenant_engine) as session:
        service = _service(session)
        with pytest.raises(ParamError):
            await service.list_published(page=1, size=10, now=utc_now(), locale="zh-CN")


async def test_locale_limit_aware_time_and_update_fields(shared_tenant_engine: AsyncEngine) -> None:
    """语言数上限 / 带时区时间 / 编辑类型优先级与时间字段 / limit=0。"""
    from datetime import UTC, datetime

    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            service = _service(session)
            many: ConcurrentStableDict[str, NoticeTextInput] = ConcurrentStableDict(
                {"zh-CN": NoticeTextInput(title="中")}
            )
            for index in range(50):
                many.set(f"l{index}", NoticeTextInput(title=f"t{index}"))
            with pytest.raises(ParamError):
                await service.create(
                    NoticeCreateRequest(i18n=many), now=utc_now(), request_locale="zh-CN", tenant_id="1001"
                )

            aware = datetime.now(UTC) + timedelta(hours=1)
            detail = await service.create(
                NoticeCreateRequest(i18n=_texts(), publish_at=aware, expire_at=aware + timedelta(days=1)),
                now=utc_now(),
                request_locale="zh-CN",
                tenant_id="1001",
            )
            row = (await session.execute(select(SysNotice).where(SysNotice.id == detail.id))).scalars().one()
            assert row.publish_at.tzinfo is None
            target = datetime.now(UTC) + timedelta(days=2)
            updated = await service.update(
                detail.id,
                NoticeUpdateRequest(
                    type="policy",
                    priority="high",
                    publish_at=target,
                    expire_at=target + timedelta(days=1),
                ),
                now=utc_now(),
                request_locale="zh-CN",
                tenant_id="1001",
                can_manage=True,
            )
            assert updated.type == "policy" and updated.priority == "high"
            assert updated.expire_at is not None
            assert await service.expire(now=utc_now(), limit=0, tenant_id="1001") == 0
        finally:
            reset_user(tokens)


async def test_mark_read_integrity_race(shared_tenant_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """并发重复回执：保存点回滚后重查既有行。"""
    from sqlalchemy.exc import IntegrityError

    from bms_notification.domains.notification.repositories.notice import NoticeRepository

    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            row = add_notice(session, title="并发阅读")
            await session.flush()
            service = _service(session)
            existing = SysNoticeRead(notice_id=int(row.id), user_id=1, read_at=utc_now())
            calls = {"get": 0}

            async def _get(self: object, notice_id: int, user_id: int) -> SysNoticeRead | None:
                del self, notice_id, user_id
                calls["get"] += 1
                return None if calls["get"] == 1 else existing

            async def _add(self: object, notice_id: int, user_id: int, *, read_at: object) -> object:
                del self, notice_id, user_id, read_at
                raise IntegrityError("INSERT", {}, Exception("duplicate"))

            monkeypatch.setattr(NoticeRepository, "get_receipt", _get)
            monkeypatch.setattr(NoticeRepository, "add_receipt", _add)
            receipt = await service.mark_read(int(row.id), now=utc_now())
            assert receipt.read_at == existing.read_at
            assert calls["get"] == 2
        finally:
            reset_user(tokens)


async def test_expire_no_progress_breaks(shared_tenant_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """到期行全部并发冲突时不死循环，直接返回 0。"""
    from bms_notification.domains.notification.repositories.notice import NoticeRepository

    async with write_session(shared_tenant_engine) as session:
        tokens = use_user(1)
        try:
            row = add_notice(session, title="冲突", expire_at=utc_now() - timedelta(minutes=1))
            await session.flush()
            service = _service(session)

            async def _expired(self: object, *, now: object, limit: int) -> ConcurrentStableList[SysNotice]:
                del self, now, limit
                return ConcurrentStableList([row])

            async def _mark(self: object, row: SysNotice) -> bool:
                del self, row
                return False

            monkeypatch.setattr(NoticeRepository, "expired", _expired)
            monkeypatch.setattr(NoticeRepository, "mark_offline", _mark)
            assert await service.expire(now=utc_now(), limit=10, tenant_id="1001") == 0
        finally:
            reset_user(tokens)

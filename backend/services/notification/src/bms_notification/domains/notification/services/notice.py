"""公告业务服务：状态机 / 可见性 / 多语言 / 富文本清洗 / 发件箱 / 已读统计 / 过期下线。

事务由调用方（路由工作单元）负责，本层只 `flush`；事件与业务写同事务写发件箱。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import (
    NoticeContentInvalidError,
    NoticeNotFoundError,
    NoticeNotVisibleError,
    NoticeStatusConflictError,
    NoticeTimeInvalidError,
    ParamError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.i18n.base import get_default_locale
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.store import SqlOutboxStore
from bms_core.repositories.i18n import (
    load_i18n_all_texts,
    load_i18n_texts,
    replace_i18n_texts,
    soft_delete_i18n,
)
from bms_core.richtext.sanitize import (
    MAX_NOTICE_CONTENT_BYTES,
    MAX_NOTICE_TITLE_LENGTH,
    html_text_length,
    sanitize_html,
)
from bms_core.schemas.pagination import BasePageResponse
from bms_notification.domains.notification.models.notice import SysNotice, SysNoticeI18n
from bms_notification.domains.notification.notice_constants import (
    NOTICE_ACTION_OFFLINE,
    NOTICE_ACTION_PUBLISHED,
    NOTICE_ACTION_UPDATED,
    NOTICE_EVENT,
    NOTICE_PRIORITY_OPTION_SET,
    NOTICE_STATUS_DRAFT,
    NOTICE_STATUS_OFFLINE,
    NOTICE_STATUS_PUBLISHED,
    NOTICE_STATUSES,
    NOTICE_TYPE_OPTION_SET,
)
from bms_notification.domains.notification.repositories.notice import NoticeRepository
from bms_notification.domains.notification.schemas.notice import (
    NoticeCreateRequest,
    NoticeDetail,
    NoticeListItem,
    NoticeReadReceipt,
    NoticeReadStats,
    NoticeTextInput,
    NoticeTextOutput,
    NoticeUpdateRequest,
)
from bms_notification.domains.notification.services.notice_audience import NoticeAudienceReader

__all__ = ["MAX_I18N_LOCALES", "NoticeService"]

MAX_I18N_LOCALES = 50
"""公告单次提交的语言数上限（防滥用；正常语言清单远小于此）。"""

_TEXT_COLUMNS: ConcurrentStableList[str] = ConcurrentStableList(("title", "content"))
"""公告附表文案列（标题 + 正文，各列独立回退）。"""


class NoticeService(BaseFrameworkObject):
    """公告业务服务（当前租户库会话）。"""

    def __init__(
        self,
        session: DbSession,
        *,
        option_sets: BaseOptionSetRegistry,
        outbox: BaseOutboxStore | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            option_sets: 选项集注册表（类型 / 优先级值域校验）。
            outbox: 发件箱存储（None 使用 SQL 实现）。
        """
        self._session = session
        self._option_sets = option_sets
        self._repository = NoticeRepository(session)
        self._outbox = (
            outbox if outbox is not None else SqlOutboxStore(contract_mode=get_settings().event.contract_mode)
        )

    async def create(
        self,
        req: NoticeCreateRequest,
        *,
        now: datetime,
        request_locale: str,
        tenant_id: str | None,
    ) -> NoticeDetail:
        """新建公告（草稿或直接发布）。

        Args:
            req: 新建请求。
            now: 当前 UTC 时间。
            request_locale: 请求语言（必填语言口径）。
            tenant_id: 租户主键（事件信封）。

        Returns:
            NoticeDetail: 新建后的详情。

        Raises:
            ParamError: 类型 / 优先级不在选项集，或语言映射非法（10001）。
            NoticeTimeInvalidError: 时间非法（70203）。
            NoticeContentInvalidError: 内容为空 / 超长（70205）。
        """
        self._validate_option(req.type, NOTICE_TYPE_OPTION_SET, "公告类型")
        self._validate_option(req.priority, NOTICE_PRIORITY_OPTION_SET, "公告优先级")
        texts = self._normalize_i18n(req.i18n, required_locale=request_locale)
        title, content = self._derive_main(texts, required_locale=request_locale)
        publish_at = self._to_utc_naive(req.publish_at) if req.publish_at is not None else now
        expire_at = self._to_utc_naive(req.expire_at) if req.expire_at is not None else None
        publishing = bool(req.publish)
        self._validate_time(publish_at, expire_at, publishing=publishing, now=now)
        if publishing:
            self._require_content(content)
        row = SysNotice(
            title=title,
            content=content,
            type=req.type,
            priority=req.priority,
            is_top=bool(req.is_top),
            publish_at=publish_at,
            expire_at=expire_at,
            status=NOTICE_STATUS_PUBLISHED if publishing else NOTICE_STATUS_DRAFT,
        )
        self._session.add(row)
        await self._session.flush()
        await replace_i18n_texts(
            self._session, SysNoticeI18n, "notice_id", int(row.id), texts, text_columns=_TEXT_COLUMNS
        )
        if publishing:
            await self._emit(row, NOTICE_ACTION_PUBLISHED, tenant_id)
        return await self._detail_contract(row, locale=request_locale, now=now, can_manage=True)

    async def update(
        self,
        notice_id: int,
        req: NoticeUpdateRequest,
        *,
        now: datetime,
        request_locale: str,
        tenant_id: str | None,
        can_manage: bool,
    ) -> NoticeDetail:
        """编辑公告（含置顶、草稿发布、已发布重新发布）。

        Args:
            notice_id: 公告主键。
            req: 编辑请求。
            now: 当前 UTC 时间。
            request_locale: 请求语言。
            tenant_id: 租户主键（事件信封）。
            can_manage: 调用方是否持有 `notice:update`（决定是否返回完整多语言映射）。

        Returns:
            NoticeDetail: 编辑后的详情。

        Raises:
            NoticeNotFoundError: 公告不存在（70201）。
            NoticeStatusConflictError: 已下线再发布 / 撤回草稿（70204）。
            NoticeTimeInvalidError: 时间非法（70203）。
            NoticeContentInvalidError: 内容为空 / 超长（70205）。
        """
        row = await self._require_notice(notice_id)
        if row.status == NOTICE_STATUS_OFFLINE:
            raise NoticeStatusConflictError("已下线公告不可再编辑或发布")
        if req.publish is False:
            raise NoticeStatusConflictError("不支持把已发布公告撤回为草稿")
        fields = req.model_fields_set
        if req.type is not None:
            self._validate_option(req.type, NOTICE_TYPE_OPTION_SET, "公告类型")
            row.type = req.type
        if req.priority is not None:
            self._validate_option(req.priority, NOTICE_PRIORITY_OPTION_SET, "公告优先级")
            row.priority = req.priority
        if req.is_top is not None:
            row.is_top = bool(req.is_top)
        if "publish_at" in fields and req.publish_at is not None:
            row.publish_at = self._to_utc_naive(req.publish_at)
        if "expire_at" in fields:
            row.expire_at = self._to_utc_naive(req.expire_at) if req.expire_at is not None else None
        texts = self._normalize_i18n(req.i18n, required_locale=request_locale) if req.i18n else None
        if texts is not None:
            title, content = self._derive_main(texts, required_locale=request_locale)
            row.title = title
            row.content = content
            await replace_i18n_texts(
                self._session, SysNoticeI18n, "notice_id", int(row.id), texts, text_columns=_TEXT_COLUMNS
            )
        publishing = bool(req.publish) or row.status == NOTICE_STATUS_PUBLISHED
        self._validate_time(row.publish_at, row.expire_at, publishing=publishing, now=now)
        if publishing:
            self._require_content(row.content)
        if row.status == NOTICE_STATUS_DRAFT and publishing:
            row.status = NOTICE_STATUS_PUBLISHED
            await self._session.flush()
            await self._emit(row, NOTICE_ACTION_PUBLISHED, tenant_id)
        elif row.status == NOTICE_STATUS_PUBLISHED:
            await self._session.flush()
            await self._emit(row, NOTICE_ACTION_UPDATED, tenant_id)
        else:
            await self._session.flush()
        return await self._detail_contract(row, locale=request_locale, now=now, can_manage=can_manage)

    async def delete(self, notice_id: int) -> bool:
        """软删除公告（连带软删多语言附表）。

        Args:
            notice_id: 公告主键。

        Returns:
            bool: 删除成功 True。

        Raises:
            NoticeNotFoundError: 公告不存在（70201）。
        """
        row = await self._require_notice(notice_id)
        row.soft_delete()
        await soft_delete_i18n(self._session, SysNoticeI18n, "notice_id", int(row.id))
        await self._session.flush()
        return True

    async def list_manage(
        self,
        *,
        page: int,
        size: int,
        now: datetime,
        locale: str,
        keyword: str | None,
        status: str | None,
        notice_type: str | None,
        can_manage: bool,
    ) -> BasePageResponse[NoticeListItem]:
        """管理列表（无 `notice:update` 时只看发布中且未过期）。

        Args:
            page: 页码。
            size: 每页条数。
            now: 当前 UTC 时间。
            locale: 请求语言。
            keyword: 标题关键字。
            status: 状态筛选。
            notice_type: 类型筛选。
            can_manage: 是否持有 `notice:update`。

        Returns:
            BasePageResponse[NoticeListItem]: 分页列表。

        Raises:
            ParamError: 状态 / 类型非法（10001）。
        """
        if status is not None and status not in NOTICE_STATUSES:
            raise ParamError(f"公告状态非法：{status}")
        if notice_type is not None:
            self._validate_option(notice_type, NOTICE_TYPE_OPTION_SET, "公告类型")
        rows, total = await self._repository.page_manage(
            page=page,
            size=size,
            now=now,
            keyword=keyword,
            status=status,
            notice_type=notice_type,
            visible_only=not can_manage,
        )
        user_id = self._current_user_id()
        read_ids = await self._repository.read_ids(user_id, ConcurrentStableList(int(row.id) for row in rows))
        localized = await self._localized_map(rows, locale)
        items: ConcurrentStableList[NoticeListItem] = ConcurrentStableList()
        for row in rows:
            items.add(self._list_item(row, localized, int(row.id) in read_ids))
        return BasePageResponse[NoticeListItem](list=items, total=total, page=page, size=size)

    async def list_published(
        self, *, page: int, size: int, now: datetime, locale: str
    ) -> BasePageResponse[NoticeListItem]:
        """全员发布中列表（置顶优先）。

        Args:
            page: 页码。
            size: 每页条数。
            now: 当前 UTC 时间。
            locale: 请求语言。

        Returns:
            BasePageResponse[NoticeListItem]: 分页列表。
        """
        rows, total = await self._repository.page_published(page=page, size=size, now=now)
        user_id = self._current_user_id()
        read_ids = await self._repository.read_ids(user_id, ConcurrentStableList(int(row.id) for row in rows))
        localized = await self._localized_map(rows, locale)
        items: ConcurrentStableList[NoticeListItem] = ConcurrentStableList()
        for row in rows:
            items.add(self._list_item(row, localized, int(row.id) in read_ids))
        return BasePageResponse[NoticeListItem](list=items, total=total, page=page, size=size)

    async def detail(self, notice_id: int, *, now: datetime, locale: str, can_manage: bool) -> NoticeDetail:
        """公告详情（普通用户仅发布中可见）。

        Args:
            notice_id: 公告主键。
            now: 当前 UTC 时间。
            locale: 请求语言。
            can_manage: 是否持有 `notice:update`。

        Returns:
            NoticeDetail: 详情。

        Raises:
            NoticeNotFoundError: 不存在或普通用户不可见（70201）。
        """
        row = await self._require_notice(notice_id)
        if not can_manage and not self._is_visible(row, now):
            raise NoticeNotFoundError("公告不存在或已下线")
        return await self._detail_contract(row, locale=locale, now=now, can_manage=can_manage)

    async def mark_read(self, notice_id: int, *, now: datetime) -> NoticeReadReceipt:
        """写已读回执（幂等，只允许可见公告）。

        Args:
            notice_id: 公告主键。
            now: 当前 UTC 时间。

        Returns:
            NoticeReadReceipt: 回执（重复阅读返回首次时间）。

        Raises:
            NoticeNotFoundError: 公告不存在（70201）。
            NoticeNotVisibleError: 公告不可读（70202）。
        """
        row = await self._require_notice(notice_id)
        if not self._is_visible(row, now):
            raise NoticeNotVisibleError("公告未发布或已下线，不能写已读回执")
        user_id = self._current_user_id()
        existing = await self._repository.get_receipt(int(row.id), user_id)
        if existing is not None:
            return NoticeReadReceipt(notice_id=int(row.id), read_at=existing.read_at)
        try:
            async with self._session.begin_nested():  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
                receipt = await self._repository.add_receipt(int(row.id), user_id, read_at=now)
        except IntegrityError:
            existing = await self._repository.get_receipt(int(row.id), user_id)
            if existing is None:  # pragma: no cover - 唯一冲突后必能读到既有行
                raise
            return NoticeReadReceipt(notice_id=int(row.id), read_at=existing.read_at)
        return NoticeReadReceipt(notice_id=int(row.id), read_at=receipt.read_at)

    async def read_stats(self, notice_id: int, *, audience_reader: NoticeAudienceReader) -> NoticeReadStats:
        """已读统计（应读人数实时读取平台启用用户数）。

        Args:
            notice_id: 公告主键。
            audience_reader: 应读人数读取器。

        Returns:
            NoticeReadStats: 统计结果。

        Raises:
            NoticeNotFoundError: 公告不存在（70201）。
            NoticeAudienceUnavailableError: 应读人数不可用（70206）。
        """
        row = await self._require_notice(notice_id)
        read_count = await self._repository.read_count(int(row.id))
        audience_count = await audience_reader.count_enabled()
        return NoticeReadStats(
            notice_id=int(row.id),
            audience_count=audience_count,
            read_count=read_count,
            unread_count=max(audience_count - read_count, 0),
        )

    async def expire(self, *, now: datetime, limit: int, tenant_id: str | None) -> int:
        """批量下线到期公告并发布 `offline` 事件。

        Args:
            now: 当前 UTC 时间。
            limit: 本次最多处理条数。
            tenant_id: 租户主键（事件信封）。

        Returns:
            int: 成功下线并发出事件的公告数。
        """
        processed = 0
        while processed < limit:
            rows = await self._repository.expired(now=now, limit=min(limit - processed, 200))
            if not rows:
                break
            progressed = False
            for row in rows:
                if await self._repository.mark_offline(row):
                    await self._emit(row, NOTICE_ACTION_OFFLINE, tenant_id)
                    processed += 1
                    progressed = True
            if not progressed:
                break
        return processed

    def _validate_option(self, value: str, option_set_key: str, label: str) -> None:
        """校验类型 / 优先级是否在选项集值域内。

        Args:
            value: 选项值。
            option_set_key: 选项集标识。
            label: 中文标签（错误消息）。

        Raises:
            ParamError: 不在值域内（10001）。
        """
        violations = self._option_sets.validate(value, option_set_key=option_set_key)
        if violations:
            raise ParamError(f"{label}非法：{value}")

    def _normalize_i18n(
        self, raw: ConcurrentStableDict[str, NoticeTextInput], *, required_locale: str
    ) -> ConcurrentStableDict[str, ConcurrentStableDict[str, str]]:
        """归一多语言文案：校验 locale / 标题 / 正文清洗与长度。

        Args:
            raw: 语言标识 → 文案入参（Pydantic 模型会先转成 `NoticeTextInput`）。
            required_locale: 必填语言（请求语言）。

        Returns:
            ConcurrentStableDict[str, ConcurrentStableDict[str, str]]: 语言 → （列 → 文本）。

        Raises:
            ParamError: 语言映射为空 / 语言数超限 / locale 非法（10001）。
            NoticeContentInvalidError: 标题或正文超长（70205）。
        """
        if not raw:
            raise ParamError("公告多语言文案不得为空")
        if len(raw) > MAX_I18N_LOCALES:
            raise ParamError(f"公告语言数不得超过 {MAX_I18N_LOCALES} 个")
        result: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for locale, item in raw.items():
            key = (locale or "").strip()
            if not key or len(key) > 16 or any(ch.isspace() for ch in key):
                raise ParamError(f"公告语言标识非法：{locale!r}")
            text = item
            title_raw = text.title
            content_raw = text.content
            title = self._clean_title(title_raw)
            content = self._clean_content(content_raw)
            if not title and not content:
                continue
            bucket: ConcurrentStableDict[str, str] = ConcurrentStableDict({"title": title, "content": content})
            result.set(key, bucket)
        if not result:
            raise ParamError("公告多语言文案不得为空")
        required = result.get(required_locale)
        if required is None or not (required.get("title") or ""):
            raise ParamError(f"缺少必填语言（{required_locale}）的公告标题")
        return result

    def _derive_main(
        self, texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]], *, required_locale: str
    ) -> tuple[str, str]:
        """派生主表默认标题 / 正文（系统默认语言 → 请求语言 → 首个有值语言）。

        Args:
            texts: 归一后的多语言文案。
            required_locale: 请求语言。

        Returns:
            tuple[str, str]: （标题, 正文）。

        Raises:
            NoticeContentInvalidError: 所有语言都没有标题（70205）。
        """
        order: ConcurrentStableList[str] = ConcurrentStableList()
        for candidate in (get_default_locale(), required_locale, *texts.keys()):
            if candidate and candidate not in order:
                order.add(candidate)
        title = ""
        content = ""
        for locale in order:
            bucket = texts.get(locale)
            if bucket is None:
                continue
            if not title and bucket.get("title"):
                title = bucket.get("title") or ""
            if not content and bucket.get("content"):
                content = bucket.get("content") or ""
        if not title:
            raise NoticeContentInvalidError("公告标题不得为空")
        return title, content

    def _clean_title(self, raw: str) -> str:
        """清洗标题（纯文本，去空白 + 长度校验）。

        Args:
            raw: 原始标题。

        Returns:
            str: 清洗后的标题。

        Raises:
            NoticeContentInvalidError: 标题超长（70205）。
        """
        title = (raw or "").strip()
        if len(title) > MAX_NOTICE_TITLE_LENGTH:
            raise NoticeContentInvalidError(f"公告标题不得超过 {MAX_NOTICE_TITLE_LENGTH} 字符")
        return title

    def _clean_content(self, raw: str) -> str:
        """清洗正文（白名单 HTML + UTF-8 字节校验）。

        Args:
            raw: 原始正文。

        Returns:
            str: 净化后的 HTML。

        Raises:
            NoticeContentInvalidError: 正文超长（70205）。
        """
        cleaned = sanitize_html(raw or "")
        if len(cleaned.encode("utf-8")) > MAX_NOTICE_CONTENT_BYTES:
            raise NoticeContentInvalidError(f"公告正文不得超过 {MAX_NOTICE_CONTENT_BYTES} 字节")
        return cleaned

    def _require_content(self, content: str) -> None:
        """发布时要求正文有可读文本。

        Args:
            content: 净化后的正文 HTML。

        Raises:
            NoticeContentInvalidError: 正文去标签后为空（70205）。
        """
        if html_text_length(content) == 0:
            raise NoticeContentInvalidError("公告发布时正文不得为空")

    def _validate_time(
        self, publish_at: datetime, expire_at: datetime | None, *, publishing: bool, now: datetime
    ) -> None:
        """校验发布时间与过期时间。

        Args:
            publish_at: 发布时间（UTC）。
            expire_at: 过期时间（UTC；可空）。
            publishing: 本次是否进入 / 保持发布中。
            now: 当前 UTC 时间。

        Raises:
            NoticeTimeInvalidError: 过期时间不晚于发布时间，或发布已过期（70203）。
        """
        if expire_at is not None and expire_at <= publish_at:
            raise NoticeTimeInvalidError("公告过期时间必须晚于发布时间")
        if publishing and expire_at is not None and expire_at <= now:
            raise NoticeTimeInvalidError("公告过期时间不得早于当前时间")

    async def _require_notice(self, notice_id: int) -> SysNotice:
        """按主键取公告，不存在抛 70201。

        Args:
            notice_id: 公告主键。

        Returns:
            SysNotice: 公告行。

        Raises:
            NoticeNotFoundError: 不存在或已软删（70201）。
        """
        row = await self._repository.get_any(notice_id)
        if row is None:
            raise NoticeNotFoundError(f"公告不存在：{notice_id}")
        return row

    async def _localized_map(
        self, rows: ConcurrentStableList[SysNotice], locale: str
    ) -> ConcurrentStableDict[int, ConcurrentStableDict[str, str]]:
        """按语言优先级装载列表文案。

        Args:
            rows: 公告行。
            locale: 请求语言。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, str]]: 公告 ID → （列 → 文本）。
        """
        if not rows:
            return ConcurrentStableDict()
        owner_ids = ConcurrentStableList(int(row.id) for row in rows)
        return await load_i18n_texts(
            self._session,
            SysNoticeI18n,
            "notice_id",
            owner_ids,
            locales=self._locale_priority(locale),
            text_columns=_TEXT_COLUMNS,
        )

    async def _detail_contract(self, row: SysNotice, *, locale: str, now: datetime, can_manage: bool) -> NoticeDetail:
        """组装详情契约（本地化标题 / 正文；管理侧含完整多语言映射与已读状态）。

        Args:
            row: 公告行。
            locale: 请求语言。
            now: 当前 UTC 时间。
            can_manage: 是否返回完整多语言映射。

        Returns:
            NoticeDetail: 详情契约。
        """
        localized = await self._localized_map(ConcurrentStableList((row,)), locale)
        text = localized.get(int(row.id), ConcurrentStableDict[str, str]())
        title = text.get("title") or row.title
        content = text.get("content") or row.content
        user_id = self._current_user_id()
        receipt = await self._repository.get_receipt(int(row.id), user_id)
        full_i18n = await self._full_i18n(int(row.id)) if can_manage else None
        return NoticeDetail(
            id=int(row.id),
            title=title,
            content=content,
            type=row.type,
            priority=row.priority,
            is_top=bool(row.is_top),
            status=row.status,
            publish_at=row.publish_at,
            expire_at=row.expire_at,
            is_read=receipt is not None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            i18n=full_i18n,
        )

    async def _full_i18n(self, notice_id: int) -> ConcurrentStableDict[str, NoticeTextOutput]:
        """取公告全部语言文案（管理侧编辑回显）。

        Args:
            notice_id: 公告主键。

        Returns:
            ConcurrentStableDict[str, NoticeTextOutput]: 语言 → 文案。
        """
        all_texts = await load_i18n_all_texts(
            self._session,
            SysNoticeI18n,
            "notice_id",
            ConcurrentStableList((notice_id,)),
            text_columns=_TEXT_COLUMNS,
        )
        result: ConcurrentStableDict[str, NoticeTextOutput] = ConcurrentStableDict()
        by_locale = all_texts.get(notice_id)
        if by_locale is None:
            return result
        for locale, values in by_locale.items():
            result.set(
                locale,
                NoticeTextOutput(title=values.get("title") or "", content=values.get("content") or ""),
            )
        return result

    def _list_item(
        self,
        row: SysNotice,
        localized: ConcurrentStableDict[int, ConcurrentStableDict[str, str]],
        is_read: bool,
    ) -> NoticeListItem:
        """组装列表行（只含标题，不含正文）。

        Args:
            row: 公告行。
            localized: 本地化文案映射。
            is_read: 当前用户是否已读。

        Returns:
            NoticeListItem: 列表行。
        """
        text = localized.get(int(row.id), ConcurrentStableDict[str, str]())
        return NoticeListItem(
            id=int(row.id),
            title=text.get("title") or row.title,
            type=row.type,
            priority=row.priority,
            is_top=bool(row.is_top),
            status=row.status,
            publish_at=row.publish_at,
            expire_at=row.expire_at,
            is_read=is_read,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _emit(self, row: SysNotice, action: str, tenant_id: str | None) -> None:
        """在业务事务内写 `sys.notice.published` 发件箱。

        Args:
            row: 公告行。
            action: `published` / `updated` / `offline`。
            tenant_id: 租户主键。

        Raises:
            ParamError: 缺少租户上下文（10001）。
        """
        if not tenant_id:
            raise ParamError("公告事件缺少租户上下文")
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "notice_id": str(int(row.id)),
                "title": row.title,
                "is_top": bool(row.is_top),
                "action": action,
                "type": row.type,
                "priority": row.priority,
                "publish_at": row.publish_at.isoformat(),
            }
        )
        if row.expire_at is not None:
            payload.set("expire_at", row.expire_at.isoformat())
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=NOTICE_EVENT,
                payload=payload,
                tenant_id=tenant_id,
                aggregate_key=f"notice:{int(row.id)}",
            ),
        )

    @staticmethod
    def _is_visible(row: SysNotice, now: datetime) -> bool:
        """公告可见性判定（发布中 + 时间窗口）。

        Args:
            row: 公告行。
            now: 当前 UTC 时间。

        Returns:
            bool: 可见为 True。
        """
        if row.status != NOTICE_STATUS_PUBLISHED:
            return False
        if row.publish_at > now:
            return False
        return row.expire_at is None or now < row.expire_at

    @staticmethod
    def _locale_priority(locale: str) -> ConcurrentStableList[str]:
        """语言优先级：请求语言 → 系统默认语言。

        Args:
            locale: 请求语言。

        Returns:
            ConcurrentStableList[str]: 语言优先级序（去空去重）。
        """
        result: ConcurrentStableList[str] = ConcurrentStableList()
        for candidate in (locale, get_default_locale()):
            value = (candidate or "").strip()
            if value and value not in result:
                result.add(value)
        return result

    @staticmethod
    def _to_utc_naive(value: datetime) -> datetime:
        """把带时区 / 无时区时间统一为 UTC naive。

        Args:
            value: 输入时间。

        Returns:
            datetime: UTC naive 时间。
        """
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    @staticmethod
    def _current_user_id() -> int:
        """取当前用户主键。

        Returns:
            int: 用户主键。

        Raises:
            ParamError: 无登录用户上下文（10001）。
        """
        user_id = get_current_user_id()
        if user_id is None:
            raise ParamError("缺少登录用户上下文")
        return user_id

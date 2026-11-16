"""邮件模板业务：租户模板 CRUD、内置默认合并、多语言三级回退、沙箱校验与渲染。

事务由调用方负责，本层只 `flush`。
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConflictError,
    MailTemplateNotFoundError,
    ParamError,
    TemplateRenderError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.i18n.base import get_default_locale
from bms_core.repositories.i18n import (
    load_i18n_all_texts,
    load_i18n_texts,
    replace_i18n_texts,
    soft_delete_i18n,
)
from bms_core.schemas.pagination import BasePageResponse
from bms_notification.domains.notification.mail_constants import (
    MAIL_TEMPLATE_CONTENT_MAX_BYTES,
    MAIL_TEMPLATE_SOURCE_BUILTIN,
    MAIL_TEMPLATE_SOURCE_TENANT,
    MAIL_TEMPLATE_STATUS_ENABLED,
    MAIL_TEMPLATE_SUBJECT_MAX_LENGTH,
)
from bms_notification.domains.notification.mail_defaults import (
    BUILTIN_MAIL_TEMPLATES,
    MailTemplateDefault,
    find_builtin_mail_template,
)
from bms_notification.domains.notification.models.mail import SysMailTemplate, SysMailTemplateI18n
from bms_notification.domains.notification.rendering import render_template, validate_template
from bms_notification.domains.notification.repositories.mail import MailRepository
from bms_notification.domains.notification.schemas.mail import (
    MailLogItem,
    MailTemplateCreateRequest,
    MailTemplateDetail,
    MailTemplateListItem,
    MailTemplateUpdateRequest,
    MailTextInput,
    MailTextOutput,
)

__all__ = ["MAX_TEMPLATE_LOCALES", "MailTemplateService"]

MAX_TEMPLATE_LOCALES = 50
"""单模板语言数上限。"""

_TEXT_COLUMNS: ConcurrentStableList[str] = ConcurrentStableList(("subject", "content"))
"""邮件附表文案列。"""


class MailTemplateService(BaseFrameworkObject):
    """邮件模板业务服务（当前租户库会话）。"""

    def __init__(self, session: DbSession, *, render_timeout_seconds: float) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            render_timeout_seconds: 沙箱渲染超时（秒）。
        """
        self._session = session
        self._render_timeout = render_timeout_seconds
        self._repository = MailRepository(session)

    async def list(
        self,
        *,
        page: int,
        size: int,
        locale: str,
        keyword: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> BasePageResponse[MailTemplateListItem]:
        """合并列出租户模板与内置默认（租户同 code 覆盖内置）。

        Args:
            page: 页码。
            size: 每页条数。
            locale: 生效语言。
            keyword: code / 名称关键字。
            status: 状态筛选。
            source: 来源筛选（tenant / builtin）。

        Returns:
            BasePageResponse[MailTemplateListItem]: 分页结果。
        """
        rows = await self._repository.list_templates(keyword=keyword, status=status)
        subjects = await self._load_subject_map(ConcurrentStableList(int(row.id) for row in rows), locale=locale)
        items: ConcurrentStableList[MailTemplateListItem] = ConcurrentStableList()
        tenant_codes: ConcurrentStableList[str] = ConcurrentStableList()
        for row in rows:
            tenant_codes.append(row.code)
            if source == MAIL_TEMPLATE_SOURCE_BUILTIN:
                continue
            items.append(
                MailTemplateListItem(
                    id=int(row.id),
                    code=row.code,
                    name=row.name,
                    status=row.status,
                    remark=row.remark,
                    source=MAIL_TEMPLATE_SOURCE_TENANT,
                    subject=subjects.get(int(row.id), row.subject),
                    updated_at=row.updated_at,
                )
            )
        if source != MAIL_TEMPLATE_SOURCE_TENANT:
            for default in BUILTIN_MAIL_TEMPLATES.values():
                if default.code in tenant_codes:
                    continue
                if status and status != MAIL_TEMPLATE_STATUS_ENABLED:
                    continue
                if (
                    keyword
                    and keyword.lower() not in default.code.lower()
                    and keyword.lower() not in default.name.lower()
                ):
                    continue
                items.append(self._builtin_item(default, locale=locale))
        ordered = sorted(items, key=lambda item: item.code)
        total = len(ordered)
        start = (page - 1) * size
        return BasePageResponse[MailTemplateListItem](
            list=ConcurrentStableList(ordered[start : start + size]), total=total, page=page, size=size
        )

    async def detail(self, template_id: int, *, locale: str) -> MailTemplateDetail:
        """租户模板详情（含完整多语言映射）。

        Args:
            template_id: 模板主键。
            locale: 生效语言。

        Returns:
            MailTemplateDetail: 详情。

        Raises:
            MailTemplateNotFoundError: 模板不存在（70301）。
        """
        row = await self._repository.get_template(template_id)
        if row is None:
            raise MailTemplateNotFoundError("邮件模板不存在或已删除")
        all_texts = await load_i18n_all_texts(
            self._session,
            SysMailTemplateI18n,
            "template_id",
            ConcurrentStableList((int(row.id),)),
            text_columns=_TEXT_COLUMNS,
        )
        by_locale = all_texts.get(int(row.id))
        subject, content = self._pick_texts(by_locale, locale=locale, fallback=(row.subject, row.content))
        i18n: ConcurrentStableDict[str, MailTextOutput] = ConcurrentStableDict()
        if by_locale:
            for item_locale, values in by_locale.items():
                i18n.set(
                    item_locale, MailTextOutput(subject=values.get("subject", ""), content=values.get("content", ""))
                )
        return MailTemplateDetail(
            id=int(row.id),
            code=row.code,
            name=row.name,
            status=row.status,
            remark=row.remark,
            source=MAIL_TEMPLATE_SOURCE_TENANT,
            subject=subject,
            updated_at=row.updated_at,
            content=content,
            i18n=i18n,
        )

    async def create(self, req: MailTemplateCreateRequest, *, request_locale: str) -> MailTemplateDetail:
        """新建租户模板（code 与内置默认相同即覆盖）。

        Args:
            req: 新建请求。
            request_locale: 请求语言。

        Returns:
            MailTemplateDetail: 新建后的详情。

        Raises:
            ConflictError: 租户同 code 模板已存在（10003）。
            ParamError: 文案为空 / 语言非法（10001）。
        """
        if await self._repository.get_template_by_code(req.code) is not None:
            raise ConflictError(f"邮件模板 code 已存在：{req.code}")
        texts = self._normalize_i18n(req.i18n, sample_params=req.sample_params)
        subject, content = self._derive_main(texts, request_locale=request_locale)
        row = SysMailTemplate(
            code=req.code,
            name=req.name,
            subject=subject,
            content=content,
            status=req.status,
            remark=req.remark,
        )
        self._session.add(row)
        await self._session.flush()
        await replace_i18n_texts(
            self._session, SysMailTemplateI18n, "template_id", int(row.id), texts, text_columns=_TEXT_COLUMNS
        )
        return await self.detail(int(row.id), locale=request_locale)

    async def update(
        self, template_id: int, req: MailTemplateUpdateRequest, *, request_locale: str
    ) -> MailTemplateDetail:
        """编辑租户模板（code 不可改；i18n 提供时整体替换）。

        Args:
            template_id: 模板主键。
            req: 编辑请求。
            request_locale: 请求语言。

        Returns:
            MailTemplateDetail: 编辑后的详情。

        Raises:
            MailTemplateNotFoundError: 模板不存在（70301）。
        """
        row = await self._repository.get_template(template_id)
        if row is None:
            raise MailTemplateNotFoundError("邮件模板不存在或已删除")
        if req.name is not None:
            row.name = req.name
        if req.status is not None:
            row.status = req.status
        if req.remark is not None:
            row.remark = req.remark
        if req.i18n:
            texts = self._normalize_i18n(req.i18n, sample_params=req.sample_params)
            subject, content = self._derive_main(texts, request_locale=request_locale)
            row.subject = subject
            row.content = content
            await replace_i18n_texts(
                self._session, SysMailTemplateI18n, "template_id", int(row.id), texts, text_columns=_TEXT_COLUMNS
            )
        await self._session.flush()
        return await self.detail(int(row.id), locale=request_locale)

    async def delete(self, template_id: int) -> bool:
        """软删除租户模板（连带软删附表；删除覆盖后发送回落内置默认）。

        Args:
            template_id: 模板主键。

        Returns:
            bool: 删除成功 True。

        Raises:
            MailTemplateNotFoundError: 模板不存在（70301）。
        """
        row = await self._repository.get_template(template_id)
        if row is None:
            raise MailTemplateNotFoundError("邮件模板不存在或已删除")
        row.soft_delete()
        await soft_delete_i18n(self._session, SysMailTemplateI18n, "template_id", int(row.id))
        await self._session.flush()
        return True

    async def test(
        self, template_id: int, *, params: ConcurrentStableDict[str, str], locale: str | None
    ) -> tuple[str, str]:
        """按 id 沙箱渲染（不发送）。

        Args:
            template_id: 模板主键。
            params: 渲染参数。
            locale: 语言（缺省系统默认语言）。

        Returns:
            tuple[str, str]: （主题, 正文）。

        Raises:
            MailTemplateNotFoundError: 模板不存在（70301）。
        """
        row = await self._repository.get_template(template_id)
        if row is None:
            raise MailTemplateNotFoundError("邮件模板不存在或已删除")
        resolved_locale = locale or get_default_locale()
        subject, content = await self._render_row(row, params=params, locale=resolved_locale)
        return subject, content

    async def preview(
        self, code: str, *, params: ConcurrentStableDict[str, str], locale: str | None
    ) -> tuple[str, str]:
        """按 code 渲染（租户优先、内置回落；不发送）。

        Args:
            code: 模板 code。
            params: 渲染参数。
            locale: 语言（缺省系统默认语言）。

        Returns:
            tuple[str, str]: （主题, 正文）。

        Raises:
            MailTemplateNotFoundError: 模板不存在或已停用（70301）。
        """
        resolved_locale = locale or get_default_locale()
        row = await self._repository.get_template_by_code(code)
        if row is not None:
            if row.status != MAIL_TEMPLATE_STATUS_ENABLED:
                raise MailTemplateNotFoundError(f"邮件模板已停用：{code}")
            return await self._render_row(row, params=params, locale=resolved_locale)
        default = find_builtin_mail_template(code)
        if default is None:
            raise MailTemplateNotFoundError(f"邮件模板不存在：{code}")
        subject_template, content_template = self._builtin_texts(default, locale=resolved_locale)
        return await self._render_pair(subject_template, content_template, params=params)

    async def render_for_send(
        self, code: str, *, params: ConcurrentStableDict[str, str], locale: str
    ) -> tuple[str, str, str]:
        """发送前渲染（租户优先、内置回落；停用不回落）。

        Args:
            code: 模板 code。
            params: 渲染参数。
            locale: 收件人语言。

        Returns:
            tuple[str, str, str]: （主题, 正文, 生效语言）。

        Raises:
            MailTemplateNotFoundError: 模板不存在或已停用（70301）。
        """
        row = await self._repository.get_template_by_code(code)
        if row is not None:
            if row.status != MAIL_TEMPLATE_STATUS_ENABLED:
                raise MailTemplateNotFoundError(f"邮件模板已停用：{code}")
            subject, content = await self._render_row(row, params=params, locale=locale)
            return subject, content, locale
        default = find_builtin_mail_template(code)
        if default is None:
            raise MailTemplateNotFoundError(f"邮件模板不存在：{code}")
        subject_template, content_template = self._builtin_texts(default, locale=locale)
        subject, content = await self._render_pair(subject_template, content_template, params=params)
        return subject, content, locale

    async def list_logs(
        self,
        *,
        page: int,
        size: int,
        status: str | None = None,
        template_code: str | None = None,
        recipient: str | None = None,
        user_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> BasePageResponse[MailLogItem]:
        """邮件发送记录分页。

        Args:
            page: 页码。
            size: 每页条数。
            status: 状态筛选。
            template_code: 模板 code。
            recipient: 收件地址（模糊）。
            user_id: 收件用户。
            start_at: 创建时间下限。
            end_at: 创建时间上限。

        Returns:
            BasePageResponse[MailLogItem]: 分页结果。
        """
        rows, total = await self._repository.page_logs(
            page=page,
            size=size,
            status=status,
            template_code=template_code,
            recipient=recipient,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )
        items = [
            MailLogItem(
                id=int(row.id),
                recipient=row.recipient,
                subject=row.subject,
                template_code=row.template_code,
                channel=row.channel,
                status=row.status,
                error_msg=row.error_msg,
                attempts=row.attempts,
                locale=row.locale,
                user_id=row.user_id,
                sent_at=row.sent_at,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return BasePageResponse[MailLogItem](list=ConcurrentStableList(items), total=total, page=page, size=size)

    async def _render_row(
        self, row: SysMailTemplate, *, params: ConcurrentStableDict[str, str], locale: str
    ) -> tuple[str, str]:
        """渲染租户模板行（按语言回退；缺省回落主表快照）。"""
        texts = await load_i18n_texts(
            self._session,
            SysMailTemplateI18n,
            "template_id",
            ConcurrentStableList((int(row.id),)),
            locales=self._locale_chain(locale),
            text_columns=_TEXT_COLUMNS,
        )
        default_bucket: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        bucket = texts.get(int(row.id), default_bucket)
        subject_template = bucket.get("subject") or row.subject
        content_template = bucket.get("content") or row.content
        return await self._render_pair(subject_template, content_template, params=params)

    async def _render_pair(
        self, subject_template: str, content_template: str, *, params: ConcurrentStableDict[str, str]
    ) -> tuple[str, str]:
        """渲染主题与正文（严格模式，超时 / 超限即失败）。"""
        render_params: ConcurrentStableDict[str, object] = cast("ConcurrentStableDict[str, object]", params)
        subject = await render_template(
            subject_template,
            render_params,
            max_bytes=MAIL_TEMPLATE_CONTENT_MAX_BYTES,
            timeout_seconds=self._render_timeout,
        )
        content = await render_template(
            content_template,
            render_params,
            max_bytes=MAIL_TEMPLATE_CONTENT_MAX_BYTES,
            timeout_seconds=self._render_timeout,
        )
        rendered_subject = subject.strip()
        if not rendered_subject or len(rendered_subject) > MAIL_TEMPLATE_SUBJECT_MAX_LENGTH:
            raise TemplateRenderError("邮件主题渲染后为空或超长")
        return rendered_subject, content

    def _normalize_i18n(
        self,
        raw: ConcurrentStableDict[str, MailTextInput],
        *,
        sample_params: ConcurrentStableDict[str, str] | None,
    ) -> ConcurrentStableDict[str, ConcurrentStableDict[str, str]]:
        """校验并归一多语言文案（去空白、限语言数、保存前沙箱校验）。"""
        if not raw:
            raise ParamError("邮件模板至少需要一种语言")
        if len(raw) > MAX_TEMPLATE_LOCALES:
            raise ParamError(f"邮件模板语言数超过 {MAX_TEMPLATE_LOCALES}")
        texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for locale, value in raw.items():
            key = (locale or "").strip()
            if not key or len(key) > 16:
                raise ParamError(f"语言标识非法：{locale!r}")
            subject = value.subject.strip()
            content = value.content.strip()
            if not subject:
                raise ParamError(f"邮件主题不得为空：{key}")
            if len(subject) > MAIL_TEMPLATE_SUBJECT_MAX_LENGTH:
                raise ParamError(f"邮件主题超过 {MAIL_TEMPLATE_SUBJECT_MAX_LENGTH} 字符：{key}")
            if not content:
                raise ParamError(f"邮件正文不得为空：{key}")
            if len(content.encode("utf-8")) > MAIL_TEMPLATE_CONTENT_MAX_BYTES:
                raise ParamError(f"邮件正文超过 {MAIL_TEMPLATE_CONTENT_MAX_BYTES} 字节：{key}")
            sample = cast("ConcurrentStableDict[str, object]", sample_params) if sample_params else None
            validate_template(
                subject,
                max_bytes=MAIL_TEMPLATE_CONTENT_MAX_BYTES,
                sample_params=sample,
            )
            validate_template(
                content,
                max_bytes=MAIL_TEMPLATE_CONTENT_MAX_BYTES,
                sample_params=sample,
            )
            texts.set(key, ConcurrentStableDict({"subject": subject, "content": content}))
        return texts

    def _derive_main(
        self, texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]], *, request_locale: str
    ) -> tuple[str, str]:
        """派生主表默认文案（系统默认语言 → 请求语言 → 首个有值语言）。"""
        for locale in self._locale_chain(request_locale):
            texts_bucket = self._find_texts(texts, locale)
            if texts_bucket is not None:
                return texts_bucket["subject"], texts_bucket["content"]
        for bucket in texts.values():
            return bucket["subject"], bucket["content"]
        raise ParamError("邮件模板至少需要一种语言")

    @staticmethod
    def _find_texts(
        texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]], locale: str
    ) -> ConcurrentStableDict[str, str] | None:
        """大小写不敏感取某语言文案。"""
        key = locale.strip().lower()
        for item_locale, bucket in texts.items():
            if item_locale.lower() == key:
                return bucket
        return None

    @staticmethod
    def _locale_chain(locale: str) -> ConcurrentStableList[str]:
        """语言回退链（请求语言 → 系统默认语言）。"""
        return ConcurrentStableList((locale, get_default_locale()))

    def _builtin_item(self, default: MailTemplateDefault, *, locale: str) -> MailTemplateListItem:
        """内置默认 → 列表行。"""
        subject, _content = self._builtin_texts(default, locale=locale)
        return MailTemplateListItem(
            id=None,
            code=default.code,
            name=default.name,
            status=MAIL_TEMPLATE_STATUS_ENABLED,
            remark=default.remark,
            source=MAIL_TEMPLATE_SOURCE_BUILTIN,
            subject=subject,
            updated_at=None,
        )

    def _builtin_texts(self, default: MailTemplateDefault, *, locale: str) -> tuple[str, str]:
        """内置模板按语言回退取主题 / 正文。"""
        for candidate in self._locale_chain(locale):
            key = candidate.strip().lower()
            for item_locale, texts in default.i18n.items():
                if item_locale.lower() == key:
                    return texts["subject"], texts["content"]
        for texts in default.i18n.values():
            return texts["subject"], texts["content"]
        raise MailTemplateNotFoundError(f"内置邮件模板无可用文案：{default.code}")

    @staticmethod
    def _pick_texts(
        by_locale: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] | None,
        *,
        locale: str,
        fallback: tuple[str, str],
    ) -> tuple[str, str]:
        """按语言链取主题 / 正文，缺省回落主表快照。"""
        if by_locale:
            for candidate in (locale, get_default_locale()):
                key = candidate.strip().lower()
                for item_locale, values in by_locale.items():
                    if item_locale.lower() == key:
                        return values.get("subject", ""), values.get("content", "")
        return fallback

    async def _load_subject_map(self, ids: ConcurrentStableList[int], *, locale: str) -> ConcurrentStableDict[int, str]:
        """批量装载租户模板主题（列表展示用）。"""
        if not ids:
            return ConcurrentStableDict()
        texts = await load_i18n_texts(
            self._session,
            SysMailTemplateI18n,
            "template_id",
            ids,
            locales=self._locale_chain(locale),
            text_columns=ConcurrentStableList(("subject",)),
        )
        return ConcurrentStableDict({key: value["subject"] for key, value in texts.items()})

"""短信模板业务：租户模板 CRUD、内置事务性模板合并、场景校验与沙箱渲染。

短信不建 i18n 附表：模板正文单语言；真实发送以厂商模板 ID + 参数为准。
事务由调用方负责，本层只 `flush`。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import SmsSettings
from bms_core.core.exceptions import (
    ChannelConfigInvalidError,
    ConflictError,
    ParamError,
    SmsTemplateUnavailableError,
)
from bms_core.core.roots import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.schemas.pagination import BasePageResponse
from bms_notification.domains.notification.models.sms import SysSmsTemplate
from bms_notification.domains.notification.rendering import render_template, validate_template
from bms_notification.domains.notification.repositories.sms import SmsRepository
from bms_notification.domains.notification.schemas.sms import (
    SmsLogItem,
    SmsTemplateCreateRequest,
    SmsTemplateDetail,
    SmsTemplateListItem,
    SmsTemplateUpdateRequest,
)
from bms_notification.domains.notification.sms_constants import (
    SMS_CHANNEL_ALIYUN,
    SMS_CHANNEL_TENCENT,
    SMS_SCENE_OPTION_SET,
    SMS_SCENES,
    SMS_TEMPLATE_CONTENT_MAX_BYTES,
    SMS_TEMPLATE_STATUS_DISABLED,
    SMS_TEMPLATE_STATUS_ENABLED,
)
from bms_notification.domains.notification.sms_defaults import (
    BUILTIN_SMS_TEMPLATES,
    SmsTemplateDefault,
    find_builtin_sms_template,
)

__all__ = ["SmsResolvedTemplate", "SmsTemplateService"]


@dataclass(frozen=True)
class SmsResolvedTemplate(BaseValueObject):
    """短信发送解析结果（本地文案 + 厂商模板要素）。"""

    content: str
    """本地渲染正文（日志脱敏前）。"""

    provider_template_id: str
    """厂商模板 ID。"""

    provider_param_keys: ConcurrentStableList[str]
    """厂商参数名顺序。"""

    scene: str
    """场景。"""


class SmsTemplateService(BaseFrameworkObject):
    """短信模板业务服务（当前租户库会话）。"""

    def __init__(
        self,
        session: DbSession,
        *,
        option_sets: BaseOptionSetRegistry | None,
        sms_settings: SmsSettings,
        render_timeout_seconds: float,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            option_sets: 选项集注册表（场景值域校验）。
            sms_settings: 短信渠道配置。
            render_timeout_seconds: 沙箱渲染超时（秒）。
        """
        self._session = session
        self._option_sets = option_sets
        self._settings = sms_settings
        self._render_timeout = render_timeout_seconds
        self._repository = SmsRepository(session)

    @property
    def active_channel(self) -> str:
        """当前生效渠道（配置值；仅允许 aliyun / tencent）。"""
        channel = self._settings.channel.strip() or SMS_CHANNEL_ALIYUN
        if channel not in (SMS_CHANNEL_ALIYUN, SMS_CHANNEL_TENCENT):
            raise ChannelConfigInvalidError(f"短信渠道配置非法：{channel}")
        return channel

    async def list(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
        channel: str | None = None,
        scene: str | None = None,
        source: str | None = None,
    ) -> BasePageResponse[SmsTemplateListItem]:
        """合并列出租户模板与内置事务性模板（仅当前渠道展示内置）。"""
        rows = await self._repository.list_templates(keyword=keyword, status=status, channel=channel, scene=scene)
        items: ConcurrentStableList[SmsTemplateListItem] = ConcurrentStableList()
        tenant_keys: ConcurrentStableList[str] = ConcurrentStableList()
        active = self.active_channel
        for row in rows:
            tenant_keys.append(f"{row.code}:{row.channel}")
            if source == "builtin":
                continue
            items.append(
                SmsTemplateListItem(
                    id=int(row.id),
                    code=row.code,
                    name=row.name,
                    channel=row.channel,
                    scene=row.scene,
                    status=row.status,
                    remark=row.remark,
                    source="tenant",
                    updated_at=row.updated_at,
                )
            )
        if (
            source != "tenant"
            and (channel in (None, "", active))
            and (status in (None, "", SMS_TEMPLATE_STATUS_ENABLED))
        ):
            for default in BUILTIN_SMS_TEMPLATES.values():
                if f"{default.code}:{active}" in tenant_keys:
                    continue
                if scene and scene != default.scene:
                    continue
                if (
                    keyword
                    and keyword.lower() not in default.code.lower()
                    and keyword.lower() not in default.name.lower()
                ):
                    continue
                items.append(self._builtin_item(default, channel=active))
        ordered = sorted(items, key=lambda item: (item.code, item.channel))
        total = len(ordered)
        start = (page - 1) * size
        return BasePageResponse[SmsTemplateListItem](
            list=ConcurrentStableList(ordered[start : start + size]), total=total, page=page, size=size
        )

    async def detail(self, template_id: int) -> SmsTemplateDetail:
        """租户模板详情。"""
        row = await self._repository.get_template(template_id)
        if row is None:
            raise SmsTemplateUnavailableError("短信模板不存在或已删除")
        return SmsTemplateDetail(
            id=int(row.id),
            code=row.code,
            name=row.name,
            channel=row.channel,
            scene=row.scene,
            status=row.status,
            remark=row.remark,
            source="tenant",
            updated_at=row.updated_at,
            content=row.content,
            provider_template_id=row.provider_template_id,
            provider_param_keys=self._parse_param_keys(row.provider_param_keys),
        )

    async def create(self, req: SmsTemplateCreateRequest) -> SmsTemplateDetail:
        """新建租户短信模板。"""
        self._validate_scene(req.scene)
        if await self._repository.get_template_by_code(req.code, req.channel) is not None:
            raise ConflictError(f"短信模板已存在：{req.code}（{req.channel}）")
        self._validate_content(req.content)
        row = _new_template(req)
        self._session.add(row)
        await self._session.flush()
        return await self.detail(int(row.id))

    async def update(self, template_id: int, req: SmsTemplateUpdateRequest) -> SmsTemplateDetail:
        """编辑租户短信模板（code / channel 不可改）。"""
        row = await self._repository.get_template(template_id)
        if row is None:
            raise SmsTemplateUnavailableError("短信模板不存在或已删除")
        if req.name is not None:
            row.name = req.name
        if req.content is not None:
            self._validate_content(req.content)
            row.content = req.content
        if req.scene is not None:
            self._validate_scene(req.scene)
            row.scene = req.scene
        if req.provider_template_id is not None:
            row.provider_template_id = req.provider_template_id or None
        if req.provider_param_keys is not None:
            row.provider_param_keys = (
                json.dumps(list(req.provider_param_keys), ensure_ascii=False) if req.provider_param_keys else None
            )
        if req.status is not None:
            row.status = req.status
        if req.remark is not None:
            row.remark = req.remark
        await self._session.flush()
        return await self.detail(int(row.id))

    async def delete(self, template_id: int) -> bool:
        """软删除租户短信模板（内置事务性模板不在库内，无法删除）。"""
        row = await self._repository.get_template(template_id)
        if row is None:
            raise SmsTemplateUnavailableError("短信模板不存在或已删除")
        row.soft_delete()
        await self._session.flush()
        return True

    async def list_logs(
        self,
        *,
        page: int,
        size: int,
        status: str | None = None,
        channel: str | None = None,
        scene: str | None = None,
        template_code: str | None = None,
        recipient: str | None = None,
        user_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> BasePageResponse[SmsLogItem]:
        """短信发送记录分页。"""
        rows, total = await self._repository.page_logs(
            page=page,
            size=size,
            status=status,
            channel=channel,
            scene=scene,
            template_code=template_code,
            recipient=recipient,
            user_id=user_id,
            start_at=start_at,
            end_at=end_at,
        )
        items = [
            SmsLogItem(
                id=int(row.id),
                recipient=row.recipient,
                channel=row.channel,
                template_code=row.template_code,
                scene=row.scene,
                content=row.content,
                status=row.status,
                error_msg=row.error_msg,
                attempts=row.attempts,
                user_id=row.user_id,
                sent_at=row.sent_at,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return BasePageResponse[SmsLogItem](list=ConcurrentStableList(items), total=total, page=page, size=size)

    async def test(self, template_id: int, *, params: ConcurrentStableDict[str, str]) -> tuple[str, str]:
        """按 id 沙箱渲染（不发送）。"""
        row = await self._repository.get_template(template_id)
        if row is None:
            raise SmsTemplateUnavailableError("短信模板不存在或已删除")
        render_params: ConcurrentStableDict[str, object] = cast("ConcurrentStableDict[str, object]", params)
        content = await render_template(
            row.content,
            render_params,
            max_bytes=SMS_TEMPLATE_CONTENT_MAX_BYTES,
            timeout_seconds=self._render_timeout,
        )
        return row.code, content

    async def resolve_for_send(self, code: str, *, params: ConcurrentStableDict[str, str]) -> SmsResolvedTemplate:
        """发送前解析模板（租户优先、内置回落；停用 / 缺厂商模板即失败）。"""
        channel = self.active_channel
        render_params: ConcurrentStableDict[str, object] = cast("ConcurrentStableDict[str, object]", params)
        row = await self._repository.get_template_by_code(code, channel)
        if row is not None:
            if row.status != SMS_TEMPLATE_STATUS_ENABLED:
                raise SmsTemplateUnavailableError(f"短信模板已停用：{code}（{channel}）")
            if not row.provider_template_id:
                raise ChannelConfigInvalidError(f"短信模板缺少厂商模板 ID：{code}（{channel}）")
            content = await render_template(
                row.content,
                render_params,
                max_bytes=SMS_TEMPLATE_CONTENT_MAX_BYTES,
                timeout_seconds=self._render_timeout,
            )
            return SmsResolvedTemplate(
                content=content,
                provider_template_id=row.provider_template_id,
                provider_param_keys=self._parse_param_keys(row.provider_param_keys) or self._param_order(params),
                scene=row.scene,
            )
        default = find_builtin_sms_template(code)
        if default is None:
            raise SmsTemplateUnavailableError(f"短信模板不存在：{code}（{channel}）")
        provider_template_id = self._builtin_provider_template_id(default)
        if not provider_template_id:
            raise ChannelConfigInvalidError(f"短信渠道未配置内置模板 ID：{code}（{channel}）")
        content = await render_template(
            default.content,
            render_params,
            max_bytes=SMS_TEMPLATE_CONTENT_MAX_BYTES,
            timeout_seconds=self._render_timeout,
        )
        return SmsResolvedTemplate(
            content=content,
            provider_template_id=provider_template_id,
            provider_param_keys=ConcurrentStableList(default.provider_param_keys),
            scene=default.scene,
        )

    def _validate_scene(self, scene: str) -> None:
        """场景必须在选项集内。"""
        if scene not in SMS_SCENES:
            raise ParamError(f"短信场景非法：{scene}")
        if self._option_sets is None:
            return
        violations = self._option_sets.validate(scene, option_set_key=SMS_SCENE_OPTION_SET)
        if violations:
            raise ParamError(f"短信场景非法：{scene}")

    def _validate_content(self, content: str) -> None:
        """正文非空、字节受限、语法与冒烟渲染通过。"""
        text = content.strip()
        if not text:
            raise ParamError("短信正文不得为空")
        if len(text.encode("utf-8")) > SMS_TEMPLATE_CONTENT_MAX_BYTES:
            raise ParamError(f"短信正文超过 {SMS_TEMPLATE_CONTENT_MAX_BYTES} 字节")
        validate_template(text, max_bytes=SMS_TEMPLATE_CONTENT_MAX_BYTES)

    def _builtin_provider_template_id(self, default: SmsTemplateDefault) -> str:
        """取内置模板在当前渠道下的厂商模板 ID。"""
        channel = self.active_channel
        provider = self._settings.aliyun if channel == SMS_CHANNEL_ALIYUN else self._settings.tencent
        value: object = getattr(provider, default.provider_config_key, "")
        return value if isinstance(value, str) else ""

    def _builtin_item(self, default: SmsTemplateDefault, *, channel: str) -> SmsTemplateListItem:
        """内置事务性模板 → 列表行。"""
        provider = self._settings.aliyun if channel == SMS_CHANNEL_ALIYUN else self._settings.tencent
        value: object = getattr(provider, default.provider_config_key, "")
        configured = isinstance(value, str) and bool(value)
        return SmsTemplateListItem(
            id=None,
            code=default.code,
            name=default.name,
            channel=channel,
            scene=default.scene,
            status=SMS_TEMPLATE_STATUS_ENABLED if configured else SMS_TEMPLATE_STATUS_DISABLED,
            remark="内置默认（厂商模板 ID 未配置）" if not configured else "内置默认（代码提供，租户可覆盖）",
            source="builtin",
            updated_at=None,
        )

    @staticmethod
    def _parse_param_keys(raw: str | None) -> ConcurrentStableList[str]:
        """解析厂商参数名 JSON 数组（脏值按空处理）。"""
        if not raw:
            return ConcurrentStableList()
        try:
            value = json.loads(raw)
        except ValueError, TypeError:
            return ConcurrentStableList()
        if not isinstance(value, list):
            return ConcurrentStableList()
        items = cast("list[object]", value)
        return ConcurrentStableList(str(item) for item in items if str(item).strip())

    @staticmethod
    def _param_order(params: ConcurrentStableDict[str, str]) -> ConcurrentStableList[str]:
        """缺省参数顺序（按传入顺序；腾讯模板需与占位顺序一致）。"""
        return ConcurrentStableList(params.keys())


def _new_template(req: SmsTemplateCreateRequest) -> SysSmsTemplate:
    """构造短信模板行（避免在服务层重复字段赋值）。"""
    return SysSmsTemplate(
        code=req.code,
        name=req.name,
        content=req.content.strip(),
        channel=req.channel,
        scene=req.scene,
        provider_template_id=req.provider_template_id or None,
        provider_param_keys=(
            json.dumps(list(req.provider_param_keys), ensure_ascii=False) if req.provider_param_keys else None
        ),
        status=req.status,
        remark=req.remark,
    )

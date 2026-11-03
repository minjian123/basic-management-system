"""个人中心偏好服务：语言 / 时区偏好的校验、生效值派生与持久化（需求 06-2）。

口径：

- **存储**：`sys_user.locale` / `sys_user.timezone`（需求明确落用户表列，不落 `sys_user_preference`）；
  语言归一为语言清单内的**标准形态**（`zh-CN`，大小写不敏感匹配），时区原样存 IANA 标识。
- **校验**：语言须已登记且启用（`44010`），时区须在 IANA 清单内（`44009`）；非法即拒、不落库。
- **派生**：`effectiveLocale` = 存值在启用清单中 → 存值，否则系统默认语言；
  `effectiveTimezone` = 存值 → 按 `effectiveLocale` 查「语言 → 时区」映射 → 兜底时区。
- **不审计、不发事件**：偏好属展示与交互状态，不承载业务事实（架构 07「用户偏好」节）。
"""

from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import I18nSettings
from bms_core.core.exceptions import ParamError, TimezoneInvalidError, UserLocaleInvalidError, UserNotFoundError
from bms_core.core.roots import BaseFrameworkObject, BaseValueObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.i18n.timezone import is_valid_timezone, resolve_timezone

from ..repositories.user import UserRepository

__all__ = ["ProfilePreference", "ProfilePreferenceService"]


@dataclass(frozen=True)
class ProfilePreference(BaseValueObject):
    """用户偏好快照（存值 + 生效值）。

    Attributes:
        locale: 语言偏好存值（可空）。
        timezone: 时区偏好存值（可空）。
        effective_locale: 生效语言。
        effective_timezone: 生效时区。
    """

    locale: str | None
    timezone: str | None
    effective_locale: str
    effective_timezone: str


class ProfilePreferenceService(BaseFrameworkObject):
    """个人中心偏好服务（读写本人语言 / 时区偏好）。"""

    def __init__(
        self,
        repository: UserRepository,
        uow: UnitOfWork,
        *,
        registry: BaseLocaleRegistry,
        i18n: I18nSettings,
    ) -> None:
        """初始化。

        Args:
            repository: 用户仓储（租户库 `sys_user`）。
            uow: 工作单元（写事务边界）。
            registry: 语言清单能力域（启用清单与默认语言）。
            i18n: 国际化配置（语言 → 时区映射与兜底时区）。
        """
        self._repository = repository
        self._uow = uow
        self._registry = registry
        self._i18n = i18n

    async def load(self, user_id: int) -> ProfilePreference:
        """读取本人偏好（含生效值派生）。

        Args:
            user_id: 当前登录用户主键。

        Returns:
            ProfilePreference: 偏好快照。

        Raises:
            UserNotFoundError: 用户不存在（会话与库不一致）。
        """
        row = await self._repository.get(user_id)
        if row is None:
            raise UserNotFoundError(f"用户不存在：{user_id}")
        return await self._compose(row.locale, row.timezone)

    async def save(
        self,
        user_id: int,
        *,
        locale: str | None,
        timezone: str | None,
        locale_provided: bool,
        timezone_provided: bool,
    ) -> ProfilePreference:
        """设置本人偏好（部分更新；未提供的字段不修改）。

        Args:
            user_id: 当前登录用户主键。
            locale: 语言偏好（`locale_provided=True` 时生效）。
            timezone: 时区偏好（`timezone_provided=True` 时生效）。
            locale_provided: 请求中是否出现语言字段。
            timezone_provided: 请求中是否出现时区字段。

        Returns:
            ProfilePreference: 更新后的偏好快照。

        Raises:
            ParamError: 两个字段都未提供（无变更）。
            UserLocaleInvalidError: 语言未登记或未启用（44010）。
            TimezoneInvalidError: 时区非法（44009）。
            UserNotFoundError: 用户不存在。
        """
        if not locale_provided and not timezone_provided:
            raise ParamError("未提供任何偏好字段（locale / timezone 至少一项）")
        changes: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if locale_provided:
            changes["locale"] = await self._normalize_locale(locale)
        if timezone_provided:
            changes["timezone"] = self._normalize_timezone(timezone)
        async with self._uow.begin():
            row = await self._repository.update(user_id, **changes)
            if row is None:
                raise UserNotFoundError(f"用户不存在：{user_id}")
            stored_locale, stored_timezone = row.locale, row.timezone
        return await self._compose(stored_locale, stored_timezone)

    async def _compose(self, locale: str | None, timezone: str | None) -> ProfilePreference:
        """组装偏好快照（派生生效值）。

        Args:
            locale: 语言偏好存值。
            timezone: 时区偏好存值。

        Returns:
            ProfilePreference: 偏好快照。
        """
        enabled = await self._registry.list_locales(enabled_only=True)
        default_locale = self._registry.default_locale()
        effective_locale = default_locale
        for item in enabled:
            if locale and item.code.lower() == locale.strip().lower():
                effective_locale = item.code
                break
        effective_timezone = timezone or resolve_timezone(
            effective_locale,
            self._i18n.timezone_by_locale,
            self._i18n.default_timezone,
        )
        return ProfilePreference(
            locale=locale,
            timezone=timezone,
            effective_locale=effective_locale,
            effective_timezone=effective_timezone,
        )

    async def _normalize_locale(self, locale: str | None) -> str | None:
        """归一语言偏好（空值放行＝清空；否则必须是已登记且启用的语言）。

        Args:
            locale: 请求中的语言偏好。

        Returns:
            str | None: 清单内标准形态的语言标识；None 表示清空。

        Raises:
            UserLocaleInvalidError: 语言未登记或未启用（44010）。
        """
        target = (locale or "").strip()
        if not target:
            return None
        for item in await self._registry.list_locales(enabled_only=True):
            if item.code.lower() == target.lower():
                return item.code
        raise UserLocaleInvalidError(f"语言未登记或未启用：{target}")

    def _normalize_timezone(self, timezone: str | None) -> str | None:
        """归一校验时区偏好（空值放行＝清空；否则必须在 IANA 清单内）。

        Args:
            timezone: 请求中的时区偏好。

        Returns:
            str | None: IANA 时区标识；None 表示清空。

        Raises:
            TimezoneInvalidError: 时区非法（44009）。
        """
        target = (timezone or "").strip()
        if not target:
            return None
        if not is_valid_timezone(target):
            raise TimezoneInvalidError(f"时区非法（须为 IANA 标识）：{target}")
        return target

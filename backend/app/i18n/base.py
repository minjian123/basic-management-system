"""国际化翻译能力域：统一翻译契约（真实语言包 / Redis 缓存 / Babel 随国际化阶段回补）。

- `DEFAULT_LOCALE` / `SUPPORTED_LOCALES`：默认语言与种子语言清单（zh-CN / en-US）。
- `BaseTranslator`：能力域中间层契约（`key = "translator"`）——`translate`（取词）/ `resolve_locale`（语言解析）/
  `load_messages`（语言包加载）。
  `load_messages` 返回空映射。
- `get_translator`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：固定文案存 `sys_i18n_message`（`msg_key` + `locale`）、运行时经 Redis 缓存下发；i18n key 命名
`模块.页面.字段`（如 `user.form.username`）；业务数据文案走 `{主表}_i18n` 附表（归上层）。后端 Babel 仅开发期提取 key。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast

from fastapi import Request

from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "BaseTranslator",
    "get_translator",
]

DEFAULT_LOCALE = "zh-CN"
"""默认语言（缺省与回退）。"""

SUPPORTED_LOCALES: tuple[str, ...] = ("zh-CN", "en-US")
"""种子语言清单（架构「语言与 RTL」节；语言清单可由 `sys_i18n_locale` 动态扩展）。"""


class BaseTranslator(BasePluggable, ABC):
    """翻译契约：取词 / 语言解析 / 语言包加载。"""

    key: str = "translator"
    plugin_key: str = "translator"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def translate(
        self, key: str, *, locale: str | None = None, params: Mapping[str, object] | None = None
    ) -> str:
        """取词（真实实现按 locale 查语言包、缺省回退默认文案）。

        Args:
            key: 文案 key（`模块.页面.字段`）。
            locale: 语言；None 用当前语言。
            params: 插值参数（可选）。

        Returns:
            str: 翻译文案。
        """

    @abstractmethod
    async def load_messages(self, locale: str) -> Mapping[str, str]:
        """加载语言包（真实实现读 `sys_i18n_message` / Redis 缓存）。

        Args:
            locale: 语言。

        Returns:
            Mapping[str, str]: key → 文案映射。
        """

    @abstractmethod
    def resolve_locale(self, accept_language: str | None = None) -> str:
        """解析语言（Accept-Language 驱动；无匹配回退 `DEFAULT_LOCALE`）。

        Args:
            accept_language: 请求 `Accept-Language` 头；None 用默认。

        Returns:
            str: 语言。
        """


def get_translator(request: Request) -> BaseTranslator:
    """取应用级翻译器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTranslator: 应用装配的翻译器实例。
    """
    return cast("BaseTranslator", request.app.state.translator)

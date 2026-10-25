"""多语言文案的请求口径助手（平台侧横切，菜单表单与权限元数据共用）。

平台内所有「主表默认文案 + `*_i18n` 附表」的资源（菜单 / 表单 / 字段 / 业务码 / 动作码）共用同一套
入参与出参口径：

- 请求语言取 `current_dict_locale`（请求作用域依赖设置），不支持时回退系统默认语言；
- 入参只收多语言映射：剔除空白值，必填语言（＝请求语言）不得缺文案，主表默认文案由服务端派生；
- 出参给完整映射，必填语言缺失时以主表默认文案回填（不改写存储）。

本模块不含表结构与业务规则，故不归属任何业务域（`shared_paths`）。
"""

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import MenuI18nRequiredError
from bms_core.dict.base import current_dict_locale
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES

__all__ = ["clean_i18n", "derive_default_name", "i18n_out", "request_locale", "require_i18n_name"]


def request_locale() -> str:
    """当前请求语言（＝必填语言口径；不支持时回退系统默认语言）。

    Returns:
        str: 生效请求语言。
    """
    locale = current_dict_locale.get() or DEFAULT_LOCALE
    return locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE


def clean_i18n(names: ConcurrentStableDict[str, str]) -> ConcurrentStableDict[str, str]:
    """归一多语言文案映射（剔空白值；不改动语言集合，停用语言存量值原样保留）。

    Args:
        names: 语言标识 → 文案。

    Returns:
        ConcurrentStableDict[str, str]: 归一后的映射。
    """
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for locale, text in names.items():
        value = (text or "").strip()
        if value:
            result.set(locale, value)
    return result


def require_i18n_name(names: ConcurrentStableDict[str, str], *, locale: str) -> None:
    """必填语言校验（缺文案即拒绝）。

    Args:
        names: 归一后的多语言文案映射。
        locale: 必填语言（请求语言）。

    Raises:
        MenuI18nRequiredError: 必填语言缺文案（40208）。
    """
    if not (names.get(locale) or ""):
        raise MenuI18nRequiredError(f"缺少必填语言（{locale}）的文案")


def derive_default_name(names: ConcurrentStableDict[str, str], *, required_locale: str) -> str:
    """派生主表默认文案（系统默认语言 → 必填语言 → 首个有值语言）。

    主表默认文案列是**派生快照**（供列表零关联展示与排序），不由调用方单独提交。

    Args:
        names: 归一后的多语言文案映射。
        required_locale: 必填语言（请求语言）。

    Returns:
        str: 主表默认文案。

    Raises:
        MenuI18nRequiredError: 全部语言皆无文案（40208）。
    """
    for candidate in (DEFAULT_LOCALE, required_locale):
        value = names.get(candidate) or ""
        if value:
            return value
    for text in names.values():
        if text:
            return text
    raise MenuI18nRequiredError("多语言文案为空：至少一种语言须有文案")


def i18n_out(names: ConcurrentStableDict[str, str] | None, *, name: str, locale: str) -> ConcurrentStableDict[str, str]:
    """出参多语言映射：完整语言映射 + 必填语言缺失时以主表默认文案回填（不改写存储）。

    Args:
        names: 该主表行的多语言文案映射（可空）。
        name: 主表默认文案。
        locale: 必填语言（请求语言）。

    Returns:
        ConcurrentStableDict[str, str]: 补全后的映射。
    """
    result: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if names is not None:
        for key, value in names.items():
            result.set(key, value)
    if not (result.get(locale) or ""):
        result.set(locale, name)
    return result

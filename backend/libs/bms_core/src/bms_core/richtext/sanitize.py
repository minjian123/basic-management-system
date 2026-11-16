"""富文本 HTML 白名单清洗（`nh3` / ammonia）。

口径（《组件设计 · 富文本字段》§4、《概要设计 · 公告管理》§7）：

- 标签 / 属性 / URL 协议 / `style` 属性级白名单在本模块**唯一维护**，公告与后续帮助中心共用；
- 后端清洗是**权威口径**：接口直写也必须净化后入库；前端提交前 / 渲染前仍是二次净化；
- 只做白名单收窄，不做「清洗失败」判定——清洗结果与原文不同属正常；服务层按「去标签后为空 /
  长度超限」判定内容校验失败（`70205`）。

安全边界：

- 禁止 `script` / `style` / `iframe` / `object` / `embed` / `form` / `input` / `video` / `audio` /
  `svg` 与全部 `on*` 事件属性；
- URL 仅允许 `http` / `https` / `mailto` 与相对路径；`data:` / `javascript:` / `vbscript:` 一律剥离；
- `style` 仅保留 `text-align` / `text-indent` / `width` / `height` / `max-width`，`expression()` /
  `url()` 由 nh3 的样式属性过滤剥离。
"""

from __future__ import annotations

import re

import nh3

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenSet,
)

__all__ = [
    "ALLOWED_ATTRIBUTES",
    "ALLOWED_TAGS",
    "ALLOWED_URL_SCHEMES",
    "MAX_NOTICE_CONTENT_BYTES",
    "MAX_NOTICE_TITLE_LENGTH",
    "STYLE_PROPERTIES",
    "html_text_length",
    "sanitize_html",
]

MAX_NOTICE_TITLE_LENGTH = 256
"""公告标题最大字符数（对齐列宽 `VARCHAR(256)`）。"""

MAX_NOTICE_CONTENT_BYTES = 60000
"""公告正文清洗后 UTF-8 字节上限（MySQL `TEXT` 65535 字节，留安全余量）。"""

ALLOWED_TAGS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "ul",
        "ol",
        "li",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "a",
        "img",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "code",
        "pre",
        "span",
        "div",
        "hr",
    )
)
"""允许的 HTML 标签（与前端富文本白名单同源）。"""

ALLOWED_ATTRIBUTES: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenSet[str]] = ConcurrentStableFrozenDict(
    {
        "a": ConcurrentStableFrozenSet(("href", "title", "target")),
        "img": ConcurrentStableFrozenSet(("src", "alt", "title", "width", "height", "style")),
        "th": ConcurrentStableFrozenSet(("colspan", "rowspan", "style")),
        "td": ConcurrentStableFrozenSet(("colspan", "rowspan", "style")),
        "code": ConcurrentStableFrozenSet(("class",)),
        "span": ConcurrentStableFrozenSet(("style",)),
        "p": ConcurrentStableFrozenSet(("style",)),
        "div": ConcurrentStableFrozenSet(("style",)),
        "table": ConcurrentStableFrozenSet(("style",)),
    }
)
"""按标签允许的属性集合（nh3 的 `attributes` 参数形态）。"""

ALLOWED_URL_SCHEMES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(("http", "https", "mailto"))
"""允许的 URL 协议（相对路径由 `url_relative=pass_through` 放行）。"""

STYLE_PROPERTIES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    ("text-align", "text-indent", "width", "height", "max-width")
)
"""允许的内联样式属性（属性级白名单）。"""

_TAG_RE = re.compile(r"<[^>]*>")
"""去标签用的保守正则（仅用于长度 / 空内容判定，不参与净化）。"""


def sanitize_html(raw: str) -> str:
    """按白名单清洗 HTML（公告正文 / 帮助文章正文共用）。

    Args:
        raw: 原始 HTML（可空）。

    Returns:
        str: 净化后的 HTML；空输入返回空串。
    """
    if not raw or not raw.strip():
        return ""
    attributes = _nh3_attributes()
    return nh3.clean(
        raw,
        tags=set(ALLOWED_TAGS),
        attributes=attributes,
        strip_comments=True,
        link_rel="noopener noreferrer",
        url_schemes=set(ALLOWED_URL_SCHEMES),
        url_relative="pass_through",
        filter_style_properties=set(STYLE_PROPERTIES),
    )


def html_text_length(html: str) -> int:
    """估算 HTML 去标签后的可见文本长度（用于空内容判定与前端字数提示对齐）。

    说明：只做保守去标签 + 实体保留，不解析 DOM；目的是判断「是否有可读文本」，不用于精确计数。

    Args:
        html: HTML 文本。

    Returns:
        int: 去标签、去首尾空白后的字符数。
    """
    if not html:
        return 0
    text = _TAG_RE.sub("", html)
    return len(text.replace("&nbsp;", " ").strip())


# bare-collections:allow — nh3 的 attributes 参数只接受内置 dict/set
def _nh3_attributes() -> dict[str, set[str]]:
    """把插入序属性表转换为 nh3 需要的 `dict[str, set[str]]`。

    Returns:
        dict[str, set[str]]: 标签 → 允许属性集合。
    """
    return {tag: set(attrs) for tag, attrs in ALLOWED_ATTRIBUTES.items()}

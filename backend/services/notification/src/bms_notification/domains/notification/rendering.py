"""Jinja2 模板沙箱：语法校验、危险结构拦截、严格渲染、输出上限与超时。

- 邮件与短信模板共用同一渲染器，规则只在这里维护一次；
- 保存期用宽松未定义做冒烟渲染（允许空参数），发送期用严格未定义（缺参即失败）；
- 无 loader、清空 globals、过滤器白名单、禁用 `include/extends/import/from/macro/call/filter`；
- 流式渲染累加输出，超过上限立即失败；线程执行 + `asyncio.wait_for` 超时。
"""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

from jinja2 import StrictUndefined, Undefined, nodes
from jinja2.exceptions import SecurityError, TemplateError, TemplateSyntaxError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import TemplateRenderError, TemplateSyntaxInvalidError

__all__ = ["ALLOWED_FILTERS", "MAX_PARAMS", "RenderedTemplate", "render_template", "validate_template"]

MAX_PARAMS = 50
"""单次渲染参数上限。"""

ALLOWED_FILTERS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (
        "upper",
        "lower",
        "title",
        "capitalize",
        "trim",
        "replace",
        "length",
        "default",
        "join",
        "round",
        "int",
        "float",
        "string",
        "safe",
        "e",
        "escape",
        "urlencode",
        "first",
        "last",
        "slice",
        "list",
        "tojson",
    )
)
"""模板可用过滤器白名单。"""

_FORBIDDEN_NODES: ConcurrentStableFrozenList[type[nodes.Node]] = ConcurrentStableFrozenList(
    (
        nodes.Include,
        nodes.Extends,
        nodes.Import,
        nodes.FromImport,
        nodes.Macro,
        nodes.CallBlock,
        nodes.FilterBlock,
    )
)
"""禁止的模板结构（文件 / 宏 / 代码块类）。"""

_PARAM_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
"""参数键规则。"""

_MAX_SET_STATEMENTS = 20
"""单模板 `set` 语句上限。"""

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mail-render")
"""渲染线程池（避免阻塞事件循环；超时后线程结果丢弃）。"""


def _environment(*, strict: bool) -> SandboxedEnvironment:
    """构造受限沙箱环境。

    Args:
        strict: 是否严格未定义（True = 缺参失败）。

    Returns:
        SandboxedEnvironment: 受限环境。
    """
    env = SandboxedEnvironment(undefined=StrictUndefined if strict else Undefined, autoescape=True, loader=None)
    env.globals.clear()
    env.filters = {name: func for name, func in env.filters.items() if name in ALLOWED_FILTERS}
    env.tests = {}
    return env


def _check_structure(source: str) -> None:
    """语法解析并拦截危险结构。

    Args:
        source: 模板源码。

    Raises:
        TemplateSyntaxInvalidError: 语法错误或含禁止结构。
    """
    try:
        ast = _environment(strict=True).parse(source)
    except TemplateSyntaxError as exc:
        raise TemplateSyntaxInvalidError(f"模板语法错误：{exc.message}（第 {exc.lineno} 行）") from exc
    set_count = 0
    for node in ast.find_all(nodes.Node):
        if isinstance(node, tuple(_FORBIDDEN_NODES)):
            raise TemplateSyntaxInvalidError(f"模板不允许使用 {type(node).__name__.lower()} 结构")
        if isinstance(node, nodes.Assign):
            set_count += 1
            if set_count > _MAX_SET_STATEMENTS:
                raise TemplateSyntaxInvalidError("模板 set 语句过多")
        if isinstance(node, nodes.Getattr) and str(node.attr).startswith("_"):
            raise TemplateSyntaxInvalidError("模板不允许访问下划线属性")
        if isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const):
            value = node.arg.value
            if isinstance(value, str) and value.startswith("_"):
                raise TemplateSyntaxInvalidError("模板不允许访问下划线键")


def _normalize_params(params: ConcurrentStableDict[str, object] | None) -> ConcurrentStableDict[str, object]:
    """校验并归一渲染参数（扁平、键合法、值只允许标量）。

    Args:
        params: 原始参数。

    Returns:
        dict[str, object]: 归一参数。

    Raises:
        TemplateRenderError: 参数非法。
    """
    if not params:
        return ConcurrentStableDict()
    if len(params) > MAX_PARAMS:
        raise TemplateRenderError(f"模板参数超过 {MAX_PARAMS} 个")
    result: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in params.items():
        if not _PARAM_KEY_PATTERN.match(key):
            raise TemplateRenderError(f"模板参数名非法：{key!r}")
        if not isinstance(value, str | int | float | bool):
            raise TemplateRenderError(f"模板参数值只允许标量：{key}")
        result[key] = value
    return result


def _render_sync(
    source: str,
    params: ConcurrentStableDict[str, object],
    *,
    max_bytes: int,
    strict: bool,
) -> RenderedTemplate:
    """同步渲染（在线程中执行）。

    Args:
        source: 模板源码。
        params: 渲染参数。
        max_bytes: 输出 UTF-8 字节上限。
        strict: 是否严格未定义。

    Returns:
        RenderedTemplate: 渲染结果。

    Raises:
        TemplateRenderError: 渲染失败 / 超限。
    """
    env = _environment(strict=strict)
    try:
        template = env.from_string(source)
        chunks: ConcurrentStableList[str] = ConcurrentStableList()
        total = 0
        for chunk in template.generate(**params):
            text = str(chunk)
            total += len(text.encode("utf-8"))
            if total > max_bytes:
                raise TemplateRenderError(f"模板渲染输出超过 {max_bytes} 字节")
            chunks.append(text)
    except TemplateRenderError:
        raise
    except UndefinedError as exc:
        raise TemplateRenderError(f"模板参数缺失：{exc}") from exc
    except SecurityError as exc:
        raise TemplateRenderError(f"模板访问被沙箱拒绝：{exc}") from exc
    except TemplateError as exc:
        raise TemplateRenderError(f"模板渲染失败：{exc}") from exc
    return RenderedTemplate(content="".join(chunks), truncated=False)


class RenderedTemplate:
    """渲染结果（内容 + 是否被截断占位）。"""

    __slots__ = ("content", "truncated")

    def __init__(self, content: str, truncated: bool = False) -> None:
        """初始化。

        Args:
            content: 渲染后的内容。
            truncated: 是否触发截断（当前超限直接失败，恒 False）。
        """
        self.content = content
        self.truncated = truncated


def validate_template(
    source: str,
    *,
    max_bytes: int,
    sample_params: ConcurrentStableDict[str, object] | None = None,
) -> None:
    """保存前校验：语法 + 危险结构 + 宽松冒烟渲染。

    Args:
        source: 模板源码。
        max_bytes: 正文 UTF-8 字节上限。
        sample_params: 可选样例参数（提供时用严格模式渲染）。

    Raises:
        TemplateSyntaxInvalidError: 语法 / 结构非法（70302）。
        TemplateRenderError: 冒烟渲染失败（70303）。
    """
    if len(source.encode("utf-8")) > max_bytes:
        raise TemplateSyntaxInvalidError(f"模板正文超过 {max_bytes} 字节")
    _check_structure(source)
    params = _normalize_params(sample_params)
    _render_sync(source, params, max_bytes=max_bytes, strict=bool(sample_params))


async def render_template(
    source: str,
    params: ConcurrentStableDict[str, object] | None,
    *,
    max_bytes: int,
    timeout_seconds: float,
) -> str:
    """发送前严格渲染（参数缺失即失败；超时 / 超限即失败）。

    Args:
        source: 模板源码。
        params: 渲染参数。
        max_bytes: 输出 UTF-8 字节上限。
        timeout_seconds: 渲染超时（秒）。

    Returns:
        str: 渲染结果。

    Raises:
        TemplateRenderError: 参数非法 / 缺参 / 超时 / 超限 / 渲染失败（70303）。
    """
    _check_structure(source)
    normalized = _normalize_params(params)
    future = _EXECUTOR.submit(_render_sync, source, normalized, max_bytes=max_bytes, strict=True)
    try:
        result = await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout_seconds)
    except TimeoutError as exc:
        future.cancel()
        raise TemplateRenderError(f"模板渲染超时（{timeout_seconds} 秒）") from exc
    return result.content

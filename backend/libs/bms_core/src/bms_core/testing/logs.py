"""统一日志断言（13_04）：解析 structlog JSON 行，替代各文件手写 `_records()`。

两种输入：

- `capsys`（structlog 输出到 stdout 的 JSON 行）——**主流**；
- `caplog`（标准 logging 记录）——兼容既有少量用例。

`log_events` 只统计带 `event` 键的结构化事件；非 JSON 行（如 pytest 进度点）自动跳过。
"""

import json
from typing import Any

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList


def _stable(payload: Any) -> ConcurrentStableDict[str, object]:
    """把普通映射转为插入序字典（保字段顺序）。

    Args:
        payload: 已解析的 JSON 映射。

    Returns:
        ConcurrentStableDict[str, object]: 插入序事件字典。
    """
    event: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in payload.items():
        event.set(str(key), value)
    return event


def _text_of(source: Any) -> str:
    """取日志文本（capsys 读 stdout；caplog 拼接 records；字符串原样）。

    Args:
        source: `capsys` / `caplog` / 文本。

    Returns:
        str: 待解析文本。
    """
    readouterr = getattr(source, "readouterr", None)
    if callable(readouterr):
        captured = readouterr()
        return str(getattr(captured, "out", "")) + str(getattr(captured, "err", ""))
    records = getattr(source, "records", None)
    if records is not None:
        lines: ConcurrentStableList[str] = ConcurrentStableList()
        for record in records:
            message = getattr(record, "msg", "")
            lines.add(str(message))
        return "\n".join(lines)
    return str(source)


def log_events(source: Any) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """解析日志事件（保序）。

    Args:
        source: `capsys` / `caplog` / 文本。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 事件列表（只含带 `event` 的结构化行）。
    """
    events: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for line in _text_of(source).splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "event" in payload:
            events.add(_stable(payload))
    return events


def assert_logged(
    source: Any,
    *,
    event: str,
    level: str | None = None,
    **fields: object,
) -> None:
    """断言存在匹配的日志事件。

    Args:
        source: `capsys` / `caplog` / 文本。
        event: 事件名（精确匹配）。
        level: 级别（大小写不敏感，如 `info` / `warning`）；`None` 不断言。
        **fields: 事件字段子集（逐项精确匹配）。

    Raises:
        AssertionError: 无匹配事件（失败信息列出候选事件名）。
    """
    events = log_events(source)
    names: ConcurrentStableList[str] = ConcurrentStableList()
    for item in events:
        names.add(str(item.get("event", "")))
        if str(item.get("event", "")) != event:
            continue
        if level is not None and str(item.get("level", "")).lower() != level.lower():
            continue
        matched = True
        for key, expected in fields.items():
            if item.get(key) != expected:
                matched = False
                break
        if matched:
            return
    raise AssertionError(
        f"未找到日志事件 event={event!r} level={level!r} fields={fields!r}；候选事件：{'、'.join(names) or '（无）'}"
    )

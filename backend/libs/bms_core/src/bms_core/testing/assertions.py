"""统一错误断言（13_04）：异常实例 / HTTP 响应 / JSON 字典三形态自动识别。

约定（《测试规范》「测试公共基座」节）：

- 用例只写 `assert_error(target, code=30010, status=403)`，不各自提取 `exc.value.code` 或
  `resp.json()["code"]`；
- 失败信息统一带期望值、实际值与消息，便于定位；
- 未给出的维度（`code` / `status` / `message` 为 `None`）不做断言。
"""

from typing import Any

from bms_core.core.concurrent import ConcurrentStableList


def _as_int(value: object) -> int | None:
    """把可能为 `int` / 数字字符串的值归一为 `int`。

    Args:
        value: 原始值。

    Returns:
        int | None: 归一结果（无法归一为 `None`）。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _from_exception(error: BaseException) -> tuple[int | None, int | None, str]:
    """从异常实例取（code, status, message）。

    Args:
        error: 异常实例（`BaseError` 体系带 `code` / `status_code`）。

    Returns:
        tuple[int | None, int | None, str]: 三元组。
    """
    code = _as_int(getattr(error, "code", None))
    status = _as_int(getattr(error, "status_code", None))
    message = str(getattr(error, "message", "") or error)
    return code, status, message


def _from_mapping(payload: Any) -> tuple[int | None, int | None, str]:
    """从映射（响应 JSON / 已解析字典）取（code, status, message）。

    Args:
        payload: 映射对象。

    Returns:
        tuple[int | None, int | None, str]: 三元组。
    """
    code = _as_int(payload.get("code"))
    status = _as_int(payload.get("status") if payload.get("status") is not None else payload.get("status_code"))
    message = payload.get("message") or payload.get("detail") or ""
    return code, status, str(message) if message else ""


def _extract(target: Any) -> tuple[int | None, int | None, str]:
    """按形态提取（code, status, message）。

    Args:
        target: 异常实例 / 响应对象 / 映射。

    Returns:
        tuple[int | None, int | None, str]: 三元组。

    Raises:
        TypeError: 无法识别的 target 形态。
    """
    if isinstance(target, BaseException):
        return _from_exception(target)
    if isinstance(target, dict):
        return _from_mapping(target)
    status_code = getattr(target, "status_code", None)
    json_reader = getattr(target, "json", None)
    if status_code is not None and callable(json_reader):
        payload = json_reader()
        if isinstance(payload, dict):
            code, _, message = _from_mapping(payload)
            return code, _as_int(status_code), message
        return None, _as_int(status_code), ""
    raise TypeError(f"assert_error 不支持的 target 形态：{type(target)!r}")


def assert_error(
    target: Any,
    *,
    code: int | None = None,
    status: int | None = None,
    message: str | None = None,
) -> None:
    """断言错误对象匹配给定维度。

    Args:
        target: 异常实例（`pytest.raises` 取到的 `exc.value`）、HTTP 响应对象或已解析 JSON 字典。
        code: 期望业务错误码；`None` 不断言。
        status: 期望 HTTP 状态码；`None` 不断言。
        message: 期望消息包含的片段；`None` 不断言。

    Raises:
        AssertionError: 任一给定维度不匹配。
        TypeError: target 形态无法识别。
    """
    actual_code, actual_status, actual_message = _extract(target)
    problems: ConcurrentStableList[str] = ConcurrentStableList()
    if code is not None and actual_code != code:
        problems.add(f"code 期望 {code}、实际 {actual_code}")
    if status is not None and actual_status != status:
        problems.add(f"status 期望 {status}、实际 {actual_status}")
    if message is not None and message not in actual_message:
        problems.add(f"message 期望包含 {message!r}、实际 {actual_message!r}")
    if problems:
        raise AssertionError("错误断言不匹配：" + "；".join(problems))


def assert_no_error(target: Any) -> None:
    """断言目标不是错误（响应 2xx 且业务码为 0 / 缺失）。

    Args:
        target: HTTP 响应对象或已解析 JSON 字典。

    Raises:
        AssertionError: 响应为错误状态或带非 0 业务码。
    """
    actual_code, actual_status, actual_message = _extract(target)
    if actual_status is not None and actual_status >= 400:
        raise AssertionError(f"期望成功响应，实际 status={actual_status}（{actual_message}）")
    if actual_code not in (None, 0):
        raise AssertionError(f"期望成功业务码，实际 code={actual_code}（{actual_message}）")

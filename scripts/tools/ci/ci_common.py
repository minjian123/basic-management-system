#!/usr/bin/env python3
"""CI 工具脚本的公共底座：凭据、HTTP、目标解析与日志清理。

`trigger.py` 保持独立历史不动；本模块给 `pipeline_jobs` / `job_log` / `pipeline_cancel` /
`pipeline_retry` / `ci_queue_lock` 共用同一套 GitLab 调用与日志清洗，避免各写一份。
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
"""bms 仓库根（本文件位于 `scripts/tools/ci/`）。"""

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_SRC_ROOT = ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from trigger import ENV_FILE, REPO_NAMES, TERMINAL_STATUSES, load_env, resolve  # noqa: E402

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList  # noqa: E402

API_TIMEOUT_SECONDS = 30
"""单次 GitLab API 调用超时（秒）。"""

API_ENV_URL = "GITLAB_API_URL"
"""API 基址的环境变量 / `.env` 键名。"""

API_ENV_TOKEN = "GITLAB_API_TOKEN"
"""访问令牌的环境变量 / `.env` 键名。"""

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
"""GitLab 日志里的 ANSI 颜色 / 清行控制码。"""

_TRACE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z \d{2}[A-Z] ?")
"""GitLab runner 给每行加的「时间戳 + 流标记」前缀（`00O` 输出 / `01E` 错误）。"""

_SECTION_LINE = re.compile(r"^\+?section_(start|end):")
"""GitLab 折叠段标记行（无信息量，剔除）。"""


@dataclass(frozen=True)
class Api:
    """GitLab API 访问上下文。"""

    url: str
    token: str


@dataclass(frozen=True)
class PipelineRef:
    """一条流水线的定位信息。"""

    project: str
    path: str
    pipeline_id: int


def load_api(env_file: Path = ENV_FILE) -> Api | None:
    """读取 API 基址与令牌（缺任一项返回 None）。

    Args:
        env_file: `.env` 文件路径。

    Returns:
        Api | None: 访问上下文；凭据缺失时为 None。
    """
    env = load_env(env_file)
    url = resolve(API_ENV_URL, env)
    token = resolve(API_ENV_TOKEN, env)
    if not url or not token:
        return None
    return Api(url=url, token=token)


def missing_credentials_hint() -> str:
    """凭据缺失时的统一提示。

    Returns:
        str: 提示文案。
    """
    return f"缺少 {API_ENV_URL} / {API_ENV_TOKEN}（读 {ENV_FILE} 或同名环境变量）"


def quoted(path: str) -> str:
    """URL 编码项目路径（`bms/bms` → `bms%2Fbms`）。

    Args:
        path: GitLab 项目路径。

    Returns:
        str: 编码后的路径。
    """
    return urllib.parse.quote(path, safe="")


def get_text(api: Api, path: str) -> str:
    """GET 原始响应文本（JSON 与 job 日志共用）。

    Args:
        api: 访问上下文。
        path: 相对 API 基址的路径。

    Returns:
        str: 响应体文本（空响应为空串）。
    """
    url = f"{api.url.rstrip('/')}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": api.token}, method="GET")
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", "replace")


def _wrap(value: object) -> object:
    """把 JSON 解析结果递归换成并发稳定容器（护栏要求集合声明走 ConcurrentStable*）。

    Args:
        value: `json.loads` 的原始结果。

    Returns:
        object: 递归替换后的结构。
    """
    if isinstance(value, dict):
        return ConcurrentStableDict((str(key), _wrap(item)) for key, item in value.items())
    if isinstance(value, list):
        return ConcurrentStableList(_wrap(item) for item in value)
    return value


def get_json(api: Api, path: str) -> object:
    """GET 并解析 JSON（对象与数组都支持）。

    Args:
        api: 访问上下文。
        path: 相对 API 基址的路径。

    Returns:
        object: 解析后的响应（空响应为 ConcurrentStableDict）。
    """
    raw = get_text(api, path)
    return _wrap(json.loads(raw)) if raw.strip() else ConcurrentStableDict()


def post_json(api: Api, path: str, payload: ConcurrentStableDict[str, object] | None = None) -> object:
    """POST JSON（取消 / 重试等写操作）。

    Args:
        api: 访问上下文。
        path: 相对 API 基址的路径。
        payload: 请求体（None 表示空对象）。

    Returns:
        object: 解析后的响应（空响应为 ConcurrentStableDict）。
    """
    url = f"{api.url.rstrip('/')}/{path.lstrip('/')}"
    body = json.dumps(dict(payload or ConcurrentStableDict())).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"PRIVATE-TOKEN": api.token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return _wrap(json.loads(raw)) if raw.strip() else ConcurrentStableDict()


def clean_trace_lines(text: str) -> ConcurrentStableList[str]:
    """清洗 job 日志：去 ANSI 控制码、runner 时间戳前缀、折叠段标记与空行。

    Args:
        text: 原始日志文本。

    Returns:
        ConcurrentStableList[str]: 清洗后的行。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _ANSI_ESCAPE.sub("", raw)
        line = _TRACE_PREFIX.sub("", line).rstrip()
        if not line.strip() or _SECTION_LINE.match(line):
            continue
        lines.append(line)
    return lines


def tail(lines: ConcurrentStableList[str], count: int) -> ConcurrentStableList[str]:
    """取末尾若干行（count <= 0 返回空）。

    Args:
        lines: 全部行。
        count: 保留的行数。

    Returns:
        ConcurrentStableList[str]: 末尾若干行。
    """
    if count <= 0:
        return ConcurrentStableList()
    return lines[-count:]


def split(values: ConcurrentStableList[str] | None) -> ConcurrentStableList[str]:
    """把可重复 / 逗号分隔的参数拍平（保序去重）。

    Args:
        values: 原始参数（可为 None）。

    Returns:
        ConcurrentStableList[str]: 拍平后的取值。
    """
    flattened: ConcurrentStableList[str] = ConcurrentStableList()
    for value in values or ():
        for item in value.split(","):
            name = item.strip()
            if name and name not in flattened:
                flattened.append(name)
    return flattened


def parse_pipeline_specs(specs: ConcurrentStableList[str]) -> ConcurrentStableList[PipelineRef]:
    """解析 `仓名:流水线ID` 形式的参数。

    Args:
        specs: 原始参数（如 `bms:1285`）。

    Returns:
        ConcurrentStableList[PipelineRef]: 目标列表（保序去重）。

    Raises:
        ValueError: 取值格式非法。
    """
    refs: ConcurrentStableList[PipelineRef] = ConcurrentStableList()
    for spec in specs:
        name, sep, raw_id = spec.partition(":")
        name = name.strip()
        raw_id = raw_id.strip()
        if not sep or not name or not raw_id.isdigit():
            raise ValueError(f"目标格式应为 <仓名>:<流水线ID>，收到：{spec}")
        ref = PipelineRef(project=name, path=REPO_NAMES.get(name, name), pipeline_id=int(raw_id))
        if ref not in refs:
            refs.append(ref)
    return refs


__all__ = [
    "API_TIMEOUT_SECONDS",
    "ENV_FILE",
    "REPO_NAMES",
    "TERMINAL_STATUSES",
    "Api",
    "ConcurrentStableDict",
    "ConcurrentStableList",
    "PipelineRef",
    "clean_trace_lines",
    "get_json",
    "get_text",
    "load_api",
    "load_env",
    "missing_credentials_hint",
    "parse_pipeline_specs",
    "post_json",
    "quoted",
    "split",
    "tail",
]

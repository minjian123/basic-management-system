#!/usr/bin/env python3
"""Alertmanager 配置渲染（08_02 告警阈值锚点；只读 `.env`，产出 gitignore 渲染物）。

Alertmanager 配置文件**不支持环境变量替换**，且 SMTP 主机 / 收件人 / webhook URL 属本地资源
（公开文档红线）——采用「模板入 Git + 本脚本渲染」：

- 模板：`deploy/observability/alertmanager.yml.tmpl`（占位符 `$global_smtp_block` /
  `$default_receiver_block` / `$critical_receiver_block`）；
- 输入：`deploy/.env`（`--env-file` 可改）中的告警变量（进程环境变量同名优先）；
- 产物：`deploy/observability/rendered/alertmanager.yml`（已 gitignore；供 compose 挂载）。

通道口径（缺失即禁用，不阻断其余组件）：

- 有 `ALERTMANAGER_SMTP_SMARTHOST`（且 `_FROM` / `_EMAIL_TO` 齐备）→ 渲染邮件 receiver；
  `ALERTMANAGER_SMTP_USERNAME` / `ALERTMANAGER_SMTP_PASSWORD` 可选；
- 有 `ALERTMANAGER_WECOM_WEBHOOK_URL` / `ALERTMANAGER_DINGTALK_WEBHOOK_URL` → `critical` receiver
  附 webhook（企业微信 / 钉钉群机器人；BMS 内部接口格式转换归通知阶段）；
- 均无 → receiver 无配置（no-op，告警仅 Alertmanager UI 可见）。

用法::

    python3 scripts/tools/observability/render_alertmanager.py --env-file deploy/.env
    python3 scripts/tools/observability/render_alertmanager.py --check   # 产物是否为最新（不一致退 1）

退出码：0 渲染成功 / 校验一致；1 `--check` 不一致；2 参数、模板或路径错误。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from string import Template

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ENV = _REPO_ROOT / "deploy" / ".env"
_DEFAULT_TEMPLATE = _REPO_ROOT / "deploy" / "observability" / "alertmanager.yml.tmpl"
_DEFAULT_OUT = _REPO_ROOT / "deploy" / "observability" / "rendered" / "alertmanager.yml"

_SMTP_KEYS = (
    "ALERTMANAGER_SMTP_SMARTHOST",
    "ALERTMANAGER_SMTP_FROM",
    "ALERTMANAGER_SMTP_USERNAME",
    "ALERTMANAGER_SMTP_PASSWORD",
    "ALERTMANAGER_EMAIL_TO",
)
_WEBHOOK_KEYS = ("ALERTMANAGER_WECOM_WEBHOOK_URL", "ALERTMANAGER_DINGTALK_WEBHOOK_URL")


def parse_env_file(path: Path) -> dict[str, str]:
    """读取键值型凭据文件（只取需要的键，不回显值）。

    Args:
        path: `.env` 文件路径（不存在时返回空字典）。

    Returns:
        dict[str, str]: 键值对（去引号）。
    """
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _get(key: str, env_file: dict[str, str]) -> str:
    """取配置值（进程环境变量优先于 `.env`，去首尾空白）。"""
    return (os.environ.get(key) or env_file.get(key, "")).strip()


def _quote(value: str) -> str:
    """YAML 单引号标量（内部单引号按 YAML 规则加倍）。"""
    return "'" + value.replace("'", "''") + "'"


def _smtp_global_block(env_file: dict[str, str]) -> str:
    """渲染 `global` 的 SMTP 默认项（无 smarthost 时返回空串）。"""
    smarthost = _get("ALERTMANAGER_SMTP_SMARTHOST", env_file)
    sender = _get("ALERTMANAGER_SMTP_FROM", env_file)
    if not smarthost or not sender:
        return ""
    lines = [
        f"  smtp_smarthost: {_quote(smarthost)}",
        f"  smtp_from: {_quote(sender)}",
        "  smtp_require_tls: false",
    ]
    username = _get("ALERTMANAGER_SMTP_USERNAME", env_file)
    password = _get("ALERTMANAGER_SMTP_PASSWORD", env_file)
    if username:
        lines.append(f"  smtp_auth_username: {_quote(username)}")
    if password:
        lines.append(f"  smtp_auth_password: {_quote(password)}")
    return "\n".join(lines)


def _email_block(env_file: dict[str, str], *, indent: str) -> str:
    """渲染 `email_configs` 块（smarthost / from / to 三者缺一不渲染；缩进由调用方给定）。"""
    smarthost = _get("ALERTMANAGER_SMTP_SMARTHOST", env_file)
    sender = _get("ALERTMANAGER_SMTP_FROM", env_file)
    recipient = _get("ALERTMANAGER_EMAIL_TO", env_file)
    if not (smarthost and sender and recipient):
        if smarthost and not (sender and recipient):
            print("警告：SMTP 主机已配置但缺少 ALERTMANAGER_SMTP_FROM / ALERTMANAGER_EMAIL_TO，邮件通道跳过")
        return ""
    return "\n".join(
        [
            f"{indent}email_configs:",
            f"{indent}  - to: {_quote(recipient)}",
            f"{indent}    from: {_quote(sender)}",
            f"{indent}    smarthost: {_quote(smarthost)}",
            f"{indent}    send_resolved: true",
        ]
    )


def _webhook_block(env_file: dict[str, str], *, indent: str) -> str:
    """渲染 `webhook_configs` 块（企业微信 / 钉钉群机器人；无 URL 时返回空串）。"""
    urls = [url for key in _WEBHOOK_KEYS if (url := _get(key, env_file))]
    if not urls:
        return ""
    lines = [f"{indent}webhook_configs:"]
    for url in urls:
        lines.append(f"{indent}  - url: {_quote(url)}")
        lines.append(f"{indent}    send_resolved: true")
    return "\n".join(lines)


def render(template_text: str, env_file: dict[str, str]) -> str:
    """按模板与凭据渲染配置文本。

    Args:
        template_text: 模板内容（`string.Template` 占位符）。
        env_file: `.env` 键值对。

    Returns:
        str: 渲染后的 YAML 文本。
    """
    return Template(template_text).substitute(
        global_smtp_block=_smtp_global_block(env_file),
        default_receiver_block=_email_block(env_file, indent="    "),
        critical_receiver_block="\n".join(
            block
            for block in (_email_block(env_file, indent="    "), _webhook_block(env_file, indent="    "))
            if block
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """入口：渲染 / 校验产物。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码（0 成功；1 `--check` 不一致；2 参数或路径错误）。
    """
    parser = argparse.ArgumentParser(description="Alertmanager 配置渲染（只读 .env，产物不入库）")
    parser.add_argument("--env-file", default=str(_DEFAULT_ENV), help="凭据文件（默认 deploy/.env）")
    parser.add_argument("--template", default=str(_DEFAULT_TEMPLATE), help="模板路径（默认 deploy/observability/alertmanager.yml.tmpl）")
    parser.add_argument("--out", default=str(_DEFAULT_OUT), help="产物路径（默认 deploy/observability/rendered/alertmanager.yml）")
    parser.add_argument("--check", action="store_true", help="校验产物是否为最新（不一致退 1，不写文件）")
    args = parser.parse_args(argv)

    template_path = Path(args.template)
    if not template_path.is_file():
        print(f"模板不存在：{template_path}")
        return 2
    env_file = parse_env_file(Path(args.env_file))
    rendered = render(template_path.read_text(encoding="utf-8"), env_file)
    out_path = Path(args.out)

    if args.check:
        if out_path.is_file() and out_path.read_text(encoding="utf-8") == rendered:
            print(f"产物为最新：{out_path}")
            return 0
        print(f"产物缺失或过期，请重新渲染：{out_path}")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    channels = []
    if _smtp_global_block(env_file):
        channels.append("邮件")
    if _webhook_block(env_file, indent=""):
        channels.append("webhook（企业微信 / 钉钉）")
    print(f"已渲染：{out_path}")
    print("已启用通道：" + ("、".join(channels) if channels else "无（no-op receiver，告警仅 Alertmanager UI 可见）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

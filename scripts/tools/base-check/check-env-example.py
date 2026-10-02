#!/usr/bin/env python3
"""`deploy/.env.example` 与 `backend/.env.example` 键位一致性门禁（04_03）。

口径：环境变量模板必须与配置实现键位一致——密钥类键位齐备、已移除键不得残留、占位示例不得误贴真实密钥。
由 preflight（本地推送前）与 CI `base-integrity` job 同口径调用。

用法::

    python3 scripts/tools/base-check/check-env-example.py [bms 仓库根]
    python3 scripts/tools/base-check/check-env-example.py --self-test

退出码：0 无问题；1 存在问题；2 仓库 / 模板文件缺失。
"""

import sys
from pathlib import Path

#: `backend/.env.example` 必须齐备的安全密钥键位（`[security]` 定稿，见 01_01 / 04_03）。
_BACKEND_SECURITY_KEYS = (
    "BMS_SECURITY__SECRET_KEY",
    "BMS_SECURITY__ACCESS_TOKEN_EXPIRE_MINUTES",
    "BMS_SECURITY__REFRESH_TOKEN_EXPIRE_DAYS",
    "BMS_SECURITY__ACTIVE_KID",
    "BMS_SECURITY__KEYS",
)

#: `deploy/.env.example` 必须齐备的密钥类键位（部署侧命令行注入）。
_DEPLOY_SECRET_KEYS = (
    "BMS_SECURITY__SECRET_KEY",
    "BMS_SECURITY__ACTIVE_KID",
    "BMS_SECURITY__KEYS",
    "BMS_SERVICE_TOKEN__KEYS",
)

#: 已移除 / 废弃键：不得在任何模板中残留。
_REMOVED_KEYS = ("BMS_SECURITY__ALGORITHM",)

#: 文档端点开关键（04_03；须在 `backend/.env.example` 中出现）。
_DOCS_KEY = "BMS_APP__DOCS_ENABLED"


def check_env_example_texts(backend_text, deploy_text):
    """比对两份环境变量模板文本，返回问题清单（纯函数，便于自检）。

    Args:
        backend_text: `backend/.env.example` 全文。
        deploy_text: `deploy/.env.example` 全文。

    Returns:
        tuple[str, ...]: 问题描述列表（空表示通过）。
    """
    problems = []
    for key in _REMOVED_KEYS:
        for label, text in (("backend/.env.example", backend_text), ("deploy/.env.example", deploy_text)):
            if key in text:
                problems.append(f"{label} 残留已移除键 {key}")
    for key in _BACKEND_SECURITY_KEYS:
        if key not in backend_text:
            problems.append(f"backend/.env.example 缺安全密钥键位 {key}")
    for key in _DEPLOY_SECRET_KEYS:
        if key not in deploy_text:
            problems.append(f"deploy/.env.example 缺密钥键位 {key}")
    if _DOCS_KEY not in backend_text:
        problems.append(f"backend/.env.example 缺文档端点开关 {_DOCS_KEY}")
    for label, text in (("backend/.env.example", backend_text), ("deploy/.env.example", deploy_text)):
        for number, line in enumerate(text.splitlines(), start=1):
            if "PRIVATE KEY" in line and "..." not in line:
                problems.append(f"{label}:{number} 疑似真实私钥（占位示例须含 `...`）")
    return tuple(problems)


def _self_test():
    """自检：正常模板通过；废弃键残留 / 缺键 / 真实私钥三类反例被拦截。

    Returns:
        int: 退出码（0 通过 / 1 失败）。
    """
    good_backend = "\n".join((*_BACKEND_SECURITY_KEYS, _DOCS_KEY))
    good_deploy = "\n".join(_DEPLOY_SECRET_KEYS)
    cases = [
        ("正常", good_backend, good_deploy, 0),
        ("废弃键残留", good_backend + "\nBMS_SECURITY__ALGORITHM=HS256", good_deploy, 1),
        ("backend 缺键", good_backend.replace("BMS_SECURITY__KEYS", ""), good_deploy, 1),
        ("deploy 缺键", good_backend, good_deploy.replace("BMS_SERVICE_TOKEN__KEYS", ""), 1),
        ("缺文档开关", good_backend.replace(_DOCS_KEY, ""), good_deploy, 1),
        ("真实私钥", good_backend + "\n-----BEGIN PRIVATE KEY-----", good_deploy, 1),
    ]
    bad = 0
    for title, backend_text, deploy_text, expect in cases:
        found = check_env_example_texts(backend_text, deploy_text)
        flag = "OK" if len(found) == expect else "FAIL"
        bad += flag == "FAIL"
        print(f"  [{flag}] {title}：期望 {expect} 项，实得 {len(found)} 项")
    print(f"\n[check-env-example self-test] {'通过' if not bad else '不通过'}：断言用例 {len(cases)} 个")
    return 1 if bad else 0


def main():
    """入口：读取两份模板并检查。

    Returns:
        int: 退出码。
    """
    if "--self-test" in sys.argv:
        return _self_test()
    args = [item for item in sys.argv[1:] if not item.startswith("-")]
    root = Path(args[0] if args else ".").resolve()
    backend_file = root / "backend" / ".env.example"
    deploy_file = root / "deploy" / ".env.example"
    missing = [str(path) for path in (backend_file, deploy_file) if not path.is_file()]
    if missing:
        print(f"[check-env-example] 模板文件缺失：{'、'.join(missing)}")
        return 2
    problems = check_env_example_texts(
        backend_file.read_text(encoding="utf-8"), deploy_file.read_text(encoding="utf-8")
    )
    if problems:
        print(f"[check-env-example] 不通过：{len(problems)} 项")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("[check-env-example] 通过：两份 `.env.example` 密钥键位齐备、无废弃键与真实密钥")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""作业类型声明解析护栏（Kiwi 2385）：真实清单 `[[jobs]]` / 字段校验 / 跨记录校验。

以本仓 `deploy/registry/platform.toml` 为基线：保证声明与平台实际装载同源，不维护第二份样例。
"""

from pathlib import Path

import pytest

from bms_core.core.exceptions import CatalogError
from bms_core.registry.products import (
    inspect_product_manifests,
    load_product_manifest,
    local_manifest_paths,
    parse_manifest_text,
)

pytestmark = pytest.mark.kiwi_id(2385)


def _platform_manifest_text() -> str:
    """读取本仓平台清单原文。

    Returns:
        str: TOML 文本。
    """
    path = next(item for item in local_manifest_paths() if item.name == "platform.toml")
    return path.read_text(encoding="utf-8")


def test_real_manifest_declares_platform_jobs() -> None:
    """真实清单声明平台两个作业（任务执行 + 孤儿回收），缺省值齐备。"""
    path = next(item for item in local_manifest_paths() if item.name == "platform.toml")
    manifest = load_product_manifest(path)
    kinds = {job.job_type: job for job in manifest.jobs}
    assert set(kinds) == {"sys.task.run", "file.cleanup_orphans", "platform.import.execute"}
    assert kinds["platform.import.execute"].service == "platform"
    assert kinds["platform.import.execute"].max_attempts == 1
    assert kinds["sys.task.run"].service == "platform"
    assert kinds["sys.task.run"].domain == "task"
    assert kinds["file.cleanup_orphans"].service == "file"
    assert kinds["file.cleanup_orphans"].max_attempts == 3
    assert kinds["file.cleanup_orphans"].concurrency == 1
    assert all(job.handler.count(":") == 1 for job in manifest.jobs)


def test_rejects_bad_job_type() -> None:
    """类型形态非法（非小写点分）：解析期拒绝。"""
    text = _platform_manifest_text().replace('job_type = "sys.task.run"', 'job_type = "SysTaskRun"')
    with pytest.raises(CatalogError, match="小写点分"):
        parse_manifest_text(text)


def test_rejects_bad_handler() -> None:
    """handler 非 `module:attr`：解析期拒绝。"""
    text = _platform_manifest_text().replace(
        'handler = "bms_platform.domains.task.jobs:TaskJobHandler"', 'handler = "no-separator"'
    )
    with pytest.raises(CatalogError, match="module:attr"):
        parse_manifest_text(text)


def test_rejects_bad_status() -> None:
    """状态非法：解析期拒绝。"""
    text = _platform_manifest_text().replace(
        'concurrency = 4\npayload_version = "1.0.0"\nstatus = "enabled"',
        'concurrency = 4\npayload_version = "1.0.0"\nstatus = "paused"',
    )
    with pytest.raises(CatalogError, match="状态非法"):
        parse_manifest_text(text)


def test_inspect_rejects_duplicate_type(tmp_path: Path) -> None:
    """跨记录校验：同清单重复作业类型 → 阻断。"""
    text = (
        _platform_manifest_text()
        + """
[[jobs]]
job_type = "sys.task.run"
service = "platform"
domain = "task"
handler = "m:f"
description = "重复声明"
"""
    )
    path = tmp_path / "platform.toml"
    path.write_text(text, encoding="utf-8")
    inspection = inspect_product_manifests([path])
    assert any("重复声明" in item for item in inspection.errors)

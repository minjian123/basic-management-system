"""作业参数护栏（Kiwi 2389）：默认值 / 非法回落 / 租约与心跳关系 / 声明覆盖。"""

import pytest

from bms_core.core.config import JobSettings
from bms_core.jobs.limits import DEFAULT_LIMITS, JobLimits

pytestmark = pytest.mark.kiwi_id(2389)


def test_defaults_when_settings_missing() -> None:
    """未传配置：全部取代码默认（不抛错）。"""
    limits = JobLimits()
    assert limits.global_concurrency == DEFAULT_LIMITS["global_concurrency"]
    assert limits.per_tenant_concurrency == DEFAULT_LIMITS["per_tenant_concurrency"]
    assert limits.lease_seconds == DEFAULT_LIMITS["lease_seconds"]
    assert limits.warnings == []


def test_invalid_values_fall_back_with_warning() -> None:
    """非法值（0 / 负数 / 非数字）：回落默认并记告警。"""
    settings = JobSettings()
    object.__setattr__(settings, "global_concurrency", 0)
    object.__setattr__(settings, "claim_batch_size", -1)
    object.__setattr__(settings, "poll_interval_seconds", 0.0)
    limits = JobLimits(settings)
    assert limits.global_concurrency == DEFAULT_LIMITS["global_concurrency"]
    assert limits.claim_batch_size == DEFAULT_LIMITS["claim_batch_size"]
    assert limits.poll_interval_seconds == DEFAULT_LIMITS["poll_interval_seconds"]
    assert len(limits.warnings) >= 3


def test_lease_must_exceed_heartbeat() -> None:
    """租约不大于心跳 × 3：抬到心跳 × 3 + 1 并告警。"""
    settings = JobSettings(lease_seconds=60, heartbeat_interval_seconds=30)
    limits = JobLimits(settings)
    assert limits.lease_seconds == 91
    assert any("lease_seconds" in item for item in limits.warnings)


def test_declaration_overrides_defaults() -> None:
    """声明值由调用方显式覆盖（执行器 / worker 按类型参数取值）。"""
    limits = JobLimits(JobSettings(max_attempts_default=7, result_max_chars=1024))
    assert limits.max_attempts_default == 7
    assert limits.result_max_chars == 1024


def test_progress_interval_allows_zero() -> None:
    """进度节流间隔允许 0（每次更新都发）。"""
    limits = JobLimits(JobSettings(progress_interval_seconds=0))
    assert limits.progress_interval_seconds == 0.0


def test_bool_and_non_numeric_fall_back() -> None:
    """bool / 非数字：按非法处理回落默认（bool 不当 0 / 1）。"""
    settings = JobSettings()
    object.__setattr__(settings, "backoff_seconds_default", True)
    object.__setattr__(settings, "progress_interval_seconds", "0.5")
    limits = JobLimits(settings)
    assert limits.backoff_seconds_default == DEFAULT_LIMITS["backoff_seconds_default"]
    assert limits.progress_interval_seconds == DEFAULT_LIMITS["progress_interval_seconds"]
    assert any("backoff_seconds_default" in item for item in limits.warnings)

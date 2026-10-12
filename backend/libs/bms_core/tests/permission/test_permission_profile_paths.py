"""权限引擎档位归一与校验路径用例（`bms_core/permission/profile.py`）。"""

from __future__ import annotations

import pytest

from bms_core.core.exceptions import ConfigError
from bms_core.permission.profile import (
    DEFAULT_PROFILE,
    PROFILE_ENTERPRISE,
    ensure_profile_supported,
    normalize_profile,
)


def test_normalize_profile_blank_and_default() -> None:
    """档位归一：`None` / 空串 / 全空白回落缺省档位；已实现档位校验通过。"""
    assert normalize_profile(None) == DEFAULT_PROFILE
    assert normalize_profile("   ") == DEFAULT_PROFILE
    assert normalize_profile(" smb ") == DEFAULT_PROFILE
    assert ensure_profile_supported(DEFAULT_PROFILE) == DEFAULT_PROFILE


def test_ensure_profile_supported_rejects_unknown_and_unimplemented() -> None:
    """非法档位与未实现档位均 fail-closed（`ConfigError`）。"""
    with pytest.raises(ConfigError):
        ensure_profile_supported("ghost")

    with pytest.raises(ConfigError):
        ensure_profile_supported(PROFILE_ENTERPRISE)

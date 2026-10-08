"""权限引擎档位（域 `permission`）。

引擎按**档位（`profile`）**分三代**递增装配形态**——同一引擎的三级能力，不是三套实现：

- `smb`（中小企业）：基础版权限引擎——主体链 → 权限码集 + 数据范围（四策略）+ 字段权限 + 两级校验 + 概要装载；
- `enterprise`（大型企业）：精细化权限管理引擎——在 `smb` 之上扩展更细的授权与生效规则；
- `enterprise_hr`（大型企业人事）：结构化权限管理引擎——在 `enterprise` 之上扩展人事权限（组织 / 岗位层级 / 汇报线）。

**与 `tier` 的区别（易混，务必区分）**：`tier` 是主体层级的**豁免标记**（超管 / 系统管理员 → 校验恒真，见
`permission/snapshot.py`）；`profile` 是**引擎档位**（能力集合）。二者维度不同，在快照中分列 `tier` 与 `profile`。

配置 `[permission].profile`（缺省 `smb`）；**未实现的档位启动即 `ConfigError`（fail-closed）**，不静默降级为 `smb`。

后代接入位（角色解析器链 / 字段权限 provider / 校验链 guard / 数据范围策略注册表 / 快照 `extensions`）见
《02_04 主体链权限计算引擎 详细设计》§11 与
《[架构设计 · 权限计算引擎](../../../../../bms文档/设计/架构设计/15_架构设计_子系统_权限计算引擎.md)》§10。
"""

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ConfigError

PROFILE_SMB = "smb"
"""档位：中小企业（基础版权限引擎，当前已实现）。"""

PROFILE_ENTERPRISE = "enterprise"
"""档位：大型企业（精细化权限管理引擎；方向已定，接缝已备）。"""

PROFILE_ENTERPRISE_HR = "enterprise_hr"
"""档位：大型企业（人事）（结构化权限管理引擎；方向已定，接缝已备）。"""

DEFAULT_PROFILE = PROFILE_SMB
"""缺省档位。"""

PERMISSION_PROFILES: tuple[str, ...] = (PROFILE_SMB, PROFILE_ENTERPRISE, PROFILE_ENTERPRISE_HR)
"""全部档位（递增装配形态）。"""

IMPLEMENTED_PROFILES: tuple[str, ...] = (PROFILE_SMB,)
"""当前已实现档位（其余档位一旦配置即启动 fail-closed）。"""

PROFILE_AUDIENCE: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        PROFILE_SMB: "中小企业",
        PROFILE_ENTERPRISE: "大型企业",
        PROFILE_ENTERPRISE_HR: "大型企业（人事）",
    }
)
"""档位受众（启动提示与文档用语）。"""


def normalize_profile(raw: str | None) -> str:
    """归一档位取值（缺省 / 空串回落 `smb`；未知值原样返回，由校验函数判错）。

    Args:
        raw: 配置原始值。

    Returns:
        str: 档位取值。
    """
    if raw is None:
        return DEFAULT_PROFILE
    trimmed = raw.strip()
    return trimmed or DEFAULT_PROFILE


def ensure_profile_supported(profile: str) -> str:
    """校验档位合法且已实现（未实现抛 `ConfigError`，启动期 fail-closed）。

    Args:
        profile: 档位取值（建议先经 `normalize_profile` 归一）。

    Returns:
        str: 校验通过的档位取值。

    Raises:
        ConfigError: 取值不在已定义集合内，或该档位尚未实现（不静默降级）。
    """
    if profile not in PERMISSION_PROFILES:
        raise ConfigError(f"[permission].profile 取值非法：{profile}（允许：{' / '.join(PERMISSION_PROFILES)}）")
    if profile not in IMPLEMENTED_PROFILES:
        audience = PROFILE_AUDIENCE.get(profile, "")
        raise ConfigError(
            f"[permission].profile = {profile}（{audience}）尚未实现；"
            f"当前仅支持 {' / '.join(IMPLEMENTED_PROFILES)}（不静默降级）"
        )
    return profile

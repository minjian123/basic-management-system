"""系统参数平台默认种子：向租户库幂等写入平台默认参数（含验证码场景策略键）。

- 幂等：按 `config_key` 判存（存在跳过）；可重复执行（`ops/seed_config.py` 与 `ops/init_tenant.py` 共用）。
- 平台默认来源：概要 10 §6.3 与《验证码与账号治理》需求 03-8；键名点分小写（《命名规范》）。
- 缺省回落：消费方（如验证码场景策略）以代码默认表兜底；本种子只投放「平台默认值」供按租户覆盖。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.config.models import SysConfig
from bms_core.core.base import BaseObject

__all__ = ["PLATFORM_CONFIG_DEFAULTS", "SeedConfig", "seed_configs"]


@dataclass(frozen=True)
class SeedConfig(BaseObject):
    """平台默认参数项。"""

    config_key: str
    value: str
    remark: str = ""


def _captcha_scene_keys(scene: str, *, required: str) -> tuple[SeedConfig, ...]:
    """构造验证码场景策略键（required / fail_threshold / ttl / cooldown）。

    Args:
        scene: 场景码。
        required: 是否强制（`"true"` / `"false"`）。

    Returns:
        tuple[SeedConfig, ...]: 该场景四个参数项。
    """
    label = {
        "login": "登录",
        "reset_password": "找回密码",
        "bind": "绑定手机",
        "unbind": "解绑手机",
        "register": "注册",
    }[scene]
    return (
        SeedConfig(f"captcha.scene.{scene}.required", required, f"{label}场景是否强制验证码"),
        SeedConfig(f"captcha.scene.{scene}.fail_threshold", "3", f"{label}场景连续失败强制验证码阈值"),
        SeedConfig(f"captcha.scene.{scene}.ttl", "300", f"{label}场景挑战有效期（秒）"),
        SeedConfig(f"captcha.scene.{scene}.cooldown", "60", f"{label}场景重发冷却（秒）"),
    )


PLATFORM_CONFIG_DEFAULTS: tuple[SeedConfig, ...] = (
    *_captcha_scene_keys("login", required="false"),
    *_captcha_scene_keys("reset_password", required="true"),
    *_captcha_scene_keys("bind", required="true"),
    *_captcha_scene_keys("unbind", required="true"),
    *_captcha_scene_keys("register", required="true"),
    SeedConfig("captcha.channel.image", "true", "图形验证码渠道可用（兜底渠道，恒可用）"),
    SeedConfig("captcha.channel.slider", "true", "滑块验证码渠道可用"),
    SeedConfig("captcha.channel.sms", "false", "短信验证码渠道可用（未配通道默认关闭）"),
)
"""平台默认参数项（本轮投放验证码场景策略与渠道开关；后续模块键顺延追加）。"""


async def seed_configs(session: AsyncSession) -> int:
    """幂等写入平台默认参数（返回新增行数；已存在项跳过）。

    Args:
        session: 租户库会话（调用方负责引擎与租户）。

    Returns:
        int: 新增行数。
    """
    created = 0
    for seed in PLATFORM_CONFIG_DEFAULTS:
        stmt = select(SysConfig).where(
            SysConfig.config_key == seed.config_key,
            SysConfig.deleted_at.is_(None),
        )
        if (await session.execute(stmt)).scalar_one_or_none() is not None:
            continue
        session.add(SysConfig(config_key=seed.config_key, value=seed.value, remark=seed.remark))
        created += 1
    await session.commit()
    return created

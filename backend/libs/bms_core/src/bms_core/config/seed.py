"""系统参数平台默认种子：向租户库幂等写入平台默认参数（含验证码场景策略键）。

- 幂等与升级：按 `config_key` 判存——缺失则插入；存在且 `is_overridden=false` 则按清单刷新
  `value` / `remark`（平台默认随发版演进可下发到未覆盖租户）；**已覆盖行（`is_overridden=true`）永不覆盖**。
- 可重复执行（`ops/seed_config.py` 与租户开通编排共用）。
- 平台默认来源：概要 10 §6.3、《验证码与账号治理》需求 03-8、会话 / 文件 / AI 开关与菜单 / 角色域键；
  键名点分小写（《命名规范》）。
- 缺省回落：消费方以代码默认表兜底；本种子只投放「平台默认值」供按租户覆盖。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject

__all__ = ["DEFAULT_FILE_WHITELIST", "PLATFORM_CONFIG_DEFAULTS", "SeedConfig", "seed_configs"]

_LOGGER = get_logger("bms")


@dataclass(frozen=True)
class SeedConfig(BaseValueObject):
    """平台默认参数项。"""

    config_key: str
    value: str
    remark: str = ""


DEFAULT_FILE_WHITELIST = (
    "image/png:png,image/jpeg:jpg|jpeg,image/gif:gif,image/webp:webp,application/pdf:pdf,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document:docx,"
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet:xlsx,"
    "application/vnd.openxmlformats-officedocument.presentationml.presentation:pptx,"
    "text/plain:txt,text/csv:csv"
)
"""文件上传类型白名单缺省值（`file.upload.whitelist` 的平台默认；文件域代码默认同源引用）。"""


def _captcha_scene_keys(scene: str, *, required: str) -> ConcurrentStableList[SeedConfig]:
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
    return ConcurrentStableList(
        (
            SeedConfig(f"captcha.scene.{scene}.required", required, f"{label}场景是否强制验证码"),
            SeedConfig(f"captcha.scene.{scene}.fail_threshold", "3", f"{label}场景连续失败强制验证码阈值"),
            SeedConfig(f"captcha.scene.{scene}.ttl", "300", f"{label}场景挑战有效期（秒）"),
            SeedConfig(f"captcha.scene.{scene}.cooldown", "60", f"{label}场景重发冷却（秒）"),
        )
    )


PLATFORM_CONFIG_DEFAULTS: ConcurrentStableList[SeedConfig] = ConcurrentStableList(
    (
        *_captcha_scene_keys("login", required="false"),
        *_captcha_scene_keys("reset_password", required="true"),
        *_captcha_scene_keys("bind", required="true"),
        *_captcha_scene_keys("unbind", required="true"),
        *_captcha_scene_keys("register", required="true"),
        SeedConfig("captcha.channel.image", "true", "图形验证码渠道可用（兜底渠道，恒可用）"),
        SeedConfig("captcha.channel.slider", "true", "滑块验证码渠道可用"),
        SeedConfig("captcha.channel.sms", "false", "短信验证码渠道可用（未配通道默认关闭）"),
        SeedConfig("password.min_length", "8", "密码最小长度"),
        SeedConfig("password.max_length", "128", "密码最大长度"),
        SeedConfig("password.require_upper", "true", "密码须含大写字母"),
        SeedConfig("password.require_lower", "true", "密码须含小写字母"),
        SeedConfig("password.require_digit", "true", "密码须含数字"),
        SeedConfig("password.require_symbol", "true", "密码须含符号"),
        SeedConfig("password.forbid_username", "true", "密码不得包含用户名"),
        SeedConfig("password.max_age_days", "90", "密码有效期（天），pwd_changed_at 驱动强制改密"),
        SeedConfig("password.history_count", "5", "历史密码不可重复比对条数"),
        SeedConfig("account.inactive_lock_days", "180", "未登录自动锁定阈值（天）"),
        SeedConfig("session.max_active", "5", "单账号活跃会话数上限（超出后最旧会话失效）"),
        SeedConfig("file.upload.max_size", "20971520", "整包上传大小上限（字节，超限走分片上传）"),
        SeedConfig("file.upload.max_file_size", "2147483648", "单文件上传上限（字节，分片上传）"),
        SeedConfig(
            "file.upload.whitelist",
            DEFAULT_FILE_WHITELIST,
            "上传类型白名单（MIME:扩展名 逗号分隔；扩展名多个用 | 连接）",
        ),
        SeedConfig("file.download.presign_ttl", "3600", "预签名下载 / 预览地址有效期上限（秒）"),
        SeedConfig("menu.tree_cache_ttl", "300", "菜单树缓存 TTL（秒，含随机偏移）"),
        SeedConfig("role.code_pattern", "^[a-z][a-z0-9_-]{1,31}$", "角色码格式（正则）"),
        SeedConfig("ai.auto_execute", "false", "AI 自动执行写操作开关（默认关闭；阶段十九消费）"),
        SeedConfig("ai.auto_approve", "false", "AI 自动审批开关（默认关闭；依赖 ai.auto_execute 开启）"),
        SeedConfig("audit.archive.operation_log_days", "90", "操作日志归档保留天数"),
        SeedConfig("audit.archive.login_log_days", "90", "登录日志归档保留天数"),
        SeedConfig("audit.archive.data_audit_log_days", "90", "数据变更审计归档保留天数"),
        SeedConfig("audit.archive.open_log_days", "90", "开放接口审计归档保留天数"),
    )
)
"""平台默认参数项（验证码场景策略与渠道开关 + 密码 / 账号策略；后续模块键顺延追加）。"""


async def seed_configs(session: AsyncSession) -> int:
    """幂等写入平台默认参数（返回新增行数；未覆盖行按清单刷新，已覆盖行不动）。

    Args:
        session: 租户库会话（调用方负责引擎与租户）。

    Returns:
        int: 新增行数（刷新条数只记日志，不改变返回值语义）。
    """
    created = 0
    refreshed = 0
    for seed in PLATFORM_CONFIG_DEFAULTS:
        stmt = select(SysConfig).where(
            SysConfig.config_key == seed.config_key,
            SysConfig.deleted_at.is_(None),
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            session.add(SysConfig(config_key=seed.config_key, value=seed.value, remark=seed.remark))
            created += 1
            continue
        if row.is_overridden:
            continue
        if row.value != seed.value or row.remark != seed.remark:
            row.value = seed.value
            row.remark = seed.remark
            refreshed += 1
    await session.commit()
    if refreshed:
        _LOGGER.info("config_platform_default_refreshed", count=refreshed)
    return created

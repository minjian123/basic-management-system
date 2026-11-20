"""跨服务测试共用夹具：把测试登录态主体置为**内置系统管理员**。

`02_04` 启用真实权限校验器（`[permission].provider = "rbac"`）后，受保护接口要求请求主体
**持权限码**。平台侧既有用例（菜单元数据 / 角色域 / 用户扩展 CRUD）测的是业务语义而非授权链路，
故统一把测试主体（用户 `1001`）置为**内置系统管理员**（`role_type=system`）——命中校验器豁免层级，
使这些用例无需逐个补授权；**权限码级判定**由权限引擎专项用例覆盖。

提供两个**普通协程函数**（非夹具）：夹具名须由用例文件自己声明，避免跨模块别名与 lint 重名。
直插租户库（绕过服务层），范式同 `tests/api/test_role_api.py::_seed_user`。
"""

from __future__ import annotations

import os
import threading

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.config import get_settings
from bms_core.models.platform.role import ROLE_TYPE_SECURITY, ROLE_TYPE_SYSTEM, SysRole, SysUserRole
from bms_core.testing.gates import TENANT_GATE, gate_scope
from tests_support.auth import TEST_SUBJECT

SYSTEM_ADMIN_CODE = "bms_system_admin"
"""测试探针角色码（避开用例自建角色码 `system_admin`）。

豁免判定只看 `role_type`（`system` 即内置），与角色码无关——故探针用独立角色码即可，
且不干扰「自定义角色可复用 `system_admin` 码」这类用例断言。
"""

SYSTEM_ADMIN_NAME = "系统管理员"
"""内置系统管理员角色名称。"""

SECURITY_ADMIN_CODE = "bms_security_admin"
"""测试探针角色码（内置安全管理员，`03_02` 三权分立后角色域用例的操作人身份）。"""

SECURITY_ADMIN_NAME = "安全管理员"
"""内置安全管理员角色名称。"""


async def grant_system_admin(user_id: int) -> int:
    """给指定主体授予内置系统管理员角色（角色不存在则先建）。

    Args:
        user_id: 用户主键（测试登录态主体）。

    Returns:
        int: 内置系统管理员角色主键。
    """
    return await _grant_builtin(user_id, code=SYSTEM_ADMIN_CODE, name=SYSTEM_ADMIN_NAME, role_type=ROLE_TYPE_SYSTEM)


async def grant_security_admin(user_id: int) -> int:
    """给指定主体授予内置安全管理员角色（角色不存在则先建）。

    `03_02` 三权分立后，**角色域**写端点要求操作人为安全管理员（系统 / 审计管理员调用即
    `30048`）；角色域用例故改用本函数构造操作人身份。

    Args:
        user_id: 用户主键（测试登录态主体）。

    Returns:
        int: 内置安全管理员角色主键。
    """
    return await _grant_builtin(
        user_id, code=SECURITY_ADMIN_CODE, name=SECURITY_ADMIN_NAME, role_type=ROLE_TYPE_SECURITY
    )


async def _grant_builtin(user_id: int, *, code: str, name: str, role_type: str) -> int:
    """直插内置角色并把主体绑上（按 `code` 判存、按 `(role_id, user_id)` 判绑）。

    Args:
        user_id: 用户主键。
        code: 角色码。
        name: 角色名称。
        role_type: 角色类型（`system` / `security` / `audit`）。

    Returns:
        int: 角色主键。
    """
    engine = create_async_engine(os.environ["BMS_DATABASE__TENANTS__URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # 共享库上「查无 → 插入」必须串行：`(code, deleted_at)` 唯一约束在 NULL 上不生效，
        # 两个 worker 同时插入会各写一行同码角色，后续 `scalar_one_or_none` 直接炸。
        # 13_08 起用租户库写门（跨进程独占，取放 0.003ms、不留残锁）代替同名文件锁。
        async with gate_scope(TENANT_GATE, read_only=False), factory() as session:
            role = await _role_row(session, code=code, name=name, role_type=role_type)
            assigned = (
                (
                    await session.execute(
                        select(SysUserRole).where(
                            SysUserRole.role_id == role.id,
                            SysUserRole.user_id == user_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if assigned is None:
                session.add(SysUserRole(role_id=role.id, user_id=user_id))
            await session.commit()
            return role.id
    finally:
        await engine.dispose()


async def _role_row(session: AsyncSession, *, code: str, name: str, role_type: str) -> SysRole:
    """取内置角色行（不存在则建；并行建同码时以先落库者为准）。

    Args:
        session: 租户库会话。
        code: 角色码。
        name: 角色名称。
        role_type: 角色类型。

    Returns:
        SysRole: 角色行。
    """
    rows = (await session.execute(select(SysRole).where(SysRole.code == code).order_by(SysRole.id))).scalars().all()
    if rows:
        return rows[0]
    role = SysRole(code=code, name=name, status="enabled", role_type=role_type)
    session.add(role)
    await session.flush()
    return role


async def assign_system_admin() -> None:
    """把测试登录态主体置为内置系统管理员（供已建租户库的用例文件调用）。"""
    await grant_system_admin(int(TEST_SUBJECT))


async def assign_security_admin() -> None:
    """把测试登录态主体置为内置安全管理员（角色域用例的操作人身份，`03_02`）。"""
    await grant_security_admin(int(TEST_SUBJECT))


_GRANTED: ConcurrentStableSet[tuple[str, int, str]] = ConcurrentStableSet()
"""已授权标记（连接串 + 主体 + 角色码）：进程级，`setup_min_tenant` 每进程只写一次。"""

_GRANT_LOCK = threading.Lock()
"""占位互斥：并发首次调用只让一个协程去写（锁内不含 await）。"""


async def _grant_once(url: str, user_id: int, *, code: str) -> None:
    """按「连接串 + 主体 + 角色码」每进程只授权一次（幂等，重复执行无副作用）。

    为什么要缓存：`setup_min_tenant` 在多个用例文件的 `autouse` 夹具里调用，原先每个用例
    都取一次租户写门并提交——24 路并行下变成「每个用例都要抢一次跨进程写门」。授权结果是
    全局的（角色行 + 绑定行），进程内只需成功一次。

    Args:
        url: 租户库连接串。
        user_id: 用户主键。
        code: 内置角色码。
    """
    key = (url, user_id, code)
    with _GRANT_LOCK:
        if key in _GRANTED:
            return
        _GRANTED.add(key)
    try:
        name = SYSTEM_ADMIN_NAME if code == SYSTEM_ADMIN_CODE else SECURITY_ADMIN_NAME
        role_type = ROLE_TYPE_SYSTEM if code == SYSTEM_ADMIN_CODE else ROLE_TYPE_SECURITY
        await _grant_builtin(user_id, code=code, name=name, role_type=role_type)
    except BaseException:
        _GRANTED.discard(key)
        raise


async def assign_role_domain_operator() -> None:
    """把测试登录态主体同时置为「豁免层级 + 角色域操作人」（角色域用例专用装配）。

    角色域写端点 `03_02` 起要求操作人为安全管理员（系统 / 审计管理员调用即 `30048`）；
    而单元用例未播种菜单 / 按钮元数据，安全管理员角色拿不到任何权限码（`security` 不属豁免层级），
    逐码校验必然 `30001`。故测试主体**同时**持内置系统管理员（命中豁免层级，替代逐码授权）
    与内置安全管理员（满足角色域操作人判定）——这是测试装配口径，不代表业务上允许三权兼任；
    三权互斥的真实判定由 `tests/role/test_separation_guard.py` 与边界用例覆盖。
    """
    await assign_system_admin()
    await assign_security_admin()


async def setup_min_tenant(tenant_url: str | None = None) -> None:
    """把测试主体置为**内置系统管理员**（表结构由共享库初始化一次建好，本函数不碰结构）。

    单库化（`04-6-2`）：不再为每个用例建临时租户库——权限引擎与图标 / 菜单元数据都落
    `.cache/test/tenant.db`，全 worker 共用。

    **13_08 T7 修订（2026-11-20）**：原先每次调用都跑 `ensure_tables`（4 张表的存在性检查 +
    可能建表）。按「结构只能由数据初始化一次建好，测试与生产不得在运行时改结构」的口径，
    这里**不再建表**——四表已随共享租户库的准备集建好；缺失即用例失败（暴露准备集缺项，
    而不是静默补结构）。授权本身幂等，按「连接串 + 主体」每进程只做一次，避免每个用例
    都跨进程取写门。

    Args:
        tenant_url: 租户库连接串（None 取夹具已注入的 `BMS_DATABASE__TENANTS__URL`）。
    """
    url = tenant_url or os.environ["BMS_DATABASE__TENANTS__URL"]
    os.environ["BMS_DATABASE__TENANTS__URL"] = url
    get_settings.cache_clear()
    await _grant_once(url, int(TEST_SUBJECT), code=SYSTEM_ADMIN_CODE)
    get_settings.cache_clear()

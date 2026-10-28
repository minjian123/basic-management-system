"""平台侧跨产品能力名常量（07B `03_01`）：**契约级标识**，不是部署字面量。

为什么单独成模块：

- 消费方取用必须传能力名（`resolve_capability(<能力名>)`），而能力名带产品段；
- `04_01` 的「平台源码不得出现产品标识」把生产源码列为禁入位置，但**三段式能力名**
  （`{产品}.{业务域}.{能力}`）是跨仓契约标识——与提供方自持声明 `[[collaborations]].name` 同名同值，
  由装载期校验对账，不是服务地址 / 路径 / 凭据；
- 故平台侧能力名**只在本模块出现**（唯一落点，便于评审与 `04_01` 规则按形态识别），别处不得再写。

口径：

- 能力名与提供方清单逐字一致，改动须与提供方清单**同批**；
- 能力名第二段是提供方**业务域**（不是服务标识）；
- 降级策略不在此声明（归清单 `[[usages]]` 段，见 `deploy/registry/platform.toml`）。
"""

__all__ = [
    "CAPABILITY_MDM_ROLE_DEPTS",
    "CAPABILITY_MDM_ROLE_POSTS",
    "CAPABILITY_MDM_USER_DEPTS",
    "CAPABILITY_MDM_USER_POSTS",
    "CAPABILITY_MDM_USER_ROLES",
    "CAPABILITY_PLATFORM_CONFIG_SNAPSHOT",
    "CAPABILITY_PLATFORM_PERMISSION_INVALIDATE",
    "CAPABILITY_PLATFORM_PERMISSION_METADATA",
    "CAPABILITY_PLATFORM_PERMISSION_SUBJECT",
    "CAPABILITY_PLATFORM_USER_QUERY",
]

# ---- 平台自身作为提供方的能力（入站判定用；声明在 deploy/registry/platform.toml）----

CAPABILITY_PLATFORM_USER_QUERY = "platform.user.query"
"""用户只读出口（`kind=read`）：供组织域取用户明细，不跨库读 `sys_user`。"""

CAPABILITY_PLATFORM_PERMISSION_INVALIDATE = "platform.permission_meta.invalidate"
"""权限失效入口（`kind=write`）：组织变更后失效权限快照（写路径，失败即拒）。"""

CAPABILITY_PLATFORM_CONFIG_SNAPSHOT = "platform.platform_config.snapshot"
"""系统参数内部读（`kind=read`）：产品侧按能力授权，`identity` 仍走平台内部白名单。"""

CAPABILITY_PLATFORM_PERMISSION_SUBJECT = "platform.permission_meta.subject"
"""权限主体数据只读出口（`kind=read`）：按用户取聚合所需原始数据（`04_01` 下沉后 identity 经契约取数）。"""

CAPABILITY_PLATFORM_PERMISSION_METADATA = "platform.permission_meta.metadata"
"""权限元数据只读出口（`kind=read`）：菜单 → 表单、权限码 id → 权限码索引。"""

# ---- 平台作为消费方的能力（取用与降级声明见 platform.toml 的 `[[usages]]` 段）----

CAPABILITY_MDM_USER_ROLES = "mdm.org.user-roles"
"""mdm 组织域只读出口：按用户解析岗位 / 部门链角色（`kind=read`，消费方降级 `empty`）。"""

CAPABILITY_MDM_USER_POSTS = "mdm.org.user-posts.assign"
"""mdm 内部写通道 + 事务参与分支：用户-岗位全量覆盖（`kind=txn-branch`，写路径不降级）。"""

CAPABILITY_MDM_USER_DEPTS = "mdm.org.user-depts.assign"
"""mdm 内部写通道 + 事务参与分支：用户-部门全量覆盖（`kind=txn-branch`，写路径不降级）。"""

CAPABILITY_MDM_ROLE_POSTS = "mdm.org.role-posts.assign"
"""mdm 内部写通道 + 事务参与分支：角色-岗位全量覆盖（`kind=txn-branch`，写路径不降级）。"""

CAPABILITY_MDM_ROLE_DEPTS = "mdm.org.role-depts.assign"
"""mdm 内部写通道 + 事务参与分支：角色-部门全量覆盖（`kind=txn-branch`，写路径不降级）。"""

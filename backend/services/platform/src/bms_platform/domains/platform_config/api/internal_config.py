"""系统参数内部读取路由：`/api/v1/platform/internal/configs`（服务间调用，不经网关）。

- **鉴权**：模块级 `require_capability_or_service("platform.platform_config.snapshot", "identity", "file")`——
  **产品调用按能力分配判定**（07B `03_01` 收编），`identity` / `file` 均属平台自持服务的内部调用、
  按白名单放行（不参与能力分配）。两者均只接受服务 JWT（`aud=service`）；用户票据与网关服务票据
  （`sub=gateway`）一律拒。
- **租户**：由服务 JWT 的 `tenant` claim 经全局租户中间件解析租户库（未走租户豁免）。
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated

from fastapi import Depends

from bms_core.api.base import BaseRouter
from bms_core.api.capability import require_capability_or_service
from bms_core.api.deps import get_config_source
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.config import ConfigResolveRequest, ConfigResolveResponse
from bms_platform.capabilities import CAPABILITY_PLATFORM_CONFIG_SNAPSHOT

router = BaseRouter(
    key="config_internal",
    prefix="/platform/internal/configs",
    tags=["config-internal"],
    dependencies=[Depends(require_capability_or_service(CAPABILITY_PLATFORM_CONFIG_SNAPSHOT, "identity", "file"))],
)

ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]


@router.post("/resolve")
async def resolve_configs(config: ConfigDep, req: ConfigResolveRequest) -> ApiResponse[ConfigResolveResponse]:
    """批量取系统参数值（仅返回存在的键；缺失由调用方回落默认）。

    Args:
        config: 系统参数取数实现。
        req: 批量取参数请求。

    Returns:
        ApiResponse[ConfigResolveResponse]: 统一响应，data 为 `{values}`。
    """
    values = await config.get_many(req.keys)
    return ApiResponse.ok(ConfigResolveResponse(values=ConcurrentStableDict(values)))

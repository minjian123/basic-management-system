"""雪花 WorkerId 动态注册能力域端口（03_06 / 需求 03-7）。

设计口径：

- **端口**：`BaseWorkerIdRegistry`（插件键 `worker_id_registry`）暴露「取号 / 释放 / 当前生效号与来源」，
  实现名 `redis`（Redis 租约）与 `null`（应急旁路 / 测试关闭）。
- **键口径**：`{key_prefix}:{env}:{unit|service|default}:worker_id:v2:{id}`——环境 + 部署单元隔离，
  `key_prefix` 取 `[redis].key_prefix`；`0` 保留为「未注册」哨兵，注册池 `1 ~ 2^40-1`。
- **生效方式**：取号后经 `id_generator.reconfigure()` 落地（生成器实例身份不变）。
- **来源标注**：`registry`（租约分配）/ `config`（显式配置占号成功）/ `fallback`（降级用配置值）。
- **生产拒启**：`assert_ready()` —— 生产环境仍为 0（未取到号）即抛 `ConfigError`（40001）。
"""

from __future__ import annotations

import os
import socket
from abc import ABC, abstractmethod
from uuid import uuid4

from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.id_bits import MAX_WORKER_ID
from bms_core.core.logging import get_logger
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "SOURCE_CONFIG",
    "SOURCE_FALLBACK",
    "SOURCE_NONE",
    "SOURCE_REGISTRY",
    "WORKER_ID_PLUGIN_KEY",
    "WORKER_ID_POOL_MAX",
    "WORKER_ID_POOL_MIN",
    "BaseWorkerIdRegistry",
    "build_holder_token",
    "build_worker_id_key",
    "build_worker_id_prefix",
    "worker_id_unit",
]

WORKER_ID_PLUGIN_KEY = "worker_id_registry"
"""插件键（`PLUGIN_WIRINGS` / 配置分区 `[worker_id]`）。"""

WORKER_ID_POOL_MIN = 1
"""注册池下限（`0` 保留为「未注册 / 单进程开发 / 兜底」哨兵，不参与分配）。"""

WORKER_ID_POOL_MAX = MAX_WORKER_ID
"""注册池上限（`2^40-1`，与雪花 40 位机器段一致）。"""

SOURCE_REGISTRY = "registry"
"""来源：Redis 租约分配。"""

SOURCE_CONFIG = "config"
"""来源：显式配置 `[app].worker_id` 占号成功（或注册关闭直接采用）。"""

SOURCE_FALLBACK = "fallback"
"""来源：降级回落 `[app].worker_id`（Redis 不可用 / 探测用尽）。"""

SOURCE_NONE = ""
"""来源：尚未取号。"""

_LOGGER = get_logger("bms")


def worker_id_unit(settings: Settings) -> str:
    """注册命名空间段（部署单元；空则回落服务标识，再空回落 `default`）。

    Args:
        settings: 应用配置。

    Returns:
        str: 单元段取值。
    """
    return settings.app.unit or settings.app.service or "default"


def build_worker_id_prefix(settings: Settings) -> str:
    """构建注册键前缀（未含号）。

    Args:
        settings: 应用配置（`[redis].key_prefix` / `[app].env` / `[app].unit|service`）。

    Returns:
        str: 形如 `bms:dev:platform:worker_id:v2:`。
    """
    return f"{settings.redis.key_prefix}:{settings.app.env}:{worker_id_unit(settings)}:worker_id:v2:"


def build_worker_id_key(settings: Settings, worker_id: int) -> str:
    """构建某号的注册键。

    Args:
        settings: 应用配置。
        worker_id: 号值。

    Returns:
        str: 完整注册键。
    """
    return f"{build_worker_id_prefix(settings)}{worker_id}"


def build_holder_token(settings: Settings) -> str:
    """构建持有者令牌（写入键值；释放时比对，防迟到释放误删他人租约）。

    Args:
        settings: 应用配置（取服务标识）。

    Returns:
        str: `{service}|{hostname}|{pid}|{uuid}`。
    """
    return f"{settings.app.service or '-'}|{socket.gethostname()}|{os.getpid()}|{uuid4().hex}"


class BaseWorkerIdRegistry(BasePluggable, ABC):
    """WorkerId 注册契约：取号 / 释放 / 当前生效号与来源。"""

    key: str = WORKER_ID_PLUGIN_KEY
    plugin_key: str = WORKER_ID_PLUGIN_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, settings: Settings) -> None:
        """初始化（未取号状态）。

        Args:
            settings: 应用配置（`[app]` / `[worker_id]` / `[redis]`）。
        """
        self._settings = settings
        self._worker_id = 0
        self._source = SOURCE_NONE
        self._key_name: str | None = None

    @property
    def worker_id(self) -> int:
        """当前生效号（未取号为 0）。

        Returns:
            int: WorkerId。
        """
        return self._worker_id

    @property
    def source(self) -> str:
        """当前来源（`registry` / `config` / `fallback`；未取号为空串）。

        Returns:
            str: 来源标注。
        """
        return self._source

    @property
    def key_name(self) -> str | None:
        """当前持有键（未持有租约为 None）。

        Returns:
            str | None: 注册键名。
        """
        return self._key_name

    @abstractmethod
    def acquire(self) -> None:
        """取号并使其生效（幂等：已取号直接返回；失败按降级口径回落配置值）。"""

    @abstractmethod
    def release(self) -> None:
        """释放持有的租约（幂等；不持有则无副作用）。"""

    async def setup(self) -> None:
        """插件生命周期入口（等价 `acquire()`）。"""
        self.acquire()

    async def aclose(self) -> None:
        """应用关闭入口（等价 `release()`）。"""
        self.release()

    def assert_ready(self) -> None:
        """生产就绪校验：生产环境仍未取到号（0）即拒启。

        Raises:
            ConfigError: 生产环境 WorkerId 未被分配。
        """
        if self._settings.app.env == "prod" and self._worker_id == 0:
            raise ConfigError(
                "生产环境未能分配 WorkerId（Redis 租约注册失败且 [app].worker_id 为 0）："
                "请修复 Redis 或显式配置 BMS_APP__WORKER_ID，否则多进程雪花 ID 会撞号"
            )

    def _apply(self, worker_id: int, source: str, key_name: str | None) -> None:
        """落地生效号（重设进程级生成器）。

        Args:
            worker_id: 号值。
            source: 来源标注。
            key_name: 持有键（未持有租约时为 None）。
        """
        from bms_core.core.id import id_generator

        id_generator.reconfigure(worker_id)
        self._worker_id = worker_id
        self._source = source
        self._key_name = key_name

    def _log_acquired(self) -> None:
        """记录取号成功事件（`worker_id_acquired`）。"""
        _LOGGER.info(
            "worker_id_acquired",
            worker_id=self._worker_id,
            source=self._source,
            key=self._key_name,
            ttl=self._settings.worker_id.lease_ttl_seconds if self._key_name else 0,
        )

"""作业 worker 进程的插件装配辅助：只登记执行侧需要的能力实现。

worker 进程不构造 FastAPI 应用，无法走 `register_platform_plugins`；本模块按需登记
对象存储 / 分片上传工厂并冻结注册表（已由服务应用装配时重复调用无副作用）。
"""

from __future__ import annotations

from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import build_plugin_registry, register_plugin

__all__ = ["ensure_job_plugins"]


def ensure_job_plugins(settings: Settings | None = None) -> None:
    """登记作业执行侧所需插件并构建注册表（幂等）。

    Args:
        settings: 应用配置；None 取全局单例。
    """
    resolved = settings if settings is not None else get_settings()
    from bms_core.core.assembly import (
        LocalMultipartUploadFactory,
        LocalObjectStorageFactory,
        MinioMultipartUploadFactory,
        MinioObjectStorageFactory,
    )

    registrations = (
        ("object_storage", "local", LocalObjectStorageFactory(resolved)),
        ("object_storage", "minio", MinioObjectStorageFactory(resolved)),
        ("multipart_upload", "local", LocalMultipartUploadFactory(resolved)),
        ("multipart_upload", "minio", MinioMultipartUploadFactory(resolved)),
    )
    for plugin_key, name, factory in registrations:
        try:
            register_plugin(plugin_key, name, factory)
        except PluginError:  # 服务应用已装配：注册表已冻结，直接复用
            break
    build_plugin_registry()

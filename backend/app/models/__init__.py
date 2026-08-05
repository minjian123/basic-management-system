"""SQLAlchemy 模型注册：re-export 全部模型，保证 Base.metadata 完整（Alembic 与建表依赖）。"""

from .probe import PlatformProbe, TenantProbe

__all__ = ["PlatformProbe", "TenantProbe"]

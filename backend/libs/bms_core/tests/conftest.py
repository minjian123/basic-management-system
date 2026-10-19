"""基座库 pytest 公共夹具：仅保留仓库专属部分。

配置隔离 / 平台库隔离 / 请求上下文复位 / 插件注册表复位由测试公共基座
`bms_core.testing.fixtures` 经 `-p bms_core.testing.plugin` 全局提供（13_04）；
本文件只保留依赖 `ops` 与 `tests_support` 的仓库专属接线：

- `isolate_settings`：在公共隔离之上追加测试令牌密钥与 fakeredis；
- `platform_db_url`：会话级平台库（用 `ops.seed_tenant` 播种租户）。

本套件只覆盖 `bms_core`（不依赖平台服务应用），故不提供 `client` 夹具。
"""

import asyncio
from collections.abc import Iterator

import pytest

from bms_core.core.config import get_settings
from bms_core.testing.fixtures import (
    isolate_settings as bms_isolate_settings,
)
from bms_core.testing.fixtures import (
    platform_db,
    reset_plugin_registry,
    reset_request_context,
)

__all__ = ("bms_isolate_settings", "platform_db", "reset_plugin_registry", "reset_request_context")
from ops.seed_tenant import seed_tenants
from tests_support.auth import configure_token_env


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_request_context: None, reset_plugin_registry: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 请求上下文 / 插件注册表复位）。

    夹具实现单源在 `bms_core.testing.fixtures`；本包装只负责在本套件启用
    （交易服务单测不依赖平台库，故不启用）。
    """


@pytest.fixture(autouse=True)
def isolate_settings(bms_isolate_settings: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """仓库专属隔离：公共隔离之后追加令牌密钥与 fakeredis。

    Args:
        bms_isolate_settings: 公共隔离夹具（保证顺序）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    from tests_support.redis import install_process_fake_redis_client

    install_process_fake_redis_client()
    configure_token_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def platform_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """会话级平台库：临时 `sys_tenant` 种子库（建库 / 播种整个测试会话只做一次）。

    Args:
        tmp_path_factory: pytest 临时目录工厂。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    asyncio.run(seed_tenants(platform_url))
    return platform_url

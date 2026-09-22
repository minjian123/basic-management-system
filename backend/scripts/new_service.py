#!/usr/bin/env python3
"""服务脚手架：按工作区统一骨架生成一个新的服务工程（`backend/services/<服务名>/`）。

用法::

    cd backend
    python scripts/new_service.py <服务名> [--title "服务中文名"]

生成内容（与平台服务同构）：独立 `pyproject.toml`（依赖 `bms-core`，src 布局）、`src/bms_<名>/`
（入口 `main.py` / `asgi.py` + api / services / repositories / models / schemas 五层 + 最小路由聚合）、
`tests/`（启动冒烟用例）。生成后 `uv sync` 即可 `uv run pytest` / `uv run uvicorn bms_<名>.asgi:app`。
"""

import argparse
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SERVICES = _BACKEND / "services"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED = {"platform"}

_PYPROJECT = """[project]
name = "bms-{name}"
version = "0.1.0"
description = "BMS {title}服务"
requires-python = ">=3.14"
dependencies = [
    "bms-core",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/bms_{name}"]

[tool.uv.sources]
bms-core = {{ workspace = true }}
"""

_INIT = '''"""{title}服务包。"""

__version__ = "0.1.0"
'''

_MAIN = '''"""{title}服务入口：应用工厂 `ApplicationFactory`（脚手架生成，按需扩展）。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bms_core.api.errors import register_exception_handlers
from bms_core.api.health import router as health_router
from bms_core.core.config import get_settings
from bms_core.core.factory import BaseApplicationFactory
from bms_core.core.logging import configure_logging
from bms_core.core.resources import ResourceManager
from bms_{name} import __version__
from bms_{name}.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """应用生命周期：登记与释放异步资源（按需补装配）。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。
    """
    app.state.resources = ResourceManager()
    app.state.startup_complete = True
    try:
        yield
    finally:
        app.state.startup_complete = False
        await app.state.resources.aclose()


class ApplicationFactory(BaseApplicationFactory):
    """应用工厂：构造 {title}服务 FastAPI 应用。"""

    key: str = "application_factory"

    def create(self, options: None = None) -> FastAPI:
        """创建 FastAPI 应用。

        Args:
            options: 未使用（零参口径）。

        Returns:
            FastAPI: 已注册基线配置与端点的应用实例。
        """
        settings = get_settings()
        configure_logging(settings)
        app = FastAPI(title="BMS {title}服务", version=__version__, lifespan=lifespan)
        register_exception_handlers(app)
        app.state.settings = settings
        app.include_router(api_router)
        app.include_router(health_router)
        return app
'''

_ASGI = '''"""ASGI 入口：模块级应用实例（`uvicorn bms_{name}.asgi:app`）。"""

from bms_{name}.main import ApplicationFactory

app = ApplicationFactory().create(None)
'''

_API_INIT = '''"""{title}服务 api 层：业务路由与参数校验，只做参数校验与路由分发。

依赖：接口层基座（路由基类 / 异常处理 / 中间件 / 探针）来自 `bms_core.api`。
禁止：直接操作模型、写业务逻辑；业务规则一律经 services 层。
"""
'''

_API_ROUTER = '''"""{title}服务路由聚合：模块路由登记后统一挂载到 `/api/v1`。"""

from bms_core.api.base import build_api_router

api_router = build_api_router()
'''

_LAYER_INIT = {
    "services": '''"""{title}服务 services 层：业务逻辑与事务边界（{{模块}}_service.py）。

继承约定：XxxService 必须继承 `bms_core.services.BaseService[T]`。
"""
''',
    "repositories": '''"""{title}服务 repositories 层：数据访问与数据源 / 分片路由（{{模块}}_repository.py）。

继承约定：XxxRepository 必须继承 `bms_core.repositories.BaseRepository[T]`。
"""
''',
    "models": '''"""{title}服务 models 层：SQLAlchemy ORM 模型。

继承约定：ORM 模型必须继承 `bms_core.models.BaseModel`。
"""
''',
    "schemas": '''"""{title}服务 schemas 层：Pydantic 请求 / 响应模型。

继承约定：请求 / 响应模型必须继承 `bms_core.schemas.BaseSchema`。
"""
''',
}

_TEST = '''"""{title}服务启动冒烟（脚手架生成）。"""

from bms_{name}.main import ApplicationFactory


def test_service_boots() -> None:
    """应用可构造且标题 / 版本就位。"""
    app = ApplicationFactory().create(None)
    assert "BMS" in app.title
'''


def generate(name: str, title: str, *, base: Path = _SERVICES) -> Path:
    """生成服务工程骨架。

    Args:
        name: 服务名（snake_case）。
        title: 服务中文名（用于标题与文档字符串）。
        base: 服务根目录（默认 `backend/services`）。

    Returns:
        Path: 生成的服务工程目录。

    Raises:
        ValueError: 服务名非法或已存在。
    """
    if not _NAME_RE.match(name):
        raise ValueError(f"服务名非法：{name}（要求 snake_case：^[a-z][a-z0-9_]*$）")
    if name in _RESERVED:
        raise ValueError(f"服务名保留：{name}")
    project = base / name
    if project.exists():
        raise ValueError(f"服务工程已存在：{project}")
    package = project / "src" / f"bms_{name}"
    (package / "api").mkdir(parents=True)
    for layer in _LAYER_INIT:
        (package / layer).mkdir()
    tests = project / "tests"
    tests.mkdir()

    (project / "pyproject.toml").write_text(_PYPROJECT.format(name=name, title=title), encoding="utf-8")
    (package / "__init__.py").write_text(_INIT.format(title=title), encoding="utf-8")
    (package / "main.py").write_text(_MAIN.format(name=name, title=title), encoding="utf-8")
    (package / "asgi.py").write_text(_ASGI.format(name=name), encoding="utf-8")
    (package / "api" / "__init__.py").write_text(_API_INIT.format(title=title), encoding="utf-8")
    (package / "api" / "router.py").write_text(_API_ROUTER.format(title=title), encoding="utf-8")
    for layer, template in _LAYER_INIT.items():
        (package / layer / "__init__.py").write_text(template.format(title=title), encoding="utf-8")
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_service_boot.py").write_text(_TEST.format(name=name, title=title), encoding="utf-8")
    return project


def main() -> int:
    """入口：解析参数并生成工程。

    Returns:
        int: 退出码（0 成功 / 1 失败）。
    """
    parser = argparse.ArgumentParser(description="生成 BMS 服务工程骨架")
    parser.add_argument("name", help="服务名（snake_case，如 payment）")
    parser.add_argument("--title", default=None, help="服务中文名（默认取服务名）")
    args = parser.parse_args()
    title = args.title or args.name
    try:
        project = generate(args.name, title)
    except ValueError as exc:
        print(f"[new-service] 失败：{exc}")
        return 1
    print(f"[new-service] 已生成：{project}")
    print(f"下一步：cd backend && uv sync && uv run pytest services/{args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

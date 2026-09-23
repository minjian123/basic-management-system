#!/usr/bin/env python3
"""服务脚手架：按工作区统一骨架生成一个新的服务工程（`backend/services/<服务名>/`）。

用法::

    cd backend
    python scripts/new_service.py <服务名> [--title "服务中文名"]

生成内容（与平台服务同构）：独立 `pyproject.toml`（依赖 `bms-core`，src 布局）、`src/bms_<名>/`
（入口 `main.py` / `asgi.py` / `__main__.py` + api / services / repositories / models / schemas 五层 +
最小路由聚合 + 统一服务运行时接入）、`tests/`（启动冒烟用例）。生成后 `uv sync` 即可
`uv run pytest` / `uv run python -m bms_<名>`（读 `[server]` 配置）或 `uv run uvicorn bms_<名>.asgi:app`。
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

[tool.pytest.ini_options]
# 工程级测试范围：从本工程目录 `uv run pytest` 只跑本工程 tests（不落工作区根全量）
asyncio_mode = "auto"
addopts = "--import-mode=importlib"
testpaths = ["tests"]
pythonpath = ["../.."]
markers = [
    "kiwi_id: Kiwi TCMS 用例编号（如 @pytest.mark.kiwi_id(1)）",
    "integration: 需要真实外部服务的集成用例（未配置环境时跳过）",
]
"""

_INIT = '''"""{title}服务包。"""

__version__ = "0.1.0"

SERVICE_NAME = "{name}"
"""服务名（`[app].service` 为空时取本声明；用于日志 `service`、探针响应与按服务配置）。"""

SERVICE_TITLE = "BMS {title}服务"
"""服务中文名（用于应用 title）。"""
'''

_MAIN = '''"""{title}服务入口：应用工厂 `ApplicationFactory`（共享基座 + 服务身份 / 路由）。"""

from collections.abc import Sequence

from fastapi import APIRouter

from bms_core.application import BaseServiceApplicationFactory
from bms_core.core.config import Settings
from bms_{name} import SERVICE_NAME, SERVICE_TITLE, __version__
from bms_{name}.api.router import api_router


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：{title}服务（通用装配由共享基座承载）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__

    def prepare_settings(self, settings: Settings) -> None:
        """最小服务暂无依赖检查：就绪探针回退 null 注册表（空检查项、恒定通过）。

        Args:
            settings: 应用配置（可变）。
        """
        settings.health_check_registry.provider = ""

    def service_routers(self) -> Sequence[APIRouter]:
        """业务路由（探针路由由基座统一挂载）。

        Returns:
            Sequence[APIRouter]: 业务聚合路由。
        """
        return (api_router,)
'''

_MAIN_ENTRY = '''"""服务启动入口：`python -m bms_{name}`（读 `[server]` 配置，SIGTERM 先摘流再优雅收尾）。"""

from bms_core.core.run import run_service
from bms_{name}.main import ApplicationFactory

if __name__ == "__main__":
    run_service(ApplicationFactory)
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

_API_ROUTER = '''"""{title}服务路由聚合：模块路由经服务级登记表统一挂到 `/api/v1`。

新增路由：建 `api/<模块>.py`（继承 `bms_core.api.base.BaseRouter`）后并入 `mount_service_routers`。
探针路由由共享应用基座统一挂载，不在此处登记。
"""

from bms_core.api.base import mount_service_routers

api_router = mount_service_routers(())
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
迁移链按服务解析模型：本服务模型模块须列入本清单（见 `bms_core/db/migration.py` 的 `MODEL_MODULES`）。
"""

MODEL_MODULES: tuple[str, ...] = ()
"""本服务模型模块清单（迁移链按服务解析模型用；无模型时为空元组）。"""
''',
    "schemas": '''"""{title}服务 schemas 层：Pydantic 请求 / 响应模型。

继承约定：请求 / 响应模型必须继承 `bms_core.schemas.BaseSchema`。
"""
''',
}

_TEST = '''"""{title}服务启动冒烟（脚手架生成）。"""

from httpx import ASGITransport, AsyncClient

from bms_{name} import SERVICE_NAME
from bms_{name}.main import ApplicationFactory


async def test_service_boots_and_exposes_probes() -> None:
    """应用可构造；`/healthz` 返回存活状态与服务身份；`/readyz` 就绪（最小服务无依赖检查）。"""
    app = ApplicationFactory().create(None)
    assert "BMS" in app.title
    assert "{title}" in app.title
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        healthz = await client.get("/healthz")
        readyz = await client.get("/readyz")
    assert healthz.status_code == 200
    assert healthz.json()["service"] == SERVICE_NAME
    assert readyz.status_code == 200
    assert readyz.json()["checks"] == {{}}
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
    (package / "__init__.py").write_text(_INIT.format(title=title, name=name), encoding="utf-8")
    (package / "main.py").write_text(_MAIN.format(name=name, title=title), encoding="utf-8")
    (package / "__main__.py").write_text(_MAIN_ENTRY.format(name=name), encoding="utf-8")
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

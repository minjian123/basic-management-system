"""装配常驻下的应用状态还原：依赖覆盖与配置快照，每例回到装配态。

背景（13_11 / 13_10 装配常驻）：全系统装配在会话级只做一次，`app` 实例跨用例复用。用例为构造
替身而替换依赖提供者、或就地改 `app.state.settings.<段>.<字段>` 时，若不在用例结束还原，后继用例
会读到上一条用例留下的状态——表现为「单文件跑绿、整目录跑红」「换个文件顺序结论就不同」。

口径：**用例仍可用替换构造替身，但必须在用例结束回到装配态**。两处还原只在这里实现，各服务
conftest 挂一条 autouse 夹具即可，不再各写一套清理。

用法（服务 conftest）::

    @pytest.fixture(autouse=True)
    def _restore_assembled_app(service_app: FastAPI) -> Generator[None]:
        with restore_assembled_app(service_app):
            yield
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from fastapi import FastAPI
from pydantic import BaseModel

from bms_core.core.concurrent import ConcurrentStableDict

__all__ = ["restore_assembled_app", "restore_dependency_overrides", "restore_settings"]


@contextmanager
def restore_dependency_overrides(app: FastAPI) -> Generator[None]:
    """保存并在退出时恢复应用的依赖覆盖表。

    Args:
        app: 全系统装配的应用实例。

    Yields:
        None: 用例运行期。
    """
    saved: ConcurrentStableDict[Any, Any] = ConcurrentStableDict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


@contextmanager
def restore_settings(settings: object) -> Generator[None]:
    """保存并在退出时恢复配置对象的各段字段（就地还原，保持对象身份不变）。

    只快照 `Settings` 顶层的各配置段（`login` / `session` / `sso` 等），退出时按字段写回；
    不替换 `app.state.settings` 本身——装配期固化的组件持有的是同一个对象。

    Args:
        settings: 应用装配期固化的配置对象（`app.state.settings`）。

    Yields:
        None: 用例运行期。
    """
    model = cast("type[BaseModel]", type(settings))
    snapshots: ConcurrentStableDict[str, BaseModel] = ConcurrentStableDict()
    for name in model.model_fields:
        snapshots.set(name, cast("BaseModel", getattr(settings, name)).model_copy(deep=True))
    try:
        yield
    finally:
        for name in tuple(snapshots):
            live = getattr(settings, name)
            snapshot = cast("BaseModel", snapshots.get(name))
            for field in type(snapshot).model_fields:
                setattr(live, field, getattr(snapshot, field))


@contextmanager
def restore_assembled_app(app: FastAPI) -> Generator[None]:
    """同时还原依赖覆盖与配置快照（服务 conftest 的唯一入口）。

    Args:
        app: 全系统装配的应用实例。

    Yields:
        None: 用例运行期。
    """
    state = cast("Any", app.state)
    settings = getattr(state, "settings", None)
    with restore_dependency_overrides(app):
        if settings is None:  # pragma: no cover - 装配态必有；防御未装配的极早期用例
            yield
            return
        with restore_settings(settings):
            yield

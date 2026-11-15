"""测试基座插件（13_04）：夹具注册与并行 SQLite 隔离的公共实现。

加载方式有两种，按仓库形态选择：

- **bms 仓**：`addopts = "-p bms_testing_plugin"`（`backend/bms_testing_plugin.py`）——该启动插件
  在**最早**阶段启动覆盖率采集，再在 `pytest_configure` 里注册本模块；这样被测模块的「导入期执行行」
  也能被采集（13_02）。
- **产品仓**：可直接 `-p bms_core.testing.plugin`（本模块）复用夹具；覆盖率采集时机由产品仓自管。

为什么不用各 conftest 写 `pytest_plugins`：pytest 7+ 禁止**非顶层 conftest** 声明
`pytest_plugins`，而本项目有 10 个测试根（每个工程一个 conftest），故统一由 `-p` 加载。

注意：`pytest_plugins` 在「由 `-p` 加载的插件模块」中**不会**再被处理（该机制只对 conftest 生效），
故这里的夹具必须显式导入到本模块命名空间，pytest 才会收集注册。
"""

import os
from collections.abc import Generator
from contextlib import ExitStack

import pytest

from bms_core.testing import ddl, fixtures, write_locks
from bms_core.testing.fixtures import (
    clear_shared_db_files,
    clear_tenant_cache,
    configure_project_root,
    ensure_shared_db,
    isolate_settings,
    ns,
    platform_db,
    project_root,
    reset_plugin_registry,
    reset_request_context,
    resolve_prepare,
    shared_db_url,
    shared_platform_db_url,
    shared_platform_engine,
    shared_tenant_db_url,
    shared_tenant_engine,
    test_db_dir,
)
from bms_core.testing.write_locks import (
    platform_db_write,
    platform_db_write_whole,
    serial_db_write,
    tenant_db_write,
    tenant_db_write_whole,
)

__all__ = (
    "clear_shared_db_files",
    "clear_tenant_cache",
    "configure_project_root",
    "ensure_shared_db",
    "isolate_settings",
    "ns",
    "platform_db",
    "platform_db_write",
    "platform_db_write_whole",
    "project_root",
    "reset_plugin_registry",
    "reset_request_context",
    "resolve_prepare",
    "serial_db_write",
    "shared_db_url",
    "shared_platform_db_url",
    "shared_platform_engine",
    "shared_tenant_db_url",
    "shared_tenant_engine",
    "tenant_db_write",
    "tenant_db_write_whole",
    "test_db_dir",
)


def pytest_configure(config: pytest.Config) -> None:
    """把 pytest basetemp 交给测试基座（并行执行按 worker 派生独立 SQLite 目录；13_02）。

    xdist worker 的 basetemp 形如 `<根>/popen-gwN`，天然按 worker 隔离；交由
    `fixtures.worker_sqlite_dir` 派生 `<basetemp>/sqlite-gwN` 作为该 worker 的 `sqlite_dir`。

    同时补齐 `--basetemp` 的父目录：`addopts` 里的 `--basetemp=.cache/pytest` 指向仓内
    缓存目录，而 pytest 的 `TmpPathFactory.getbasetemp()` 只 `mkdir` 末级目录、**不递归建父目录**
    （`tmpdir.py` 中 `basetemp.mkdir(mode=0o700)`），父目录 `.cache` 不存在时 xdist 起 worker
    即 `FileNotFoundError` 崩掉。此处在本钩子里 `makedirs(exist_ok=True)`——本钩子早于
    `pytest_sessionstart`（xdist 在后者里才取 basetemp），故能保证父目录就位。

    Args:
        config: pytest 配置对象。
    """
    # 覆盖率入口守卫最先执行：`pytest --cov` / 换覆盖率落点在本钩子里直接终止（code=2）。
    # 本钩子被**所有**子工程 addopts（`-p bms_core.testing.plugin`）与工程根插件转调，是唯一全覆盖入口。
    from bms_core.testing.coverage_guard import assert_entrypoint

    assert_entrypoint(config)
    # 共享测试库基址钉在会话起始的工程根：用例 `chdir` 后解析夹具也不会把库落到临时目录
    # （否则表现为随机的「no such table」；见 `fixtures.configure_project_root`）。
    fixtures.configure_project_root(os.getcwd())
    # 单库叠加：DDL 串行化。并发 worker 同时首次建同一张表时，`create_all(checkfirst=True)` 的存在性
    # 判断看不到他人未提交的建表事务，后提交方撞 `table ... already exists`（服务子流水线实测）。
    ddl.serialize_ddl()
    basetemp = getattr(config.option, "basetemp", "") or ""
    if basetemp:
        # `abspath` 结果必然含父目录，无需再判空
        os.makedirs(os.path.dirname(os.path.abspath(os.fspath(basetemp))), exist_ok=True)
    notice = fixtures.isolation_notice()
    if notice:
        print(notice)
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        # 会话开始清空共享测试库（controller 先于 xdist worker 启动，不与 worker 建库竞争）
        failed = fixtures.clear_shared_db_files()
        stuck_locks = [name for name in failed if name.endswith(".lock")]
        if stuck_locks:
            # 残留锁会让后续每个等待方等满整段上限后才超时（bms#1659 续修实测：8 worker × 300s），
            # 带锁开跑只会把「一行启动错误」拖成「一堆假超时」，必须立即阻断。
            raise RuntimeError(
                f"[bms_testing_plugin] 残留测试锁清理失败：{stuck_locks}；"
                f"请结束占用进程或手工删除 {fixtures.test_db_dir()} 下的同名 .lock 后重跑"
            )
        if failed:
            print(f"[bms_testing_plugin] 共享测试库清理失败（Windows 句柄占用），本次改用新库：{failed}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    """在**用例调用阶段**持有该用例声明的写锁（准备 / 清理阶段不持锁）。

    为什么放在钩子里而不是夹具里：夹具的生命周期横跨「准备 → 调用 → 清理」，把几个秒级的
    夹具准备（建表 / 造种子 / 装配应用）也算进临界区，等于让整轮并行退化为串行（2026-11-15
    实测：持锁 97.9s 中约 88.7s 是夹具准备）。声明来自 `platform_db_write` / `tenant_db_write`
    两个夹具，本钩子只负责按声明取锁与放锁。

    Args:
        item: 用例节点。
    """
    names = write_locks.declared_locks(item)
    if not names:
        yield
        return
    with ExitStack() as stack:
        for name in names:
            stack.enter_context(write_locks.file_lock(name))
        yield

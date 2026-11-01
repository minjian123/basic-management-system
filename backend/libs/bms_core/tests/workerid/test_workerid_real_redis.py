"""WorkerId 租约 · 真 Redis 双实例用例（integration 标记；需 `BMS_TEST_REDIS_URL`，未配置即跳过）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from redis import Redis

from bms_core.core.concurrent import ConcurrentStableList

pytestmark = pytest.mark.integration

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_UNIT = "workerid-it"

_SCRIPT = """
import json
import sys
import time

from bms_core.core.config import Settings
from bms_core.workerid.redis import RedisWorkerIdRegistry

registry = RedisWorkerIdRegistry(Settings())
registry.acquire()
print(json.dumps({"id": registry.worker_id, "source": registry.source, "key": registry.key_name or ""}))
sys.stdout.flush()
time.sleep(0.8)          # 两进程同时在租（证明并发占用不撞号）
registry.release()
"""


# 子进程环境变量（普通 dict 直接交给 subprocess）
# bare-collections:allow
def _env(url: str) -> dict[str, str]:
    """构造子进程环境（真 Redis + 独立命名空间 + 短 TTL）。

    Args:
        url: 真实 Redis 连接串。

    Returns:
        dict[str, str]: 环境变量。
    """
    env = dict(os.environ)
    env.update(
        {
            "BMS_ENV": "test",
            "BMS_REDIS__URL": url,
            "BMS_REDIS__PROVIDER": "redis",
            "BMS_APP__WORKER_ID": "0",
            "BMS_APP__SERVICE": "platform",
            "BMS_APP__UNIT": _UNIT,
            "BMS_WORKER_ID__ENABLED": "true",
            "BMS_WORKER_ID__PROVIDER": "redis",
            "BMS_WORKER_ID__LEASE_TTL_SECONDS": "10",
            "BMS_WORKER_ID__HEARTBEAT_SECONDS": "5",
        }
    )
    return env


@pytest.mark.kiwi_id(2398)
def test_two_processes_acquire_distinct_worker_ids() -> None:
    """真 Redis：两个独立进程同时取号，号不同；退出后租约释放（键清空）。"""
    url = os.environ.get("BMS_TEST_REDIS_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_REDIS_URL，跳过真实 Redis 集成用例")

    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _SCRIPT],
            cwd=str(_BACKEND_ROOT),
            env=_env(url),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        outputs: ConcurrentStableList[str] = ConcurrentStableList()
        for proc in procs:
            out, err = proc.communicate(timeout=90)
            assert proc.returncode == 0, err
            outputs.append(out.strip().splitlines()[-1])
    finally:
        for proc in procs:
            if proc.poll() is None:  # pragma: no cover - 仅在超时/异常时兜底
                proc.kill()

    records = [cast("dict[str, Any]", json.loads(line)) for line in outputs]
    ids = [cast("int", item["id"]) for item in records]
    assert all(worker_id > 0 for worker_id in ids)
    assert len(set(ids)) == 2, records
    assert all(item["source"] == "registry" for item in records)

    client: Redis = Redis.from_url(url, decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
    try:
        assert list(client.scan_iter(match=f"*:{_UNIT}:worker_id:v2:*")) == []  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    finally:
        client.close()

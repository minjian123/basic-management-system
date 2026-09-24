#!/usr/bin/env python3
"""服务部署 / 回滚 / 健康门禁 / 数据引导 CLI（阶段二 09_02 不可变镜像与回滚）。

在部署服务器（mjbk）仓库检出根执行；以 `docker compose` 驱动 `deploy/compose/bms.yml`，
只依赖 Python 标准库（无需后端虚拟环境），凭据只读 `deploy/.env`（不改写、不打印）。

用法::

    python3 scripts/tools/deploy/release.py bootstrap [--env-file deploy/.env]
    python3 scripts/tools/deploy/release.py deploy --service platform --tag v0.2.0
    python3 scripts/tools/deploy/release.py deploy --all --tag <sha 或 vX.Y.Z>
    python3 scripts/tools/deploy/release.py rollback --service platform [--to <tag>]
    python3 scripts/tools/deploy/release.py status [--service platform]
    python3 scripts/tools/deploy/release.py health-gate --service platform
    python3 scripts/tools/deploy/release.py prune --keep 30

口径（详见 `bms文档/项目/02_后端基座与服务化地基/任务/09_多服务CI-CD与契约门禁/09_…_02_…/设计/`）：

- **不可变标签**：commit short SHA 主标签 + Git tag `vX.Y.Z` 追加语义化标签；禁 `latest`；版本台账
  `deploy/releases/<service>.json`（当前 / 上一版本）+ `deploy/releases/release-log.jsonl`（运行时状态，不入库）。
- **迁移先行**：`deploy` 先以目标镜像跑一次性迁移容器（`ops.migrate_tenants`，幂等），再起容器。
- **健康门禁**：容器 `healthy`（`/healthz`）→ `/readyz` 200 → 经网关路由可达（非 502/503/504/000）；
  失败**自动回滚**上一版本并记录。
- **回滚**：切换上一 tag（或 `--to`）；迁移向前修复优先，**不执行 downgrade**。
- **留存**：semver 标签永久；SHA 标签每服务保留最近 N（`prune` 经 GitLab Registry API 删除）。

退出码：0 成功；1 失败（含门禁失败与自动回滚后仍失败）；2 参数 / 环境错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
"""仓库根（`scripts/tools/deploy/release.py` 上溯 3 级）。"""

SERVICES: tuple[str, ...] = (
    "platform",
    "identity",
    "tenant",
    "org",
    "file",
    "notification",
    "search",
    "ai",
    "report",
)
"""已启用服务（与 `enabled_service_keys()` 一致；护栏用例断言，防漂移）。"""

COMPOSE_FILE = "compose/bms.yml"
GATEWAY_SMOKE_PATH = "/api/{service}/v1/__gate__"
"""网关路由可达探测路径（命中网关服务路由即可；状态码 200/401/403/404 视为可达）。"""

GATEWAY_SMOKE_PASS = frozenset({200, 201, 202, 204, 301, 302, 401, 403, 404})
"""网关冒烟通过状态码（路由 / 认证可达即过；502/503/504/000 判失败）。"""

_SEMVER_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


# ---------------------------------------------------------------------------
# 纯函数（可单测；不触网 / 不调用 docker）
# ---------------------------------------------------------------------------
def parse_env(text: str) -> dict[str, str]:
    """解析 `.env` 文本为字典（忽略注释 / 空行；去引号；支持 `export ` 前缀）。

    Args:
        text: `.env` 文件内容。

    Returns:
        dict[str, str]: 键值映射（值已去首尾引号）。
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
            val = val[1:-1]
        values[key] = val
    return values


def is_semver(tag: str) -> bool:
    """判断是否为语义化版本标签（`vX.Y.Z`）。

    Args:
        tag: 镜像标签。

    Returns:
        bool: 语义化版本 True。
    """
    return bool(_SEMVER_RE.match(tag))


def rotate_ledger(
    ledger: dict[str, object],
    *,
    tag: str,
    actor: str,
    at: str,
    sha: str = "",
    digest: str = "",
) -> dict[str, object]:
    """台账轮转：`previous ← current`，`current ← 新版本`（纯函数）。

    Args:
        ledger: 现行台账（可空）。
        tag: 新版本标签。
        actor: 操作者。
        at: 时间（ISO 字符串）。
        sha: 提交短 SHA（可选）。
        digest: 镜像 digest（可选）。

    Returns:
        dict[str, object]: 新台账（不改动入参）。
    """
    current = {"tag": tag, "sha": sha, "digest": digest, "deployed_at": at, "deployed_by": actor}
    previous = ledger.get("current") if isinstance(ledger.get("current"), dict) else None
    return {"service": ledger.get("service", ""), "current": current, "previous": previous}


def resolve_rollback_target(ledger: dict[str, object], to: str = "") -> str:
    """解析回滚目标标签（`--to` 优先，缺省取台账 `previous`）。

    Args:
        ledger: 现行台账。
        to: 显式目标标签（可空）。

    Returns:
        str: 目标标签。

    Raises:
        ValueError: 未显式指定且台账无上一版本。
    """
    if to:
        return to
    previous = ledger.get("previous")
    if isinstance(previous, dict) and previous.get("tag"):
        return str(previous["tag"])
    raise ValueError("无上一版本可回滚：请用 --to 显式指定目标标签")


def select_prunable_tags(tags: list[dict[str, str]], keep: int) -> list[str]:
    """选择可清理的 SHA 标签（semver 永久保留；SHA 保留最近 `keep` 个）。

    Args:
        tags: 标签列表（每项 `{"name": …, "created_at": …}`，`created_at` 为 ISO 字符串）。
        keep: SHA 标签保留数量（<=0 视为不清理）。

    Returns:
        list[str]: 待删除标签名（空表示无需清理）。
    """
    if keep <= 0:
        return []
    ordered = sorted(tags, key=lambda item: item.get("created_at", ""), reverse=True)
    sha_tags = [item["name"] for item in ordered if not is_semver(item["name"])]
    return sha_tags[keep:]


def build_manifest(
    *,
    service: str,
    commit: str,
    short_sha: str,
    image: str,
    digest: str,
    scan: str,
    pipeline_url: str,
    tag: str = "",
    built_at: str = "",
) -> dict[str, object]:
    """构造发布清单（CI 采集项 + 不可采集项「人工确认」占位）。

    Args:
        service: 服务标识。
        commit: 完整 commit SHA。
        short_sha: 提交短 SHA。
        image: 镜像引用（含标签）。
        digest: 镜像 digest。
        scan: Trivy 扫描结论（`pass` / `fail`）。
        pipeline_url: 流水线 URL。
        tag: Git 标签（tag 流水线）。
        built_at: 构建时间（ISO 字符串）。

    Returns:
        dict[str, object]: 发布清单。
    """
    return {
        "service": service,
        "commit": commit,
        "short_sha": short_sha,
        "tag": tag,
        "image": image,
        "digest": digest,
        "scan": scan,
        "pipeline_url": pipeline_url,
        "built_at": built_at,
        "checklist": {
            "ci": "pass",
            "image_scan": scan,
            "contract_snapshot": "人工确认（父流水线 swagger-snapshot 归档）",
            "migration_drill": "人工确认（三库迁移演练）",
            "backup_restorable": "人工确认（当日备份可恢复）",
            "release_notes": "人工确认（发布说明）",
        },
    }


# ---------------------------------------------------------------------------
# 运行时辅助
# ---------------------------------------------------------------------------
def _now() -> str:
    """取当前 UTC 时间（ISO 秒级）。"""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _read_env(env_file: Path) -> dict[str, str]:
    """读取 `.env` 文件（缺失返回空）。"""
    if not env_file.is_file():
        return {}
    return parse_env(env_file.read_text(encoding="utf-8"))


def _base_env(env_file: Path) -> dict[str, str]:
    """合并进程环境与 `.env`（保留 PATH 等运行环境；`.env` 填充，进程内 BMS_/MYSQL_ 优先）。"""
    merged = dict(os.environ)
    merged.update(_read_env(env_file))
    merged.update({k: v for k, v in os.environ.items() if k.startswith(("BMS_", "MYSQL_"))})
    return merged


def _fill_service_tags(deploy_dir: Path, env: dict[str, str]) -> dict[str, str]:
    """补齐所有服务的 `BMS_TAG_<SERVICE>`（compose 需全部变量方可插值；台账当前版本兜底）。

    取值优先：进程 / `.env` 已有 > 服务台账 `current.tag` > `BMS_IMAGE_TAG`。
    """
    result = dict(env)
    for service in SERVICES:
        key = f"BMS_TAG_{service.upper()}"
        if result.get(key):
            continue
        ledger = _load_ledger(deploy_dir, service)
        current = ledger.get("current") if isinstance(ledger.get("current"), dict) else None
        result[key] = str((current or {}).get("tag") or env.get("BMS_IMAGE_TAG", ""))
    return result


def _ensure_registry_login(env: dict[str, str], *, stdout=print) -> None:
    """best-effort 登录 GitLab Registry（有 token 时；失败不中止，交由 compose 拉取时报错）。"""
    prefix = env.get("REGISTRY_IMAGE_PREFIX", "")
    host = prefix.split("/", 1)[0]
    token = env.get("GITLAB_API_TOKEN", "")
    if not host or not token:
        return
    user = env.get("REGISTRY_USER", "root")
    proc = subprocess.run(
        ["docker", "login", host, "-u", user, "--password-stdin"],
        input=token,
        text=True,
        check=False,
        capture_output=True,
    )
    if proc.returncode == 0:
        stdout(f"[registry] 已登录 {host}")
    else:
        stdout(f"[registry] 登录 {host} 失败（{proc.stderr.strip()}）；若镜像不可拉取请先手工 docker login")


def _compose(deploy_dir: Path, env: dict[str, str], args: list[str], *, capture: bool = False) -> str:
    """执行 `docker compose`（cwd = deploy 目录）。

    Args:
        deploy_dir: deploy 目录。
        env: 子进程环境（含 `.env` 与标签覆盖）。
        args: compose 子命令参数。
        capture: 是否捕获 stdout。

    Returns:
        str: stdout（capture 时）。
    """
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "--env-file", ".env", *args]
    proc = subprocess.run(
        cmd,
        cwd=deploy_dir,
        env=env,
        check=False,
        capture_output=not capture,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"docker compose {' '.join(args)} 失败（rc={proc.returncode}）：{detail}")
    return proc.stdout if capture else ""


def _compose_run(
    deploy_dir: Path,
    env: dict[str, str],
    service: str,
    command: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> None:
    """以 `compose run --rm --no-deps` 在服务镜像内执行一次性命令（迁移 / 种子）。"""
    run_env = dict(env)
    if extra_env:
        run_env.update(extra_env)
    _compose(deploy_dir, run_env, ["run", "--rm", "--no-deps", service, *command])


def _ledger_path(deploy_dir: Path, service: str) -> Path:
    """取服务版本台账路径。"""
    root = Path(os.environ.get("BMS_RELEASES_DIR") or (deploy_dir / "releases"))
    return root / f"{service}.json"


def _load_ledger(deploy_dir: Path, service: str) -> dict[str, object]:
    """读取服务台账（缺失返回空 dict）。"""
    path = _ledger_path(deploy_dir, service)
    if not path.is_file():
        return {"service": service}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"service": service}


def _save_ledger(deploy_dir: Path, service: str, ledger: dict[str, object]) -> None:
    """写入服务台账（自动创建目录）。"""
    path = _ledger_path(deploy_dir, service)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_log(deploy_dir: Path, record: dict[str, object]) -> None:
    """追加发布日志（`release-log.jsonl`）。"""
    path = deploy_dir / "releases" / "release-log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 健康门禁
# ---------------------------------------------------------------------------
def _wait_container_healthy(container: str, timeout: float) -> bool:
    """等待容器健康检查转为 `healthy`（轮询）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.stdout.strip() == "healthy":
            return True
        time.sleep(3)
    return False


def _wait_readyz(deploy_dir: Path, env: dict[str, str], service: str, timeout: float) -> bool:
    """等待服务 `/readyz` 返回 200（容器内探测）。"""
    script = (
        "import sys,urllib.request\n"
        "try:\n"
        "    r=urllib.request.urlopen('http://127.0.0.1:8000/readyz',timeout=3)\n"
        "    sys.exit(0 if r.status==200 else 1)\n"
        "except Exception:\n"
        "    sys.exit(1)\n"
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                COMPOSE_FILE,
                "--env-file",
                ".env",
                "exec",
                "-T",
                service,
                "python",
                "-c",
                script,
            ],
            cwd=deploy_dir,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return True
        time.sleep(3)
    return False


def _check_gateway(env: dict[str, str], service: str, timeout: float) -> bool:
    """经网关探测服务路由可达（不依赖登录；200/401/403/404 视为可达）。"""
    port = env.get("GATEWAY_HTTP_PORT", "8088")
    url = f"http://127.0.0.1:{port}" + GATEWAY_SMOKE_PATH.format(service=service)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except OSError:
        # 含 urllib.error.URLError（其子类）与底层连接错误
        status = 0
    return status in GATEWAY_SMOKE_PASS


def health_gate(deploy_dir: Path, env: dict[str, str], service: str, *, stdout=print) -> bool:
    """三步健康门禁（容器健康 → `/readyz` → 网关路由可达）。"""
    timeout = float(env.get("BMS_GATE_TIMEOUT", "90"))
    smoke_timeout = float(env.get("BMS_GATEWAY_SMOKE_TIMEOUT", "30"))
    container = f"bms-{service}"
    if not _wait_container_healthy(container, timeout):
        stdout(f"[gate] {service}：容器未就绪（{container} 非 healthy）")
        return False
    if not _wait_readyz(deploy_dir, env, service, timeout):
        stdout(f"[gate] {service}：/readyz 未返回 200")
        return False
    if not _check_gateway(env, service, smoke_timeout):
        stdout(f"[gate] {service}：网关路由不可达")
        return False
    stdout(f"[gate] {service}：门禁通过（healthy + /readyz 200 + 网关可达）")
    return True


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def _up(deploy_dir: Path, env: dict[str, str], service: str, tag: str) -> None:
    """以指定标签起（或更新）服务容器。"""
    run_env = dict(env)
    run_env[f"BMS_TAG_{service.upper()}"] = tag
    _compose(deploy_dir, run_env, ["up", "-d", service])


def _migrate(deploy_dir: Path, env: dict[str, str], service: str, tag: str, tenants: list[str]) -> None:
    """以目标标签镜像跑一次性迁移容器（迁移先行）。"""
    run_env = dict(env)
    run_env[f"BMS_TAG_{service.upper()}"] = tag
    args = ["python", "-m", "ops.migrate_tenants", "--service", service]
    if tenants:
        for tenant in tenants:
            args += ["--code", tenant]
    else:
        args.append("--all-tenants")
    _compose_run(deploy_dir, run_env, service, args)


def _deploy_one(deploy_dir: Path, env: dict[str, str], service: str, tag: str, actor: str) -> bool:
    """单服务部署：迁移 → 起容器 → 门禁 → 台账；门禁失败自动回滚。"""
    ledger = _load_ledger(deploy_dir, service)
    old_current = ledger.get("current") if isinstance(ledger.get("current"), dict) else None
    tenants = [t for t in (env.get("BMS_DEPLOY_TENANTS", "demo,acme") or "").split(",") if t]
    print(f"[deploy] {service} → {tag}：迁移先行")
    _migrate(deploy_dir, env, service, tag, tenants)
    print(f"[deploy] {service} → {tag}：起容器")
    _up(deploy_dir, env, service, tag)
    if health_gate(deploy_dir, env, service):
        new_ledger = rotate_ledger(ledger, tag=tag, actor=actor, at=_now())
        new_ledger["service"] = service
        _save_ledger(deploy_dir, service, new_ledger)
        _append_log(
            deploy_dir,
            {
                "at": _now(),
                "by": actor,
                "action": "deploy",
                "service": service,
                "from": (old_current or {}).get("tag", ""),
                "to": tag,
                "result": "success",
            },
        )
        return True
    print(f"[deploy] {service} 门禁失败 → 自动回滚")
    if not old_current or not old_current.get("tag"):
        _append_log(
            deploy_dir,
            {
                "at": _now(),
                "by": actor,
                "action": "deploy",
                "service": service,
                "from": "",
                "to": tag,
                "result": "failure",
            },
        )
        return False
    old_tag = str(old_current["tag"])
    _up(deploy_dir, env, service, old_tag)
    ok = health_gate(deploy_dir, env, service)
    _append_log(
        deploy_dir,
        {
            "at": _now(),
            "by": actor,
            "action": "rollback",
            "service": service,
            "from": tag,
            "to": old_tag,
            "result": "success" if ok else "failure",
        },
    )
    return False


def _rollback_one(deploy_dir: Path, env: dict[str, str], service: str, to: str, actor: str) -> bool:
    """单服务回滚：切换上一 tag → 起容器 → 门禁 → 台账（不 downgrade）。"""
    ledger = _load_ledger(deploy_dir, service)
    target = resolve_rollback_target(ledger, to)
    old_current = ledger.get("current") if isinstance(ledger.get("current"), dict) else None
    print(f"[rollback] {service} → {target}")
    _up(deploy_dir, env, service, target)
    ok = health_gate(deploy_dir, env, service)
    if ok:
        new_ledger = rotate_ledger(ledger, tag=target, actor=actor, at=_now())
        new_ledger["service"] = service
        _save_ledger(deploy_dir, service, new_ledger)
    _append_log(
        deploy_dir,
        {
            "at": _now(),
            "by": actor,
            "action": "rollback",
            "service": service,
            "from": (old_current or {}).get("tag", ""),
            "to": target,
            "result": "success" if ok else "failure",
        },
    )
    return ok


def _ensure_app_user(deploy_dir: Path, env: dict[str, str]) -> None:
    """经 mysql 容器 root 创建应用账号并按 `bms\\_%` 库授权（幂等）。"""
    user = env.get("BMS_APP_DB_USER", "bms_app")
    password = env.get("BMS_APP_DB_PASSWORD") or env.get("BMS_DATABASE__PLATFORM__PASSWORD", "")
    root_pw = env.get("MYSQL_ROOT_PASSWORD", "")
    if not password:
        raise RuntimeError("缺少 BMS_APP_DB_PASSWORD（应用账号密码）")
    if not root_pw:
        raise RuntimeError("缺少 MYSQL_ROOT_PASSWORD（建库 / 授权管理口令）")
    literal = password.replace("'", "''")
    sql = (
        f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{literal}'; "
        f"ALTER USER '{user}'@'%' IDENTIFIED BY '{literal}'; "
        f"GRANT ALL PRIVILEGES ON `bms\\_%`.* TO '{user}'@'%'; FLUSH PRIVILEGES;"
    )
    _compose(deploy_dir, env, ["exec", "-T", "-e", f"MYSQL_PWD={root_pw}", "mysql", "mysql", "-uroot", "-e", sql])


def _tenant_url(env: dict[str, str], service: str, tenant: str) -> str:
    """构造服务租户库连接串（含密码；供 seed_dict 经 `BMS_MIGRATION_URL` 使用）。"""
    template = env.get("BMS_DATABASE__TENANTS__URL_TEMPLATE", "")
    if not template:
        raise RuntimeError("缺少 BMS_DATABASE__TENANTS__URL_TEMPLATE")
    url = template.format(service=service, tenant=tenant, database=f"bms_{service}_{tenant}")
    password = env.get("BMS_DATABASE__TENANTS__PASSWORD", "")
    if not password:
        return url
    parsed = urllib.parse.urlsplit(url)
    user = urllib.parse.quote(parsed.username or "", safe="")
    auth = f"{user}:{urllib.parse.quote(password, safe='')}@"
    netloc = auth + (parsed.hostname or "")
    if parsed.port:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def cmd_bootstrap(deploy_dir: Path, env: dict[str, str], *, services: list[str], actor: str) -> int:
    """首次数据引导：建库授权 → 分链迁移 → 种子（幂等；`services` 可限定子集）。"""
    tenants = [t for t in (env.get("BMS_DEPLOY_TENANTS", "demo,acme") or "").split(",") if t]
    print("[bootstrap] 1/4 应用账号与授权")
    _ensure_registry_login(env)
    _ensure_app_user(deploy_dir, env)
    print("[bootstrap] 2/4 建库（按服务 × 租户）")
    admin_url = f"mysql+aiomysql://root:{urllib.parse.quote(env.get('MYSQL_ROOT_PASSWORD', ''), safe='')}@mysql:3306"
    provision = ["python", "-m", "ops.provision_tenant", "--admin-url", admin_url]
    for tenant in tenants:
        provision += ["--code", tenant]
    _compose_run(deploy_dir, env, "platform", provision)
    print("[bootstrap] 3/4 分链迁移（按服务）")
    for service in services:
        _migrate(deploy_dir, env, service, _bootstrap_tag(env, service), tenants)
    print("[bootstrap] 4/4 种子")
    # 种子按「服务包归属」选运行镜像：seed_module 需 bms_platform；seed_tenant 需 bms_tenant；
    # seed_tables / seed_dict 仅需 bms_core（平台 / 各服务镜像均可）
    if "platform" in services:
        _compose_run(deploy_dir, env, "platform", ["python", "-m", "ops.seed_module"])
        _compose_run(deploy_dir, env, "platform", ["python", "-m", "ops.seed_tables"])
    if "tenant" in services:
        _compose_run(deploy_dir, env, "tenant", ["python", "-m", "ops.seed_tenant"])
    for service in services:
        for tenant in tenants:
            url = _tenant_url(env, service, tenant)
            _compose_run(
                deploy_dir,
                env,
                service,
                ["python", "-m", "ops.seed_dict"],
                extra_env={"BMS_MIGRATION_URL": url},
            )
    print("[bootstrap] 完成（幂等，可重跑）")
    return 0


def _bootstrap_tag(env: dict[str, str], service: str) -> str:
    """bootstrap 迁移所用镜像标签（缺省取 `.env` 的 BMS_IMAGE_TAG；无则报错）。"""
    tag = env.get(f"BMS_TAG_{service.upper()}") or env.get("BMS_IMAGE_TAG", "")
    if not tag:
        raise RuntimeError(f"bootstrap 需镜像标签：请设置 BMS_IMAGE_TAG 或 BMS_TAG_{service.upper()}")
    return tag


def cmd_deploy(deploy_dir: Path, env: dict[str, str], *, services: list[str], tag: str, actor: str) -> int:
    """部署（迁移 → 起容器 → 门禁 → 台账；失败自动回滚）。"""
    if not tag:
        print("错误：deploy 必须显式 --tag（不可变标签，禁 latest）", file=sys.stderr)
        return 2
    _ensure_registry_login(env)
    ok = True
    for service in services:
        ok = _deploy_one(deploy_dir, env, service, tag, actor) and ok
    return 0 if ok else 1


def cmd_rollback(deploy_dir: Path, env: dict[str, str], *, service: str, to: str, actor: str) -> int:
    """一键回滚（切换上一 tag / 指定 tag；不 downgrade）。"""
    _ensure_registry_login(env)
    return 0 if _rollback_one(deploy_dir, env, service, to, actor) else 1


def cmd_status(deploy_dir: Path, env: dict[str, str], *, services: list[str]) -> int:
    """打印版本台账（当前 / 上一版本）。"""
    for service in services:
        ledger = _load_ledger(deploy_dir, service)
        current = ledger.get("current") or {}
        previous = ledger.get("previous") or {}
        print(
            f"{service}: current={current.get('tag', '-')} "
            f"previous={previous.get('tag', '-')} "
            f"deployed_at={current.get('deployed_at', '-')}"
        )
    return 0


def cmd_prune(deploy_dir: Path, env: dict[str, str], *, keep: int, dry_run: bool) -> int:
    """清理超窗 SHA 标签（semver 永久保留）。"""
    api = env.get("GITLAB_API_URL", "").rstrip("/")
    token = env.get("GITLAB_API_TOKEN", "")
    project = env.get("CI_PROJECT_ID") or env.get("GITLAB_PROJECT_ID", "")
    if not api or not token or not project:
        print("错误：prune 需 GITLAB_API_URL / GITLAB_API_TOKEN / CI_PROJECT_ID（读 deploy/.env）", file=sys.stderr)
        return 2
    headers = {"PRIVATE-TOKEN": token}
    repos = _api_get(f"{api}/projects/{project}/registry/repositories?per_page=100", headers)
    total = 0
    for service in SERVICES:
        repo = _find_repo(repos, service)
        if repo is None:
            continue
        tags = _api_get(f"{api}/projects/{project}/registry/repositories/{repo['id']}/tags?per_page=100", headers)
        prunable = select_prunable_tags(tags, keep)
        for name in prunable:
            total += 1
            if dry_run:
                print(f"[prune] 将删除 {service}:{name}（dry-run）")
                continue
            _api_delete(
                f"{api}/projects/{project}/registry/repositories/{repo['id']}/tags/{urllib.parse.quote(name, safe='')}",
                headers,
            )
            print(f"[prune] 已删除 {service}:{name}")
    print(f"[prune] 完成，共 {total} 个 SHA 标签（semver 永久保留；磁盘回收另经 registry-garbage-collect）")
    return 0


def _find_repo(repos: list[dict[str, object]], service: str) -> dict[str, object] | None:
    """从 Registry 仓库列表定位服务镜像仓库（按路径后缀匹配）。"""
    for repo in repos:
        path = str(repo.get("path", ""))
        if path.endswith(f"/bms-{service}") or path == f"bms-{service}":
            return repo
    return None


def _api_get(url: str, headers: dict[str, str]) -> list[dict[str, object]]:
    """GET JSON 数组（GitLab API）。"""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data if isinstance(data, list) else []


def _api_delete(url: str, headers: dict[str, str]) -> None:
    """DELETE（GitLab Registry 标签删除）。"""
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    with urllib.request.urlopen(req, timeout=30):
        pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="BMS 服务部署 / 回滚 / 门禁 / 数据引导 CLI（09_02）")
    parser.add_argument("--deploy-dir", default=str(REPO_ROOT / "deploy"), help="deploy 目录（默认仓库 deploy/）")
    parser.add_argument("--env-file", default="", help="环境变量文件（默认 <deploy-dir>/.env）")
    parser.add_argument("--actor", default=os.environ.get("USER", "unknown"), help="操作者（记入台账 / 日志）")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="一次性数据引导（建库 + 迁移 + 种子）")
    bootstrap.add_argument(
        "--service", action="append", choices=SERVICES, default=[], help="限定服务（可重复；缺省全部启用服务）"
    )

    deploy = sub.add_parser("deploy", help="部署（迁移 → 起容器 → 门禁 → 台账）")
    deploy.add_argument("--service", choices=SERVICES, help="目标服务")
    deploy.add_argument("--all", action="store_true", help="全部已启用服务")
    deploy.add_argument("--tag", default="", help="目标镜像标签（必填；禁 latest）")

    rollback = sub.add_parser("rollback", help="一键回滚（切换上一 tag / --to）")
    rollback.add_argument("--service", choices=SERVICES, required=True, help="目标服务")
    rollback.add_argument("--to", default="", help="目标标签（缺省取台账上一版本）")

    status = sub.add_parser("status", help="打印版本台账")
    status.add_argument("--service", choices=SERVICES, help="目标服务（缺省全部）")

    gate = sub.add_parser("health-gate", help="单独跑健康门禁")
    gate.add_argument("--service", choices=SERVICES, required=True, help="目标服务")

    prune = sub.add_parser("prune", help="清理超窗 SHA 标签（semver 永久保留）")
    prune.add_argument(
        "--keep", type=int, default=int(os.environ.get("BMS_KEEP_SHA_TAGS", "30")), help="SHA 标签保留数"
    )
    prune.add_argument("--dry-run", action="store_true", help="只列出将删除的标签")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    args = _parse_args(argv)
    deploy_dir = Path(args.deploy_dir).resolve()
    env_file = Path(args.env_file) if args.env_file else deploy_dir / ".env"
    env = _fill_service_tags(deploy_dir, _base_env(env_file))
    if not deploy_dir.is_dir():
        print(f"错误：deploy 目录不存在：{deploy_dir}", file=sys.stderr)
        return 2
    try:
        if args.command == "bootstrap":
            return cmd_bootstrap(deploy_dir, env, services=(args.service or list(SERVICES)), actor=args.actor)
        if args.command == "deploy":
            services = list(SERVICES) if args.all else ([args.service] if args.service else [])
            if not services:
                print("错误：deploy 需 --service 或 --all", file=sys.stderr)
                return 2
            return cmd_deploy(deploy_dir, env, services=services, tag=args.tag, actor=args.actor)
        if args.command == "rollback":
            return cmd_rollback(deploy_dir, env, service=args.service, to=args.to, actor=args.actor)
        if args.command == "status":
            return cmd_status(deploy_dir, env, services=[args.service] if args.service else list(SERVICES))
        if args.command == "health-gate":
            return 0 if health_gate(deploy_dir, env, args.service) else 1
        if args.command == "prune":
            return cmd_prune(deploy_dir, env, keep=args.keep, dry_run=args.dry_run)
    except (RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

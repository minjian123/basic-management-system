#!/usr/bin/env python3
"""服务部署 / 回滚 / 健康门禁 / 数据引导 CLI（阶段二 09_02 不可变镜像与回滚）。

在部署服务器（mjbk）仓库检出根执行；以 `docker compose` 驱动 `deploy/compose/bms.yml`，
只依赖 Python 标准库（无需后端虚拟环境），凭据只读 `deploy/.env`（不改写、不打印）。

用法::

    python3 scripts/tools/deploy/release.py bootstrap [--env-file deploy/.env]
    python3 scripts/tools/deploy/release.py gateway [--render]
    python3 scripts/tools/deploy/release.py deploy --service platform --tag v0.2.0
    python3 scripts/tools/deploy/release.py deploy --all --tag <sha 或 vX.Y.Z>
    python3 scripts/tools/deploy/release.py deploy --all --tag <tag> --skip-gateway-check
    python3 scripts/tools/deploy/release.py provision [--service mdm]
    python3 scripts/tools/deploy/release.py exec --service mdm -- python -m ops.seed_platform --tenant demo
    python3 scripts/tools/deploy/release.py rollback --service platform [--to <tag>]
    python3 scripts/tools/deploy/release.py status [--service platform]
    python3 scripts/tools/deploy/release.py health-gate --service platform
    python3 scripts/tools/deploy/release.py prune --keep 30

**产品仓复用（跨仓，2026-11-05）**：同一入口也用于产品服务部署，产品侧只给**通用参数**
（`--repo-root` / `--deploy-dir` / `--compose-file` / `--services` / `--container-name` / `--tag-env` /
`--image-prefix-env` / `--health-path` / `--gateway-path` / `--init-command` / `--provision-command`），
命令实现里不出现产品字面量。示例（mdm 首次部署）::

    python3 ~/bms/scripts/tools/deploy/release.py \
      --repo-root ~/mdm --deploy-dir ~/mdm/deploy --compose-file compose/mdm.yml \
      --services mdm --container-name mdm --tag-env MDM_TAG \
      --image-prefix-env MDM_REGISTRY_IMAGE_PREFIX \
      --gateway-path /api/mdm/v1/mdm/__gate__ \
      --init-command "python -m ops.migrate {tenants}" \
      --provision-command "python -m ops.provision {tenants}" \
      deploy --service mdm --tag <sha> --skip-gateway-check --skip-gateway-probe

口径（详见 `bms文档/项目/02_后端基座与服务化地基/任务/09_多服务CI-CD与契约门禁/09_…_02_…/设计/`）：

- **不可变标签**：commit short SHA 主标签 + Git tag `vX.Y.Z` 追加语义化标签；禁 `latest`；版本台账
  `deploy/releases/<service>.json`（当前 / 上一版本）+ `deploy/releases/release-log.jsonl`（运行时状态，不入库）。
- **注册表对账先行**（07B `02_06`）：`deploy` 起容器前在 platform 镜像内跑 `gateway`（注册表重渲 ↔
  `deploy/gateway/apisix.yaml` 逐字比对），不一致即中止（不落容器）；首部署 / 应急用
  `--skip-gateway-check` 显式跳过并记入发布日志。
- **建表先行**：`deploy` 先以目标镜像跑一次性建表容器（`ops.init_schema`，幂等），再起容器。
- **健康门禁**：容器 `healthy`（`/healthz`）→ `/readyz` 200 → 经网关路由可达（非 502/503/504/000）；
  失败**自动回滚**上一版本并记录。
- **回滚**：切换上一 tag（或 `--to`）；结构变更由幂等建表承接（**不执行 downgrade**）。
- **留存**：semver 标签永久；SHA 标签每服务保留最近 N（`prune` 经 GitLab Registry API 删除）。

退出码：0 成功；1 失败（含门禁失败与自动回滚后仍失败）；2 参数 / 环境错误。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
"""仓库根（`scripts/tools/deploy/release.py` 上溯 3 级）。"""

_SRC_ROOT = REPO_ROOT / "backend" / "libs" / "bms_core" / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bms_core.core.concurrent import (  # noqa: E402
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.serialization import normalize_collections  # noqa: E402


def _to_stable(value: object) -> object:
    """把 JSON 读回的内置容器**递归**转为插入序集合类（脚本自备，对齐 `models.base.to_stable_value`）。

    脚本不引 SQLAlchemy（`models` 依赖第三方），故此处复用 `core` 层能力自备一份：
    `Mapping` → `ConcurrentStableDict`、`list` / `tuple` → `ConcurrentStableList`、
    `set` / `frozenset` → `ConcurrentStableSet`，标量原样返回。

    Args:
        value: JSON 反序列化结果。

    Returns:
        object: 集合类 / 标量（递归）。
    """
    if isinstance(value, Mapping):
        return ConcurrentStableDict({key: _to_stable(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return ConcurrentStableList(_to_stable(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return ConcurrentStableSet(_to_stable(item) for item in value)
    return value


SERVICES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "platform",
        "identity",
        "tenant",
        "file",
        "notification",
        "search",
        "ai",
        "report",
        "txn",
    )
)
"""已启用**平台服务**（与 `enabled_service_keys()` 一致；护栏用例断言，防漂移）。

`org` 随组织主数据归 mdm 产品服务（2026-10-07，bms 11_01）：退出平台服务清单、改由
`SERVICE_CATALOG` 的产品分组承载（网关 upstream 仍生成、对外只经产品命名空间）。
"""

COMPOSE_FILE = "compose/bms.yml"
GATEWAY_SMOKE_PATH = "/api/{service}/v1/__gate__"
"""网关路由可达探测路径（命中网关服务路由即可；状态码 200/401/403/404 视为可达）。"""

GATEWAY_CHECK_IMAGE = "platform"
"""注册表对账所用镜像（07B `02_06`）。

`ops.gateway_config` 声明 `RUN_IMAGE = "ci"`（无部署镜像对应的 CI 专用件），故不能走
`_run_image_of()`；platform 镜像含 `bms_core` + `bms_platform` + `ops`，正是注册表取数所需，
且部署态必然已存在（与 `ops.check_modules` 接库口径同源）。
"""

GATEWAY_CHECK_ROOT = "/opt/registry-check"
"""对账容器内的仓库根挂载点（只读；`deploy/` 挂到 `<root>/deploy`）。

镜像内 `WORKDIR=/opt/bms` 且**无 `deploy/` 目录**（部署镜像只装源码与 `ops`），故对账把宿主
`deploy/` 以只读方式挂到独立根——避开 `services.yml` 已有的 `/opt/deploy/boundaries` 挂载点
（不覆盖、不嵌套），并由 `--root` 显式指向。
"""

GATEWAY_SMOKE_PASS: ConcurrentStableSet[int] = ConcurrentStableSet({200, 201, 202, 204, 301, 302, 401, 403, 404})
"""网关冒烟通过状态码（路由 / 认证可达即过；502/503/504/000 判失败）。"""

_SEMVER_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class Profile:
    """部署画像：把「bms 平台默认」与「产品仓（mdm 等）」的差异收敛为参数。

    CLI 只给值、不写产品字面量——新增产品部署只需给一组参数，发布 / 回滚 / 门禁 / 台账仍走同一实现。

    Attributes:
        repo_root: 仓库根（`ops` 脚本定位与只读挂载基准）。
        compose_file: compose 文件（相对 `deploy-dir`）。
        services: 需补齐镜像标签的服务全集（bms 为已启用平台服务；产品为单服务）。
        container_template: 容器名模板（`{service}` 占位）。
        tag_env_template: 镜像标签环境变量名模板（`{service}` / `{SERVICE}` 占位）。
        image_prefix_env: 镜像前缀环境变量名。
        health_path: 容器内就绪探测路径。
        gateway_path_template: 网关冒烟路径模板（`{service}` 占位）。
        init_command: 建表 / 迁移命令模板；占位符 `{service}` / `{tenant}` / `{tenants}` / `{tenants_or_all}`。
        provision_command: 建库命令模板（同上占位符；空表示不支持 `provision`）。
        db_grant_pattern: 应用账号授权库模式（`bootstrap` 用）。
    """

    repo_root: Path = REPO_ROOT
    compose_file: str = COMPOSE_FILE
    services: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(SERVICES))
    container_template: str = "bms-{service}"
    tag_env_template: str = "BMS_TAG_{SERVICE}"
    image_prefix_env: str = "REGISTRY_IMAGE_PREFIX"
    health_path: str = "/readyz"
    gateway_path_template: str = GATEWAY_SMOKE_PATH
    init_command: ConcurrentStableFrozenList[str] = field(
        default_factory=lambda: ConcurrentStableFrozenList(
            ["python", "-m", "ops.init_schema", "--service", "{service}", "{tenants_or_all}"]
        )
    )
    provision_command: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList())
    db_grant_pattern: str = "bms\\_%"

    def container_name(self, service: str) -> str:
        """容器名（按模板渲染）。

        Args:
            service: 服务标识。

        Returns:
            str: 容器名。
        """
        return self.container_template.format(service=service)

    def tag_env(self, service: str) -> str:
        """镜像标签环境变量名。

        Args:
            service: 服务标识。

        Returns:
            str: 变量名（如 `BMS_TAG_PLATFORM` / `MDM_TAG`）。
        """
        return self.tag_env_template.format(service=service, SERVICE=service.upper())

    def gateway_path(self, service: str) -> str:
        """网关冒烟路径。

        Args:
            service: 服务标识。

        Returns:
            str: 路径（如 `/api/platform/v1/__gate__`）。
        """
        return self.gateway_path_template.format(service=service)


def render_commands(
    template: ConcurrentStableFrozenList[str], *, service: str, tenants: ConcurrentStableList[str]
) -> ConcurrentStableList[ConcurrentStableList[str]]:
    """把命令模板渲染为「待执行命令」清单。

    占位符口径：`{service}` 服务标识；`{tenants}` 展开为 `--code X --code Y`（无租户为空）；
    `{tenants_or_all}` 同上，但无租户时展开为 `--all-tenants`；含 `{tenant}` 时**逐租户**各一条命令。

    Args:
        template: 命令模板（已按 shell 词法拆好）。
        service: 服务标识。
        tenants: 租户编码清单。

    Returns:
        ConcurrentStableList[ConcurrentStableList[str]]: 待执行命令清单。
    """
    joined = " ".join(template)
    flags = " ".join(f"--code {tenant}" for tenant in tenants)
    if "{tenant}" in joined:
        return ConcurrentStableList(
            ConcurrentStableList(shlex.split(joined.format(service=service, tenant=tenant, tenants=flags)))
            for tenant in tenants
        )
    rendered = joined.format(service=service, tenants=flags, tenants_or_all=flags or "--all-tenants")
    return ConcurrentStableList([ConcurrentStableList(shlex.split(rendered))])


# ---------------------------------------------------------------------------
# 纯函数（可单测；不触网 / 不调用 docker）
# ---------------------------------------------------------------------------
def parse_env(text: str) -> ConcurrentStableDict[str, str]:
    """解析 `.env` 文本为字典（忽略注释 / 空行；去引号；支持 `export ` 前缀）。

    Args:
        text: `.env` 文件内容。

    Returns:
        ConcurrentStableDict[str, str]: 键值映射（值已去首尾引号）。
    """
    values: ConcurrentStableDict[str, str] = ConcurrentStableDict()
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
        values.set(key, val)
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
    ledger: ConcurrentStableDict[str, object],
    *,
    tag: str,
    actor: str,
    at: str,
    sha: str = "",
    digest: str = "",
) -> ConcurrentStableDict[str, object]:
    """台账轮转：`previous ← current`，`current ← 新版本`（纯函数）。

    Args:
        ledger: 现行台账（可空）。
        tag: 新版本标签。
        actor: 操作者。
        at: 时间（ISO 字符串）。
        sha: 提交短 SHA（可选）。
        digest: 镜像 digest（可选）。

    Returns:
        ConcurrentStableDict[str, object]: 新台账（不改动入参）。
    """
    current = ConcurrentStableDict(
        {
            "tag": tag,
            "sha": sha,
            "digest": digest,
            "deployed_at": at,
            "deployed_by": actor,
        }
    )
    raw_previous = ledger.get("current")
    previous = raw_previous if isinstance(raw_previous, Mapping) else None
    return ConcurrentStableDict({"service": ledger.get("service", ""), "current": current, "previous": previous})


def resolve_rollback_target(ledger: ConcurrentStableDict[str, object], to: str = "") -> str:
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
    if isinstance(previous, Mapping) and previous.get("tag"):
        return str(previous["tag"])
    raise ValueError("无上一版本可回滚：请用 --to 显式指定目标标签")


def select_prunable_tags(
    tags: ConcurrentStableList[ConcurrentStableDict[str, str]], keep: int
) -> ConcurrentStableList[str]:
    """选择可清理的 SHA 标签（semver 永久保留；SHA 保留最近 `keep` 个）。

    Args:
        tags: 标签列表（每项 `{"name": …, "created_at": …}`，`created_at` 为 ISO 字符串）。
        keep: SHA 标签保留数量（<=0 视为不清理）。

    Returns:
        ConcurrentStableList[str]: 待删除标签名（空表示无需清理）。
    """
    if keep <= 0:
        return ConcurrentStableList()
    ordered = sorted(tags, key=lambda item: item.get("created_at", ""), reverse=True)
    sha_tags = ConcurrentStableList(item["name"] for item in ordered if not is_semver(item["name"]))
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
) -> ConcurrentStableDict[str, object]:
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
        ConcurrentStableDict[str, object]: 发布清单。
    """
    return ConcurrentStableDict(
        {
            "service": service,
            "commit": commit,
            "short_sha": short_sha,
            "tag": tag,
            "image": image,
            "digest": digest,
            "scan": scan,
            "pipeline_url": pipeline_url,
            "built_at": built_at,
            "checklist": ConcurrentStableDict(
                {
                    "ci": "pass",
                    "image_scan": scan,
                    "contract_snapshot": "人工确认（父流水线 swagger-snapshot 归档）",
                    "schema_drill": "人工确认（三库建表演练）",
                    "backup_restorable": "人工确认（当日备份可恢复）",
                    "release_notes": "人工确认（发布说明）",
                }
            ),
        }
    )


# ---------------------------------------------------------------------------
# 注册表对账（07B `02_06`）
# ---------------------------------------------------------------------------
def gateway_check_args(*, render: bool = False) -> ConcurrentStableList[str]:
    """对账 / 重渲容器内的命令。

    `--from-registry` 省略 `--url`：容器内按配置解析平台库（与 `ops.check_modules` 同口径），
    不在宿主传凭据；`--root` 指向只读 / 可写挂载点（见 `GATEWAY_CHECK_ROOT`）。

    Args:
        render: True 时执行 `render`（按注册表重渲并写回仓库生成件）；False 为 `check`（零漂移比对）。

    Returns:
        ConcurrentStableList[str]: 容器内命令参数。
    """
    return ConcurrentStableList(
        [
            "python",
            "-m",
            "ops.gateway_config",
            "render" if render else "check",
            "--from-registry",
            "--root",
            GATEWAY_CHECK_ROOT,
        ]
    )


def gateway_check_volumes(deploy_dir: Path, *, render: bool = False) -> ConcurrentStableList[str]:
    """对账 / 重渲容器的挂载（宿主 `deploy/` → `<GATEWAY_CHECK_ROOT>/deploy`）。

    Args:
        deploy_dir: deploy 目录。
        render: True 时以读写挂载（需写回 `gateway/apisix.yaml`）。

    Returns:
        ConcurrentStableList[str]: `-v` 挂载声明。
    """
    mode = "" if render else ":ro"
    return ConcurrentStableList([f"{Path(deploy_dir).resolve()}:{GATEWAY_CHECK_ROOT}/deploy{mode}"])


# ---------------------------------------------------------------------------
# 运行时辅助
# ---------------------------------------------------------------------------
def _now() -> str:
    """取当前 UTC 时间（ISO 秒级）。"""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _read_env(env_file: Path) -> ConcurrentStableDict[str, str]:
    """读取 `.env` 文件（缺失返回空）。"""
    if not env_file.is_file():
        return ConcurrentStableDict()
    return parse_env(env_file.read_text(encoding="utf-8"))


def _base_env(env_file: Path) -> ConcurrentStableDict[str, str]:
    """合并进程环境与 `.env`（保留 PATH 等运行环境；`.env` 填充，进程内 BMS_/MYSQL_ 优先）。"""
    merged = ConcurrentStableDict(os.environ)
    merged.update(_read_env(env_file).items())
    merged.update((k, v) for k, v in os.environ.items() if k.startswith(("BMS_", "MYSQL_")))
    return merged


def _fill_service_tags(
    profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str]
) -> ConcurrentStableDict[str, str]:
    """补齐所有服务的镜像标签（compose 需全部变量方可插值；台账当前版本兜底）。

    取值优先：进程 / `.env` 已有 > 服务台账 `current.tag` > `BMS_IMAGE_TAG`。
    """
    result = ConcurrentStableDict(env)
    for service in profile.services:
        key = profile.tag_env(service)
        if result.get(key):
            continue
        ledger = _load_ledger(deploy_dir, service)
        raw_current = ledger.get("current")
        current = raw_current if isinstance(raw_current, Mapping) else None
        result.set(key, str((current or {}).get("tag") or env.get("BMS_IMAGE_TAG", "")))
    return result


def _ensure_registry_login(profile: Profile, env: ConcurrentStableDict[str, str], *, stdout=print) -> None:
    """best-effort 登录 GitLab Registry（有 token 时；失败不中止，交由 compose 拉取时报错）。"""
    prefix = env.get(profile.image_prefix_env, "")
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


def _compose_proc(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    args: ConcurrentStableList[str],
    *,
    capture: bool = False,
    raise_on_error: bool = True,
) -> subprocess.CompletedProcess[str]:
    """执行 `docker compose`（cwd = deploy 目录），返回进程结果。

    Args:
        profile: 部署画像（决定 compose 文件）。
        deploy_dir: deploy 目录。
        env: 子进程环境（含 `.env` 与标签覆盖）。
        args: compose 子命令参数。
        capture: 是否捕获 stdout（False 时输出到终端）。
        raise_on_error: 非零退出码是否抛 `RuntimeError`。

    Returns:
        subprocess.CompletedProcess[str]: 进程结果（退出码供需读取业务码的调用方使用）。

    Raises:
        RuntimeError: `raise_on_error` 且退出码非零。
    """
    cmd = ["docker", "compose", "-f", profile.compose_file, "--env-file", ".env", *args]
    proc = subprocess.run(
        cmd,
        cwd=deploy_dir,
        env=dict(env),
        check=False,
        capture_output=capture,
        text=True,
    )
    if raise_on_error and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"docker compose {' '.join(args)} 失败（rc={proc.returncode}）：{detail}")
    return proc


def _compose(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    args: ConcurrentStableList[str],
    *,
    capture: bool = False,
) -> str:
    """执行 `docker compose`（cwd = deploy 目录），失败即抛错。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 子进程环境（含 `.env` 与标签覆盖）。
        args: compose 子命令参数。
        capture: 是否捕获 stdout。

    Returns:
        str: stdout（capture 时）。
    """
    return _compose_proc(profile, deploy_dir, env, args, capture=capture).stdout or ""


def _compose_run(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    service: str,
    command: ConcurrentStableList[str],
    *,
    extra_env: ConcurrentStableDict[str, str] | None = None,
    volumes: ConcurrentStableList[str] | None = None,
    raise_on_error: bool = True,
) -> int:
    """以 `compose run --rm --no-deps` 在服务镜像内执行一次性命令（迁移 / 种子 / 对账）。

    `extra_env` 经 `-e KEY=VAL` 注入**容器内**（compose 仅自动传入服务 `environment` 声明的变量，
    子进程环境只用于 compose 插值）；`volumes` 经 `-v host:container[:ro]` 追加挂载。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 子进程环境。
        service: 运行镜像对应的服务名。
        command: 容器内命令。
        extra_env: 追加注入的容器内环境变量。
        volumes: 追加挂载（`host:container[:ro]`）。
        raise_on_error: 非零退出码是否抛 `RuntimeError`（False 时由调用方读取业务退出码）。

    Returns:
        int: 容器内命令退出码。
    """
    run_env = ConcurrentStableDict(env)
    args = ConcurrentStableList(["run", "--rm", "--no-deps"])
    for key, value in (extra_env or {}).items():
        args.update(["-e", f"{key}={value}"])
    for volume in volumes or ():
        args.update(["-v", volume])
    args.update([service, *command])
    return _compose_proc(profile, deploy_dir, run_env, args, raise_on_error=raise_on_error).returncode


def _ledger_path(deploy_dir: Path, service: str) -> Path:
    """取服务版本台账路径。"""
    root = Path(os.environ.get("BMS_RELEASES_DIR") or (deploy_dir / "releases"))
    return root / f"{service}.json"


def _load_ledger(deploy_dir: Path, service: str) -> ConcurrentStableDict[str, object]:
    """读取服务台账（缺失返回空 dict）。"""
    path = _ledger_path(deploy_dir, service)
    if not path.is_file():
        return ConcurrentStableDict({"service": service})
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return ConcurrentStableDict({"service": service})
    return ConcurrentStableDict({str(key): _to_stable(item) for key, item in data.items()})


def _save_ledger(deploy_dir: Path, service: str, ledger: ConcurrentStableDict[str, object]) -> None:
    """写入服务台账（自动创建目录）。"""
    path = _ledger_path(deploy_dir, service)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(normalize_collections(ledger), ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")


def _append_log(deploy_dir: Path, record: ConcurrentStableDict[str, object]) -> None:
    """追加发布日志（`release-log.jsonl`）。"""
    path = deploy_dir / "releases" / "release-log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalize_collections(record), ensure_ascii=False) + "\n")


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


def _wait_readyz(
    profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str], service: str, timeout: float
) -> bool:
    """等待服务就绪端点返回 200（容器内探测）。"""
    path = profile.health_path
    script = (
        "import sys,urllib.request\n"
        "try:\n"
        f"    r=urllib.request.urlopen('http://127.0.0.1:8000{path}',timeout=3)\n"
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
                profile.compose_file,
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
            env=dict(env),
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return True
        time.sleep(3)
    return False


def _check_gateway(profile: Profile, env: ConcurrentStableDict[str, str], service: str, timeout: float) -> bool:
    """经网关探测服务路由可达（不依赖登录；200/401/403/404 视为可达）。"""
    port = env.get("GATEWAY_HTTP_PORT", "8088")
    url = f"http://127.0.0.1:{port}" + profile.gateway_path(service)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except OSError:
        # 含 urllib.error.URLError（其子类）与底层连接错误
        status = 0
    return status in GATEWAY_SMOKE_PASS


def health_gate(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    service: str,
    *,
    stdout=print,
    skip_gateway_probe: bool = False,
) -> bool:
    """三步健康门禁（容器健康 → 就绪端点 → 网关路由可达）。"""
    timeout = float(env.get("BMS_GATE_TIMEOUT", "90"))
    smoke_timeout = float(env.get("BMS_GATEWAY_SMOKE_TIMEOUT", "30"))
    container = profile.container_name(service)
    if not _wait_container_healthy(container, timeout):
        stdout(f"[gate] {service}：容器未就绪（{container} 非 healthy）")
        return False
    if not _wait_readyz(profile, deploy_dir, env, service, timeout):
        stdout(f"[gate] {service}：{profile.health_path} 未返回 200")
        return False
    if skip_gateway_probe:
        stdout(f"[gate] {service}：跳过网关可达探测（--skip-gateway-probe）")
        return True
    if not _check_gateway(profile, env, service, smoke_timeout):
        stdout(f"[gate] {service}：网关路由不可达")
        return False
    stdout(f"[gate] {service}：门禁通过（healthy + {profile.health_path} 200 + 网关可达）")
    return True


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def _ledger_tag(deploy_dir: Path, service: str, fallback: str) -> str:
    """取服务台账当前 tag；缺失时回落 fallback。

    Args:
        deploy_dir: deploy 目录。
        service: 服务名。
        fallback: 台账缺失时的回退 tag。

    Returns:
        str: 当前 tag。
    """
    ledger = _load_ledger(deploy_dir, service)
    current = ledger.get("current")
    if isinstance(current, Mapping) and current.get("tag"):
        return str(current["tag"])
    return fallback


def _service_env(
    profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str], service: str, tag: str
) -> ConcurrentStableDict[str, str]:
    """构造 compose 子进程环境：**所有**服务标签齐全（compose 会解析整份文件）。

    目标服务用新 tag；其余取各自台账当前 tag（缺失回落新 tag）。不补齐会让
    `docker compose up -d <服务>` 因其它服务镜像标签缺失直接报错。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 基础环境（含 `.env`）。
        service: 目标服务。
        tag: 目标 tag。

    Returns:
        ConcurrentStableDict[str, str]: 补齐后的子进程环境。
    """
    run_env = ConcurrentStableDict(env)
    for name in profile.services:
        run_env.set(
            profile.tag_env(name),
            tag if name == service else _ledger_tag(deploy_dir, name, tag),
        )
    return run_env


def _compose_services(
    profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str]
) -> ConcurrentStableList[str]:
    """列出 compose 文件内全部服务名。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 已补齐标签的子进程环境。

    Returns:
        ConcurrentStableList[str]: 服务名清单。
    """
    output = _compose(profile, deploy_dir, env, ConcurrentStableList(["config", "--services"]), capture=True)
    return ConcurrentStableList(line.strip() for line in output.splitlines() if line.strip())


def _up(profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str], service: str, tag: str) -> None:
    """以指定标签起（或更新）服务容器（含同镜像的 `-jobs` 容器）。"""
    run_env = _service_env(profile, deploy_dir, env, service, tag)
    targets = ConcurrentStableList([service])
    jobs = f"{service}-jobs"
    if jobs in _compose_services(profile, deploy_dir, run_env):
        targets.add(jobs)
    _compose(profile, deploy_dir, run_env, ConcurrentStableList(["up", "-d", "--no-deps", *targets]))


def _init_schema(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    service: str,
    tag: str,
    tenants: ConcurrentStableList[str],
) -> None:
    """以目标标签镜像跑一次性建表 / 迁移命令（建表先行）。"""
    run_env = _service_env(profile, deploy_dir, env, service, tag)
    for command in render_commands(profile.init_command, service=service, tenants=tenants):
        _compose_run(profile, deploy_dir, run_env, service, command)


def _deploy_one(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    service: str,
    tag: str,
    actor: str,
    *,
    skip_gateway_probe: bool = False,
) -> bool:
    """单服务部署：建表 → 起容器 → 门禁 → 台账；门禁失败自动回滚。"""
    ledger = _load_ledger(deploy_dir, service)
    raw_old_current = ledger.get("current")
    old_current = raw_old_current if isinstance(raw_old_current, Mapping) else None
    tenants = ConcurrentStableList(t for t in (env.get("BMS_DEPLOY_TENANTS", "demo,acme") or "").split(",") if t)
    print(f"[deploy] {service} → {tag}：建表先行")
    _init_schema(profile, deploy_dir, env, service, tag, tenants)
    print(f"[deploy] {service} → {tag}：起容器")
    _up(profile, deploy_dir, env, service, tag)
    if health_gate(profile, deploy_dir, env, service, skip_gateway_probe=skip_gateway_probe):
        new_ledger = rotate_ledger(ledger, tag=tag, actor=actor, at=_now())
        new_ledger.set("service", service)
        _save_ledger(deploy_dir, service, new_ledger)
        _append_log(
            deploy_dir,
            ConcurrentStableDict(
                {
                    "at": _now(),
                    "by": actor,
                    "action": "deploy",
                    "service": service,
                    "from": (old_current or {}).get("tag", ""),
                    "to": tag,
                    "result": "success",
                }
            ),
        )
        return True
    print(f"[deploy] {service} 门禁失败 → 自动回滚")
    if not old_current or not old_current.get("tag"):
        _append_log(
            deploy_dir,
            ConcurrentStableDict(
                {
                    "at": _now(),
                    "by": actor,
                    "action": "deploy",
                    "service": service,
                    "from": "",
                    "to": tag,
                    "result": "failure",
                }
            ),
        )
        return False
    old_tag = str(old_current["tag"])
    _up(profile, deploy_dir, env, service, old_tag)
    ok = health_gate(profile, deploy_dir, env, service)
    _append_log(
        deploy_dir,
        ConcurrentStableDict(
            {
                "at": _now(),
                "by": actor,
                "action": "rollback",
                "service": service,
                "from": tag,
                "to": old_tag,
                "result": "success" if ok else "failure",
            }
        ),
    )
    return False


def _rollback_one(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    service: str,
    to: str,
    actor: str,
) -> bool:
    """单服务回滚：切换上一 tag → 起容器 → 门禁 → 台账（不 downgrade）。"""
    ledger = _load_ledger(deploy_dir, service)
    target = resolve_rollback_target(ledger, to)
    raw_old_current = ledger.get("current")
    old_current = raw_old_current if isinstance(raw_old_current, Mapping) else None
    print(f"[rollback] {service} → {target}")
    _up(profile, deploy_dir, env, service, target)
    ok = health_gate(profile, deploy_dir, env, service)
    if ok:
        new_ledger = rotate_ledger(ledger, tag=target, actor=actor, at=_now())
        new_ledger.set("service", service)
        _save_ledger(deploy_dir, service, new_ledger)
    _append_log(
        deploy_dir,
        ConcurrentStableDict(
            {
                "at": _now(),
                "by": actor,
                "action": "rollback",
                "service": service,
                "from": (old_current or {}).get("tag", ""),
                "to": target,
                "result": "success" if ok else "failure",
            }
        ),
    )
    return ok


def _ensure_app_user(profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str]) -> None:
    """经 mysql 容器 root 创建应用账号并按画像的库模式授权（幂等）。"""
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
        f"GRANT ALL PRIVILEGES ON `{profile.db_grant_pattern}`.* TO '{user}'@'%'; FLUSH PRIVILEGES;"
    )
    _compose(
        profile,
        deploy_dir,
        env,
        ConcurrentStableList(
            [
                "exec",
                "-T",
                "-e",
                f"MYSQL_PWD={root_pw}",
                "mysql",
                "mysql",
                "-uroot",
                "-e",
                sql,
            ]
        ),
    )


def cmd_bootstrap(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    services: ConcurrentStableList[str],
    actor: str,
) -> int:
    """首次数据引导：建库授权 → 建表 → 种子（幂等；`services` 可限定子集）。"""
    tenants = ConcurrentStableList(t for t in (env.get("BMS_DEPLOY_TENANTS", "demo,acme") or "").split(",") if t)
    # 显式 `BMS_IMAGE_TAG` 优先于台账：首部署 / 重建库时台账还是旧版本，
    # 若按台账 tag 建表会用旧镜像（缺新列），导致随后新镜像启动失败。
    image_tag = env.get("BMS_IMAGE_TAG", "")
    if image_tag:
        for service in services:
            env.set(profile.tag_env(service), image_tag)
    print("[bootstrap] 1/4 应用账号与授权")
    _ensure_registry_login(profile, env)
    _ensure_app_user(profile, deploy_dir, env)
    print("[bootstrap] 2/4 建库（按服务 × 租户）")
    admin_url = f"mysql+aiomysql://root:{urllib.parse.quote(env.get('MYSQL_ROOT_PASSWORD', ''), safe='')}@mysql:3306"
    provision = ConcurrentStableList(["python", "-m", "ops.provision_tenant", "--admin-url", admin_url])
    for tenant in tenants:
        provision.update(["--code", tenant])
    _compose_run(profile, deploy_dir, env, _run_image_of(profile, "ops.provision_tenant"), provision)
    print("[bootstrap] 3/4 建表（按服务）")
    for service in services:
        _init_schema(profile, deploy_dir, env, service, _bootstrap_tag(profile, env, service), tenants)
    print("[bootstrap] 4/4 种子（统一编排：平台 + 产品同构声明，一个 XA 全局事务）")
    # 07B `02_03`：种子由**统一编排入口**执行（原 3 条独立脚本已并入）。
    # 约束：XA 分支要求参与方在线，故本步骤须在服务已起、未接流量时执行——
    # `bootstrap` 只建库建表，种子由 `seed` 子命令在 `deploy` 之后单独触发（见 cmd_seed）。
    print("[bootstrap] 提示：种子编排须在服务启动后执行（python3 ... seed --tenant <租户>）")
    print("[bootstrap] 完成（幂等，可重跑）")
    return 0


_RUN_IMAGE_FALLBACK = "platform"
"""`RUN_IMAGE` 为 `*` 或缺失时的回落镜像（任意镜像可运行，取 platform 与历史行为等价）。"""

_RUN_IMAGE_MODULE_PREFIX = "ops."
"""`ops` 脚本模块名前缀（`python -m ops.<script>`）。"""


def _ops_script_path(profile: Profile, module: str) -> Path:
    """取 `ops` 脚本源码路径。

    Args:
        profile: 部署画像（决定仓库根）。
        module: 模块名（`ops.seed_module`）。

    Returns:
        Path: 脚本文件路径。

    Raises:
        RuntimeError: 模块名不属 `ops` 包或脚本不存在。
    """
    if not module.startswith(_RUN_IMAGE_MODULE_PREFIX):
        raise RuntimeError(f"仅支持 ops 脚本（收到 {module!r}）")
    name = module[len(_RUN_IMAGE_MODULE_PREFIX) :].replace(".", "/")
    path = profile.repo_root / "backend" / "ops" / f"{name}.py"
    if not path.is_file():
        raise RuntimeError(f"ops 脚本不存在：{path}")
    return path


def _run_image_of(profile: Profile, module: str) -> str:
    """读取 `ops` 脚本声明的运行镜像（标准库 `ast` 静态读取，部署机无需后端虚拟环境）。

    口径：`RUN_IMAGE` 为脚本内的机器可读声明（`platform` / `tenant` / `txn` / `ci` / `*`）；
    取值为 `*` 时回落 platform 镜像（任意服务镜像均可运行该脚本）。

    Args:
        profile: 部署画像。
        module: 模块名（`ops.seed_module`）。

    Returns:
        str: 运行镜像标识（`platform` / `tenant` / `txn`）。

    Raises:
        RuntimeError: 脚本未声明 `RUN_IMAGE`、声明值非法或声明为 `ci`（无对应部署镜像）。
    """
    path = _ops_script_path(profile, module)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    declared = ""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "RUN_IMAGE" for target in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                declared = value.value
            break
    if not declared:
        raise RuntimeError(f"{module} 未声明 RUN_IMAGE（须在脚本内声明运行镜像；见 14_03）")
    if declared == "*":
        return _RUN_IMAGE_FALLBACK
    if declared == "ci":
        raise RuntimeError(f"{module} 声明 RUN_IMAGE = 'ci'（CI / 开发机专用，无部署镜像可选）")
    if declared not in ("platform", "tenant", "txn"):
        raise RuntimeError(f"{module} 的 RUN_IMAGE 声明非法：{declared!r}")
    return declared


def _bootstrap_tag(profile: Profile, env: ConcurrentStableDict[str, str], service: str) -> str:
    """bootstrap 建表所用镜像标签（缺省取 `.env` 的 BMS_IMAGE_TAG；无则报错）。"""
    tag = env.get(profile.tag_env(service)) or env.get("BMS_IMAGE_TAG", "")
    if not tag:
        raise RuntimeError(f"bootstrap 需镜像标签：请设置 BMS_IMAGE_TAG 或 {profile.tag_env(service)}")
    return tag


def cmd_seed(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    tenant: str,
    dry_run: bool,
    actor: str,
) -> int:
    """种子统一编排（07B `02_03`）：在 platform 容器内调编排端点，逐项报告。

    **为什么在 deploy 之后**：XA 分支要求参与方在线（跨服务分支经 `/api/v1/txn/branches`
    驱动），故顺序必须是「起服务 → 跑种子 → 开流量」。

    Args:
        deploy_dir: deploy 目录。
        env: 部署环境变量。
        tenant: 目标租户。
        dry_run: 只做装载 + 排序 + 冲突预检（不开事务）。
        actor: 操作者（记入日志）。

    Returns:
        int: 退出码（0 成功 / 1 冲突 / 2 执行失败 / 3 前置错误）。
    """
    mode = "（dry-run）" if dry_run else ""
    print(f"[seed] 种子统一编排：租户 {tenant}{mode}")
    args = ConcurrentStableList(["python", "-m", "ops.seed_platform", "--tenant", tenant])
    if dry_run:
        args.update(["--dry-run"])
    # 编排的业务退出码（0 成功 / 1 冲突 / 2 执行失败 / 3 前置错误）须原样透出，
    # 故关闭「非零即抛」——否则调用方拿到的是异常而非可区分的退出码。
    code = _compose_run(
        profile, deploy_dir, env, _run_image_of(profile, "ops.seed_platform"), args, raise_on_error=False
    )
    if code != 0:
        print(f"[seed] 编排未通过（退出码 {code}）：整体已回滚，无脏数据", file=sys.stderr)
        return code
    print(f"[seed] 完成（操作者 {actor}；幂等，可重跑）")
    return 0


def cmd_gateway_check(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    render: bool = False,
    stdout=print,
) -> int:
    """注册表对账 / 重渲（07B `02_06`）：platform 镜像内按注册表取数。

    - 缺省（`check`）：重渲结果与仓库生成件**逐字比对**，校验声明漂移 + 生成件忘重生成；
    - `render=True`：按注册表**写回** `deploy/gateway/apisix.yaml`（APISIX standalone 文件轮询
      自动热加载），用于「产品声明刚上报、路由尚未生成」的首次接入。

    部署流水线把「注册表是权威」落到实处：`deploy/gateway/apisix.yaml` 必须与**平台库注册表**
    的渲染结果一致（`--from-manifest` 与 `--from-registry` 产物由用例守住逐字相等）。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 部署环境变量。
        render: True 时重渲写回（False 为对账）。
        stdout: 输出函数。

    Returns:
        int: 退出码（0 一致 / 成功；1 不一致 / 注册表不可读；2 缺 platform 镜像标签）。
    """
    tag = env.get(profile.tag_env(GATEWAY_CHECK_IMAGE)) or env.get("BMS_IMAGE_TAG", "")
    if not tag:
        print(
            "错误：注册表对账需 platform 镜像标签（台账无 current 时请先设 BMS_TAG_PLATFORM / BMS_IMAGE_TAG）",
            file=sys.stderr,
        )
        return 2
    run_env = ConcurrentStableDict(env)
    run_env.set(profile.tag_env(GATEWAY_CHECK_IMAGE), tag)
    action = "重渲" if render else "对账"
    stdout(f"[gateway] 注册表{action}：platform:{tag}（--from-registry → deploy/gateway/apisix.yaml）")
    code = _compose_run(
        profile,
        deploy_dir,
        run_env,
        GATEWAY_CHECK_IMAGE,
        gateway_check_args(render=render),
        volumes=gateway_check_volumes(deploy_dir, render=render),
        raise_on_error=False,
    )
    if code != 0:
        print(
            f"[gateway] {action}未通过：注册表不可读 / 未建表，或渲染结果与仓库生成件不一致——"
            "确认平台已启动完成注册后再试",
            file=sys.stderr,
        )
        return 1
    if render:
        stdout("[gateway] 重渲完成：deploy/gateway/apisix.yaml 已按注册表写回（APISIX 文件轮询热加载）")
    else:
        stdout("[gateway] 对账通过：注册表渲染结果与仓库生成件逐字一致")
    return 0


def cmd_deploy(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    services: ConcurrentStableList[str],
    tag: str,
    actor: str,
    skip_gateway_check: bool = False,
    skip_gateway_probe: bool = False,
) -> int:
    """部署（注册表对账 → 建表 → 起容器 → 门禁 → 台账；失败自动回滚）。

    对账**前置**（fail-closed）：不一致即中止，不落任何容器；首部署（注册表尚未建立）与应急场景
    用 `--skip-gateway-check` 显式跳过，跳过会写入发布日志留痕。
    """
    if not tag:
        print("错误：deploy 必须显式 --tag（不可变标签，禁 latest）", file=sys.stderr)
        return 2
    _ensure_registry_login(profile, env)
    if skip_gateway_check:
        print("[deploy] 跳过注册表对账（--skip-gateway-check）：仅限首部署 / 应急，部署后请跑 gateway 复核")
        _append_log(
            deploy_dir,
            ConcurrentStableDict(
                {
                    "at": _now(),
                    "by": actor,
                    "action": "gateway-check",
                    "service": GATEWAY_CHECK_IMAGE,
                    "from": "",
                    "to": tag,
                    "result": "skipped",
                }
            ),
        )
    else:
        gateway_code = cmd_gateway_check(profile, deploy_dir, env)
        _append_log(
            deploy_dir,
            ConcurrentStableDict(
                {
                    "at": _now(),
                    "by": actor,
                    "action": "gateway-check",
                    "service": GATEWAY_CHECK_IMAGE,
                    "from": "",
                    "to": tag,
                    "result": "success" if gateway_code == 0 else "failure",
                }
            ),
        )
        if gateway_code != 0:
            print("[deploy] 注册表对账未通过 → 中止部署（未起任何容器）", file=sys.stderr)
            return 1
    ok = True
    for service in services:
        ok = (
            _deploy_one(
                profile,
                deploy_dir,
                env,
                service,
                tag,
                actor,
                skip_gateway_probe=skip_gateway_probe,
            )
            and ok
        )
    return 0 if ok else 1


def cmd_provision(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    services: ConcurrentStableList[str],
) -> int:
    """建库（首次部署第 ② 步）：按画像的建库命令在目标镜像内执行（幂等）。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 部署环境变量。
        services: 目标服务清单。

    Returns:
        int: 退出码（0 成功；1 建库失败；2 画像未声明建库命令）。
    """
    if not profile.provision_command:
        print("错误：当前画像未声明 --provision-command（无法建库）", file=sys.stderr)
        return 2
    tenants = ConcurrentStableList(t for t in (env.get("BMS_DEPLOY_TENANTS", "demo,acme") or "").split(",") if t)
    _ensure_registry_login(profile, env)
    code = 0
    for service in services:
        run_env = _service_env(profile, deploy_dir, env, service, env.get(profile.tag_env(service), ""))
        for command in render_commands(profile.provision_command, service=service, tenants=tenants):
            print(f"[provision] {service}：{' '.join(command)}")
            code = _compose_run(profile, deploy_dir, run_env, service, command, raise_on_error=False) or code
    return 0 if code == 0 else 1


def cmd_exec(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    service: str,
    command: ConcurrentStableList[str],
) -> int:
    """通用一次性执行（种子 / 排障）：在目标服务镜像内跑给定命令，退出码原样透出。

    Args:
        profile: 部署画像。
        deploy_dir: deploy 目录。
        env: 部署环境变量。
        service: 目标服务。
        command: 容器内命令。

    Returns:
        int: 容器内命令退出码（2 表示未给命令）。
    """
    if not command:
        print("错误：exec 需在 `--` 之后给出容器内命令", file=sys.stderr)
        return 2
    run_env = _service_env(profile, deploy_dir, env, service, env.get(profile.tag_env(service), ""))
    return _compose_run(profile, deploy_dir, run_env, service, command, raise_on_error=False)


def cmd_rollback(
    profile: Profile,
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    service: str,
    to: str,
    actor: str,
) -> int:
    """一键回滚（切换上一 tag / 指定 tag；不 downgrade）。"""
    _ensure_registry_login(profile, env)
    return 0 if _rollback_one(profile, deploy_dir, env, service, to, actor) else 1


def cmd_status(
    deploy_dir: Path,
    env: ConcurrentStableDict[str, str],
    *,
    services: ConcurrentStableList[str],
) -> int:
    """打印版本台账（当前 / 上一版本）。"""
    for service in services:
        ledger = _load_ledger(deploy_dir, service)
        raw_current = ledger.get("current")
        raw_previous = ledger.get("previous")
        current = raw_current if isinstance(raw_current, Mapping) else {}
        previous = raw_previous if isinstance(raw_previous, Mapping) else {}
        print(
            f"{service}: current={current.get('tag', '-')} "
            f"previous={previous.get('tag', '-')} "
            f"deployed_at={current.get('deployed_at', '-')}"
        )
    return 0


def cmd_prune(
    profile: Profile, deploy_dir: Path, env: ConcurrentStableDict[str, str], *, keep: int, dry_run: bool
) -> int:
    """清理超窗 SHA 标签（semver 永久保留）。"""
    api = env.get("GITLAB_API_URL", "").rstrip("/")
    token = env.get("GITLAB_API_TOKEN", "")
    project = env.get("CI_PROJECT_ID") or env.get("GITLAB_PROJECT_ID", "")
    if not api or not token or not project:
        print(
            "错误：prune 需 GITLAB_API_URL / GITLAB_API_TOKEN / CI_PROJECT_ID（读 deploy/.env）",
            file=sys.stderr,
        )
        return 2
    headers = ConcurrentStableDict({"PRIVATE-TOKEN": token})
    repos = _api_get(f"{api}/projects/{project}/registry/repositories?per_page=100", headers)
    total = 0
    for service in profile.services:
        repo = _find_repo(repos, service)
        if repo is None:
            continue
        tags = _api_get(
            f"{api}/projects/{project}/registry/repositories/{repo['id']}/tags?per_page=100",
            headers,
        )
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


def _find_repo(
    repos: ConcurrentStableList[ConcurrentStableDict[str, object]], service: str
) -> ConcurrentStableDict[str, object] | None:
    """从 Registry 仓库列表定位服务镜像仓库（按路径后缀匹配）。"""
    for repo in repos:
        path = str(repo.get("path", ""))
        if path.endswith(f"/bms-{service}") or path == f"bms-{service}":
            return repo
    return None


def _api_get(
    url: str, headers: ConcurrentStableDict[str, str]
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """GET JSON 数组（GitLab API）。"""
    req = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    if not isinstance(data, list):
        return items
    for item in data:
        if isinstance(item, dict):
            items.add(_to_stable(item))
    return items


def _api_delete(url: str, headers: ConcurrentStableDict[str, str]) -> None:
    """DELETE（GitLab Registry 标签删除）。"""
    req = urllib.request.Request(url, headers=dict(headers), method="DELETE")
    with urllib.request.urlopen(req, timeout=30):
        pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _parse_args(argv: ConcurrentStableList[str] | None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="BMS 服务部署 / 回滚 / 门禁 / 数据引导 CLI（09_02）")
    # ---- 部署画像（产品仓复用同一入口时只给值，不写产品字面量）----
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="仓库根（`ops` 脚本定位；默认脚本所在仓）")
    parser.add_argument("--deploy-dir", default="", help="deploy 目录（默认 <repo-root>/deploy）")
    parser.add_argument("--env-file", default="", help="环境变量文件（默认 <deploy-dir>/.env）")
    parser.add_argument("--compose-file", default=COMPOSE_FILE, help=f"compose 文件（默认 {COMPOSE_FILE}）")
    parser.add_argument(
        "--services",
        default=",".join(SERVICES),
        help="需补齐镜像标签的服务全集（逗号分隔；产品部署传自己的服务键）",
    )
    parser.add_argument(
        "--container-name",
        default="bms-{service}",
        help="容器名模板（默认 bms-{service}；产品镜像常与 compose 服务同名，传 {service}）",
    )
    parser.add_argument(
        "--tag-env",
        default="BMS_TAG_{SERVICE}",
        help="镜像标签环境变量名模板（默认 BMS_TAG_{SERVICE}）",
    )
    parser.add_argument(
        "--image-prefix-env",
        default="REGISTRY_IMAGE_PREFIX",
        help="镜像前缀环境变量名（默认 REGISTRY_IMAGE_PREFIX）",
    )
    parser.add_argument("--health-path", default="/readyz", help="容器内就绪探测路径（默认 /readyz）")
    parser.add_argument(
        "--gateway-path",
        default=GATEWAY_SMOKE_PATH,
        help=f"网关冒烟路径模板（默认 {GATEWAY_SMOKE_PATH}）",
    )
    parser.add_argument(
        "--init-command",
        default="python -m ops.init_schema --service {service} {tenants_or_all}",
        help="建表 / 迁移命令模板（占位符 {service} / {tenant} / {tenants} / {tenants_or_all}）",
    )
    parser.add_argument(
        "--provision-command",
        default="",
        help="建库命令模板（同上占位符；缺省不支持 provision）",
    )
    parser.add_argument("--db-grant-pattern", default="bms\\_%", help="应用账号授权库模式（bootstrap 用）")
    parser.add_argument(
        "--actor",
        default=os.environ.get("USER", "unknown"),
        help="操作者（记入台账 / 日志）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="一次性数据引导（建库 + 建表 + 种子）")
    bootstrap.add_argument(
        "--service",
        action="append",
        default=[],
        help="限定服务（可重复；缺省全部启用服务）",
    )

    deploy = sub.add_parser("deploy", help="部署（注册表对账 → 建表 → 起容器 → 门禁 → 台账）")
    deploy.add_argument("--service", help="目标服务")
    deploy.add_argument("--all", action="store_true", help="全部已启用服务")
    deploy.add_argument("--tag", default="", help="目标镜像标签（必填；禁 latest）")
    deploy.add_argument(
        "--skip-gateway-check",
        action="store_true",
        help="跳过注册表对账（仅限首部署 / 应急；跳过记入发布日志）",
    )
    deploy.add_argument(
        "--skip-gateway-probe",
        action="store_true",
        help="容器门禁跳过「网关可达」探测（首部署路由尚未生成时用）",
    )

    provision = sub.add_parser("provision", help="建库（按 --provision-command；仅首部署）")
    provision.add_argument("--service", help="目标服务（缺省首位服务）")

    gateway = sub.add_parser("gateway", help="注册表对账 / 重渲（platform 镜像内 --from-registry）")
    gateway.add_argument("--render", action="store_true", help="按注册表重渲并写回生成件（APISIX 热加载）")

    seed = sub.add_parser("seed", help="种子统一编排（须在 deploy 之后执行；一个 XA 全局事务）")
    seed.add_argument("--tenant", required=True, help="目标租户")
    seed.add_argument("--dry-run", action="store_true", help="只做装载 + 排序 + 冲突预检")

    exec_parser = sub.add_parser("exec", help="在目标服务镜像内执行一次性命令（种子 / 排障）")
    exec_parser.add_argument("--service", required=True, help="目标服务")
    exec_parser.add_argument("exec_command", nargs=argparse.REMAINDER, help="容器内命令（`--` 之后）")

    rollback = sub.add_parser("rollback", help="一键回滚（切换上一 tag / --to）")
    rollback.add_argument("--service", required=True, help="目标服务")
    rollback.add_argument("--to", default="", help="目标标签（缺省取台账上一版本）")

    status = sub.add_parser("status", help="打印版本台账")
    status.add_argument("--service", help="目标服务（缺省全部）")

    gate = sub.add_parser("health-gate", help="单独跑健康门禁")
    gate.add_argument("--service", required=True, help="目标服务")
    gate.add_argument(
        "--skip-gateway-probe",
        action="store_true",
        help="跳过「网关可达」探测（只验容器健康 + 就绪端点）",
    )

    prune = sub.add_parser("prune", help="清理超窗 SHA 标签（semver 永久保留）")
    prune.add_argument(
        "--keep",
        type=int,
        default=int(os.environ.get("BMS_KEEP_SHA_TAGS", "30")),
        help="SHA 标签保留数",
    )
    prune.add_argument("--dry-run", action="store_true", help="只列出将删除的标签")
    return parser.parse_args(argv)


def _profile_of(args: argparse.Namespace) -> Profile:
    """由命令行参数构造部署画像。

    Args:
        args: 命令行参数。

    Returns:
        Profile: 部署画像。

    Raises:
        ValueError: 服务清单为空（`--all` 时以 compose 内服务为准，由调用方补齐）。
    """
    return Profile(
        repo_root=Path(args.repo_root).resolve(),
        compose_file=args.compose_file,
        services=ConcurrentStableFrozenList(item for item in args.services.split(",") if item),
        container_template=args.container_name,
        tag_env_template=args.tag_env,
        image_prefix_env=args.image_prefix_env,
        health_path=args.health_path,
        gateway_path_template=args.gateway_path,
        init_command=ConcurrentStableFrozenList(shlex.split(args.init_command)),
        provision_command=ConcurrentStableFrozenList(
            shlex.split(args.provision_command) if args.provision_command else []
        ),
        db_grant_pattern=args.db_grant_pattern,
    )


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """CLI 入口。"""
    args = _parse_args(argv)
    profile = _profile_of(args)
    deploy_dir = Path(args.deploy_dir).resolve() if args.deploy_dir else profile.repo_root / "deploy"
    env_file = Path(args.env_file) if args.env_file else deploy_dir / ".env"
    if not deploy_dir.is_dir():
        print(f"错误：deploy 目录不存在：{deploy_dir}", file=sys.stderr)
        return 2
    env = _fill_service_tags(profile, deploy_dir, _base_env(env_file))
    try:
        if args.command == "bootstrap":
            services = ConcurrentStableList(args.service) if args.service else ConcurrentStableList(profile.services)
            return cmd_bootstrap(profile, deploy_dir, env, services=services, actor=args.actor)
        if args.command == "deploy":
            if args.all:
                services = _compose_services(profile, deploy_dir, _fill_service_tags(profile, deploy_dir, env))
            else:
                services = ConcurrentStableList([args.service]) if args.service else ConcurrentStableList()
            if not services:
                print("错误：deploy 需 --service 或 --all", file=sys.stderr)
                return 2
            return cmd_deploy(
                profile,
                deploy_dir,
                env,
                services=services,
                tag=args.tag,
                actor=args.actor,
                skip_gateway_check=args.skip_gateway_check,
                skip_gateway_probe=args.skip_gateway_probe,
            )
        if args.command == "provision":
            services = (
                ConcurrentStableList([args.service]) if args.service else ConcurrentStableList(profile.services[:1])
            )
            return cmd_provision(profile, deploy_dir, env, services=services)
        if args.command == "gateway":
            return cmd_gateway_check(profile, deploy_dir, env, render=args.render)
        if args.command == "seed":
            return cmd_seed(
                profile,
                deploy_dir,
                env,
                tenant=args.tenant,
                dry_run=args.dry_run,
                actor=args.actor,
            )
        if args.command == "exec":
            command = ConcurrentStableList(item for item in args.exec_command if item != "--")
            return cmd_exec(profile, deploy_dir, env, service=args.service, command=command)
        if args.command == "rollback":
            return cmd_rollback(profile, deploy_dir, env, service=args.service, to=args.to, actor=args.actor)
        if args.command == "status":
            services = ConcurrentStableList([args.service]) if args.service else ConcurrentStableList(profile.services)
            return cmd_status(deploy_dir, env, services=services)
        if args.command == "health-gate":
            return (
                0
                if health_gate(
                    profile,
                    deploy_dir,
                    env,
                    args.service,
                    skip_gateway_probe=args.skip_gateway_probe,
                )
                else 1
            )
        if args.command == "prune":
            return cmd_prune(profile, deploy_dir, env, keep=args.keep, dry_run=args.dry_run)
    except (RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""部署入口（`scripts/tools/deploy/release.py`）的画像与命令模板纯逻辑用例。

口径（mdm `01_07` 跨仓协同）：产品仓复用同一发布入口时**只给通用参数**，命令实现不出现产品字面量；
本套用例锁三件事——① 缺省画像与 bms 现役行为逐字一致（防回归）；② 占位符展开语义（`{tenant}` 逐租户 /
`{tenants}` 拼 `--code` / `{tenants_or_all}` 空集回落 `--all-tenants`）；③ 产品参数可被解析且服务不再受限。

真机路径（docker compose 起容器 / 门禁探测）归部署窗口复验，不在本套用例覆盖范围。
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList

_REPO_ROOT = Path(__file__).resolve().parents[5]
"""bms 仓库根（本文件位于 `backend/libs/bms_core/tests/ops/`，上溯 5 级）。"""


def _load_release() -> ModuleType:
    """按路径加载部署入口（不经包导入，避免与 `ops.release` 同名混淆）。

    Returns:
        ModuleType: 已加载模块。
    """
    path = _REPO_ROOT / "scripts" / "tools" / "deploy" / "release.py"
    spec = importlib.util.spec_from_file_location("deploy_release_entry", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _load_release()


def test_default_profile_matches_bms_behaviour() -> None:
    """缺省画像 = bms 现役口径（compose / 容器名 / 标签变量 / 就绪路径 / 网关路径 / 建表命令）。"""
    profile = release.Profile()
    assert profile.compose_file == "compose/bms.yml"
    assert profile.container_name("platform") == "bms-platform"
    assert profile.tag_env("platform") == "BMS_TAG_PLATFORM"
    assert profile.image_prefix_env == "REGISTRY_IMAGE_PREFIX"
    assert profile.health_path == "/readyz"
    assert profile.gateway_path("platform") == "/api/platform/v1/__gate__"
    assert list(profile.provision_command) == []
    assert list(profile.init_command) == [
        "python",
        "-m",
        "ops.init_schema",
        "--service",
        "{service}",
        "{tenants_or_all}",
    ]


def test_product_profile_renders_service_keys() -> None:
    """产品画像：容器名 / 标签变量 / 网关路径按给定模板渲染，不依赖任何产品字面量。"""
    profile = release.Profile(
        services=ConcurrentStableFrozenList(["mdm"]),
        container_template="mdm",
        tag_env_template="MDM_TAG",
        image_prefix_env="MDM_REGISTRY_IMAGE_PREFIX",
        gateway_path_template="/api/mdm/v1/mdm/__gate__",
        init_command=ConcurrentStableFrozenList(["python", "-m", "ops.migrate", "{tenants}"]),
        provision_command=ConcurrentStableFrozenList(["python", "-m", "ops.provision", "{tenants}"]),
    )
    assert profile.container_name("mdm") == "mdm"
    assert profile.tag_env("mdm") == "MDM_TAG"
    assert profile.gateway_path("mdm") == "/api/mdm/v1/mdm/__gate__"
    assert list(profile.provision_command) == ["python", "-m", "ops.provision", "{tenants}"]


def test_render_commands_expands_tenant_placeholders() -> None:
    """占位符展开：`{tenants}` 拼 `--code`；`{tenants_or_all}` 空集回落 `--all-tenants`；`{tenant}` 逐租户一条。"""
    tenants = ConcurrentStableList(["demo", "acme"])
    assert release.render_commands(
        ConcurrentStableFrozenList(["python", "-m", "ops.migrate", "{tenants}"]), service="mdm", tenants=tenants
    ) == [["python", "-m", "ops.migrate", "--code", "demo", "--code", "acme"]]
    assert release.render_commands(
        ConcurrentStableFrozenList(["python", "-m", "ops.init_schema", "--service", "{service}", "{tenants_or_all}"]),
        service="platform",
        tenants=tenants,
    ) == [["python", "-m", "ops.init_schema", "--service", "platform", "--code", "demo", "--code", "acme"]]
    assert release.render_commands(
        ConcurrentStableFrozenList(["python", "-m", "ops.init_schema", "--service", "{service}", "{tenants_or_all}"]),
        service="platform",
        tenants=ConcurrentStableList(),
    ) == [["python", "-m", "ops.init_schema", "--service", "platform", "--all-tenants"]]
    assert release.render_commands(
        ConcurrentStableFrozenList(["python", "-m", "ops.x", "--code", "{tenant}"]),
        service="mdm",
        tenants=tenants,
    ) == [["python", "-m", "ops.x", "--code", "demo"], ["python", "-m", "ops.x", "--code", "acme"]]


def test_gateway_args_and_volumes_by_mode() -> None:
    """注册表取数两档：`check` 只读挂载，`render` 读写挂载且子命令切 render。"""
    assert list(release.gateway_check_args()) == [
        "python",
        "-m",
        "ops.gateway_config",
        "check",
        "--from-registry",
        "--root",
        release.GATEWAY_CHECK_ROOT,
    ]
    assert list(release.gateway_check_args(render=True))[3] == "render"
    deploy_dir = Path("/tmp/deploy")
    assert list(release.gateway_check_volumes(deploy_dir)) == [
        f"{deploy_dir.resolve()}:{release.GATEWAY_CHECK_ROOT}/deploy:ro"
    ]
    assert list(release.gateway_check_volumes(deploy_dir, render=True)) == [
        f"{deploy_dir.resolve()}:{release.GATEWAY_CHECK_ROOT}/deploy"
    ]


def test_parser_accepts_product_parameters() -> None:
    """参数解析：产品参数齐备时画像按下发值构造，且 `--service` 不再受平台服务清单限制。"""
    args = release._parse_args(  # pyright: ignore[reportPrivateUsage]
        [
            "--repo-root",
            "/srv/mdm",
            "--deploy-dir",
            "/srv/mdm/deploy",
            "--compose-file",
            "compose/mdm.yml",
            "--services",
            "mdm",
            "--container-name",
            "mdm",
            "--tag-env",
            "MDM_TAG",
            "--image-prefix-env",
            "MDM_REGISTRY_IMAGE_PREFIX",
            "--health-path",
            "/healthz",
            "--gateway-path",
            "/api/mdm/v1/mdm/__gate__",
            "--init-command",
            "python -m ops.migrate {tenants}",
            "--provision-command",
            "python -m ops.provision {tenants}",
            "--db-grant-pattern",
            "mdm\\_%",
            "deploy",
            "--service",
            "mdm",
            "--tag",
            "abc1234",
            "--skip-gateway-check",
            "--skip-gateway-probe",
        ]
    )
    profile = release._profile_of(args)  # pyright: ignore[reportPrivateUsage]
    assert args.command == "deploy"
    assert args.service == "mdm"
    assert args.skip_gateway_probe is True
    assert list(profile.services) == ["mdm"]
    assert profile.container_name("mdm") == "mdm"
    assert profile.health_path == "/healthz"
    assert profile.db_grant_pattern == "mdm\\_%"
    assert list(profile.init_command) == ["python", "-m", "ops.migrate", "{tenants}"]
    assert list(profile.provision_command) == ["python", "-m", "ops.provision", "{tenants}"]


def test_exec_remainder_strips_separator() -> None:
    """`exec` 子命令：`--` 之后命令按 REMAINDER 收下（分隔符由调用方剥离）。"""
    args = release._parse_args(  # pyright: ignore[reportPrivateUsage]
        ["exec", "--service", "mdm", "--", "python", "-m", "ops.seed_platform", "--tenant", "demo"]
    )
    assert args.command == "exec"
    assert [item for item in args.exec_command if item != "--"] == [
        "python",
        "-m",
        "ops.seed_platform",
        "--tenant",
        "demo",
    ]


def test_deploy_requires_tag_not_latest() -> None:
    """部署缺 tag 即拒绝（不可变标签口径，不回落 latest）。"""
    assert (
        release.cmd_deploy(
            release.Profile(),
            Path("/tmp/deploy"),
            ConcurrentStableDict(),
            services=ConcurrentStableList(["platform"]),
            tag="",
            actor="tester",
        )
        == 2
    )


@pytest.mark.parametrize("keep", [0, -1])
def test_prune_keep_non_positive_disables(keep: int) -> None:
    """标签清理：`keep <= 0` 不清理（semver 与 SHA 全部保留）。"""
    tags = ConcurrentStableList([ConcurrentStableDict({"name": "abc1234", "created_at": "2026-01-01"})])
    assert list(release.select_prunable_tags(tags, keep)) == []

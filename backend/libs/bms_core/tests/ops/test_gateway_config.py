"""网关声明式配置 CLI 测试（render / check 零漂移 + 请求体上限三方一致）。Kiwi 2165 / 2264。"""

import asyncio
import runpy
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

import ops.gateway_config as gateway_config
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.services.gateway_catalog import render_apisix_yaml


def _seed_body_size(
    root: Path,
    *,
    template_variable: bool = True,
    compose_default: str | None = "32m",
    apisix_value: str = "32m",
    env_value: str = "32m",
) -> None:
    """在临时仓库根写出请求体上限四方文件（04-1-2）。

    Args:
        root: 临时仓库根。
        template_variable: 模板是否以变量化声明（False 即硬编码，用于负例）。
        compose_default: 编排缺省值（None 即不给缺省，用于负例）。
        apisix_value: APISIX 配置值。
        env_value: 环境变量模板值。
    """
    template = root / gateway_config.NGINX_TEMPLATE_RELATIVE
    template.parent.mkdir(parents=True, exist_ok=True)
    size_line = "client_max_body_size ${GATEWAY_MAX_BODY_SIZE};" if template_variable else "client_max_body_size 32m;"
    template.write_text(f"server {{\n    location /api/ {{\n        {size_line}\n    }}\n}}\n", encoding="utf-8")

    compose = root / gateway_config.COMPOSE_GATEWAY_RELATIVE
    compose.parent.mkdir(parents=True, exist_ok=True)
    default_expr = (
        f"${{GATEWAY_MAX_BODY_SIZE:-{compose_default}}}" if compose_default is not None else "${GATEWAY_MAX_BODY_SIZE}"
    )
    compose.write_text(
        f"services:\n  gateway-nginx:\n    environment:\n      GATEWAY_MAX_BODY_SIZE: {default_expr}\n",
        encoding="utf-8",
    )

    apisix = root / gateway_config.APISIX_CONFIG_RELATIVE
    apisix.write_text(f'nginx_config:\n  http:\n    client_max_body_size: "{apisix_value}"\n', encoding="utf-8")

    env_example = root / gateway_config.ENV_EXAMPLE_RELATIVE
    env_example.parent.mkdir(parents=True, exist_ok=True)
    env_example.write_text(f"GATEWAY_MAX_BODY_SIZE={env_value}\n", encoding="utf-8")


@pytest.mark.kiwi_id(2165)
def test_render_and_check_roundtrip(tmp_path: Path) -> None:
    """render 写出生成件；check 对生成件通过（零漂移 + 请求体上限三方一致）。"""
    _seed_body_size(tmp_path)
    assert gateway_config.main(ConcurrentStableList(["render", "--root", str(tmp_path)])) == 0
    assert gateway_config.config_path(tmp_path).read_text(encoding="utf-8") == render_apisix_yaml()
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 0


def _seed_registry(url: str, *, default_units: ConcurrentStableDict[str, str] | None = None) -> None:
    """把本仓平台清单写进临时库注册表，并写入默认拓扑行（等价于「平台启动已完成注册」）。

    Args:
        url: 平台库连接串。
        default_units: 默认拓扑的「域 → 单元」覆盖（None 表示按域登记面派生：域 → 承载服务）。
    """
    import importlib

    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.ext.asyncio import async_sessionmaker as _maker
    from sqlalchemy.ext.asyncio import create_async_engine as _create

    importlib.import_module("bms_core.models.platform.tenant_topology")  # 建表前导入模型（拓扑表参与 create_all）
    from bms_core.models.base import BaseModel
    from bms_core.registry.declarations import RegistrySnapshot, from_manifest, plan_declarations
    from bms_core.registry.products import load_product_manifest, local_manifest_paths
    from bms_core.services.module_registry import domain_service_view
    from bms_platform.domains.platform_registry.repositories.declaration_repository import (
        DeclarationRepository,
    )

    async def _run() -> None:
        """建表、把平台清单落库并写默认拓扑行（在同步入口内跑一次事件循环）。"""
        engine = _create(url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(BaseModel.metadata.create_all)
            factory: _maker[_AsyncSession] = _maker(engine, expire_on_commit=False)
            manifest_path = next(item for item in local_manifest_paths() if item.name == "platform.toml")
            payload = from_manifest(load_product_manifest(manifest_path))
            async with factory() as session:
                plan, conflicts = plan_declarations(payload, RegistrySnapshot())
                assert list(conflicts) == []
                await DeclarationRepository(session).apply(plan, product_key=payload.product_key)
                await session.commit()
            units = ConcurrentStableDict(domain_service_view().to_list()) if default_units is None else default_units
            async with engine.begin() as connection:
                for index, (domain, unit) in enumerate(units.items(), start=1):
                    await connection.execute(
                        text(
                            "INSERT INTO sys_tenant_topology (id, tenant_id, domain_key, unit_key, "
                            "topology_version, status, created_at, updated_at, version) VALUES "
                            "(:id, 0, :domain, :unit, 1, 'enabled', '2026-10-30 00:00:00', "
                            "'2026-10-30 00:00:00', 0)"
                        ),
                        {"id": index, "domain": domain, "unit": unit},
                    )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.kiwi_id(2165)
def test_registry_source_matches_manifest_source(tmp_path: Path) -> None:
    """两档取数产物一致：注册表模式与清单模式渲染出的网关配置逐字相同。"""
    gateway_config.load_registries(gateway_config.REPO_ROOT)
    expected = render_apisix_yaml()

    url = f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}"
    _seed_registry(url)

    assert list(gateway_config.load_registries_from_db(url)) == []
    assert render_apisix_yaml() == expected


@pytest.mark.kiwi_id(2165)
def test_registry_source_requires_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--from-registry` 未给 --url 且按配置解析失败：退出码 1 且提示补参。"""

    def _boom() -> str:
        raise RuntimeError("配置缺 BMS_DATABASE__PLATFORM__URL_TEMPLATE")

    monkeypatch.setattr(gateway_config, "default_platform_url", _boom)
    assert gateway_config.main(ConcurrentStableList(["render", "--from-registry", "--root", str(tmp_path)])) == 1
    err = capsys.readouterr().err
    assert "--from-registry 未给 --url" in err
    assert "BMS_DATABASE__PLATFORM__URL_TEMPLATE" in err


@pytest.mark.kiwi_id(2165)
def test_registry_source_default_url_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--from-registry` 省略 --url：按配置解析平台库并取数（产物与清单模式一致）。"""
    gateway_config.load_registries(gateway_config.REPO_ROOT)
    expected = render_apisix_yaml()

    url = f"sqlite+aiosqlite:///{tmp_path / 'default-url.db'}"
    _seed_registry(url)
    monkeypatch.setattr(gateway_config, "default_platform_url", lambda: url)

    assert gateway_config.render(tmp_path, source="registry") == 0
    assert gateway_config.config_path(tmp_path).read_text(encoding="utf-8") == expected


@pytest.mark.kiwi_id(2165)
def test_registry_source_empty_default_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """按配置解析得到空连接串：退出码 1 且明示「解析为空」（不静默连库）。"""
    monkeypatch.setattr(gateway_config, "default_platform_url", lambda: "")
    assert gateway_config.render(tmp_path, source="registry") == 1
    assert "按配置解析得到空连接串" in capsys.readouterr().err


@pytest.mark.kiwi_id(2165)
def test_default_platform_url_uses_platform_service_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺省 URL 解析与 `ops.check_modules` 同口径：按平台库键解析（含密码）。"""
    calls: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()

    def _fake_resolve(url: str, *, service: str) -> str:
        calls.add((url, service))
        return "mysql+aiomysql://u:p@h:3306/bms_platform"

    import bms_core.db.keys as db_keys
    import bms_core.tenant.seed.tenant as seed_tenant

    monkeypatch.setattr(db_keys, "PLATFORM_SERVICE_KEY", "platform")
    monkeypatch.setattr(seed_tenant, "resolve_url", _fake_resolve)
    assert gateway_config.default_platform_url() == "mysql+aiomysql://u:p@h:3306/bms_platform"
    assert list(calls) == [("", "platform")]


@pytest.mark.kiwi_id(2165)
def test_registry_source_reports_unreadable_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """注册表不可读：退出码 1 且提示改用清单模式（不静默降级）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'missing-dir' / 'nope.db'}"

    assert gateway_config.render(tmp_path, source="registry", url=url) == 1
    assert "注册表不可读" in capsys.readouterr().err


@pytest.mark.kiwi_id(2165)
def test_check_registry_source_reports_unreadable_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """check 走注册表模式且库不可读：退出码 1 且给出明细。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'missing-dir' / 'check.db'}"

    assert gateway_config.check(tmp_path, source="registry", url=url) == 1
    assert "注册表不可读" in capsys.readouterr().err


@pytest.mark.kiwi_id(2165)
def test_check_registry_source_requires_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """check 走注册表模式且按配置解析失败：退出码 1 且提示补参。"""

    def _boom() -> str:
        raise RuntimeError("库键非法")

    monkeypatch.setattr(gateway_config, "default_platform_url", _boom)
    assert gateway_config.main(ConcurrentStableList(["check", "--from-registry", "--root", str(tmp_path)])) == 1
    assert "--from-registry 未给 --url" in capsys.readouterr().err


@pytest.mark.kiwi_id(2165)
def test_render_print_outputs_content(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """render --print 打印生成内容，同时写出文件。"""
    assert gateway_config.main(ConcurrentStableList(["render", "--print", "--root", str(tmp_path)])) == 0
    assert render_apisix_yaml() in capsys.readouterr().out
    assert gateway_config.config_path(tmp_path).is_file()


@pytest.mark.kiwi_id(2165)
def test_check_missing_file_fails(tmp_path: Path) -> None:
    """生成件缺失时 check 退出码非 0。"""
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2165)
def test_check_drift_fails(tmp_path: Path) -> None:
    """生成件被篡改（与服务目录漂移）时 check 退出码非 0。"""
    target = gateway_config.config_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_apisix_yaml().replace("platform", "platform-x"), encoding="utf-8")
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2165)
def test_committed_config_in_sync() -> None:
    """仓库内 deploy/gateway/apisix.yaml 与服务目录（含本仓 `deploy/registry/*.toml` 自动发现）零漂移。"""
    assert gateway_config.check(gateway_config.REPO_ROOT) == 0


@pytest.mark.kiwi_id(2167)
def test_check_blocks_hardcoded_ip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check 在服务发现校验失败（硬编码 IP）时退出码非 0。"""
    assert gateway_config.main(ConcurrentStableList(["render", "--root", str(tmp_path)])) == 0

    def _fake(config: ConcurrentStableDict[str, object]) -> ConcurrentStableList[str]:
        return ConcurrentStableList(["上游 platform 节点为硬编码 IP：10.0.0.5:8000"])

    monkeypatch.setattr(gateway_config, "validate_service_discovery", _fake)
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2165)
def test_module_main_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ops.gateway_config` 入口（__main__ 守卫）可执行。"""
    _seed_body_size(tmp_path)
    assert gateway_config.render(tmp_path) == 0
    monkeypatch.setattr(sys, "argv", ["gateway_config", "check", "--root", str(tmp_path)])
    monkeypatch.delitem(sys.modules, "ops.gateway_config", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("ops.gateway_config", run_name="__main__")
    assert excinfo.value.code == 0


@pytest.mark.kiwi_id(2264)
def test_body_size_repo_passes_and_parse_size() -> None:
    """仓库内请求体上限三方一致且 ≥ 文件上传整包上限；体积字面量解析支持 k/m/g 与纯字节。"""
    assert gateway_config.validate_body_size(gateway_config.REPO_ROOT) == []

    assert gateway_config.parse_size("32m") == 32 * 1024 * 1024
    assert gateway_config.parse_size("1024k") == 1024 * 1024
    assert gateway_config.parse_size("1g") == 1024 * 1024 * 1024
    assert gateway_config.parse_size("20971520") == gateway_config.UPLOAD_MAX_SIZE_BYTES
    assert gateway_config.parse_size("32mq") is None
    assert gateway_config.parse_size("") is None


@pytest.mark.kiwi_id(2264)
def test_body_size_template_literal_rejected(tmp_path: Path) -> None:
    """边缘模板硬编码请求体上限（未变量化）即违规。"""
    _seed_body_size(tmp_path, template_variable=False)

    problems = gateway_config.validate_body_size(tmp_path)

    assert any("GATEWAY_MAX_BODY_SIZE" in item for item in problems)
    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1


@pytest.mark.kiwi_id(2264)
def test_body_size_cross_file_mismatch_rejected(tmp_path: Path) -> None:
    """APISIX / 环境变量模板与编排缺省值不一致即违规。"""
    _seed_body_size(tmp_path, apisix_value="24m")
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("APISIX 请求体上限" in item and "不一致" in item for item in problems)

    _seed_body_size(tmp_path, env_value="64m")
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("环境变量模板" in item for item in problems)


@pytest.mark.kiwi_id(2264)
def test_body_size_missing_default_or_below_upload_limit_rejected(tmp_path: Path) -> None:
    """编排未给缺省值、或上限低于文件上传整包上限（20MB）即违规。"""
    _seed_body_size(tmp_path, compose_default=None)
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("须为 GATEWAY_MAX_BODY_SIZE 提供缺省值" in item for item in problems)

    _seed_body_size(tmp_path, compose_default="16m", apisix_value="16m", env_value="16m")
    problems = gateway_config.validate_body_size(tmp_path)
    assert any("小于文件上传整包上限 20MB" in item for item in problems)


@pytest.mark.kiwi_id(2264)
def test_check_reports_body_size_problem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """check 在请求体上限口径违规时退出码非 0 且给出说明。"""
    _seed_body_size(tmp_path, apisix_value="8m")
    assert gateway_config.main(ConcurrentStableList(["render", "--root", str(tmp_path)])) == 0

    assert gateway_config.main(ConcurrentStableList(["check", "--root", str(tmp_path)])) == 1
    assert "请求体上限校验失败" in capsys.readouterr().err


def test_load_topology_from_db_maps_units_and_status(tmp_path: Path) -> None:
    """拓扑读面：默认租户当前版本行 → 域 / 单元 / 状态（停用域保留状态，供网关跳过生成）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'units.db'}"
    _seed_registry(url, default_units=ConcurrentStableDict({"org": "grpops", "role": "platform"}))
    asyncio.run(_disable_domain(url, domain="role"))

    topology, warnings = gateway_config.load_topology_from_db(url)

    assert {domain: target.unit_key for domain, target in topology.items()} == {
        "org": "grpops",
        "role": "platform",
    }
    assert not topology["role"].enabled, "停用域保留状态（生成时跳过）"
    assert list(warnings) == []


def test_registry_source_warns_on_tenant_deviation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """其它租户把某域迁到别的单元：边缘只用默认拓扑，故只告警不失败（按租户路由属开放项）。"""
    _seed_body_size(tmp_path)
    url = f"sqlite+aiosqlite:///{tmp_path / 'deviation.db'}"
    _seed_registry(url, default_units=ConcurrentStableDict({"role": "platform"}))
    asyncio.run(_insert_tenant_row(url, tenant_id=7, domain="role", unit="grpops"))

    assert gateway_config.render(tmp_path, source="registry", url=url) == 0
    assert gateway_config.check(tmp_path, source="registry", url=url) == 0, "生成件与默认拓扑一致即通过"
    err = capsys.readouterr().err
    assert "租户 7 的业务域 role 位于单元 grpops" in err


def test_registry_source_falls_back_when_topology_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """平台默认拓扑为空（尚未自举）：告警并要求，退回域登记面派生（不静默错址、也不误拒）。"""
    _seed_body_size(tmp_path)
    url = f"sqlite+aiosqlite:///{tmp_path / 'empty-topology.db'}"
    _seed_registry(url, default_units=ConcurrentStableDict())

    assert gateway_config.render(tmp_path, source="registry", url=url) == 0
    assert "平台默认拓扑为空" in capsys.readouterr().err


async def _insert_tenant_row(url: str, *, tenant_id: int, domain: str, unit: str) -> None:
    """插入一条非默认租户的当前版本拓扑行。

    Args:
        url: 平台库连接串。
        tenant_id: 租户主键。
        domain: 业务域标识。
        unit: 部署单元标识。
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO sys_tenant_topology (id, tenant_id, domain_key, unit_key, topology_version, "
                    "status, created_at, updated_at, version) VALUES "
                    "(:id, :tenant, :domain, :unit, 1, 'enabled', '2026-10-30 00:00:00', "
                    "'2026-10-30 00:00:00', 0)"
                ),
                {"id": 900 + tenant_id, "tenant": tenant_id, "domain": domain, "unit": unit},
            )
    finally:
        await engine.dispose()


async def _disable_domain(url: str, *, domain: str) -> None:
    """把默认拓扑中某域置为停用（模拟 `disabled` 拓扑行）。

    Args:
        url: 平台库连接串。
        domain: 业务域标识。
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE sys_tenant_topology SET status = 'disabled' WHERE domain_key = :domain"),
                {"domain": domain},
            )
    finally:
        await engine.dispose()


def test_load_reports_topology_read_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """注册表可读但拓扑不可读：退出码 1 并明示「平台拓扑不可读」（不静默按默认拓扑生成）。"""
    _seed_body_size(tmp_path)
    url = f"sqlite+aiosqlite:///{tmp_path / 'broken-topology.db'}"
    _seed_registry(url)

    def _boom(_url: str) -> object:
        """模拟拓扑读面异常。

        Args:
            _url: 连接串（未使用）。

        Returns:
            object: 不会返回。

        Raises:
            RuntimeError: 恒定抛出。
        """
        raise RuntimeError("topology unavailable")

    monkeypatch.setattr(gateway_config, "load_topology_from_db", _boom)

    assert gateway_config.render(tmp_path, source="registry", url=url) == 1
    assert "平台拓扑不可读" in capsys.readouterr().err


def test_load_topology_ignores_tenant_domain_absent_from_default(tmp_path: Path) -> None:
    """租户有、默认拓扑没有的域：不算偏离（不告警），避免把新接入域报成迁移。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'extra-domain.db'}"
    _seed_registry(url, default_units=ConcurrentStableDict({"role": "platform"}))
    asyncio.run(_insert_tenant_row(url, tenant_id=9, domain="brand_new", unit="grpops"))

    _topology, warnings = gateway_config.load_topology_from_db(url)

    assert list(warnings) == []


def test_resolve_manifests_normalizes_relative_and_absolute(tmp_path: Path) -> None:
    """`--manifest` 路径规整：相对路径锚 `backend/`，绝对路径原样保留。"""
    root = tmp_path / "repo"
    absolute = tmp_path / "elsewhere" / "p.toml"

    resolved = gateway_config.resolve_manifests(root, ["deploy/registry/p.toml", str(absolute)])

    assert resolved[0] == str(root / "backend" / "deploy" / "registry" / "p.toml")
    assert resolved[1] == str(absolute)


def test_body_size_reports_missing_files(tmp_path: Path) -> None:
    """四方文件全缺：逐项给出「缺少 …」结论（不因首项缺失短路）。"""
    problems = gateway_config.validate_body_size(tmp_path)

    assert any("缺少边缘 nginx 模板" in item for item in problems)
    assert any("缺少网关编排" in item for item in problems)
    assert any("缺少 APISIX 启动配置" in item for item in problems)
    assert any("缺少环境变量模板" in item for item in problems)


def test_body_size_reports_declaration_gaps(tmp_path: Path) -> None:
    """声明缺失 / 不可解析：编排缺省值不可解析、APISIX 缺上限、环境变量模板缺键位。"""
    _seed_body_size(tmp_path, compose_default="abc")
    assert any("缺省值不可解析" in item for item in gateway_config.validate_body_size(tmp_path))

    _seed_body_size(tmp_path)
    apisix = tmp_path / gateway_config.APISIX_CONFIG_RELATIVE
    apisix.write_text("nginx_config:\n  http: {}\n", encoding="utf-8")
    assert any("缺请求体上限" in item for item in gateway_config.validate_body_size(tmp_path))

    _seed_body_size(tmp_path)
    env_example = tmp_path / gateway_config.ENV_EXAMPLE_RELATIVE
    env_example.write_text("OTHER=1\n", encoding="utf-8")
    assert any("缺 GATEWAY_MAX_BODY_SIZE 键位" in item for item in gateway_config.validate_body_size(tmp_path))

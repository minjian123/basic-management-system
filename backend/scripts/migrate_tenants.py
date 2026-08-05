"""批量迁移租户库：遍历已注册租户逐个执行 Alembic 升级。

用法（backend 目录下）：
    uv run python scripts/migrate_tenants.py            # 迁移 dev_tenants（阶段一配置演练）
    uv run python scripts/migrate_tenants.py --tenant acme  # 指定租户编码（阶段三起按 sys_tenant 注册表）
    uv run python scripts/migrate_tenants.py --all      # 阶段三起：读取 sys_tenant 注册表全量迁移

阶段一实现框架与 dev_tenants 演练路径；sys_tenant 注册表驱动的全量迁移在阶段三完整启用。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings

TENANT_INI = "alembic_tenant.ini"


def migrate_tenant(tenant_code: str) -> None:
    """对单个租户库执行升级到最新版本。"""
    settings = get_settings()
    url = settings.database.tenant_url_template.replace("{code}", tenant_code)
    if url.startswith("sqlite"):
        # 开发环境 SQLite 由应用启动 create_all 自动建表，Alembic 迁移面向 MySQL/PostgreSQL
        print(f"[migrate] tenant={tenant_code} SQLite 开发库由 create_all 管理，跳过 Alembic 迁移")
        return
    cfg = Config(TENANT_INI)
    cfg.attributes["tenant_url"] = url
    print(f"[migrate] tenant={tenant_code} url={url}")
    command.upgrade(cfg, "head")
    print(f"[migrate] tenant={tenant_code} done")


def main() -> None:
    parser = argparse.ArgumentParser(description="租户库批量迁移工具")
    parser.add_argument("--tenant", help="仅迁移指定租户编码")
    parser.add_argument("--all", action="store_true", help="迁移全部已注册租户（阶段三起按 sys_tenant）")
    args = parser.parse_args()

    settings = get_settings()
    if args.tenant:
        migrate_tenant(args.tenant)
        return
    codes = settings.database.dev_tenants
    if args.all and not codes:
        print("[migrate] --all 依赖 sys_tenant 注册表，阶段三完整启用；当前按 dev_tenants 执行")
    if not codes:
        print("[migrate] dev_tenants 为空，无租户可迁移")
        return
    for code in codes:
        migrate_tenant(code)
    print(f"[migrate] 全部完成，共 {len(codes)} 个租户")


if __name__ == "__main__":
    main()

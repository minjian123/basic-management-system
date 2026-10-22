"""service-build 镜像导入自检用例（Kiwi 2345）：`deploy/ci/templates/backend-service.yml`。

不依赖 docker：从模板抽取 `docker run ... -c '<脚本>'` 的脚本体，用本机 python 跑三种场景——
入口可导入（退出码 0）、入口缺模块（退出码 1 且**打印缺失模块名**）、入口其它异常（退出码 1）。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[5]
"""仓库根（`backend/libs/bms_core/tests/ops/` 上溯 5 级）。"""

_TEMPLATE = _REPO_ROOT / "deploy" / "ci" / "templates" / "backend-service.yml"


def _selfcheck_script() -> str:
    """从服务子流水线模板抽取导入自检脚本体（去掉 YAML 块标量缩进）。

    Returns:
        str: 可直接交给 `python -c` 的脚本。
    """
    text = _TEMPLATE.read_text(encoding="utf-8")
    match = re.search(
        r'docker run --rm --entrypoint python "\$IMAGE" -c \'\n(.*?)\n      \' "\$SERVICE"',
        text,
        re.DOTALL,
    )
    assert match is not None, "模板中未找到 service-build 导入自检步骤"
    lines = [line[6:] if line.startswith("      ") else line for line in match.group(1).splitlines()]
    return "\n".join(lines)


@pytest.mark.kiwi_id(2345)
def test_service_build_has_import_selfcheck_step() -> None:
    """`service-build` 在 docker build 之后有导入自检步骤，且位置在推送之前。"""
    text = _TEMPLATE.read_text(encoding="utf-8")
    build_at = text.index("docker build --provenance=false")
    selfcheck_at = text.index("--entrypoint python")
    assert build_at < selfcheck_at, "导入自检须在 docker build 之后"
    assert "[service-build] 镜像缺模块" in text
    assert "sys.exit(1)" in text


@pytest.mark.kiwi_id(2345)
def test_selfcheck_passes_for_importable_entry(tmp_path: Path) -> None:
    """入口可导入：退出码 0 且打印通过标记。"""
    (tmp_path / "bms_ok").mkdir()
    (tmp_path / "bms_ok" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "bms_ok" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", _selfcheck_script(), "ok"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(tmp_path)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "[service-build] 导入自检通过：bms_ok.main" in result.stdout


@pytest.mark.kiwi_id(2345)
def test_selfcheck_prints_missing_module_name(tmp_path: Path) -> None:
    """入口缺模块：退出码 1 且**直接打印缺失模块名**（本次缺陷的定位诉求）。"""
    (tmp_path / "bms_missing").mkdir()
    (tmp_path / "bms_missing" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "bms_missing" / "main.py").write_text("import bms_ghost_package\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", _selfcheck_script(), "missing"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(tmp_path)},
        check=False,
    )
    assert result.returncode == 1
    assert "镜像缺模块：bms_ghost_package" in result.stderr


@pytest.mark.kiwi_id(2345)
def test_selfcheck_reports_other_import_errors(tmp_path: Path) -> None:
    """入口其它异常（非缺模块）：退出码 1 且打印异常类型与消息。"""
    (tmp_path / "bms_boom").mkdir()
    (tmp_path / "bms_boom" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "bms_boom" / "main.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", _selfcheck_script(), "boom"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(tmp_path)},
        check=False,
    )
    assert result.returncode == 1
    assert "入口导入失败：RuntimeError: boom" in result.stderr


@pytest.mark.kiwi_id(2345)
def test_dockerfile_documents_image_boundary() -> None:
    """`backend/Dockerfile` 说明镜像只装 `bms_core` + 目标服务 + `ops`，并提示构建期自检。"""
    text = (_REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "构建期" in text
    assert "导入自检" in text
    assert "bms_core" in text

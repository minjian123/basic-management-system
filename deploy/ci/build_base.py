#!/usr/bin/env python3
"""CI 基础镜像构建（Python 单一实现；CI job 与本地 bootstrap 共用）。

调用方式（路径均以本文件位置为基准，不依赖调用者 cwd）：
    sh deploy/ci/build_base.sh                 # CI job `ci-base-build`（docker:27-cli 镜像）
    python3 deploy/ci/build_base.py            # 本地 bootstrap / 任意 cwd
同名 `build_base.sh` 仅为转调本文件的 **POSIX sh 瘦包装**（CI 以 `sh` 调用；docker:27-cli 为
Alpine 镜像、默认无 python3，故 `.gitlab-ci.yml` 于调用前 `apk add --no-cache python3`）。

口径（与历史 shell 实现一致，2026-10-16 起改 Python 单一实现）：
- 标签：前后端分列——后端（uv.lock + Dockerfile.backend）、前端（Dockerfile.frontend，仅工具链）
  各自哈希前 12 位；镜像写入 label bms.lock-hash（Dockerfile 变更同样触发重建）
- 幂等：本地已存在同哈希镜像则跳过（构建与消费共用宿主 docker daemon，本流水线即用新镜像）
- 产物：$REGISTRY_IMAGE_PREFIX/ci-backend:<backend_tag>、ci-frontend:<frontend_tag>
  前端镜像**不再预装任何依赖**：各前端 job 内 `pnpm install --frozen-lockfile`，
  依赖经 runner /cache/pnpm 缓存卷 + npmmirror 现装（内容寻址 store，命中即秒级 link）。
- 构建上下文：mktemp 临时目录（与 shell 版一致不清理）；后端按工作区成员清单铺 pyproject
  （libs/* 与 services/*，Dockerfile 从工作区根 COPY 各成员 pyproject；上下文按 libs/** 与
  services/** 落位），前端仅 Dockerfile。
环境变量：
- REGISTRY_IMAGE_PREFIX：必填，未设置即报错退出 1（原 `${REGISTRY_IMAGE_PREFIX:?...}` 语义）；
- CI_REGISTRY / CI_REGISTRY_USER / CI_REGISTRY_PASSWORD：CI_REGISTRY_USER 非空时执行 docker login。
"""

import contextlib
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREFIX = "[ci-base]"
# 本文件位于 <仓库根>/deploy/ci/ 下，上跳两级即仓库根
ROOT = Path(__file__).resolve().parents[2]
# 工作区成员清单：共享库 + 各服务（Dockerfile 从工作区根 COPY 各成员 pyproject）
MEMBER_GLOBS = ("backend/libs/*/pyproject.toml", "backend/services/*/pyproject.toml")


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def info(message):
    """即时输出（逐行 flush，避免与 docker 子进程输出交错错位）。"""
    print(message, flush=True)


class BuildInputError(Exception):
    """构建输入缺失 / 不可读（可预期的前置失败，打印消息并退出 1）。"""


def lock_tag(*paths):
    """锁文件哈希标签：等价 `cat <files...> | sha256sum | cut -c1-12`（拼接原始字节后取前 12 位）。

    注：原 shell 在锁文件缺失时会把「cat 失败的产物」喂给 sha256sum（等于按空内容算哈希、静默继续）；
    此处改为快速失败——构建输入不可读即报错，避免 CI 用错标签重建镜像。
    """
    digest = hashlib.sha256()
    for path in paths:
        try:
            digest.update(Path(path).read_bytes())
        except OSError as exc:
            raise BuildInputError(f"构建输入不可读：{path}（{exc.strerror or exc}）") from None
    return digest.hexdigest()[:12]


def docker(*args, **kwargs):
    """调用 docker CLI（argv 直传，不走 shell）。"""
    return subprocess.run(["docker", *args], **kwargs)


def build_if_needed(prefix, name, static_tag, fixed_tag, ctx):
    """等价 shell 的 build_if_needed：哈希 label 相同即跳过，否则构建 → 复打固定标签 → best-effort push。"""
    image = f"{prefix}/{name}:{static_tag}"
    fixed_image = f"{prefix}/{name}:{fixed_tag}"
    current = ""
    inspected = docker(
        "image",
        "inspect",
        "-f",
        '{{ index .Config.Labels "bms.lock-hash" }}',
        image,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    if inspected.returncode == 0:  # 镜像不存在即视为未命中（原 `2>/dev/null || true`）
        current = (inspected.stdout or "").strip()
    if current == static_tag:
        info(f"{PREFIX} {image} 已最新，跳过")
        return
    info(f"{PREFIX} 构建 {image}（lock-hash={static_tag}）")
    docker("build", "--label", f"bms.lock-hash={static_tag}", "-t", image, str(ctx), check=True)
    # 复打固定标签供各 job 引用（ci-backend:py314 / ci-frontend:node22）：job 的 image 保持
    # 固定标签不变，每次重建即更新固定标签指向最新工具链
    docker("tag", image, fixed_image, check=True)
    # push 尽力而为：registry 对层报 blob unknown（见 04-1 遗留），单 runner 场景本机镜像即可用
    for target in (fixed_image, image):
        if docker("push", target).returncode != 0:
            info(f"{PREFIX} 警告：push {target} 失败，使用本机镜像继续")


def prepare_backend_context():
    """后端构建上下文：根 pyproject/uv.lock + 工作区成员 pyproject（libs/** 与 services/** 原样落位）+ Dockerfile。"""
    ctx = Path(tempfile.mkdtemp())
    shutil.copy2(ROOT / "backend" / "pyproject.toml", ctx)
    shutil.copy2(ROOT / "backend" / "uv.lock", ctx)
    for pattern in MEMBER_GLOBS:
        manifests = sorted(glob.glob(str(ROOT / pattern)))
        if not manifests:
            # 原 shell 的 glob 无匹配时会把字面量原样交给 cp 而失败（set -e）——此处同口径快速失败
            raise BuildInputError(f"工作区成员清单为空：{pattern}")
        for manifest in manifests:
            dest = ctx / Path(manifest).relative_to(ROOT / "backend")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest, dest)
    shutil.copy2(ROOT / "deploy" / "ci" / "Dockerfile.backend", ctx / "Dockerfile")
    return ctx


def prepare_frontend_context():
    """前端构建上下文：仅 Dockerfile（依赖由各前端 job 内 pnpm 现装）。"""
    ctx = Path(tempfile.mkdtemp())
    shutil.copy2(ROOT / "deploy" / "ci" / "Dockerfile.frontend", ctx / "Dockerfile")
    return ctx


def main(argv=None):
    prefix = os.environ.get("REGISTRY_IMAGE_PREFIX", "")
    if not prefix:
        sys.stderr.write(f"{PREFIX} REGISTRY_IMAGE_PREFIX 未设置\n")
        return 1

    try:
        backend_tag = lock_tag(ROOT / "backend" / "uv.lock", ROOT / "deploy" / "ci" / "Dockerfile.backend")
        frontend_tag = lock_tag(ROOT / "deploy" / "ci" / "Dockerfile.frontend")
        info(f"{PREFIX} 构建输入哈希标签 backend={backend_tag} frontend={frontend_tag}")

        # 有凭据才登录；CI_REGISTRY_USER 非空而未给齐 CI_REGISTRY(_PASSWORD) 时与原 shell `set -u` 同口径失败
        if os.environ.get("CI_REGISTRY_USER", ""):
            registry = os.environ.get("CI_REGISTRY", "")
            password = os.environ.get("CI_REGISTRY_PASSWORD", "")
            if not registry or not password:
                sys.stderr.write(f"{PREFIX} CI_REGISTRY / CI_REGISTRY_PASSWORD 未设置（CI_REGISTRY_USER 已设置）\n")
                return 1
            docker(
                "login",
                registry,
                "-u",
                os.environ["CI_REGISTRY_USER"],
                "--password-stdin",
                input=(password + "\n").encode("utf-8"),
                check=True,
            )

        backend_ctx = prepare_backend_context()
        frontend_ctx = prepare_frontend_context()

        build_if_needed(prefix, "ci-backend", backend_tag, "py314", backend_ctx)
        build_if_needed(prefix, "ci-frontend", frontend_tag, "node22", frontend_ctx)
    except BuildInputError as exc:
        sys.stderr.write(f"{PREFIX} {exc}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"{PREFIX} 命令或文件不存在：{exc}\n")
        return 127
    except OSError as exc:
        sys.stderr.write(f"{PREFIX} 文件操作失败：{exc}\n")
        return 1
    except subprocess.CalledProcessError as exc:
        # 对齐 shell `set -e`：以失败命令的退出码结束
        return exc.returncode or 1

    info(
        f"{PREFIX} 完成：{prefix}/ci-backend:{backend_tag}（fixed:py314）、"
        f"{prefix}/ci-frontend:{frontend_tag}（fixed:node22）"
    )
    return 0


if __name__ == "__main__":
    configure_stdio()
    sys.exit(main(sys.argv))

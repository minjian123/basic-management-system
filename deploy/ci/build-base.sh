#!/bin/sh
# CI 基础镜像构建（POSIX sh；CI job 与本地 bootstrap 共用）
# - 标签：锁文件（含 workspace 根）+ 两份 Dockerfile 合并哈希前 12 位；镜像写入 label bms.lock-hash
#   （Dockerfile 变更——如系统依赖调整——同样触发重建，2026-09-14 补）
# - 幂等：本地已存在同哈希镜像则跳过（构建与消费共用宿主 docker daemon，本流水线即用新镜像）
# - 产物：$REGISTRY_IMAGE_PREFIX/ci-backend:<tag>、ci-frontend:<tag>
#   ci-frontend 含三套预装依赖（workspace 根 / apps/desktop / modules/*）：workspace 根（frontend/packages/*：core / vue）/ frontend/apps/desktop（镜像内路径 /opt/ci/workspace、/opt/ci/frontend/apps/desktop）
set -eu

REGISTRY_IMAGE_PREFIX="${REGISTRY_IMAGE_PREFIX:?REGISTRY_IMAGE_PREFIX 未设置}"
MODULE_LOCKS=$(find frontend/modules -maxdepth 2 -name package-lock.json 2>/dev/null | sort)
TAG=$(cat backend/uv.lock frontend/apps/desktop/package-lock.json package-lock.json $MODULE_LOCKS \
  deploy/ci/Dockerfile.backend deploy/ci/Dockerfile.frontend | sha256sum | cut -c1-12)
echo "[ci-base] 构建输入哈希标签（锁文件 + Dockerfile）: $TAG"

if [ -n "${CI_REGISTRY_USER:-}" ]; then
  echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
fi

backend_ctx=$(mktemp -d)
cp backend/pyproject.toml backend/uv.lock "$backend_ctx/"
# 工作区成员清单：共享库 + 各服务（Dockerfile 从工作区根 COPY 各成员 pyproject；上下文按 libs/* 与 services/* 落位）
for manifest in backend/libs/*/pyproject.toml backend/services/*/pyproject.toml; do
  rel=${manifest#backend/}
  mkdir -p "$backend_ctx/$(dirname "$rel")"
  cp "$manifest" "$backend_ctx/$rel"
done
cp deploy/ci/Dockerfile.backend "$backend_ctx/Dockerfile"

frontend_ctx=$(mktemp -d)
mkdir -p "$frontend_ctx/frontend/apps/desktop" "$frontend_ctx/frontend/packages"
cp frontend/apps/desktop/package.json frontend/apps/desktop/package-lock.json "$frontend_ctx/frontend/apps/desktop/"
# workspace 根依赖集：根清单 + 各包清单（npm ci 按 frontend/packages/* 计算依赖，镜像内只需清单）
cp package.json package-lock.json tsconfig.base.json "$frontend_ctx/"
for manifest in frontend/packages/*/package.json; do
  mkdir -p "$frontend_ctx/$(dirname "$manifest")"
  cp "$manifest" "$frontend_ctx/$manifest"
done
# 模块工程依赖集：各模块清单 + 锁文件（其 `file:` 依赖指向 frontend/packages/<包>，故 packages 清单须同置于 /opt/ci/frontend/ 下）
for manifest in frontend/modules/*/package.json; do
  mkdir -p "$frontend_ctx/$(dirname "$manifest")"
  cp "$manifest" "$frontend_ctx/$manifest"
  cp "${manifest%package.json}package-lock.json" "$frontend_ctx/$(dirname "$manifest")/"
done
cp deploy/ci/Dockerfile.frontend "$frontend_ctx/Dockerfile"

build_if_needed() {
  name="$1"
  static_tag="$2"
  ctx="$3"
  image="$REGISTRY_IMAGE_PREFIX/$name:$static_tag"
  current=$(docker image inspect -f '{{ index .Config.Labels "bms.lock-hash" }}' "$image" 2>/dev/null || true)
  if [ "$current" = "$TAG" ]; then
    echo "[ci-base] $image 已最新，跳过"
    return 0
  fi
  echo "[ci-base] 构建 $image（lock-hash=$TAG）"
  docker build --label "bms.lock-hash=$TAG" -t "$image" "$ctx"
  # push 尽力而为：registry 对层报 blob unknown（见 04-1 遗留），单 runner 场景本机镜像即可用
  docker push "$image" || echo "[ci-base] 警告：push $image 失败，使用本机镜像继续"
}

build_if_needed ci-backend py314 "$backend_ctx"
build_if_needed ci-frontend node22 "$frontend_ctx"
echo "[ci-base] 完成：$REGISTRY_IMAGE_PREFIX/ci-backend:py314、$REGISTRY_IMAGE_PREFIX/ci-frontend:node22（lock-hash=$TAG）"

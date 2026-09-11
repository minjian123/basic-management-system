#!/bin/sh
# CI 基础镜像构建（POSIX sh；CI job 与本地 bootstrap 共用）
# - 标签：三份锁文件合并哈希前 12 位；镜像写入 label bms.lock-hash
# - 幂等：本地已存在同哈希镜像则跳过（构建与消费共用宿主 docker daemon，本流水线即用新镜像）
# - 产物：$REGISTRY_IMAGE_PREFIX/ci-backend:<tag>、ci-frontend:<tag>
set -eu

REGISTRY_IMAGE_PREFIX="${REGISTRY_IMAGE_PREFIX:?REGISTRY_IMAGE_PREFIX 未设置}"
TAG=$(cat backend/uv.lock frontend/package-lock.json frontend-mobile/package-lock.json | sha256sum | cut -c1-12)
echo "[ci-base] 锁文件哈希标签: $TAG"

if [ -n "${CI_REGISTRY_USER:-}" ]; then
  echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
fi

backend_ctx=$(mktemp -d)
cp backend/pyproject.toml backend/uv.lock "$backend_ctx/"
cp deploy/ci/Dockerfile.backend "$backend_ctx/Dockerfile"

frontend_ctx=$(mktemp -d)
mkdir -p "$frontend_ctx/frontend" "$frontend_ctx/frontend-mobile"
cp frontend/package.json frontend/package-lock.json "$frontend_ctx/frontend/"
cp frontend-mobile/package.json frontend-mobile/package-lock.json "$frontend_ctx/frontend-mobile/"
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
  # push 尽力而为：registry 对层报 blob unknown（见 05-1 遗留），单 runner 场景本机镜像即可用
  docker push "$image" || echo "[ci-base] 警告：push $image 失败，使用本机镜像继续"
}

build_if_needed ci-backend py314 "$backend_ctx"
build_if_needed ci-frontend node22 "$frontend_ctx"
echo "[ci-base] 完成：$REGISTRY_IMAGE_PREFIX/ci-backend:py314、$REGISTRY_IMAGE_PREFIX/ci-frontend:node22（lock-hash=$TAG）"

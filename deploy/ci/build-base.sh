#!/bin/sh
# CI 基础镜像构建（POSIX sh；CI job 与本地 bootstrap 共用）
# - 标签：前后端分列——后端（uv.lock + Dockerfile.backend）、前端（Dockerfile.frontend，仅工具链）
#   各自哈希前 12 位；镜像写入 label bms.lock-hash（Dockerfile 变更同样触发重建）
# - 幂等：本地已存在同哈希镜像则跳过（构建与消费共用宿主 docker daemon，本流水线即用新镜像）
# - 产物：$REGISTRY_IMAGE_PREFIX/ci-backend:<backend_tag>、ci-frontend:<frontend_tag>
#   前端镜像**不再预装任何依赖**：各前端 job 内 `pnpm install --frozen-lockfile`，
#   依赖经 runner /cache/pnpm 缓存卷 + npmmirror 现装（内容寻址 store，命中即秒级 link）。
set -eu

REGISTRY_IMAGE_PREFIX="${REGISTRY_IMAGE_PREFIX:?REGISTRY_IMAGE_PREFIX 未设置}"
BACKEND_TAG="$(cat backend/uv.lock deploy/ci/Dockerfile.backend | sha256sum | cut -c1-12)"
FRONTEND_TAG="$(cat deploy/ci/Dockerfile.frontend | sha256sum | cut -c1-12)"
echo "[ci-base] 构建输入哈希标签 backend=$BACKEND_TAG frontend=$FRONTEND_TAG"

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
cp deploy/ci/Dockerfile.frontend "$frontend_ctx/Dockerfile"

build_if_needed() {
  name="$1"
  static_tag="$2"
  fixed_tag="$3"
  ctx="$4"
  image="$REGISTRY_IMAGE_PREFIX/$name:$static_tag"
  fixed_image="$REGISTRY_IMAGE_PREFIX/$name:$fixed_tag"
  current=$(docker image inspect -f '{{ index .Config.Labels "bms.lock-hash" }}' "$image" 2>/dev/null || true)
  if [ "$current" = "$static_tag" ]; then
    echo "[ci-base] $image 已最新，跳过"
    return 0
  fi
  echo "[ci-base] 构建 $image（lock-hash=$static_tag）"
  docker build --label "bms.lock-hash=$static_tag" -t "$image" "$ctx"
  # 复打固定标签供各 job 引用（ci-backend:py314 / ci-frontend:node22）：job 的 image 保持
  # 固定标签不变，每次重建即更新固定标签指向最新工具链
  docker tag "$image" "$fixed_image"
  # push 尽力而为：registry 对层报 blob unknown（见 04-1 遗留），单 runner 场景本机镜像即可用
  docker push "$fixed_image" || echo "[ci-base] 警告：push $fixed_image 失败，使用本机镜像继续"
  docker push "$image" || echo "[ci-base] 警告：push $image 失败，使用本机镜像继续"
}

build_if_needed ci-backend "$BACKEND_TAG" "py314" "$backend_ctx"
build_if_needed ci-frontend "$FRONTEND_TAG" "node22" "$frontend_ctx"
echo "[ci-base] 完成：$REGISTRY_IMAGE_PREFIX/ci-backend:$BACKEND_TAG（fixed:py314）、$REGISTRY_IMAGE_PREFIX/ci-frontend:$FRONTEND_TAG（fixed:node22）"
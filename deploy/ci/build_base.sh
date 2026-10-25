#!/bin/sh
# CI 基础镜像构建 —— POSIX sh 入口（CI 以 `sh deploy/ci/build_base.sh` 调用；逻辑见同目录 build_base.py）
# docker:27-cli（Alpine）默认无 python3，`.gitlab-ci.yml` 于调用前 `apk add --no-cache python3`；
# 标签哈希 / 幂等跳过 / label / push best-effort 等口径见 build_base.py 头部注释。
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$HERE/build_base.py" "$@"

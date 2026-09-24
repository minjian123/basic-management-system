# BMS 服务运行镜像（按服务参数化；构建上下文为 backend/）
#
# 构建（CI 服务子流水线 service-build 调用，见 deploy/ci/templates/backend-service.yml）：
#   docker build --provenance=false --build-arg SERVICE=platform -t <registry>/bms-platform:<sha> -f backend/Dockerfile backend/
#   （--provenance=false：BuildKit 默认 attestation 清单推送会被 GitLab Registry 拒绝，报 blob unknown）
# 运行（容器编排 / 部署与回滚见 09_02）：
#   docker run --rm -p 8000:8000 -e BMS_ENV=<环境> <image>
# 口径：依赖以 uv.lock 锁定（--frozen）；非目标服务源码不入镜像；启动入口 python -m bms_{service}。
FROM python:3.14-slim

ARG SERVICE
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple \
    UV_PROJECT_ENVIRONMENT=/opt/bms-venv \
    UV_NO_SYNC=1 \
    SERVICE=${SERVICE}

# 系统包安全更新（Trivy CRITICAL/HIGH 阻断发版；base 镜像自带包常落后于 Debian 安全更新）；
# apt 换清华源（官方 Debian 源国内慢，与 deploy/ci/Dockerfile.backend 同口径）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get upgrade -y \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /opt/bms
# 工作区元数据：uv.lock 与各成员 pyproject（工作区解析需要；成员源码后续按目标服务 COPY）；
# alembic.ini 供基座定位工程根（bms_core.db.migration._find_backend_root 向上搜根）；
# config*.toml 为配置基线 / 环境分层（密钥不入配置文件，经 BMS_ 环境变量注入）
COPY pyproject.toml uv.lock alembic.ini config.toml config.*.toml ./
COPY libs/bms_core/pyproject.toml libs/bms_core/pyproject.toml
COPY services/platform/pyproject.toml services/platform/pyproject.toml
COPY services/identity/pyproject.toml services/identity/pyproject.toml
COPY services/tenant/pyproject.toml services/tenant/pyproject.toml
COPY services/org/pyproject.toml services/org/pyproject.toml
COPY services/file/pyproject.toml services/file/pyproject.toml
COPY services/notification/pyproject.toml services/notification/pyproject.toml
COPY services/search/pyproject.toml services/search/pyproject.toml
COPY services/ai/pyproject.toml services/ai/pyproject.toml
COPY services/report/pyproject.toml services/report/pyproject.toml
# 第三方依赖层（不装工作区成员；锁文件零漂移）
RUN uv sync --frozen --no-install-workspace --package "bms-${SERVICE}" && rm -rf /root/.cache

# 工作区成员源码（共享基座库 + 目标服务）
COPY libs/bms_core/src libs/bms_core/src
COPY services/${SERVICE}/src services/${SERVICE}/src
RUN uv sync --frozen --no-dev --package "bms-${SERVICE}" && rm -rf /root/.cache

# 运行时移除 pip（base 镜像自带；其 vendored msgpack / setuptools 会被镜像扫描按包计洞，
# 运行时不需要 pip——venv 自包含、uv 二进制不受影响）
RUN python -m pip uninstall -y pip

ENV PATH=/opt/bms-venv/bin:$PATH
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["sh", "-c", "exec python -m bms_${SERVICE}"]

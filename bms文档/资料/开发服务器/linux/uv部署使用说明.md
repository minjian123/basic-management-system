# uv 部署使用说明（开发服务器 CI 侧）

[文档首页](../../../../文档首页.md) › 资料 › 开发服务器 › linux › uv 部署使用说明　|　[同级：pnpm 部署使用说明 →](pnpm部署使用说明.md)　[契约门禁与契约测试使用说明 →](契约门禁与契约测试使用说明.md)　[服务编排与发布部署使用说明 →](服务编排与发布部署使用说明.md)

## 1. 本机与服务器的口径对照 <a id="contrast"></a>

uv 在**开发机**与**开发服务器（CI）**上是互补两侧，先讲清站位：

| 维度 | 开发机（`资料/开发机/`） | 开发服务器 CI（本文） |
| --- | --- | --- |
| 虚拟环境 `backend/.venv` | **外置**到本地依赖仓（`UV_PROJECT_ENVIRONMENT` 指过去） | **不落仓库**；job 内现装到 `/opt/bms-venv`（镜像生命期卷） |
| 工具链 | uv 本地固定版（`~/.local/bin/uv`） | 服务器 CI 内置 uv 固定版（依赖 `backend/uv.lock` 哈希驱动 rebuild，见《[开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)》「服务部署说明文档索引」节） |
| 网源 | 清华 PyPI（开发机 npmrc/uv 同源） | 清华 PyPI（CI env `UV_DEFAULT_INDEX`） |
| 断言 | `uv sync --frozen` | `uv sync --frozen`（两者共用一条权威 `uv.lock`） |

**一句话**：开发机把 venv 与依赖**外置到本地依赖仓**避免依赖在真正仓库树内被检索误扫；服务器 CI 则在基础镜像生命期**现装**（frozen 锁，命 runner store 卷）——两条都是「依赖不进 git 树」的收敛，只是落点不同：本地侧外置、CI 侧现装。**本机是外置口径、服务器是现装口径，两方都保证仓库树内零 node_modules/.venv 残留。**

## 2. 工具链宿主 <a id="toolchain"></a>

服务器侧 uv 在 **CI 基础镜像**内（非开发机）

```bash
# build-base.sh 后端段（伪代码口径，与开发机 uv 配置文件两处独立但同锁）
uv sync --frozen                      # job 内现装，读仓库树 backend/uv.lock 单一权威
```

- 基础镜像 `ci-backend:py314` 内置 uv（`Dockerfile.backend`，uv.lock 哈希驱动 rebuild）
- job 内 `uv sync --frozen`：store/缓存走 runner `/cache/uv` 持久卷；命中即秒级 link
- hardware：与开发机 uv 版本一致（见《[uv 部署使用说明（开发机）](../../开发机/uv部署使用说明.md)》），锁单一权威 `backend/uv.lock`

## 3. CI 现装口径 <a id="ci"></a>

后端各 job（build / lint / typecheck / test）统一：

```bash
uv sync --frozen
```

- `--frozen`：以 `backend/uv.lock` 为锁权威，锁漂移即失败（锁由开发机 `uv add` / `uv remove` 维护后提交）
- 缓存卷：`/cache/uv`（runner 持久卷，job 间复用 store）
- registry：清华 PyPI（`UV_DEFAULT_INDEX` 基座镜像 env）

## 4. 与开发机 uv 的对照 <a id="dev"></a>

- 开发机（同 workspace 不同落点）：`.venv` 外置到本地依赖仓，`UV_PROJECT_ENVIRONMENT` 指本地仓
- 服务器（CI）：基础镜像内置 `venv` 现装到 `/opt/bms-venv`，job 内 `uv sync --frozen` 现装
- **两方都不在 git 树里残留 .venv**：开发机外置、CI 现装后随镜像同批丢弃

## 5. 关联文档 <a id="related"></a>

- 《[pnpm 部署使用说明](pnpm部署使用说明.md)》：前端依赖（CI 现装 + store 缓存卷）
- 《[uv 部署使用说明（开发机）](../../开发机/uv部署使用说明.md)》：本地侧 uv（.venv 外置 + 外置/还原/重装脚本）
- 《[开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)》：CI 构建口径与基础镜像总体

# pnpm 部署使用说明

[文档首页](../../文档首页.md) › 资料 › 开发服务器 › linux › pnpm 部署使用说明　|　[同级：uv 部署使用说明 →](uv部署使用说明.md)　[开发服务器部署使用说明总览 →](开发服务器部署使用说明总览.md)

## 1. 本机与服务器的依赖口径差异 <a id="diff"></a>

pnpm 在**开发机**与**开发服务器**上的部署口径**相反**，先讲清站位：

| 维度 | 开发机（`资料/开发机/`） | 开发服务器（本文） |
| --- | --- | --- |
| 依赖落点 | 外置到本地依赖仓（`~/dev-deps/bms`，node_modules symlink） | 不落服务器仓库树；仅 job 内现装 + runner 缓存卷 |
| 工具链 | pnpm 本地安装（`~/.nvm/versions/node/v24.20.0` 配套） | CI 基础镜像内置（`ci-frontend:node22`，node 22 + pnpm） |
| 装法 | `pnpm install`（store 外置、命中即秒级 link） | `pnpm install --frozen-lockfile`（job 内现装，store 走 `/cache/pnpm` 持久卷） |
| 网络源 | npmmirror（本地镜像） | npmmirror（runner 缓存卷复用 store） |
| 产物 | 喂本地 build / lint / test | 喂前端构建 job，产物进镜像（不入 git） |

**一句话**：开发机负责「装得对、检得快」，服务器 CI 负责「按锁现装、产出可发布镜像」——两者互不依赖，服务器**不读开发机的依赖仓外置**。

## 2. CI 基础镜像中的工具链 <a id="toolchain"></a>

前端 CI 基础镜像 `ci-frontend:node22`（构建见 `deploy/ci/build-base.sh`）仅内置工具链，**不带任何 node_modules**：

- 基础镜像 `node:22-slim`（`deploy/ci/Dockerfile.frontend`）
- 内置 `npm install -g pnpm@11.7.0` —— pnpm 版本与开发机一致（单一 workspace 语义对齐）
- 配置 `npm_config_registry=https://registry.npmmirror.com`（scoped 走 `npm_config_@bms:registry` 同源）

> CI 内**不预装依赖**：node_modules 一律 job 运行时现装（内容寻址 store），有意为之——镜像不掺依赖、上传体积小、CI 与开发机口径一致。

## 3. CI job 内现装口径 <a id="ciscript"></a>

前端各 job（`build-frontend` / `lint-frontend` / `test-frontend` 等）统一走：

```bash
pnpm install --frozen-lockfile
```

- `--frozen-lockfile`：严格按 `pnpm-lock.yaml` 装，锁文件漂移直接失败（改动锁文件须过契约门禁）
- 源码全部经**单一 workspace**（`pnpm-workspace.yaml`）收敛，job 内 `pnpm install` 一次装齐全部包
- store 走 runner `/cache/pnpm` 持久缓存卷——内容寻址，跨 job / 跨流水线命中即秒级 link
- 装完即用（`pnpm --filter ... build` 等），不落地到服务器磁盘

## 4. 缓存与加速 <a name="cache"></a>

| 项 | 值 |
| --- | --- |
| store 缓存卷 | `/cache/pnpm`（runner 持久卷，不随流水线重建） |
| registry | `https://registry.npmmirror.com` |
| 缓存清退 | `wc -l` 校验 store 内容寻址，未命中才回源（常规 flow 均命中） |

## 5. 与开发机 workspace 的一致性 <a name="consistency"></a>

- 服务器 CI 与开发机**同锁单源**：`frontend/pnpm-lock.yaml` + `frontend/pnpm-workspace.yaml` 是唯一权威
- 平台基座包（`@bms/*`）在两端均以 `workspace:*` 协议复现，保证 job 内装与本地装依赖树逐字节一致（`--frozen-lockfile` 校验）

## 6. 关联文档 <a id="related"></a>

- 开发机口径见 [资料/开发机/pnpm部署使用说明](资料/开发机/pnpm部署使用说明.md)（依赖外置到本地依赖仓，开发机不直接喂 CI）
- uv 后端口径见 [uv 部署使用说明](uv部署使用说明.md)
- CI 基础镜像构建见《[服务编排与发布部署使用说明](服务编排与发布部署使用说明.md)》

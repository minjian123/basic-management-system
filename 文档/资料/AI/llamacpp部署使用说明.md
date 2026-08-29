# llamacpp 部署与使用说明

> mjpc 开发机（Ubuntu 26.04 / RTX 4090 24G）· llama.cpp（llama-server 路由模式）· 由 **LlamaForge** 图形化管理
>
> 修订说明：2026-08-29 起，llama.cpp 不再由旧 `qwen.service`（已删除）单模型直管，改为 **LlamaForge**（llama.cpp 控制面板）统一管理：llama-server 以**路由模式**（`--models-preset`）在 `8080` 服务、按需加载模型；面板在 `8090`。

[文档首页](../../文档首页.md) › 资料 › llamacpp 部署与使用说明

## 1. 概述 <a id="intro"></a>

llama.cpp 是 C/C++ 实现的本地大模型推理引擎，自带 `llama-server`——一个 **OpenAI 兼容** 的 HTTP 服务。
本项目用它在 mjpc 上跑本地大模型，作为 [opencode](https://opencode.ai) 与 dsh（DeepSeek Harness）的本地模型后端，
全程离线、免费、无 API Key（dsh 侧需配占位 key，见 5.4 节）。

管理与运行方式（2026-08-29 更新）：

- **LlamaForge**（[github.com/dadwritestech/LlamaForge](https://github.com/dadwritestech/LlamaForge)）是 llama.cpp 的图形控制面板：
  - 面板（dashboard）：`http://127.0.0.1:8090`
  - llama.cpp 路由（OpenAI 兼容）：`http://127.0.0.1:8080`
  - 它把 `llama-server` 以**路由模式**（`--models-preset models.ini`）启动，模型**按需加载**（`--models-max 1` 同一时刻只跑一个），并有模型下拉切换、逐项调参（上下文/GPU 层数/采样）、HF 模型发现（含显存适配评级）、llama.cpp 增量编译等能力。
- 模型注册在 `models.ini`（各模型一个 `[id]` 段），`/home/minjian/ai/models/` 下的 GGUF 由面板扫描登记。
- **客户端 `model` 字段用模型别名**（`/v1/models` 返回的 `id`），**不是 GGUF 全路径**——这是与旧版最大的不同，否则报 `model not found`（见 5.2 / 5.3 / 5.4）。

与 LM Studio 的关系：opencode / dsh 的 `llamacpp` 提供商接的是 LlamaForge 启动的 `llama-server`（端口 **8080**），
与 `lmstudio` 提供商（端口 1234，当前未运行）互不相干。本文只讲 llama.cpp 这一条链路。

核心特点：

- **OpenAI 兼容**：`/v1/chat/completions`、`/v1/models` 标准接口，任意 OpenAI SDK 直连。
- **CUDA 加速**：模型权重全层（`-ngl 999`）卸载到 RTX 4090 显存，K/V 量化 q4_0 省显存。
- **长上下文**：默认 150000（`--ctx-size 150000`，可在面板按模型调），配合 Flash Attention。
- **多模态**：Qwen 模型带 mmproj 视觉投影，支持图片输入（当前 models.ini 未挂 mmproj，需要时在面板给该模型加 `mmproj` 即可）。
- **人工启动**：LlamaForge 的启停走桌面包壳脚本 `/home/minjian/.local/bin/llamaforge-control.sh`（`run.sh` / `stop.sh`），非 systemd、不随开机自启，手动启停（见 3.4 节）。

## 2. 环境要求 <a id="prereq"></a>

本机（mjpc，Ubuntu 26.04.1 LTS）已验证的环境：

| 项 | 值 |
| --- | --- |
| 主机 | mjpc（内网 `192.168.0.124`） |
| GPU | NVIDIA GeForce RTX 4090，显存 24564 MiB，驱动 595.84 |
| 编译工具链 | GCC/GNU 15.2.0（Linux x86_64）+ CUDA（`nvcc`） |
| llama.cpp | 0.3.0-dev（commit `cb30059`），CMake Release，CUDA 开启 |
| 源码目录 | `/home/minjian/develop/llama.cpp` |
| LlamaForge | `/home/minjian/develop/LlamaForge`（Python 3.10+，纯标准库，零 pip 依赖） |
| 模型目录 | `/home/minjian/ai/models/` |

模型文件（3 个 GGUF + 1 个 mmproj）：

```text
/home/minjian/ai/models/
├── Qwen3.8-27B-UD-Q4_K_M.gguf                  # 主模型，Q4_K_M 量化，约 16G
├── Qwen3.8-27B-Uncensored-Q4_K_M.gguf          # 同基座的 uncensored 版，约 16G
├── gemma-4-26B-A4B-it-ultra-uncensored-heretic.i1-Q4_K_M.gguf  # gemma-4 26B(A4B MoE) uncensored，约 16G
└── mmproj-Qwen3.8-27B-f16.gguf                 # Qwen 多模态视觉投影，f16，约 885M
```

> 显存核算：任一 27B/26B Q4_K_M 权重约 16G，`-ngl 999` 全上卡，K/V 用 q4_0 量化，24G 显存可容纳。

## 3. 部署 <a id="deploy"></a>

### 3.1 获取并编译 llama.cpp <a id="deploy-build"></a>

```bash
# 克隆源码（国内网络加 ghfast.top 前缀加速，实测有效）
git clone https://github.com/ggml-org/llama.cpp /home/minjian/develop/llama.cpp
# 加速写法：git clone https://ghfast.top/https://github.com/ggml-org/llama.cpp

cd /home/minjian/develop/llama.cpp
# 配置：Release + CUDA，架构 89 对应 RTX 4090（Ada，sm_89）
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89
# 编译（-j 并行）
cmake --build build --config Release -j
# 产物
ls build/bin/llama-server
```

> 只跑 CPU 可去掉 `-DGGML_CUDA=ON`；换 GPU 改 `CMAKE_CUDA_ARCHITECTURES`（如 30 系=86、4090=89）。
> LlamaForge 的 **Build/Update** 页也能增量编译/更新 llama.cpp（自动探测 CPU/GPU 架构），两种方式任选。

### 3.2 放置模型 <a id="deploy-model"></a>

- 模型与 mmproj 放 `/home/minjian/ai/models/`（见第 2 节清单）。
- **新加模型**：把 `.gguf` 放进该目录，然后在 LlamaForge 面板的 **Setup / Models** 页点一次扫描，或在 `models.ini` 手动登记。

### 3.3 获取并配置 LlamaForge <a id="deploy-llamaforge"></a>

```bash
# 克隆（加 ghfast.top 加速）
git clone https://ghfast.top/https://github.com/dadwritestech/LlamaForge.git /home/minjian/develop/LlamaForge
```

配置文件 `config.json`（未提供时 `run.sh` 会从 `config.example.json` 复制并提示）——本机为**复用已编译好的 llama.cpp**：

```json
{
  "llama_src":   "/home/minjian/develop/llama.cpp",
  "build_dir":   "/home/minjian/develop/llama.cpp/build",
  "server_bin":  "/home/minjian/develop/llama.cpp/build/bin/llama-server",
  "models_ini":  "./models.ini",
  "model_dirs":  ["/home/minjian/ai/models"],
  "router_port": 8080,
  "panel_port":  8090,
  "router_host": "127.0.0.1",
  "router_api_key": "",
  "wsl_distro":  "",
  "vllm_port":   8081,
  "cmake_flags": {},
  "git_remote":  "https://github.com/ggml-org/llama.cpp"
}
```

> **注意**：`server_bin` 需要是**支持路由模式**（`--models-preset` 等）的 llama.cpp 构建，否则路由起不来。
> `router_host` 若改成 `0.0.0.0`（局域网可访问），务必设置非空 `router_api_key`（面板会提示），面板默认只在本机 `127.0.0.1`。

### 3.4 启停（桌面包壳脚本 / run.sh + stop.sh） <a id="deploy-run"></a>

LlamaForge 不是 systemd 服务，启停用其自带脚本（`check` 端口、`nohup` 后台、失败自恢复逻辑在 `run.sh` 内）：

```bash
# 启动：读 config.json，启动 llama.cpp 路由(8080) + 后端面板(8090)，并打开浏览器
bash /home/minjian/develop/LlamaForge/run.sh
# 停止：结束面板 + 路由 + 所有模型实例
bash /home/minjian/develop/LlamaForge/stop.sh
# 是否在运行（端口探测）
lsof -ti tcp:8090 -sTCP:LISTEN && echo 面板运行中
lsof -ti tcp:8080 -sTCP:LISTEN && echo 路由运行中
```

本机已做成**桌面快捷方式**（手工启停、不随开机自启）：

- 「LlamaForge 启动」→ 调 `~/.local/bin/llamaforge-control.sh start`（等价 `run.sh`，开面板）
- 「LlamaForge 停止」→ 调 `~/.local/bin/llamaforge-control.sh stop`（等价 `stop.sh`）

> `llamaforge-control.sh` 亦支持 `status`。日志在 `/home/minjian/develop/LlamaForge/logs/`（`router.err.log` / `panel.err.log` 等）。

### 3.5 模型注册表 models.ini <a id="deploy-modelsini"></a>

`models.ini`（LlamaForge 根目录）由路由器读取，格式为 INI，每模型一个 `[id]` 段，键为 llama-server 参数：

```ini
; LlamaForge model registry - read by llama-server's router.
version = 1

[*]
ctx-size = 150000

[gemma-4-26b-a4b-it-ultra-uncensored-heretic.i1-q4-k-m]
model = /home/minjian/ai/models/gemma-4-26B-A4B-it-ultra-uncensored-heretic.i1-Q4_K_M.gguf
ctx-size = 150000

[qwen3.8-27b-ud-q4-k-m]
model = /home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf
ctx-size = 150000

[qwen3.8-27b-uncensored-q4-k-m]
model = /home/minjian/ai/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
ctx-size = 150000
```

- `[id]`（模型别名）即客户端请求里的 `model` 字段，也出现在 `/v1/models` 的 `id`。
- 字段如 `model`（路径）、`mmproj`（视觉投影）、`ctx-size`、`n-gpu-layers`、`flash-attn`、`embeddings` 等。
- **改完 `models.ini` 需重启路由**（`stop.sh && run.sh`）才生效；面板 Models 页调参则由后端自动应用并重载。

> 也可在面板的 Discover / Models 页直接登记 / 改参，效果等同。

## 4. 运行参数说明 <a id="params"></a>

llama-server（路由模式）关键参数（在 `models.ini` 的模型段或面板 Models 页按模型配置）：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `--models-preset` | `models.ini` | 加载模型注册表（路由模式入口） |
| `--models-max 1` | 1 | 同一时刻最多同时加载的模型数 |
| `-m` / `model` | 模型路径 | 某模型的权重路径（`models.ini` 段内为 `model = ...`） |
| `-mm` / `mmproj` | mmproj 路径 | Qwen 视觉投影，启用图片输入 |
| `-ngl` / `n-gpu-layers 999` | 999 | 全部 Transformer 层卸载到 GPU |
| `-c` / `ctx-size 150000` | 150000 | 上下文窗口（可在面板按模型加大到 256K） |
| `-ctk q4_0` / `-ctv q4_0` | q4_0 | K cache / V cache 量化，压缩长上下文显存 |
| `--flash-attn on` | on | 开启 Flash Attention |
| `--host` / `--port` | `127.0.0.1` / `8080` | 监听地址 |
| `--jinja-jinjatemplate` | 模板 | 无内置模板的模型可在面板指定 jinja 模板 |

服务与调用关系：

```mermaid
flowchart LR
  subgraph mjpc ["mjpc 开发机"]
    OE ["opencode<br/>llamacpp provider"]
    DSH ["dsh web :3080<br/>llamacpp provider"]
    LF ["LlamaForge 面板 :8090<br/>(run.sh / stop.sh)"]
    R ["llama-server 路由 :8080<br/>OpenAI 兼容 / 按需加载"]
    M ["models.ini 注册表<br/>gemma-4 · Qwen-UD · Qwen-Unc"]
    GPU ["RTX 4090<br/>CUDA sm_89 全层上卡"]
  end
  OE -->|"model=别名 HTTP /v1/chat/completions"| R
  DSH -->|"model=别名 HTTP /v1/chat/completions"| R
  LF -->|"重载路由 / 按需加载"| R
  R -->|"按 models.ini 加载"| M
  R -->|"CUDA 上卡推理"| GPU
```

## 5. 日常使用 <a id="daily"></a>

### 5.1 验证服务就绪 <a id="daily-check"></a>

```bash
# 列出已注册/可加载模型（返回别名列表即就绪）
curl -s http://127.0.0.1:8080/v1/models
# 健康检查
curl -s http://127.0.0.1:8080/health
# 面板
curl -s http://127.0.0.1:8090/
```

### 5.2 调用推理接口 <a id="daily-chat"></a>

> ⚠️ `model` 字段用**模型别名**（`/v1/models` 的 `id`，即 `models.ini` 的 `[id]`），**不用 GGUF 全路径**。

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "model": "gemma-4-26b-a4b-it-ultra-uncensored-heretic.i1-q4-k-m",
        "messages": [{"role": "user", "content": "1+1=？"}],
        "max_tokens": 64,
        "stream": false
      }'
```

> 用全路径会报 `400 {"error":"model '...' not found"}`。换模型只需改 `model` 别名。

> **推理模型 token 预算**：上下文里若启用带思考的模型，会先输出 `reasoning_content`（思考）再出 `content`，
> 短问答也要给足 `max_tokens`（32/64 起步），长任务（带图评审等）思考可能上万 token，注意 `max_tokens` 与耗时。

### 5.3 接入 opencode <a id="daily-opencode"></a>

项目 `.opencode/opencode.json` 的 `llamacpp` 提供商指向本服务（`baseURL` 为 `http://127.0.0.1:8080/v1`）：

```jsonc
"model": "llamacpp/gemma-4-26b-a4b-it-ultra-uncensored-heretic.i1-q4-k-m",
"provider": {
  "llamacpp": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "本地（llama.cpp / LlamaForge）",
    "options": { "baseURL": "http://127.0.0.1:8080/v1", "apiKey": "local" },
    "models": {
      "gemma-4-26b-a4b-it-ultra-uncensored-heretic.i1-q4-k-m": {
        "name": "gemma-4-26b (LlamaForge)",
        "limit": { "context": 150000, "output": 150000 },
        "tool_call": true, "reasoning": true, "attachment": true
      }
    }
  }
}
```

> ⚠️ **改点**：`model` 与 `models` 的键名必须是**模型别名**（如 `gemma-4-...` / `qwen3.8-27b-ud-q4-k-m`），
> 不再是 GGUF 全路径。若沿用旧的全路径配置，会因 `model not found` 而失效。
> 同文件里还有 `lmstudio` 提供商（`baseURL` 指向 `127.0.0.1:1234`），当前未运行；本地推理走 `llamacpp`（8080）。

### 5.4 接入 dsh（DeepSeek Harness） <a id="daily-dsh"></a>

dsh 同样以自定义 provider `llamacpp` 接本服务（同一 `127.0.0.1:8080`）：`baseURL` 为 `http://127.0.0.1:8080/v1`，**model id 用模型别名**（与 5.2 示例的 `model` 一致，如 `qwen3.8-27b-ud-q4-k-m`）。
dsh 的 pi-ai 适配器要求该 provider **必须配置一个（占位）API key**，否则报 `No API key for provider: llamacpp`；llama.cpp 不校验该 key，占位值即可。完整配置见《deepseek_harness部署使用说明》5.3 节，注意把 `model` 由全路径改成别名。

### 5.5 LlamaForge 面板使用 <a id="daily-panel"></a>

- 浏览器打开 `http://127.0.0.1:8090`。
- **Models**：选模型、调参（上下文/GPU 层数/采样等）、加载/卸载；选"启动自动加载"的模型。
- **Discover**：在 huggingface.co 搜 GGUF（llama.cpp）模型，带显存适配评级（FITS/TIGHT/CPU OFFLOAD），一键下载并登记。
- **Build / Update**：增量编译 / 更新 llama.cpp（自动探测 CUDA 架构，旧版备份）。
- **Setup**：检测 Git/CMake/Ninja/编译器/CUDA，扫描磁盘上的 GGUF，检出已删除模型。
- 加载大模型会**占用 GPU**；与 ComfyUI（出图）不能同时跑大模型，用哪个先停另一个（桌面「ComfyUI 停止」）。

## 6. 维护与排障 <a id="maintain"></a>

### 6.1 模型清单与显存 <a id="maintain-models"></a>

| 模型别名（= model 字段） | GGUF 文件 | 约显存 |
| --- | --- | --- |
| `gemma-4-26b-a4b-it-ultra-uncensored-heretic.i1-q4-k-m` | `/home/minjian/ai/models/gemma-4-26B-A4B-it-ultra-uncensored-heretic.i1-Q4_K_M.gguf` | ~16G |
| `qwen3.8-27b-ud-q4-k-m` | `/home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf` | ~16G |
| `qwen3.8-27b-uncensored-q4-k-m` | `/home/minjian/ai/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf` | ~16G |

### 6.2 改动后的生效顺序 <a id="maintain-apply"></a>

| 改动对象 | 生效方式 |
| --- | --- |
| `models.ini`（加模型 / 改模型参数） | 重启路由：`stop.sh && run.sh`（或面板 Models 页改参自动重载） |
| `config.json`（端口 / server_bin / model_dirs） | `stop.sh && run.sh` 重读 |
| `.opencode/opencode.json` | 重启 opencode（启动时读取；`model` 用别名） |
| `~/.dsh/settings.yaml` / `~/.dsh/.credentials.yaml`（5.4 节） | dsh 下一次请求即生效 |

### 6.3 调参建议 <a id="maintain-tune"></a>

- **显存吃紧**：降某模型的 `ctx-size`、保持 `-ctk/-ctv q4_0`，或换更小量化（面板 Discover 可看适配评级）。
- **速度优先**：确认 `-ngl 999` 与 `--flash-attn on` 已开；`ctx-size` 不宜远超实际所需。
- **换模型**：在面板 Models 页切换即可（`--models-max 1` 会卸载旧模型加载新模型）；切换后客户端 `model` 字段改用对应别名。

## 7. 常见问题 <a id="faq"></a>

| 问题 | 处理 |
| --- | --- |
| 面板/路由起不来？ | `bash /home/minjian/develop/LlamaForge/run.sh` 看输出；`tail -50 /home/minjian/develop/LlamaForge/logs/router.err.log` 看报错（多为 `server_bin` 不支持路由模式、端口被占、显存不足）。 |
| 客户端报 `model not found`？ | `model` 字段用了 GGUF 全路径，须改**别名**（`/v1/models` 的 `id`）。 |
| 端口 8080 被占？ | 检查是否有旧 llama-server 或服务占用；确认旧的 `qwen.service` 已删（`systemctl --user status qwen`）。 |
| 加载模型很慢？ | 16G 权重首次加载 30–60 秒属正常；用 `curl /v1/models` 确认状态，勿反复重启。 |
| `content` 返回空？ | 推理模型思考占满 `max_tokens`（5.2 节）。调大 `max_tokens`，或读 `reasoning_content`。 |
| 想加新模型？ | 放 `.gguf` 到 `/home/minjian/ai/models/`，面板 Setup/Models 扫描，或手动写入 `models.ini` 后重启路由。 |
| 端口想改？ | 改 `config.json` 的 `router_port`/`panel_port` 与 `router_host`，`stop.sh && run.sh` 生效；`router_host` 非 localhost 时须设 `router_api_key`。 |

## 8. 历史遗留：旧的 qwen.service 与启停脚本 <a id="legacy"></a>

2026-08-29 前，llama.cpp 由单模型 systemd 用户服务 `~/.config/systemd/user/qwen.service`（固定加载 Qwen3.8-27B-UD、端口 8080）直接托管，另有 `qwen-start.sh / qwen-stop.sh / qwen-restart.sh` 脚本。**现状**：

- `qwen.service` **已删除**（不再随开机自启、不再存在），桌面「本地LLM」快捷方式也已移除。
- `~/develop/llama.cpp/qwen-start.sh / qwen-stop.sh / qwen-restart.sh` 与 `qwen-server.log` **已于 2026-08-29 删除**（过时且与 LlamaForge 路由同抢 8080）。如需改回单模型 systemd 直管方式，请先停掉 LlamaForge 路由避免端口冲突。

---

> 本文档基于 llama.cpp 0.3.0-dev（commit `cb30059`，CUDA sm_89 / RTX 4090）+ LlamaForge（Python 3.10+ 纯标准库）编写。
> 项目：[github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) · [github.com/dadwritestech/LlamaForge](https://github.com/dadwritestech/LlamaForge) · 生成日期：2026-08-28 · 修订：2026-08-29（改为 LlamaForge 主导，模型清单 3 个，客户端 `model` 改用别名）

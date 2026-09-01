# llamacpp 部署与使用说明

> mjpc 开发机（Ubuntu 26.04 / RTX 4090 24G）· 基于 llama.cpp 0.3.0-dev（build 87，commit `9d81721`）

[文档首页](../../文档首页.md) › 资料 › llamacpp 部署与使用说明

## 1. 概述 <a id="intro"></a>

llama.cpp 是 C/C++ 实现的本地大模型推理引擎，自带 `llama-server`——一个 **OpenAI 兼容** 的 HTTP 服务。
本项目用它在本机跑 **Qwen3.8-27B** 系列三个量化模型（均含多模态视觉投影 mmproj），作为
[opencode](https://opencode.ai) 与 dsh（DeepSeek Harness，见《[deepseek_harness部署使用说明](deepseek_harness部署使用说明.md)》）的本地模型后端，
全程离线、免费、无 API Key（dsh 侧需配一个占位 key，见 5.4 节）。

与 LM Studio 的关系：opencode 的 `llamacpp` 提供商接的是 llama.cpp 的 `llama-server`（端口 **8080**），
与 `lmstudio` 提供商（端口 1234，当前未运行）互不相干。本文只讲 llama.cpp 这一条链路。

核心特点：

- **OpenAI 兼容**：`/v1/chat/completions`、`/v1/models` 标准接口，任意 OpenAI SDK 直连。
- **CUDA 加速**：27B 模型全层（`-ngl 999`）卸载到 RTX 4090 显存，K/V 量化 q4_0 省显存。
- **长上下文**：256K（`-c 262144`），配合 Flash Attention。
- **多模态**：加载 mmproj 视觉投影（`-mm`），支持图片输入。
- **推理模型**：以 `--reasoning-format deepseek` 运行，先输出思考（`reasoning_content`）再出正文。
- **多模型可选、人工启动**：三个 Qwen3.8-27B 量化版（UD / 官方标准版 / Uncensored）各配一个启动脚本，
  换模型即换脚本；**不常驻**，需要时手动启动（纯脚本 nohup 方式，见第 3.3 / 3.4 节），启动前自动停掉当前模型、一次只跑一个。

## 2. 环境要求 <a id="prereq"></a>

本机（mjpc，Ubuntu 26.04.1 LTS）已验证的环境：

| 项 | 值 |
| --- | --- |
| 主机 | mjpc（内网 `192.168.0.124`） |
| GPU | NVIDIA GeForce RTX 4090，显存 24564 MiB，驱动 595.84 |
| 编译工具链 | GCC/GNU 15.2.0（Linux x86_64）+ CUDA（`nvcc`） |
| llama.cpp | 0.3.0-dev（build 87，commit `9d81721`），CMake Release，CUDA 开启 |
| 源码目录 | `/home/minjian/develop/llama.cpp` |
| 模型目录 | `/home/minjian/ai/models/` |

模型文件（三个 Qwen 主模型 + 一个共享 mmproj；gemma 已删除，见第 6.1 节）：

```text
/home/minjian/ai/models/
└── Qwen3.8-27B-UD-Q4_K_M.gguf             # 主模型 1：UD 版，Q4_K_M 量化，约 16.4G（多模态）
└── Qwen3.8-27B-Q4_K_M.gguf                # 主模型 2：官方标准版，Q4_K_M 量化，约 16.8G（多模态）
└── Qwen3.8-27B-Uncensored-Q4_K_M.gguf     # 主模型 3：Uncensored 版，Q4_K_M 量化，约 16.8G（多模态）
└── mmproj-Qwen3.8-27B-f16.gguf            # 多模态视觉投影，f16，885M（三个主模型共用）
```

> 显存核算：单个 Q4_K_M 权重约 16.4–16.8G + mmproj 0.9G，`-ngl 999` 全上卡，K/V 用 q4_0 量化压住 256K 上下文的 cache，
> 三个模型均可在 24G 显存内加载（实测峰值约 23.8–24.0 GiB）。启动日志有一条
> `n_gpu_layers already set by user to 999` 的 W 级提示，属正常，不影响加载。

## 3. 部署 <a id="deploy"></a>

### 3.1 获取并编译 llama.cpp <a id="deploy-build"></a>

```bash
# 克隆源码（国内网络可加 ghfast.top 前缀加速，实测有效）
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

> **源码更新后需重新编译**：llama.cpp 为自编译源码运行，`git pull` 拉新源码后若不重建，
> 二进制仍是旧编译版。2026-09-01 实测：旧编译版（build 1，commit `cb30059`）加载 mmproj 时在
> `mtmd/clip` 处 `ggml_abort` 崩溃（core-dump / CUDA OOM）；`git pull` 到新源码（含 `qwen4exp` 系
> `mtmd input, cuda abort` 修复）并重编译为 build 87（`9d81721`）后，mmproj 加载正常，256K + mmproj
> 三个模型均能启动。编译完成后用 `llama-server --version` 核对 commit。

### 3.2 放置模型与 chat 模板 <a id="deploy-model"></a>

- 模型与 mmproj 放 `/home/minjian/ai/models/`（见第 2 节清单）。
- chat 模板 `templates/chat_template_qwen38_v22.4.jinja` 放源码目录 `templates/` 下，服务以 `--jinja` + `--chat-template-file` 引用（第 4 节）。

### 3.3 启动方式：纯脚本 + nohup（不常驻） <a id="deploy-scripts"></a>

服务**不常驻**，需要时用脚本手动启动；脚本以 nohup 后台拉起 `llama-server`，每次启动前自动停止当前
端口 8080 上的其它模型（一次只跑一个）。多模型靠**多脚本**区分，换模型即运行对应脚本。

源码目录脚本清单：

```text
/home/minjian/develop/llama.cpp/
└── qwen-ud.sh        # 启动 UD 版（Qwen3.8-27B-UD-Q4_K_M）
└── qwen-std.sh       # 启动官方标准版（Qwen3.8-27B-Q4_K_M，无 UD 后缀）
└── qwen-unc.sh       # 启动 Uncensored 版（Qwen3.8-27B-Uncensored-Q4_K_M）
└── qwen-start.sh     # 通用启动：qwen-start.sh [ud|std|unc]，默认 ud（上三脚本即转发至此）
└── qwen-stop.sh      # 停止当前端口 8080 服务（一次一个，无需区分模型）
└── qwen-restart.sh   # 重启：qwen-restart.sh [ud|std|unc]，默认 ud
└── qwen-server.log   # 运行时日志（nohup 追加写入）
└── qwen-server.pid   # 最近一次启动的 PID 文件
```

用法：

```bash
~/develop/llama.cpp/qwen-ud.sh        # 启动 UD 版（先自动停其它）
~/develop/llama.cpp/qwen-std.sh       # 启动官方标准版
~/develop/llama.cpp/qwen-unc.sh       # 启动 Uncensored 版
~/develop/llama.cpp/qwen-stop.sh      # 停止当前服务
~/develop/llama.cpp/qwen-restart.sh std   # 重启为标准版
```

> 历史说明：早期采用 systemd 用户服务 `qwen.service`（disabled，人工启停）。为承载多模型自选，
> 2026-09-01 起改为纯脚本 + nohup 管理，`qwen.service` 已禁用并移除；相关 `qwen-start.sh` 亦由
> systemd 优先改通用模型启动器。

### 3.4 启停脚本内部约定 <a id="deploy-notes"></a>

- 三个模型共用 `-m` 换路径、`-mm` 固定为同一 mmproj、其余参数一致（`-ngl 999 -c 262144 -ctk q4_0 -ctv q4_0 --flash-attn on --jinja --chat-template-file ... --reasoning-format deepseek --reasoning-preserve`）。
- 每次 `qwen-*.sh` 启动前先调用 `qwen-stop.sh`（按端口 8080 pkill），保证一次仅一个模型。
- 参数改动集中在 `qwen-start.sh` 的 `MODEL` / `DISPLAY` 映射与公共参数处；换模型无需动启动脚本。

## 4. 运行参数说明 <a id="params"></a>

`llama-server` 关键参数：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `-m` | 主模型路径 | 对应所选 Qwen3.8-27B 版本（UD / 官方标准版 / Uncensored）的 `Q4_K_M` 权重 |
| `-mm` | mmproj 路径 | 多模态视觉投影（`f16`），启用图片输入（三模型共用） |
| `-ngl 999` | 999 | 全部 Transformer 层卸载到 GPU |
| `-c 262144` | 256K | 上下文窗口长度 |
| `-ctk q4_0` / `-ctv q4_0` | q4_0 | K cache / V cache 量化，压缩长上下文显存占用 |
| `--flash-attn on` | on | 开启 Flash Attention |
| `--host` / `--port` | `127.0.0.1` / `8080` | 监听地址；8080 为 llama.cpp 默认端口 |
| `--jinja` | — | 用 Jinja 模板渲染对话（配合下项） |
| `--chat-template-file` | `.jinja` 路径 | 自定义 Qwen3.8 chat 模板 |
| `--reasoning-format deepseek` | deepseek | 推理模型思考格式，正文前先输出 `reasoning_content` |
| `--reasoning-preserve` | — | 保留思考内容（不丢弃） |

服务与调用关系：

```mermaid
flowchart LR
  subgraph mjpc ["mjpc 开发机"]
    OE ["opencode<br/>llamacpp provider"]
    DSH ["dsh web :3080<br/>llamacpp provider"]
    LS ["llama-server :8080<br/>OpenAI 兼容"]
    M ["Qwen3.8-27B Q4_K_M 16.4-16.8G<br/>UD / 标准版 / Uncensored 三选一<br/>+ mmproj f16"]
    SC ["qwen-ud / qwen-std / qwen-unc.sh<br/>nohup 手动启动"]
  end
  OE -->|"HTTP /v1/chat/completions"| LS
  DSH -->|"HTTP /v1/chat/completions"| LS
  SC -->|"手动启动 / 停止（一次一个）"| LS
  LS -->|"CUDA sm_89 全层上卡"| M
```

## 5. 日常使用 <a id="daily"></a>

### 5.1 启动与验证服务就绪 <a id="daily-check"></a>

```bash
~/develop/llama.cpp/qwen-ud.sh          # 或 qwen-std.sh / qwen-unc.sh
curl -s http://127.0.0.1:8080/health    # {"status":"ok"} 即就绪
curl -s http://127.0.0.1:8080/v1/models # 返回加载的主模型全路径
```

> 模型加载约 30–60 秒，就绪前 `curl` 会连接失败，用轮询确认，勿反复重启。

### 5.2 调用推理接口 <a id="daily-chat"></a>

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "model": "/home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf",
        "messages": [{"role": "user", "content": "1+1=？"}],
        "max_tokens": 64,
        "stream": false
      }'
```

> **推理模型 token 预算**：`--reasoning-format deepseek` 下，先输出 `reasoning_content`（思考）再出 `content`。
> 实测 `max_tokens=8` 时全被思考占满、`content` 为空；放到 32/64 才出正文。短问答也要给足预算，
> 长任务（带图评审等）思考可能上万 token，注意 `max_tokens` 与耗时。

### 5.3 接入 opencode <a id="daily-opencode"></a>

项目 `.opencode/opencode.json` 已配置 `llamacpp` 提供商（启动时读取，改动后需重启 opencode）：

```jsonc
"model": "llamacpp/qwen3.8-27b-ud-q4-k-m",
"provider": {
  "llamacpp": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "本地（llama.cpp）",
    "options": { "baseURL": "http://127.0.0.1:8080/v1", "apiKey": "local" },
    "models": {
      "qwen3.8-27b-ud-q4-k-m": {
        "name": "Qwen3.8-27B-UD-Q4_K_M",
        "limit": { "context": 262144, "output": 131072 },
        "options": { "reasoningEffort": "medium" },
        "tool_call": true, "reasoning": true, "attachment": true
      }
      // qwen3.8-27b-q4-k-m（官方标准版）、qwen3.8-27b-uncensored-q4-k-m（Uncensored 版）同理
    }
  }
}
```

> 同文件里还有一个 `lmstudio` 提供商（`baseURL` 指向 `127.0.0.1:1234`），当前未运行；本地推理走的是 `llamacpp`（8080）。
> opencode 的模型 id 只是**调用端名称**（lamacpp 服务端 `/v1/models` 恒返回当前加载的 GGUF 全路径），
> 实际切换靠服务端脚本（第 3.3 节）；`models` 注册的多个别名对应同一个 8080 服务，当前加载哪个即提供哪个的响应。

### 5.4 接入 dsh（DeepSeek Harness） <a id="daily-dsh"></a>

dsh 同样以自定义 provider `llamacpp` 接本服务（同一 `127.0.0.1:8080`）：`baseURL` 为 `http://127.0.0.1:8080/v1`，model id 即模型 GGUF 全路径（与 5.2 示例的 `model` 字段一致）。
注意 dsh 的 pi-ai 适配器要求该 provider **必须配置一个（占位）API key**，否则报 `No API key for provider: llamacpp`；llama.cpp 不校验该 key，占位值即可。完整配置见《deepseek_harness部署使用说明》5.3 节。

## 6. 维护与排障 <a id="maintain"></a>

### 6.1 模型清单变更记录 <a id="maintain-move"></a>

- **2026-08-28 模型迁移**：将 UD 版主模型与 mmproj 两个 gguf 从 `~/下载`（易被清理的目录）原子迁移到 `/home/minjian/ai/models/`，此后模型路径以 `/home/minjian/ai/models/` 为准。
- **2026-09-01 多模型化**：目录新增官方标准版 `Qwen3.8-27B-Q4_K_M.gguf` 与 Uncensored 版 `Qwen3.8-27B-Uncensored-Q4_K_M.gguf`；删除 gemma-4-26B 模型（`gemma-4-26B-A4B-it-ultra-uncensored-heretic.i1-Q4_K_M.gguf`，已不复存在）。
- **2026-09-01 systemd 退役**：`qwen.service` 禁用并移除，改多脚本 + nohup 手动启动（第 3.3 节）。

### 6.2 改动后的生效顺序 <a id="maintain-apply"></a>

| 改动对象 | 生效方式 |
| --- | --- |
| `qwen-ud.sh` / `qwen-std.sh` / `qwen-unc.sh` / `qwen-start.sh`（模型路径 / 参数） | 下次调用脚本即生效（需先停再启，`qwen-restart.sh` 可一键完成） |
| `qwen-stop.sh` | 下次调用即生效 |
| `.opencode/opencode.json` | 重启 opencode（配置启动时读取） |
| `~/.dsh/settings.yaml` / `~/.dsh/.credentials.yaml`（dsh 接入，5.4 节） | dsh **下一次请求**即生效，无需重启 dsh 或本服务 |

### 6.3 调参建议 <a id="maintain-tune"></a>

- **显存吃紧**：降 `-c`（上下文）、保持 `-ctk/-ctv q4_0`，或降量化精度（更小量化）。实测三个模型在
  256K + mmproj 下显存峰值约 23.8–24.0 GiB，接近 24G 上限；若加其它显存占用建议降 `-c`。
- **速度优先**：确认 `-ngl 999` 与 `--flash-attn on` 已开；`-c` 不宜远超实际所需（cache 按上限预留）。
- **换模型**：直接运行对应脚本（`qwen-ud/std/unc.sh`），无需改任何配置；opencode 侧 `models` 别名均已注册。

## 7. 常见问题 <a id="faq"></a>

| 问题 | 处理 |
| --- | --- |
| 服务起不来 / 端口 8080 连不上？ | `~/develop/llama.cpp/qwen-server.log` 看报错（多为显存不足、路径错、或 mmproj 架构不匹配）；`tail -50 qwen-server.log`。 |
| 模型加载很慢？ | 16G+ 权重 + 256K 上下文首次加载 30–60 秒属正常；用 `curl /v1/models` 轮询确认就绪，勿反复重启。 |
| `content` 返回空？ | 推理模型思考占满 `max_tokens`（5.2 节）。调大 `max_tokens`，或读 `reasoning_content` 字段。 |
| 日志里 `n_gpu_layers already set by user to 999`？ | W 级正常提示：`-ngl 999` 已显式指定，跳过自动拟合，忽略即可。 |
| 日志里 `GGML_ASSERT(buffer) failed` / `cudaMalloc failed: out of memory`？ | 多为共享显存不足或旧二进制 mmproj 崩溃（见 3.1 节重编译提示）；先 `qwen-stop.sh` 释放显存再启；还不行检查是否 `git pull` 后未重编译。 |
| 端口想用别的？ | 改 `qwen-start.sh` 的 `PORT` 与 opencode 的 `baseURL`，两处一致后重启脚本。 |
| 如何彻底停止？ | `~/develop/llama.cpp/qwen-stop.sh`（停止并释放显存；脚本不常驻、无开机自启）。 |

---

> 本文档基于 llama.cpp 0.3.0-dev（build 87 / commit `9d81721`，CUDA sm_89 / RTX 4090 环境）编写。
> 项目：[github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) · 生成日期：2026-08-28 · 修订：2026-09-01（多模型脚本化、重编译至 9d81721、gemma 移除、systemd 退役）
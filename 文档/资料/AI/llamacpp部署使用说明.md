# llamacpp 部署与使用说明

> mjpc 开发机（Ubuntu 26.04 / RTX 4090 24G）· 基于 llama.cpp 0.3.0-dev（build 1，commit `cb30059`）

[文档首页](../../文档首页.md) › 资料 › llamacpp 部署与使用说明

## 1. 概述 <a id="intro"></a>

llama.cpp 是 C/C++ 实现的本地大模型推理引擎，自带 `llama-server`——一个 **OpenAI 兼容** 的 HTTP 服务。
本项目用它在本机跑 **Qwen3.8-27B**（含多模态视觉投影），作为 [opencode](https://opencode.ai) 的本地模型后端，
全程离线、免费、无 API Key。

与 LM Studio 的关系：opencode 的 `llamacpp` 提供商接的是 llama.cpp 的 `llama-server`（端口 **8080**），
与 `lmstudio` 提供商（端口 1234，当前未运行）互不相干。本文只讲 llama.cpp 这一条链路。

核心特点：

- **OpenAI 兼容**：`/v1/chat/completions`、`/v1/models` 标准接口，任意 OpenAI SDK 直连。
- **CUDA 加速**：27B 模型全层（`-ngl 999`）卸载到 RTX 4090 显存，K/V 量化 q4_0 省显存。
- **长上下文**：256K（`-c 262144`），配合 Flash Attention。
- **多模态**：加载 mmproj 视觉投影（`-mm`），支持图片输入。
- **推理模型**：以 `--reasoning-format deepseek` 运行，先输出思考（`reasoning_content`）再出正文。
- **systemd 托管**：用户服务 `qwen.service` 自动拉起、失败自恢复，另备启停脚本。

## 2. 环境要求 <a id="prereq"></a>

本机（mjpc，Ubuntu 26.04.1 LTS）已验证的环境：

| 项 | 值 |
| --- | --- |
| 主机 | mjpc（内网 `192.168.0.124`） |
| GPU | NVIDIA GeForce RTX 4090，显存 24564 MiB，驱动 595.84 |
| 编译工具链 | GCC/GNU 15.2.0（Linux x86_64）+ CUDA（`nvcc`） |
| llama.cpp | 0.3.0-dev（commit `cb30059`），CMake Release，CUDA 开启 |
| 源码目录 | `/home/minjian/develop/llama.cpp` |
| 模型目录 | `/home/minjian/ai/models/` |

模型文件（已从 `~/下载` 迁移至此，避免误删，见第 6.1 节）：

```text
/home/minjian/ai/models/
└── Qwen3.8-27B-UD-Q4_K_M.gguf     # 主模型，Q4_K_M 量化，16G
└── mmproj-Qwen3.8-27B-f16.gguf    # 多模态视觉投影，f16，885M
```

> 显存核算：Q4_K_M 权重约 16G + mmproj 0.9G，`-ngl 999` 全上卡，K/V 用 q4_0 量化压住 256K 上下文的 cache，
> 24G 显存可容纳（启动日志有一条 `n_gpu_layers already set by user to 999` 的 W 级提示，属正常，不影响加载）。

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

### 3.2 放置模型与 chat 模板 <a id="deploy-model"></a>

- 模型与 mmproj 放 `/home/minjian/ai/models/`（见第 2 节清单）。
- chat 模板 `templates/chat_template_qwen38_v22.4.jinja` 放源码目录 `templates/` 下，服务以 `--jinja` + `--chat-template-file` 引用（第 4 节）。

### 3.3 systemd 用户服务 <a id="deploy-systemd"></a>

服务单元 `~/.config/systemd/user/qwen.service`：

```ini
[Unit]
Description=Qwen3.8-27B llama.cpp 本地推理服务
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/minjian/develop/llama.cpp
ExecStart=/home/minjian/develop/llama.cpp/build/bin/llama-server \
  -m /home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf \
  -mm /home/minjian/ai/models/mmproj-Qwen3.8-27B-f16.gguf \
  -ngl 999 -c 262144 -ctk q4_0 -ctv q4_0 \
  --flash-attn on --host 127.0.0.1 --port 8080 \
  --jinja \
  --chat-template-file /home/minjian/develop/llama.cpp/templates/chat_template_qwen38_v22.4.jinja \
  --reasoning-format deepseek \
  --reasoning-preserve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

启用与查看：

```bash
systemctl --user daemon-reload
systemctl --user enable --now qwen.service    # 启用并立即启动
systemctl --user status qwen.service --no-pager
journalctl --user -u qwen.service -f          # 跟踪日志
```

### 3.4 启停脚本 <a id="deploy-scripts"></a>

源码目录另备三个脚本（systemd 不可用时退化为 nohup 后台进程，参数须与 service 保持一致）：

```text
/home/minjian/develop/llama.cpp/
└── qwen-start.sh     # 启动（优先 systemd，退化 nohup；端口 8080）
└── qwen-stop.sh      # 停止（优先 systemd，退化按端口 pkill）
└── qwen-restart.sh   # 重启（优先 systemd，退化先停后起）
└── qwen-server.log   # 仅 nohup 退化路径的日志（systemd 日志走 journal）
└── qwen-server.pid   # 仅 nohup 退化路径的 PID 文件
```

```bash
~/develop/llama.cpp/qwen-start.sh
~/develop/llama.cpp/qwen-stop.sh
~/develop/llama.cpp/qwen-restart.sh
```

## 4. 运行参数说明 <a id="params"></a>

`llama-server` 关键参数：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `-m` | 主模型路径 | Qwen3.8-27B `Q4_K_M` 权重 |
| `-mm` | mmproj 路径 | 多模态视觉投影（`f16`），启用图片输入 |
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
    LS ["llama-server :8080<br/>OpenAI 兼容"]
    M ["Qwen3.8-27B Q4_K_M 16G<br/>+ mmproj f16"]
    SD ["systemd qwen.service"]
  end
  OE -->|"HTTP /v1/chat/completions"| LS
  SD -->|"托管启停 / 失败自恢复"| LS
  LS -->|"CUDA sm_89 全层上卡"| M
```

## 5. 日常使用 <a id="daily"></a>

### 5.1 验证服务就绪 <a id="daily-check"></a>

```bash
# 列出已加载模型（返回主模型路径即就绪；加载约 30–60 秒）
curl -s http://127.0.0.1:8080/v1/models
# 健康检查
curl -s http://127.0.0.1:8080/health
```

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
"model": "llamacpp//home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf",
"provider": {
  "llamacpp": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "本地（llama.cpp）",
    "options": { "baseURL": "http://127.0.0.1:8080/v1", "apiKey": "local" },
    "models": {
      "/home/minjian/ai/models/Qwen3.8-27B-UD-Q4_K_M.gguf": {
        "name": "qwen3.8-27b llama.cpp",
        "limit": { "context": 262144, "output": 262144 },
        "options": { "reasoningEffort": "medium" },
        "tool_call": true, "reasoning": true, "attachment": true
      }
    }
  }
}
```

> 同文件里还有一个 `lmstudio` 提供商（`baseURL` 指向 `127.0.0.1:1234`），当前未运行；本地推理走的是 `llamacpp`（8080）。
> 模型路径变动时，`model`、`models` 键名两处须同步（本仓库内，见第 6.2 节迁移记录）。

## 6. 维护与排障 <a id="maintain"></a>

### 6.1 模型迁移（下载 → ai/models） <a id="maintain-move"></a>

2026-08-28 将两个 gguf 从 `~/下载`（易被清理的目录）原子迁移到 `/home/minjian/ai/models/`，
并同步 4 处引用：`qwen.service`、`qwen-start.sh`、`.opencode/opencode.json`、《本地资源》（gitignore）。
此后模型路径以 `/home/minjian/ai/models/` 为准。

### 6.2 改动后的生效顺序 <a id="maintain-apply"></a>

| 改动对象 | 生效方式 |
| --- | --- |
| `qwen.service` / 模型路径 / 参数 | `systemctl --user daemon-reload && systemctl --user restart qwen.service`（约 1 分钟重载） |
| `qwen-start.sh` / `qwen-stop.sh` | 下次调用脚本即生效（systemd 路径下以 service 为准） |
| `.opencode/opencode.json` | 重启 opencode（配置启动时读取） |

### 6.3 调参建议 <a id="maintain-tune"></a>

- **显存吃紧**：降 `-c`（上下文）、保持 `-ctk/-ctv q4_0`，或降量化精度（更小量化）。
- **速度优先**：确认 `-ngl 999` 与 `--flash-attn on` 已开；`-c` 不宜远超实际所需（cache 按上限预留）。
- **换模型**：改 `-m`/`-mm` 路径与 `-c`，重命名后同步第 6.2 节各处引用。

## 7. 常见问题 <a id="faq"></a>

| 问题 | 处理 |
| --- | --- |
| 服务起不来 / 端口 8080 连不上？ | `systemctl --user status qwen.service` 看状态；`journalctl --user -u qwen.service -n 50` 看报错（多为显存不足或路径错）。 |
| 模型加载很慢？ | 16G 权重 + 256K 上下文首次加载 30–60 秒属正常；用 `curl /v1/models` 轮询确认就绪，勿反复重启。 |
| `content` 返回空？ | 推理模型思考占满 `max_tokens`（5.2 节）。调大 `max_tokens`，或读 `reasoning_content` 字段。 |
| 日志里 `n_gpu_layers already set by user to 999`？ | W 级正常提示：`-ngl 999` 已显式指定，跳过自动拟合，忽略即可。 |
| 端口想用别的？ | 改 `qwen.service` 的 `--port` 与 `qwen-start/stop.sh` 的 `PORT`、opencode 的 `baseURL`，三处一致后重启。 |
| `qwen-server.log` 显示旧路径？ | 该文件仅 nohup 退化路径写入；systemd 运行日志在 journal，以 `journalctl --user -u qwen.service` 为准。 |
| 如何彻底停止？ | `systemctl --user disable --now qwen.service`（停并取消开机自启）。 |

---

> 本文档基于 llama.cpp 0.3.0-dev（commit `cb30059`，CUDA sm_89 / RTX 4090 环境）编写。
> 项目：[github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) · 生成日期：2026-08-28

# mjw 识图 MCP 使用说明

> opencode 侧 MCP 识图工具 · 调 mjw LM Studio 的 qwen3-vl-8b

[文档首页](../../文档首页.md) › 资料 › mjw 识图 MCP 使用说明

> **来源与接入（2026-09-09）**：本文自 cw 仓库同名文档导入，导入时配套已同步到本仓库——`scripts/tools/vision/mjw_vision_mcp.py`、`.opencode/opencode.json` 的 `mjw-vision` MCP 登记与 `deploy/.env` 的 `LMSTUDIO_MJW_*` 凭据键均已就位；cw 仓库若有更新，以 cw 为准并同步回本文。

## 1. 概述 <a id="intro"></a>

本仓库在 opencode 里登记了一个本地 MCP server **mjw-vision**（脚本 `scripts/tools/vision/mjw_vision_mcp.py`），把本地模型机 **mjw** 上 LM Studio 的 `qwen3-vl-8b-instruct-abliterated-v2`（多模态识图模型）包装成两个会话内工具：

| 工具 | 作用 |
| --- | --- |
| `describe_image` | 识图：详述画面内容、构图、风格，以及画面中的对话框/气泡与其内文字 |
| `read_text` | OCR：识别图片中的文字，默认专注漫画气泡内对话并标注位置 |

与《[LM Studio 模型服务使用说明](LM Studio模型服务使用说明.md)》的关系：前者讲 mjw 上 LM Studio **服务端**本身（模型清单、curl 直调）；本文讲 opencode **客户端侧**把该服务接成 MCP 工具链的配置、协议与使用。

## 2. 注册与前置条件 <a id="setup"></a>

### 2.1 配置登记 <a id="config"></a>

MCP server 登记在 `.opencode/opencode.json` 的 `mcp` 段：

```json
"mcp": {
  "mjw-vision": {
    "type": "local",
    "command": ["python3", "scripts/tools/vision/mjw_vision_mcp.py"],
    "enabled": true
  }
},
"experimental": { "mcp_timeout": 200000 }
```

- `command` 用**数组**形式；脚本路径相对于仓库根解析。
- `enabled: false` 可停用；`experimental.mcp_timeout`（毫秒）放宽连接与工具调用超时。

### 2.2 前置条件 <a id="prereq"></a>

- **mjw 开机且 LM Studio 已加载多模态模型**：服务走 OpenAI 兼容接口，机器不在线时工具调用会直接报「无法连接 mjw 识图服务」。
- **凭据写入 `deploy/.env`**（已 gitignore，不入库）：

```text
LMSTUDIO_MJW_BASE=http://<mjw服务地址>/v1
LMSTUDIO_MJW_API_KEY=<token>
LMSTUDIO_MJW_MODEL=qwen3-vl-8b-instruct-abliterated-v2   # 可选，默认即此
```

`LMSTUDIO_MJW_BASE` 与 `LMSTUDIO_MJW_API_KEY` 必填，缺任一脚本启动即报凭据缺失；具体值见《[本地资源](../../用户文档/本地资源.md)》，本文不落内网细节与 token 明文。

## 3. 传输协议与历史坑 <a id="protocol"></a>

MCP stdio 传输自 **2025-06-18 起规范改为 NDJSON**（每条 JSON-RPC 消息单独一行，`\n` 定界）；opencode 内置的 MCP SDK（1.29+，协议版本 2025-11-25）按新规范封帧，本脚本同步实现 NDJSON 读写。

> **历史坑（2026-09-08 修复）**：实现早期用的是 2024 版 `Content-Length:` 帧头，与新版 SDK **双向互不相认**，表现为握手 30 秒超时、日志反复出现 `server unavailable ... key=mjw-vision ... status=failed`，会话里的识图工具一直不出现。排查命令：
>
> ```bash
> rg "mjw-vision" ~/.local/share/opencode/log/opencode.log
> ```
>
> 修复后已用 opencode 同款 SDK（`@modelcontextprotocol/sdk`）直连脚本做最小客户端验证：握手、工具列表、实际调用全部通过。若日后脚本改动后怀疑握手异常，可用同款 SDK 写最小客户端复现，避免绕开 SDK 手写帧误导排查。

## 4. 工具与行为细节 <a id="tools"></a>

### 4.1 describe_image（识图） <a id="describe"></a>

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `image_path` | 是 | 图片路径，绝对路径或相对当前工作目录 |
| `question` | 否 | 针对图片的具体问题；留空则完整描述画面 |

输出：中文详尽描述（内容、构图、角色与动作、背景、色调风格），并逐条引用画面中的对话框/气泡文字；有 `question` 时优先围绕问题回答再补充细节。

### 4.2 read_text（OCR） <a id="readtext"></a>

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `image_path` | 是 | 图片路径，同 4.1 |
| `focus` | 否 | 识别重点；默认「画面内全部文字，优先气泡对话」 |

输出：按行/按块列出识别文字（简体原样），标注大致位置（左上/右上/中央/气泡内/外）；识别不出的字符用 `…` 标出，不编造。

### 4.3 内部处理 <a id="detail"></a>

- **图片压缩**：识图把图缩放至长边 ≤ 1024、OCR ≤ 1536，转 JPEG（质量 88）后 base64 内联进请求，控制 body 体积；无 Pillow 环境时退回原文件 base64。
- **模型参数**：识图 `max_tokens` 1100、OCR 900，`temperature` 0.2（输出稳妥）。
- **多模态模型可自由替换**：`LMSTUDIO_MJW_MODEL` 换成 mjw 上其他多模态模型即可，工具层无感知。

## 5. 使用与验证 <a id="usage"></a>

- **加载时机**：opencode 会话启动时自动拉起 MCP server；会话工具列表出现 `describe_image` / `read_text` 即就绪。
- **触发方式（自然语言）**：把图片路径交给工具即可，例如「读取 `output/xxx.png` 里的对话文字」走 `read_text`，「描述这张图」走 `describe_image`。
- **连通性检查**：会话内直接调用一次工具看返回；或查 `~/.local/share/opencode/log/opencode.log` 是否有 `server unavailable`（无 = 正常）。
- 排查顺序：mjw 开机？→ `deploy/.env` 凭据齐全？→ LM Studio 已加载 qwen3-vl 模型？→ 日志 `server unavailable`？

## 6. 注意事项 <a id="notes"></a>

- **小字 OCR 有偏差**（2026-09-07 实测）：测试图底部小字被读错，大幅清晰图形可靠；重要小字需人工复核。
- **显存共存**：qwen3-vl-8b 与专职翻译 hy-mt2 若同驻 mjw 的 8GB 显存会互相挤占，大批量识别任务建议按需切换加载（见《[LM Studio 模型服务使用说明](LM Studio模型服务使用说明.md)》第 5 节）。
- **定位**：本工具是本地 AI 助手的能力（识图/界面评审/文档图理解/交叉检查），与业务项目的 AI 链路相互独立；识图推理全在 mjw 本机，图片不上云。
- **凭据纪律**：服务地址与 token 只允许出现在 gitignore 的 `deploy/.env` 与《[本地资源](../../用户文档/本地资源.md)》，不得写入本文档或其他被跟踪文件。

> 本文档依《[文档生成规范](../../规范/文档生成规范.md)》编写 · 生成日期：2026-09-08
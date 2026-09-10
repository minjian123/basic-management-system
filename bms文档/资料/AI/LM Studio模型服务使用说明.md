# LM Studio 模型服务使用说明

> 本地模型机 mjw · LM Studio 本地推理服务 · 专职翻译 + 多模态识图

[文档首页](../../文档首页.md) › 资料 › LM Studio 模型服务使用说明

> **来源与接入（2026-09-09）**：本文自 cw 仓库同名文档导入；所述服务（mjw 的 LM Studio）与本仓库的 mjw-vision MCP 工具链（脚本、`.opencode/opencode.json` 登记、`deploy/.env` 凭据键）已同步就位；cw 仓库若有更新，以 cw 为准并同步回本文。

## 1. 概述 <a id="intro"></a>

LM Studio 是 Windows/macOS 上的本地大模型运行工具（基于 llama.cpp 生态），内置 **OpenAI 兼容** 的本地推理服务（`/v1/chat/completions`、`/v1/models` 标准接口），任意 OpenAI SDK 直连。

本地模型机 **mjw** 上常驻该服务，当前提供两个模型：

| 模型 | 定位 |
| --- | --- |
| `hy-mt2-30b-a3b-uncensored-heretic` | **专职翻译**（英⇄中），基于腾讯混元 Hy-MT2-30B-A3B 的社区去审查版 |
| `qwen3-vl-8b-instruct-abliterated-v2` | **多模态**（识图 / 对话 / OCR） |

> 与 llama.cpp 服务（`llamacpp` 提供商，见《[llamacpp部署使用说明](llamacpp部署使用说明.md)》）互不相干：本文服务常驻 mjw（Windows 11 模型机），llama.cpp 跑在 mjpc（Ubuntu）本机。bms 的 dsh / opencode 目前仅经 mjw-vision MCP 工具使用本服务（见《[mjw识图MCP使用说明](mjw识图MCP使用说明.md)》），未登记独立的 `lmstudio` 提供商（如需 dsh 侧直调，另行在 `~/.dsh/settings.yaml` 登记，本文不展开）。

## 2. 访问与鉴权 <a id="access"></a>

访问地址（OpenAI 兼容端点）、主机信息与机器凭据见《[本地资源](../../用户文档/本地资源.md)》的「本地模型机」小节，本文不重复内网细节。

鉴权：服务开启 **API token**（Bearer 方式），请求须携带请求头：

```text
Authorization: Bearer <token>
```

token 值不落公开文档，仅引用位置：

- 明文见《[本地资源](../../用户文档/本地资源.md)》「本地模型机」小节的 **API token** 行。
- LM Studio 服务端：在 mjw 的 LM Studio → Developer（开发者）设置中查看/重置。

## 3. 模型清单与实测结论 <a id="models"></a>

### 3.1 hy-mt2-30b-a3b-uncensored-heretic（专职翻译）

- **定位**：英⇄中专职翻译。社区去审查版（uncensored/heretic），绕开审查限制，译文学术语不敏感词可直译。
- **实测质量（2026-09-07）**：技术段落英译中、中译英均**自然流畅**——术语准确（多租户架构/租户隔离/数据库模式/速率限制）、无直译腔、衔接连贯，达"人话"级翻译。
- **性能**：RTX 3070 Laptop（8 GB）上约 **7 token/秒**（一段 70 词左右译文约 10 秒）。批量长文需等待，建议按段/按页拆分提交。

### 3.2 qwen3-vl-8b-instruct-abliterated-v2（多模态识图）

- **定位**：多模态（识图 / 对话 / OCR），同样为社区去审查版。
- **实测质量（2026-09-07）**：图形/颜色识别准确，中文描述流利；**小字 OCR 有偏差**（测试图中底部小字「测试图片 v1」被读成「©2023 简单设计」）——大幅清晰图形可靠，小字/模糊文字识别会打折扣。
- **翻译能力**：可应急翻译，但质量明显不如 hy-mt2（逐词对应、润色不足），**翻译任务请用 hy-mt2**。
- **经 opencode 使用**：本服务已封装为 opencode 的 mjw-vision MCP 工具（`describe_image` / `read_text`，脚本在 opencode 侧），注册配置、协议与使用见《[mjw识图MCP使用说明](mjw识图MCP使用说明.md)》。

## 4. 调用示例 <a id="usage"></a>

OpenAI 兼容端点，`curl` 直调：

```bash
# 翻译（英译中）
curl http://<服务地址>/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hy-mt2-30b-a3b-uncensored-heretic",
    "messages": [
      {"role": "system", "content": "You are a professional translator. Translate the user text from English to Simplified Chinese. Output only the translation, no explanations."},
      {"role": "user", "content": "文本…"}
    ],
    "temperature": 0.3,
    "max_tokens": 1024
  }'

# 识图（qwen3-vl，图片走 base64 data URI）
curl http://<服务地址>/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-vl-8b-instruct-abliterated-v2",
    "messages": [
      {"role": "user", "content": [
        {"type": "text", "text": "请描述这张图片的内容"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,<base64>"}}
      ]}
    ],
    "max_tokens": 512
  }'
```

`<服务地址>` 与 `<token>` 分别见《[本地资源](../../用户文档/本地资源.md)》与上文第 2 节。

## 5. 注意事项 <a id="notes"></a>

- 翻译参数建议 `temperature=0.3` 左右，偏保守输出更稳；`max_tokens` 给足（一段译文 200-500 词时给 1024 以上）。
- 30B A3B 模型推理较慢，长文翻译需耐心或分段提交；避免超大单请求占满显存拖慢其他任务。
- 两个模型若同时常驻显存会互相挤占（8 GB 显存紧张），大批量任务建议按需切换加载。
- LM Studio 服务机（mjw）非 7×24 常开，调用前确认其已开机且服务在跑。

> 本文档依《文档生成规范》编写 · 生成日期：2026-09-07

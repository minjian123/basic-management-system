#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mjw_vision_mcp.py - opencode MCP server：调用 mjw（192.168.0.114）的 qwen3-vl-8b（LM Studio）识图/OCR
#
# 注册：.opencode/opencode.json 的 mcp.local
#   "mjw-vision": { "type": "local", "command": ["python3", "scripts/tools/vision/mjw_vision_mcp.py"], "enabled": true }
#
# 传输层说明：MCP stdio 自 2025-06-18 规范起改为 NDJSON（每条 JSON-RPC 消息单独一行，\n 定界），
# opencode（MCP SDK 1.29+）按新规范封帧。旧版 Content-Length 帧已废弃，双向互不相认会握手超时
# （表现为日志 "server unavailable" status=failed）。本脚本按 NDJSON 实现读写。
#
# 凭据：从仓库根 deploy/.env 读取（不写进被跟踪文件）
#   LMSTUDIO_MJW_BASE    如 http://192.168.0.114:1234/v1
#   LMSTUDIO_MJW_API_KEY  LM Studio 的 token
#   LMSTUDIO_MJW_MODEL   多模态模型名（默认 qwen3-vl-8b-instruct-abliterated-v2）
#
# 工具：
#   describe_image(image_path, question?)  识图：详尽描述画面（含气泡与其中文字）
#   read_text(image_path, focus?)          OCR：识别图片文字，默认专注气泡内文字
import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None

PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "mjw-vision"
SERVER_VERSION = "1.1.0"


def project_root():
    # scripts/tools/vision/mjw_vision_mcp.py -> 上溯 4 级到仓库根
    return Path(__file__).resolve().parents[3]


def load_env():
    keys = {}
    env_path = project_root() / "deploy" / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return keys
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def env_cfg():
    env = load_env()
    base = env.get("LMSTUDIO_MJW_BASE")
    token = env.get("LMSTUDIO_MJW_API_KEY")
    model = env.get("LMSTUDIO_MJW_MODEL", "qwen3-vl-8b-instruct-abliterated-v2")
    if not base or not token:
        raise RuntimeError(
            "mjw 识图服务凭据缺失：请在 deploy/.env 配置 LMSTUDIO_MJW_BASE 与 LMSTUDIO_MJW_API_KEY"
        )
    return base.rstrip("/"), token, model


def load_image_b64(path, max_edge, quality=88):
    """读图 -> 转正/缩放/压缩 -> jpeg base64。PIL 缺失时返回原文件原始 base64。"""
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"图片不存在: {path}")
    if Image is None or ImageOps is None:
        return "image/png", base64.b64encode(p.read_bytes()).decode("ascii")
    with Image.open(p) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if max(im.size) > max_edge:
            ratio = max_edge / float(max(im.size))
            im = im.resize((int(im.width * ratio), int(im.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return "image/jpeg", base64.b64encode(buf.getvalue()).decode("ascii")


def ask_vlm(mime, b64, system, user, max_tokens=900):
    base, token, model = env_cfg()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            },
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"mjw 识图服务返回 HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 mjw 识图服务({base})：{e.reason}，请确认 mjw 已开机且 LM Studio 已加载模型")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError(f"mjw 响应格式异常: {str(data)[:400]}")


def describe_image(image_path, question):
    sys_prompt = (
        "你是一个本地识图助手。请用中文详尽描述画面：主要内容、构图、角色与动作、"
        "背景细节、色调风格，以及画面中所有对话框/气泡/文字的位置与文字内容（按原样引用）。"
        "若用户有具体问题，优先围绕问题回答，再补充其他可见细节。"
    )
    mime, b64 = load_image_b64(image_path, max_edge=1024)
    q = question.strip() if question and question.strip() else "请详尽描述这张图片的全部内容。"
    return ask_vlm(mime, b64, sys_prompt, q, max_tokens=1100)


def read_text(image_path, focus):
    focus = (focus or "").strip()
    sys_prompt = (
        "你是一个 OCR 助手。请将图片中出现的文字按行或按块识别出来，逐条列出；"
        "中文用简体原样输出，并尽量标注每条文字所在的大致位置（左上/右上/中央/左下/右下、气泡内/外）。"
        "若图片是漫画/插画，优先识别气泡内的对话文字。识别不出的字符用…标出，不要编造。"
    )
    user = f"识别范围与重点：{focus or '画面内全部文字，优先气泡对话'}。请给出识别结果。"
    mime, b64 = load_image_b64(image_path, max_edge=1536)
    return ask_vlm(mime, b64, sys_prompt, user, max_tokens=900)


# ---------------- MCP stdio JSON-RPC（NDJSON，每条消息一行，\n 定界） ----------------

def read_message():
    """读一条 NDJSON（按 \n 定界）。readline 会阻塞到行尾，仅 EOF 时可能返回不完整行。EOF 返回 None。"""
    buf = b""
    while True:
        chunk = sys.stdin.buffer.readline()
        if not chunk:
            if not buf:
                return None
            buf += b"\n"
            break
        buf += chunk
        if buf.endswith(b"\n"):
            break
    try:
        return json.loads(buf.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def write_message(obj):
    data = json.dumps(obj).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def result_meta():
    return {"tools": [
        {
            "name": "describe_image",
            "description": "识图：调用本地多模态模型（mjw qwen3-vl-8b）详尽描述图片画面，"
                           "包括内容、构图、风格，以及画面中的对话框/气泡与其内文字。"
                           "image_path 可为绝对路径或相对当前工作目录的路径。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片文件路径"},
                    "question": {"type": "string", "description": "可选：针对图片的具体问题"},
                },
                "required": ["image_path"],
            },
        },
        {
            "name": "read_text",
            "description": "OCR：调用本地多模态模型（mjw qwen3-vl-8b）识别图片中的文字，"
                           "默认专注漫画气泡内的对话文字并标注位置；可用 focus 指定识别重点。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片文件路径"},
                    "focus": {"type": "string", "description": "可选：识别重点（默认：画面气泡内文字）"},
                },
                "required": ["image_path"],
            },
        },
    ]}


def handle(msg):
    msgid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msgid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}

    if method == "notifications/initialized" or method.startswith("notifications/"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msgid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msgid, "result": result_meta()}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "describe_image":
                text = describe_image(args.get("image_path", ""), args.get("question", ""))
            elif name == "read_text":
                text = read_text(args.get("image_path", ""), args.get("focus", ""))
            else:
                raise RuntimeError(f"未知工具: {name}")
            return {"jsonrpc": "2.0", "id": msgid, "result": {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            }}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msgid, "result": {
                "content": [{"type": "text", "text": f"[识图失败] {e}"}],
                "isError": True,
            }}

    return {"jsonrpc": "2.0", "id": msgid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    while True:
        msg = read_message()
        if msg is None:
            break
        out = handle(msg)
        if out is not None:
            write_message(out)


if __name__ == "__main__":
    main()
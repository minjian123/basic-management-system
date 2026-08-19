#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地多模态 MCP server（LM Studio 后端）。

把本机 LM Studio（OpenAI 兼容）的多模态模型能力暴露为 MCP 工具：

- multimodal_chat：通用多模态对话。文本 + 可选图片（路径）+ 可选文本文档 + 可选系统提示，
  支持 prompts/ 下的场景模板（如 prototype-review）。
- screenshot：Edge/Chrome 无头截图（HTML 或 URL -> PNG），供识图评审前置使用。

环境变量（均可省略，有默认值）：
  MULTIMODAL_API_ENDPOINT   默认 http://127.0.0.1:1234
  MULTIMODAL_API_KEY        默认 local
  MULTIMODAL_API_MODEL      默认 qwen/qwen3.8-27b
  MULTIMODAL_API_TIMEOUT    默认 60
  MULTIMODAL_API_REASONING  默认 none（关闭本地推理模型的思考过程）

运行（项目根目录执行）：
  uv run --project deploy/tools/multimodal python deploy/tools/multimodal/mcp_server.py

依赖：mcp（uv 项目，见 pyproject.toml）。
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"

ENDPOINT = os.environ.get("MULTIMODAL_API_ENDPOINT", "http://127.0.0.1:1234")
API_KEY = os.environ.get("MULTIMODAL_API_KEY", "local")
MODEL = os.environ.get("MULTIMODAL_API_MODEL", "qwen/qwen3.8-27b")
TIMEOUT = float(os.environ.get("MULTIMODAL_API_TIMEOUT", "60"))
REASONING = os.environ.get("MULTIMODAL_API_REASONING", "none")

MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
DOC_EXTS = (".md", ".txt", ".json", ".log", ".py", ".js", ".ts", ".html", ".css", ".yml", ".yaml", ".toml", ".ini", ".csv", ".sql", ".xml")


def img_to_data_uri(path: str) -> str:
    p = Path(path)
    mime = MIME.get(p.suffix.lower(), "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return "data:%s;base64,%s" % (mime, b64)


def resolve_prompt(arg: str) -> str | None:
    """支持三种输入：prompts/ 下的模板名、模板文件路径、直接提示词文本。"""
    if not arg:
        return None
    p = Path(arg)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    cand = PROMPTS_DIR / (arg if arg.endswith(".md") else arg + ".md")
    if cand.is_file():
        return cand.read_text(encoding="utf-8")
    return arg


def call_chat(system, text, data_uris, doc_texts, timeout, reasoning, temperature):
    """调用 OpenAI 兼容 chat/completions 接口；reasoning_effort 不识别时去掉重试一次。"""
    content = [{"type": "text", "text": text}]
    for d in doc_texts:
        content.append({"type": "text", "text": "【文档内容】\n" + d})
    for u in data_uris:
        content.append({"type": "image_url", "image_url": {"url": u}})
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    payload = {
        "model": MODEL,
        "temperature": temperature,
        "messages": messages,
    }
    if reasoning:
        payload["reasoning_effort"] = reasoning
    url = ENDPOINT.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + API_KEY}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 400 and reasoning:
            payload.pop("reasoning_effort")
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        else:
            raise
    return result["choices"][0]["message"]["content"]


def call_with_retry(system, text, data_uris, doc_texts, timeout, reasoning, temperature, max_retries=2):
    last = None
    raw = None
    for attempt in range(max_retries + 1):
        try:
            return call_chat(system, text, data_uris, doc_texts, timeout, reasoning, temperature)
        except urllib.error.HTTPError as e:
            last = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:500])
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if attempt < max_retries:
            time.sleep(2 * (attempt + 1))
    return "错误：调用本地模型失败（%s）" % last


def check_images(images):
    for i in images:
        p = Path(i)
        if not p.is_file():
            raise ValueError("图片不存在: %s" % i)
        if p.suffix.lower() not in IMG_EXTS:
            raise ValueError("不支持的图片格式（支持 %s）: %s" % ("/".join(IMG_EXTS), i))


def check_documents(documents):
    texts = []
    for d in documents:
        p = Path(d)
        if not p.is_file():
            raise ValueError("文档不存在: %s" % d)
        if p.suffix.lower() not in DOC_EXTS:
            raise ValueError("不支持的文档格式（支持 %s）: %s" % ("/".join(DOC_EXTS), d))
        texts.append("[%s]\n%s" % (d, p.read_text(encoding="utf-8", errors="replace")))
    return texts


def run_screenshot(url, out, width, height, budget):
    """调用同目录 screenshot.py（Edge/Chrome 无头截图）。"""
    cmd = [sys.executable, str(BASE_DIR / "screenshot.py"),
           "--url", url, "--out", out,
           "--width", str(width), "--height", str(height), "--budget", str(budget)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        return "错误：截图失败（%s）" % (proc.stderr or proc.stdout or "").strip()
    return "OK：%s" % out


mcp = MCPServer("multimodal-local")


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def multimodal_chat(
    text: str,
    images: list[str] | None = None,
    documents: list[str] | None = None,
    prompt: str | None = None,
    system: str | None = None,
    temperature: float = 0.2,
    reasoning: str = REASONING,
) -> str:
    """通用多模态对话：调用本地模型（LM Studio，多模态）处理文本、图片与文本文档。

    适用：用它看图/评审界面截图；文本整理、翻译、结构化抽取等
    简单重复劳动；需要第二模型交叉检查时。

    参数说明：
      text        用户指令（必填）
      images      图片路径列表（png/jpg/jpeg/webp/gif/bmp）
      documents   文本文档路径列表（md/txt/json/log/py/js/ts/html/css/yml/toml/ini/csv/sql/xml）
      prompt      prompts/ 目录下的场景模板名（如 prototype-review、general-review、
                  image-understanding、mobile-review），或模板文件路径；与 system 二选一
      system      直接给出系统提示词（覆盖模板）
      temperature 采样温度，默认 0.2
      reasoning   思考强度：none/off/low/medium/high，本地推理模型默认 none（关闭思考，快）
    返回：模型回复文本。
    """
    if not text.strip():
        return "错误：text 不能为空"
    data_uris = []
    if images:
        check_images(images)
        data_uris = [img_to_data_uri(i) for i in images]
    doc_texts = check_documents(documents or [])
    if prompt and system:
        return "错误：prompt 与 system 只能二选一"
    sys_prompt = system
    if prompt:
        sys_prompt = resolve_prompt(prompt)
        if sys_prompt is None:
            return "错误：找不到模板 %s" % prompt
    if data_uris and not sys_prompt:
        sys_prompt = "你是识图助手，请按要求仔细分析图片，输出结构化结果。"
    return call_with_retry(sys_prompt, text, data_uris, doc_texts, TIMEOUT, reasoning, temperature)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False))
def screenshot(
    url: str,
    out: str,
    width: int = 1440,
    height: int = 900,
    budget: int = 3000,
) -> str:
    """Edge/Chrome 无头截图：把 HTML 文件或 URL 渲染为 PNG 图片。

    适用于：界面评审、原型走查前先截图为图片，再交给 multimodal_chat 识图分析。

    参数说明：
      url     必填，file:// 本地路径或 http(s) URL
      out     必填，PNG 输出路径
      width   窗口宽度，默认 1440
      height  窗口高度，默认 900
      budget  渲染等待毫秒数（动画/角标模拟），默认 3000
    返回：截图结果（OK：路径 或 错误信息）。
    """
    return run_screenshot(url, out, width, height, budget)


if __name__ == "__main__":
    mcp.run()

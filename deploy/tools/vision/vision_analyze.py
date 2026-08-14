#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用识图客户端：调用 OpenAI 兼容视觉模型 API 分析本地图片。

用法示例：
  python vision_analyze.py --image page.png --prompt prototype-review
  python vision_analyze.py --image page.png --text "检查是否遮挡"
  python vision_analyze.py --images a.png,b.png --text "对比两张图"
  python vision_analyze.py --dir shots/ --prompt prototype-review --out report.json

环境变量：
  VISION_API_ENDPOINT   API 基地址（自动补 /v1/chat/completions）
  VISION_API_KEY        密钥（不入配置文件）
  VISION_API_MODEL      识图模型名
  VISION_API_TIMEOUT    请求超时秒数（默认 60）

输出：stdout 输出 JSON（单图分析时直接为该图的结果对象；--images 多图一次调用时返回合并结果）。
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def img_to_data_uri(path):
    p = Path(path)
    mime = MIME.get(p.suffix.lower(), "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return "data:%s;base64,%s" % (mime, b64)


def resolve_prompt(arg):
    """--prompt 支持三种输入：prompts/ 下的模板名、模板文件路径、直接提示词文本。"""
    if not arg:
        return None
    p = Path(arg)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    cand = Path(__file__).parent / "prompts" / (arg if arg.endswith(".md") else arg + ".md")
    if cand.is_file():
        return cand.read_text(encoding="utf-8")
    return arg


def call_api(data_uris, text, endpoint, key, model, timeout, reasoning="none"):
    """调用 OpenAI 兼容接口。reasoning 默认 'none'：关闭推理模型的思考过程（本地 LM Studio 用
    reasoning_effort=none 关闭，否则每次请求先输出大量思考 token，评审会非常慢）。
    不识别该参数的云端 API 会返回 400，自动去掉该字段重试一次。"""
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": text}]
            + [{"type": "image_url", "image_url": {"url": u}} for u in data_uris],
        }],
    }
    if reasoning:
        payload["reasoning_effort"] = reasoning
    url = endpoint.rstrip("/") + "/v1/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
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


def parse_json(raw):
    """把模型输出解析为 JSON：先直接解析，失败则提取 ```json 块，再剥离首尾非 JSON 字符。"""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(s[i:j + 1])
        except Exception:  # noqa: BLE001
            return None
    return None


def analyze_with_retry(uris, prompt, endpoint, key, model, timeout, reasoning="none", max_retries=2):
    """单次识图：调用 + JSON 解析，调用失败或解析失败时按 2s/4s 退避重试（默认共 3 次尝试）。"""
    last = None
    for attempt in range(max_retries + 1):
        try:
            raw = call_api(uris, prompt, endpoint, key, model, timeout, reasoning)
        except urllib.error.HTTPError as e:
            last = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:500])
        except Exception as e:  # noqa: BLE001
            last = str(e)
        else:
            parsed = parse_json(raw)
            if parsed is not None:
                parsed.setdefault("ok", True)
                return parsed
            last = "JSON 解析失败（输出非 JSON）: %s" % raw[:200]
        if attempt < max_retries:
            time.sleep(2 * (attempt + 1))
    return {"ok": False, "error": last, "raw": raw if "raw" in locals() else None}


def fail(msg):
    sys.exit(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="通用识图客户端（OpenAI 兼容视觉模型）")
    ap.add_argument("--image", help="单张图片路径")
    ap.add_argument("--images", help="多张图片路径，逗号分隔（一次调用，供模型对比/综合）")
    ap.add_argument("--dir", help="目录批量分析（每图独立调用，图片扩展名自动识别）")
    ap.add_argument("--prompt", help="提示词模板名（prompts/ 下）或模板文件路径")
    ap.add_argument("--text", help="直接提示词文本（与 --prompt 二选一）")
    ap.add_argument("--out", help="输出 JSON 文件路径（缺省输出 stdout）")
    ap.add_argument("--timeout", type=int, default=int(os.environ.get("VISION_API_TIMEOUT", "300")))
    reasoning = os.environ.get("VISION_API_REASONING", "none")
    args = ap.parse_args()

    endpoint = os.environ.get("VISION_API_ENDPOINT", "")
    key = os.environ.get("VISION_API_KEY", "")
    model = os.environ.get("VISION_API_MODEL", "")
    if not (endpoint and key and model):
        fail("缺少环境变量 VISION_API_ENDPOINT / VISION_API_KEY / VISION_API_MODEL")

    prompt = resolve_prompt(args.prompt) if args.prompt else (args.text or "请分析这张图片并输出结构化结果")

    images = []
    if args.image:
        images = [args.image]
    elif args.images:
        images = [s.strip() for s in args.images.split(",") if s.strip()]
    elif args.dir:
        d = Path(args.dir)
        images = sorted(str(p) for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS)
        if not images:
            fail("目录下无图片: %s" % args.dir)
    else:
        fail("必须指定 --image / --images / --dir 之一")

    for i in images:
        if not Path(i).is_file():
            fail("图片不存在: %s" % i)

    # --images：多图一次调用（对比/综合），结果合并为一个对象
    if args.images:
        try:
            uris = [img_to_data_uri(i) for i in images]
            out = analyze_with_retry(uris, prompt, endpoint, key, model, args.timeout, reasoning)
            out["images"] = images
        except Exception as e:  # noqa: BLE001
            out = {"ok": False, "images": images, "error": str(e)}
        text = json.dumps(out, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        print(text)
        return

    uris = [img_to_data_uri(i) for i in images]

    results = []
    for i, u in enumerate(uris):
        try:
            parsed = analyze_with_retry([u], prompt, endpoint, key, model, args.timeout, reasoning)
        except Exception as e:  # noqa: BLE001
            parsed = {"ok": False, "error": str(e)}
        parsed.setdefault("image", images[i])
        results.append(parsed)

    out = results[0] if len(results) == 1 else {"ok": True, "batch": results}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

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


def call_api(data_uris, text, endpoint, key, model, timeout):
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": text}]
            + [{"type": "image_url", "image_url": {"url": u}} for u in data_uris],
        }],
    }
    url = endpoint.rstrip("/") + "/v1/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


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
    ap.add_argument("--timeout", type=int, default=int(os.environ.get("VISION_API_TIMEOUT", "60")))
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
            raw = call_api(uris, prompt, endpoint, key, model, args.timeout)
            try:
                out = json.loads(raw)
                out.setdefault("ok", True)
            except Exception:
                out = {"ok": True, "raw": raw}
            out["images"] = images
        except urllib.error.HTTPError as e:
            out = {"ok": False, "images": images,
                   "error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:500])}
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
            raw = call_api([u], prompt, endpoint, key, model, args.timeout)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"ok": True, "raw": raw}
            parsed.setdefault("ok", True)
            parsed.setdefault("image", images[i])
            results.append(parsed)
        except urllib.error.HTTPError as e:
            results.append({"ok": False, "image": images[i],
                            "error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:500])})
        except Exception as e:  # noqa: BLE001
            results.append({"ok": False, "image": images[i], "error": str(e)})

    out = results[0] if len(results) == 1 else {"ok": True, "batch": results}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

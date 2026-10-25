#!/usr/bin/env python3
"""前台常驻版 llama-server 包装（供 systemd --user 使用；不做 stop-others / nohup）。

用法: qwen_serve.sh [ud|std|unc]     默认 std
环境变量: HOST(默认 0.0.0.0) PORT(默认 8080) MODEL_KEY(默认 std)
与人工脚本 qwen-start.sh 的区别：前台运行、不杀其它进程、默认监听 0.0.0.0。

2026-10-16 起「Python 单一实现 + 薄包装」：逻辑只维护在本文件，Linux 入口
qwen_serve.sh 仅转调本文件（历史完整 shell 实现见 git 历史）。
install-systemd.py 会把包装 qwen_serve.sh 与本文件一并同步到 llama.cpp 源码目录，
两者必须同目录并存；chat 模板 / llama-server 二进制路径一律以「本文件所在目录」
为基准（该脚本在 llama.cpp 源码目录内运行）。

systemd 口径：最终用 os.execv 以 llama-server 的实参替换自身进程——
保持 systemd 对 PID / 信号 / 退出码的跟踪（Type=simple 前台进程模型）。

退出码: 0 = 交给 llama-server（execv 后本进程即 llama-server）；
        1 = 未知模型 / 模型文件不存在；126 = 无执行权限；127 = 找不到可执行文件
"""

import contextlib
import os
import sys

MODELS_DIR = "/home/minjian/ai/models"
MMPROJ = os.path.join(MODELS_DIR, "mmproj-Qwen3.8-27B-f16.gguf")
MODELS = {
    "ud": os.path.join(MODELS_DIR, "Qwen3.8-27B-UD-Q4_K_M.gguf"),
    "std": os.path.join(MODELS_DIR, "Qwen3.8-27B-Q4_K_M.gguf"),
    "unc": os.path.join(MODELS_DIR, "Qwen3.8-27B-Uncensored-Q4_K_M.gguf"),
}


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def main(argv):
    # 目录基准＝本文件所在目录（安装脚本会把包装与本文件一并拷到 llama.cpp 源码目录）
    script_dir = os.path.dirname(os.path.realpath(os.fspath(__file__)))
    host = os.environ.get("HOST") or "0.0.0.0"
    port = os.environ.get("PORT") or "8080"

    key = argv[1] if len(argv) > 1 and argv[1] else (os.environ.get("MODEL_KEY") or "std")
    gguf = MODELS.get(key, "")
    if not gguf:
        sys.stderr.write(f"未知模型: {key}（可选: ud / std / unc）\n")
        return 1
    if not os.path.isfile(gguf):
        sys.stderr.write(f"模型文件不存在: {gguf}\n")
        return 1

    print(f"启动 llama-server: model={key} host={host} port={port} file={gguf}")

    exe = os.path.join(script_dir, "build", "bin", "llama-server")
    chat_tpl = os.path.join(script_dir, "templates", "chat_template_qwen38_v22.4.jinja")
    # llama-server 实参：模型 / 上下文与 GPU / 服务 / 模板 / 推理 / 推测解码，逐项与原 shell 版一致
    args = [
        exe,
        "-m",
        gguf,
        "-mm",
        MMPROJ,
        "-ngl",
        "999",
        "-c",
        "153600",
        "-ctk",
        "q4_0",
        "-ctv",
        "q4_0",
        "--flash-attn",
        "on",
        "--host",
        host,
        "--port",
        port,
        "--jinja",
        "--chat-template-file",
        chat_tpl,
        "--reasoning-format",
        "deepseek",
        "--reasoning-effort",
        "max",
        "--reasoning-preserve",
        "--spec-type",
        "ngram-mod",
        "--spec-ngram-mod-n-match",
        "16",
        "--spec-ngram-mod-n-min",
        "32",
        "--spec-ngram-mod-n-max",
        "64",
    ]

    # execv 换进程前必须清空缓冲，否则 systemd 日志里会丢启动提示行
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execv(exe, args)
    except OSError as exc:
        # 与 shell 口径一致：找不到可执行文件 127、无执行权限 126
        code = 127 if isinstance(exc, FileNotFoundError) else 126
        sys.stderr.write(f"无法启动 llama-server（{exe}）：{exc}\n")
        return code


if __name__ == "__main__":
    configure_stdio()
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
# mirix_mcp.py - opencode MCP server：接入 MIRIX 长期记忆（mjbk:8531）
#
# 注册：工作区/项目 .opencode/opencode.json(c) 或全局 ~/.config/opencode/opencode.jsonc 的 mcp.servers
#   "mirix": { "type": "local", "command": ["python3", "scripts/tools/mirix/mirix_mcp.py"], "enabled": true }
#
# 传输层：MCP stdio NDJSON（每条 JSON-RPC 一行，\n 定界），与 scripts/tools/vision/mjw_vision_mcp.py 同构。
#
# 凭据：从仓库根 deploy/.env 读取（不写进被跟踪文件）
#   MIRIX_API_BASE   如 http://192.168.0.107:8531
#   MIRIX_API_KEY    客户端 API Key（~/mirix/api_key.txt 的值）
#   MIRIX_META_AGENT_ID  可选；不填则由 /agents 自动发现
#
# 分层：user_id 用「用户级 + 项目级」——scope=user → minjian；scope=project → minjian@<git 根目录名>
#
# 工具：
#   remember(content|messages, scope?)    写入记忆（异步抽取）
#   recall(query, scope?, limit?)         按当前上下文检索相关记忆
#   list_memories(scope?, memory_type?)   列出记忆（分层尽览）
#   consolidate(scope?, mode?, dry_run?)  归并整理（auto_dream）
#   memory_status()                       服务与本地模型健康状态
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "mirix"
SERVER_VERSION = "0.1.0"
DEFAULT_USER = "minjian"


def project_root():
    # scripts/tools/mirix/mirix_mcp.py -> 上溯 4 级到仓库根
    return Path(__file__).resolve().parents[3]


def load_env():
    keys = {}
    env_path = project_root() / "deploy" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("MIRIX_API_BASE", "MIRIX_API_KEY", "MIRIX_META_AGENT_ID"):
        if os.environ.get(k):
            keys[k] = os.environ[k]
    return keys


_CFG = load_env()


def api_base():
    base = _CFG.get("MIRIX_API_BASE")
    if not base:
        raise RuntimeError("缺少 MIRIX_API_BASE（请在 deploy/.env 配置）")
    return base.rstrip("/")


def api_key():
    key = _CFG.get("MIRIX_API_KEY")
    if not key:
        raise RuntimeError("缺少 MIRIX_API_KEY（请在 deploy/.env 配置）")
    return key


def http_json(path, body=None, method="POST", timeout=900):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        api_base() + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-API-Key": api_key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"MIRIX {path} HTTP {e.code}: {e.read().decode(errors='replace')[:400]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 MIRIX({api_base()})：{e.reason}") from e


def git_root(start=None):
    d = Path(start or os.getcwd()).resolve()
    for p in [d, *d.parents]:
        if (p / ".git").exists():
            return p
    return None


def workspace_root():
    """向上找最近含 *.code-workspace 的目录（工作区根），用于项目级命名。"""
    d = Path(os.getcwd()).resolve()
    for p in [d, *d.parents]:
        if list(p.glob("*.code-workspace")):
            return p
    return None


def project_name():
    if _CFG.get("MIRIX_PROJECT"):
        return _CFG["MIRIX_PROJECT"]
    ws = workspace_root()
    if ws:
        return ws.name
    root = git_root()
    if root:
        return root.name
    return Path.cwd().name


def project_user_id():
    return f"{DEFAULT_USER}@{project_name()}"


def resolve_user_id(scope):
    scope = (scope or "project").lower()
    if scope == "user":
        return [DEFAULT_USER]
    if scope in ("all", "both"):
        return [project_user_id(), DEFAULT_USER]
    return [project_user_id()]


_META = {"id": _CFG.get("MIRIX_META_AGENT_ID")}
_ENSURED = set()


def ensure_user(uid):
    """幂等创建用户（MIRIX 要求 user_id 已注册，否则部分接口 500）。"""
    if uid in _ENSURED:
        return
    try:
        http_json("/users/create_or_get", {"user_id": uid, "name": uid}, timeout=30)
        _ENSURED.add(uid)
    except Exception:
        pass  # 已存在或创建失败时继续，让后续请求给出真实错误


def meta_agent_id():
    if _META["id"]:
        return _META["id"]
    _, agents = http_json("/agents", method="GET", timeout=60)
    for a in agents or []:
        t = str(a.get("agent_type", "")) + str(a.get("name", ""))
        if "meta" in t.lower():
            _META["id"] = a.get("id")
            return _META["id"]
    if agents:
        _META["id"] = agents[0].get("id")
        return _META["id"]
    raise RuntimeError("找不到 meta agent，请先初始化 MIRIX")


def to_messages(content):
    """把纯文本或字符串列表转成 MIRIX 需要的 OpenAI 消息格式。"""
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return content
    if isinstance(content, list):
        return [{"role": "user", "content": [{"type": "text", "text": str(c)}]} for c in content]
    return [{"role": "user", "content": [{"type": "text", "text": str(content)}]}]


# ---------------- 工具实现 ----------------


def tool_remember(args):
    content = args.get("content")
    if not content and args.get("messages"):
        content = args["messages"]
    if not content:
        raise RuntimeError("需要 content 或 messages")
    users = resolve_user_id(args.get("scope"))
    out = []
    for uid in users:
        ensure_user(uid)
        st, res = http_json("/memory/add", {
            "user_id": uid, "meta_agent_id": meta_agent_id(), "messages": to_messages(content)})
        out.append(f"{uid}: {res.get('status')}（{res.get('message', st)}）")
    return "已写入记忆（后台异步抽取）：\n" + "\n".join(out)


def tool_recall(args):
    query = args.get("query")
    if not query:
        raise RuntimeError("需要 query")
    limit = int(args.get("limit") or 8)
    users = resolve_user_id(args.get("scope"))
    blocks = []
    for uid in users:
        ensure_user(uid)
        qs = urllib.parse.urlencode({
            "user_id": uid, "query": query, "memory_type": "all",
            "search_method": "embedding", "limit": limit})
        st, res = http_json("/memory/search?" + qs, method="GET", timeout=180)
        results = (res or {}).get("results", []) if isinstance(res, dict) else []
        lines = [f"### 作用域 {uid}（命中 {len(results)} 条）"]
        for it in results:
            lines.append(f"- [{it.get('memory_type')}] " + json.dumps(it, ensure_ascii=False)[:400])
        if not results:
            lines.append("（无命中）")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def tool_list(args):
    users = resolve_user_id(args.get("scope") or "all")
    mtype = args.get("memory_type") or "all"
    blocks = []
    for uid in users:
        st, res = http_json(f"/memory/components?user_id={urllib.parse.quote(uid)}&memory_type={mtype}",
                            method="GET", timeout=120)
        mems = (res or {}).get("memories", {}) if isinstance(res, dict) else {}
        lines = [f"### 作用域 {uid}"]
        for kind, v in (mems or {}).items():
            lines.append(f"- {kind}: {v.get('total_count')} 条")
            for it in (v.get("items") or [])[:5]:
                lines.append(f"    {json.dumps(it, ensure_ascii=False)[:300]}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def tool_consolidate(args):
    mode = args.get("mode") or "experience"
    dry = bool(args.get("dry_run"))
    users = resolve_user_id(args.get("scope") or "all")
    out = []
    for uid in users:
        st, res = http_json(f"/memory/auto_dream?user_id={urllib.request.quote(uid)}",
                            {"mode": mode, "dry_run": dry}, timeout=1800)
        out.append(f"{uid}: {json.dumps(res, ensure_ascii=False)[:500]}")
    return "归并整理（auto_dream）：\n" + "\n".join(out)


def tool_status(_args):
    out = []
    try:
        st, res = http_json("/health", method="GET", timeout=20)
        out.append(f"MIRIX: {res}")
    except Exception as e:
        out.append(f"MIRIX: 不可用（{e}）")
    try:
        st, res = http_json("/memory/components?user_id=" + urllib.request.quote(project_user_id()),
                            method="GET", timeout=30)
        mems = (res or {}).get("memories", {})
        counts = {k: v.get("total_count") for k, v in mems.items()}
        out.append(f"本次项目记忆({project_user_id()}): {counts}")
    except Exception as e:
        out.append(f"项目记忆: 读取失败（{e}）")
    return "\n".join(out)


TOOLS = [
    {
        "name": "remember",
        "description": "写入长期记忆：把事实/偏好/决策交给 MIRIX 后台抽取成分层记忆（异步）。"
        "scope=project（默认，minjian@<项目名>）/ user（用户级）/ both。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "要记住的内容（纯文本）"},
                "messages": {"type": "array", "description": "或按对话消息数组 [{role,content}]"},
                "scope": {"type": "string", "enum": ["project", "user", "both"], "description": "记忆落点，默认 project"},
            },
        },
    },
    {
        "name": "recall",
        "description": "检索长期记忆：按上下文语义召回相关的分层记忆（episodic/semantic/procedural/resource/knowledge_vault/core）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要检索的问题或上下文"},
                "scope": {"type": "string", "enum": ["project", "user", "all"], "description": "检索范围，默认 project"},
                "limit": {"type": "integer", "description": "每类返回上限，默认 10"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_memories",
        "description": "列出记忆（分层尽览）：查看项目级/用户级各记忆类型的条目与数量。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["project", "user", "all"], "description": "范围，默认 all"},
                "memory_type": {"type": "string", "description": "记忆类型过滤，默认 all"},
            },
        },
    },
    {
        "name": "consolidate",
        "description": "归并整理记忆：调 MIRIX auto_dream，合并重复、消解冲突/过期条目（整理成更精炼的记忆）。可先 dry_run 预览。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["project", "user", "all"], "description": "范围，默认 all"},
                "mode": {"type": "string", "enum": ["core", "episodic", "semantic", "resource", "procedural", "knowledge", "experience"],
                         "description": "整理的记忆类型，默认 experience"},
                "dry_run": {"type": "boolean", "description": "只预览不落库"},
            },
        },
    },
    {
        "name": "memory_status",
        "description": "查看 MIRIX 服务与当前项目记忆概览（健康状态与各类记忆条数）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "remember": tool_remember,
    "recall": tool_recall,
    "list_memories": tool_list,
    "consolidate": tool_consolidate,
    "memory_status": tool_status,
}


# ---------------- MCP stdio JSON-RPC（NDJSON） ----------------


def read_message():
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
    sys.stdout.buffer.write(json.dumps(obj).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def handle(msg):
    msgid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msgid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}}
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msgid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msgid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            fn = HANDLERS.get(name)
            if not fn:
                raise RuntimeError(f"未知工具: {name}")
            return {"jsonrpc": "2.0", "id": msgid, "result": {
                "content": [{"type": "text", "text": fn(args)}], "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msgid, "result": {
                "content": [{"type": "text", "text": f"[记忆操作失败] {e}"}], "isError": True}}
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

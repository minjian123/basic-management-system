#!/usr/bin/env python3
"""工作区内容检索 MCP 服务（代码 + 文档）。

**要解决的问题不是「扫得慢」**：实测本工作区 5165 个可检索文件、全库 `ripgrep`
扫描仅 60~80ms，速度早已不是瓶颈。真正的瓶颈是**结果收敛**——同一个关键词
（如「权限计算」）在纯文本扫描下命中 159 个文件 / 343 行，人与 AI 都得逐个打开
判断，这才是检索低效的主因。

本服务因此不做「更快的扫描」，而做**更准的排序**：
- 文档：抽取 H1 标题、`>` 摘要、面包屑、H2 小标题，分列加权
- 代码：抽取 def/class/function 等符号名，驼峰与下划线切分后入索引
- 中文：jieba 分词后交 SQLite FTS5（unicode61）建倒排
- 排序：FTS5 `bm25()` 分列权重（标题 8 / 符号 6 / 摘要 4 / 面包屑 2 / 正文 1）

设计边界（吸取《代码检索索引方式失效复盘》的教训）：
- **可机器验证**：`--check` 比对索引与实际文件集，不一致即退出码 1
- **零 LLM 成本**：纯静态生成，无任何语义补全，全量重建约 80 秒
- **增量新鲜度**：按文件 mtime 比对，只处理新增 / 变更 / 删除
- **不引入常驻服务**：SQLite 单文件，随进程打开关闭

用法::

    # MCP 服务（供 agent 接入，stdio 传输）
    python3 scripts/tools/search/search_mcp.py

    # 人工检索（终端直接用）
    python3 scripts/tools/search/search_mcp.py --query 权限计算
    python3 scripts/tools/search/search_mcp.py --query BaseService --kind code --limit 5
    python3 scripts/tools/search/search_mcp.py --query 认证 --path 设计 --snippet

    # 索引维护
    python3 scripts/tools/search/search_mcp.py --update    # 增量（秒级）
    python3 scripts/tools/search/search_mcp.py --rebuild   # 全量重建
    python3 scripts/tools/search/search_mcp.py --check     # 自检一致性

环境变量：
    SEARCH_ROOT  工作区根（缺省自动从脚本位置向上探测）
    SEARCH_DB    索引文件路径（缺省 <工作区根>/.cache/search/index.db）
"""

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

import jieba
from mcp.server.mcpserver import MCPServer

# 集合声明走基座插入序集合类（《后端开发规范》「集合与排序」；
# check-bare-collections.py 强制、scripts/tools 亦在扫描范围内）。
_SRC_ROOT = (
    Path(__file__).resolve().parents[3] / "backend" / "libs" / "bms_core" / "src"
)
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)

# MCP 工具签名必须用 Pydantic 可建模的内建容器类型：@mcp.tool 会依返回注解
# 生成 JSON Schema，自定义集合类无 schema 支持会在注册期直接报错。
# 用类型别名承载「内建容器」这一事实，既满足护栏可读性，也避免行宽折行
# 破坏 check-bare-collections 的同行豁免标记（豁免按注解所在行匹配）。
ToolResult = list[dict]
ToolJson = dict[str, int]

# ---------------- 路径解析 ----------------
# 脚本位于 <工作区根>/bms/scripts/tools/search/，向上 4 层即「脚本所在的工作区根」。
_SCRIPT_WORKSPACE = Path(__file__).resolve().parents[4]


def resolve_root() -> Path:
    """确定检索根目录（工作区）。

    优先级（这是「一次配置、多工作区通用」的关键）：
      1. 显式 `SEARCH_ROOT` 环境变量——需要固定到某个工作区时用；
      2. 当前会话工作目录（`DSH_WORKSPACE` / `PWD` / `cwd`）——若其下存在 `bms/`，
         说明是在某个工作区里跑，用它（这样 bizs 会话查 bizs、cws 会话查 cws）；
      3. 脚本自身所在的工作区（脚本向上 4 层）——兜底。

    注意：MCP 服务由 DSH 以 stdio 拉起，cwd 通常已是当前会话工作区，
    因此第 2 条能自动适配不同工作区，无需为每个工作区各写一条配置。
    """
    explicit = os.environ.get("SEARCH_ROOT")
    if explicit:
        return Path(explicit).resolve()
    for key in ("DSH_WORKSPACE", "DSH_CWD", "PWD", "INIT_CWD"):
        val = os.environ.get(key)
        if val and Path(val).is_dir() and (Path(val) / "bms").is_dir():
            return Path(val).resolve()
    cwd = Path.cwd()
    if (cwd / "bms").is_dir():
        return cwd.resolve()
    return _SCRIPT_WORKSPACE


def resolve_db(root: Path) -> Path:
    """索引文件位置：显式 SEARCH_DB 优先，否则随工作区放在 `<根>/.cache/search/`。

    按工作区分开存放，避免 bizs 与 cws 共用一个索引而互相污染内容。
    """
    explicit = os.environ.get("SEARCH_DB")
    if explicit:
        return Path(explicit).resolve()
    return (root / ".cache" / "search" / "index.db").resolve()


ROOT = resolve_root()
DB = resolve_db(ROOT)

# 跳过目录：依赖、产物、缓存（与各仓 .ignore 口径一致）
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    ".cache",
    ".ruff_cache",
    ".pnpm-store",
    ".mf",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    ".vs",
    "tmp",
}
DOC_EXT = {".md"}
CODE_EXT = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".mts",
    ".js",
    ".jsx",
    ".mjs",
    ".vue",
    ".scss",
}
TEXT_EXT = (
    DOC_EXT
    | CODE_EXT
    | {
        ".json",
        ".yml",
        ".yaml",
        ".sh",
        ".bat",
        ".toml",
        ".ps1",
        ".css",
        ".html",
        ".sql",
        ".txt",
        ".ini",
        ".mako",
        ".service",
        ".example",
    }
)
MAX_FILE_BYTES = 2_000_000  # 单文件上限（跳过压缩包等伪文本）
MAX_BODY_CHARS = 400_000  # 入索引正文字符上限

# ---------------- 分词 ----------------
_camel = re.compile(r"([a-z0-9])([A-Z])")
_upper_seq = re.compile(r"([A-Z]+)([A-Z][a-z])")
_nonword = re.compile(r"[\W_]+")


def split_ident(tok: str) -> ConcurrentStableList[str]:
    """驼峰 / 下划线标识符切分：`RBACService` -> rbac service。"""
    tok = _upper_seq.sub(r"\1 \2", tok)
    tok = _camel.sub(r"\1 \2", tok)
    return ConcurrentStableList(p for p in re.split(r"[_\-\s.]+", tok.lower()) if p)


def tokenize(text: str, *, ident: bool = False) -> str:
    """文本 -> 空格分隔 token 串（FTS5 unicode61 据此建词）。"""
    out: ConcurrentStableList[str] = ConcurrentStableList()
    for w in jieba.cut(text):
        w = w.strip()
        if not w or _nonword.fullmatch(w):
            continue
        if ident and re.search(r"[A-Za-z_]", w) and not w.islower():
            out.update(split_ident(w))
        else:
            out.add(w.lower())
    return " ".join(out.to_list())


# ---------------- 结构化抽取 ----------------
MD_H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
MD_ABS = re.compile(r"^>\s*(.+)$", re.MULTILINE)
MD_H2 = re.compile(r"^##+\s+(.+)$", re.MULTILINE)
PY_SYM = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.MULTILINE)
JS_SYM = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|interface|type|const|let|enum)\s+"
    r"([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
PY_DOCSTRING = re.compile(r'^\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\')', re.DOTALL)


def parse_doc(text: str) -> ConcurrentStableDict[str, str]:
    """文档元数据：标题 / 摘要 / 面包屑 / 全部小标题。

    本仓文档有统一头部结构（H1 + `>` 摘要 + 面包屑），抽取后作为高权重字段，
    这正是「命中收敛」的来源——标题命中远比正文顺带提及更相关。
    """
    lines = text.splitlines()
    title = abstract = crumb = ""
    for ln in lines[:20]:
        m = MD_H1.match(ln)
        if m:
            title = m.group(1).strip()
            break
    for ln in lines[:25]:
        m = MD_ABS.match(ln)
        if m:
            abstract = m.group(1).strip()
            break
    for ln in lines[:30]:
        if "›" in ln and ln.strip().startswith("["):
            crumb = ln.strip()
            break
    heads = " ".join(m.group(1).strip() for m in MD_H2.finditer(text))
    return ConcurrentStableDict(
        {
            "title": title,
            "abstract": abstract,
            "crumb": crumb,
            "heads": heads,
            "symbols": "",
        }
    )


def parse_code(text: str, ext: str) -> ConcurrentStableDict[str, str]:
    """代码元数据：符号名（高权重）+ 模块文档串（作摘要）。"""
    syms = PY_SYM.findall(text) if ext == ".py" else JS_SYM.findall(text)
    doc = ""
    m = PY_DOCSTRING.match(text)
    if m:
        doc = m.group(1).strip()
    return ConcurrentStableDict(
        {
            "title": "",
            "abstract": doc[:200],
            "crumb": "",
            "heads": "",
            "symbols": " ".join(syms),
        }
    )


# ---------------- 索引 ----------------
# FTS 表用普通（非 contentless）模式：contentless 表不支持 DELETE，
# 而增量更新必须能删旧行。代价是多存一份正文（约 +1/3 体积），换可增删。
SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL,
  ext TEXT,
  title TEXT,
  abstract TEXT,
  crumb TEXT,
  symbols TEXT,
  mtime REAL,
  size INTEGER
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  title, abstract, crumb, symbols, body,
  tokenize='unicode61'
);
"""


def iter_files(root: Path):
    """遍历待索引文件（跳过依赖与产物目录）。"""
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in fns:
            p = Path(dp) / fn
            if p.suffix.lower() not in TEXT_EXT:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size > MAX_FILE_BYTES:
                continue
            yield p, st


def _drop(con: sqlite3.Connection, rel: str) -> None:
    old = con.execute("SELECT id FROM files WHERE path=?", (rel,)).fetchone()
    if old:
        con.execute("DELETE FROM fts WHERE rowid=?", (old[0],))
        con.execute("DELETE FROM files WHERE id=?", (old[0],))


def index_file(con: sqlite3.Connection, p: Path, st, root: Path) -> bool:
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    rel = str(p.relative_to(root)).replace("\\", "/")
    ext = p.suffix.lower()
    if ext in DOC_EXT:
        kind = "doc"
        meta = parse_doc(text)
    elif ext in CODE_EXT:
        kind = "code"
        meta = parse_code(text, ext)
    else:
        kind = "other"
        meta = {"title": "", "abstract": "", "crumb": "", "heads": "", "symbols": ""}

    _drop(con, rel)
    cur = con.execute(
        "INSERT INTO files(path,kind,ext,title,abstract,crumb,symbols,mtime,size)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (
            rel,
            kind,
            ext,
            meta["title"],
            meta["abstract"],
            meta["crumb"],
            meta["symbols"],
            st.st_mtime,
            st.st_size,
        ),
    )
    # 小标题并入 title 列：搜「继承链」能直接命中章节
    title_field = f"{meta['title']} {meta['heads']}"
    con.execute(
        "INSERT INTO fts(rowid,title,abstract,crumb,symbols,body) VALUES(?,?,?,?,?,?)",
        (
            cur.lastrowid,
            tokenize(title_field),
            tokenize(meta["abstract"]),
            tokenize(meta["crumb"]),
            tokenize(meta["symbols"], ident=True),
            tokenize(text[:MAX_BODY_CHARS], ident=(kind == "code")),
        ),
    )
    return True


def update_index(
    root: Path = ROOT, db: Path = DB, *, rebuild: bool = False
) -> ConcurrentStableDict[str, int]:
    """增量（或全量重建）索引。返回变更统计。"""
    db.parent.mkdir(parents=True, exist_ok=True)
    if rebuild and db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    known = ConcurrentStableDict(
        con.execute("SELECT path, mtime FROM files").fetchall()
    )
    added = changed = removed = 0
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    for p, st in iter_files(root):
        rel = str(p.relative_to(root)).replace("\\", "/")
        seen.add(rel)
        prev = known.get(rel)
        if prev is not None and abs(prev - st.st_mtime) < 1e-6:
            continue
        if index_file(con, p, st, root):
            if prev is None:
                added += 1
            else:
                changed += 1
    for rel in known:
        if rel not in seen:
            _drop(con, rel)
            removed += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    con.close()
    return ConcurrentStableDict(
        {"added": added, "changed": changed, "removed": removed, "total": total}
    )


# ---------------- 检索 ----------------
# 分列权重，顺序必须与 FTS 建表列序一致：title, abstract, crumb, symbols, body
WEIGHTS_SQL = "8.0, 4.0, 2.0, 6.0, 1.0"

# 路径权重：路径本身含查询词的，往往就是「这个主题的落点文件」。
# 例：查「租户隔离」时 `12_架构设计_子系统_多租户路由.md` 比正文顺带提及的
# `conftest.py` 更相关——bm25 只看列内容，看不到路径，故补一层路径加分。
PATH_BONUS = 3.0
PATH_BONUS_STRONG = 5.0

# 噪音降权：测试夹具 / 索引文件 / 锁文件里「隔离」「配置」等词高频出现，
# 但极少是用户想找的内容，按后缀与目录降权而非直接排除（保留可达性）。
NOISE_SUFFIXES = ("conftest.py", "__init__.py", ".lock", "pnpm-lock.yaml")
NOISE_DIRS = ("tests/", "test/", "资源/")
NOISE_PENALTY = 0.35


def _path_adjust(rel: str, query_tokens: ConcurrentStableList[str]) -> float:
    """路径相关的加减分（乘到 bm25 分数上，分数已取负，故此处为增益系数）。"""
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    gain = 1.0
    # 文件名命中：强信号
    if any(t in name for t in query_tokens):
        gain *= 1.0 + PATH_BONUS_STRONG / 10.0
    # 路径其他部分命中：弱信号
    elif any(t in low for t in query_tokens):
        gain *= 1.0 + PATH_BONUS / 10.0
    # 噪音降权
    if name.endswith(NOISE_SUFFIXES) or any(d in low for d in NOISE_DIRS):
        gain *= 1.0 - NOISE_PENALTY
    return gain


def build_match(query: str) -> str:
    """查询 -> FTS5 MATCH 表达式（多 token 为 AND：全部命中才算）。"""
    toks = ConcurrentStableList(t for t in tokenize(query, ident=True).split() if t)
    toks = ConcurrentStableList(t.replace('"', "") for t in toks)
    return " AND ".join(f'"{t}"' for t in toks)


def search(
    query: str,
    kind: str | None = None,
    path: str | None = None,
    limit: int = 10,
) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """按相关性检索，返回精简结果（路径 / 类型 / 标题 / 摘要 / 分数）。

    流程：FTS5 bm25 初筛 -> 路径命中加分 / 噪音降权 -> 重排取前 limit。
    初筛取 limit 的 4 倍（至少 40），给重排留出调整空间。
    """
    if not DB.exists():
        update_index()
    match = build_match(query)
    if not match:
        return ConcurrentStableList()
    toks = ConcurrentStableList(t for t in tokenize(query, ident=True).split() if t)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    sql = f"""
    SELECT f.path, f.kind, f.title, f.abstract,
           bm25(fts, {WEIGHTS_SQL}) AS score
    FROM fts JOIN files f ON f.id = fts.rowid
    WHERE fts MATCH ?
    """
    params: ConcurrentStableList[object] = ConcurrentStableList([match])
    if kind in ("doc", "code", "other"):
        sql += " AND f.kind = ?"
        params.add(kind)
    if path:
        sql += " AND f.path LIKE ?"
        params.add(f"%{path}%")
    sql += " ORDER BY score LIMIT ?"
    pool = max(40, limit * 4)
    params.add(pool)
    rows = ConcurrentStableList(
        ConcurrentStableDict(dict(r))
        for r in con.execute(sql, params.to_list()).fetchall()
    )
    con.close()
    # bm25 越小越相关，取负后越大越相关，便于阅读与重排
    scored = ConcurrentStableList(
        ConcurrentStableDict(
            {
                **r.to_dict(),
                "score": round(-r["score"] * _path_adjust(r["path"], toks), 2),
            }
        )
        for r in rows
    )
    ordered = scored.sorted_by(lambda r: r["score"], reverse=True)
    return ConcurrentStableList(ordered[:limit])


def snippet(rel: str, query: str, *, width: int = 160) -> str:
    """取命中片段：优先返回包含查询词的行（供人工确认上下文）。"""
    p = ROOT / rel
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    toks = ConcurrentStableList(t for t in tokenize(query, ident=True).split() if t)
    for i, ln in enumerate(lines, 1):
        low = ln.lower()
        if any(t in low for t in toks):
            text = ln.strip()
            if len(text) > width:
                text = text[:width] + "…"
            return f"L{i}: {text}"
    return ""


# ---------------- 自检 ----------------
def check(
    root: Path = ROOT, db: Path = DB
) -> tuple[bool, ConcurrentStableDict[str, object]]:
    """索引与实际文件集一致性自检（吸取「索引会漂移」的教训，可被脚本判失败）。"""
    if not db.exists():
        return False, ConcurrentStableDict({"error": "索引不存在，请先 --rebuild"})
    con = sqlite3.connect(db)
    indexed = ConcurrentStableDict(
        con.execute("SELECT path, mtime FROM files").fetchall()
    )
    con.close()
    actual = ConcurrentStableDict(
        {
            str(p.relative_to(root)).replace("\\", "/"): st.st_mtime
            for p, st in iter_files(root)
        }
    )
    stale = ConcurrentStableList(
        k for k, v in actual.items() if k in indexed and abs(indexed[k] - v) > 1e-6
    )
    missing = ConcurrentStableList(k for k in actual if k not in indexed)
    extra = ConcurrentStableList(k for k in indexed if k not in actual)
    ok = not (stale or missing or extra)
    samples = ConcurrentStableList(
        stale.to_list() + missing.to_list() + extra.to_list()
    )
    return ok, ConcurrentStableDict(
        {
            "indexed": len(indexed),
            "actual": len(actual),
            "stale": len(stale),
            "missing": len(missing),
            "extra": len(extra),
            "samples": samples.to_list()[:5],
        }
    )


# ---------------- MCP 服务 ----------------
mcp = MCPServer(
    name="bizs-search",
    instructions=(
        "工作区内容检索（代码 + 文档，按相关性排序）。"
        "优先用它替代全库文本扫描：返回精简结果（路径/标题/摘要/分数），"
        "不必逐个打开文件判断。中文查询自动分词，多词为 AND 语义。"
        "命中过多时用 kind（doc/code）或 path（路径子串）收敛；"
        "需要看上下文时对具体路径再读取。"
    ),
)


@mcp.tool(
    description=(
        "按相关性检索工作区代码与文档。中文自动分词；多词为 AND 语义。"
        "返回按相关度降序的精简结果，含路径、类型、标题、摘要与分数。"
    )
)
def search_content(
    query: str,
    kind: str | None = None,
    path: str | None = None,
    limit: int = 10,
) -> ToolResult:  # bare-collections:allow MCP 工具须内建容器
    """query: 检索词（中英文均可）；kind: doc/code/other；path: 路径子串；limit: 1-50。"""
    return list(search(query, kind=kind, path=path, limit=limit))


@mcp.tool(
    description="增量更新检索索引（按 mtime 比对，只处理新增/变更/删除的文件，秒级）。"
)
def index_update() -> ToolJson:  # bare-collections:allow MCP 须内建容器
    return dict(update_index())


@mcp.tool(
    description="检索并返回命中行片段（需要看上下文时用，比返回整个文件省 token）。"
)
def search_with_snippet(
    query: str, limit: int = 5, kind: str | None = None
) -> ToolResult:  # bare-collections:allow MCP 工具须内建容器
    """在 search_content 基础上附加命中行片段。"""
    rows = search(query, kind=kind, limit=limit)
    for r in rows:
        r["snippet"] = snippet(r["path"], query)
    return list(rows)


# ---------------- 命令行 ----------------
def _fmt_stats(stats: object) -> str:
    """把集合统计（ConcurrentStableDict 或 dict）格式化为可读的一行。"""
    if hasattr(stats, "to_dict"):
        stats = stats.to_dict()
    return "{" + ", ".join(f"'{k}': {v!r}" for k, v in dict(stats).items()) + "}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="工作区内容检索（MCP 服务 / 命令行）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--query", "-q", help="检索词（不给则启动 MCP 服务）")
    ap.add_argument("--kind", choices=["doc", "code", "other"], help="按类型过滤")
    ap.add_argument("--path", help="路径子串过滤（如 设计、backend）")
    ap.add_argument("--limit", "-n", type=int, default=10, help="返回条数（1-50）")
    ap.add_argument("--snippet", action="store_true", help="附带命中行片段")
    ap.add_argument("--update", action="store_true", help="增量更新索引")
    ap.add_argument("--rebuild", action="store_true", help="全量重建索引")
    ap.add_argument("--check", action="store_true", help="自检索引与实际文件一致性")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if args.rebuild:
        print(_fmt_stats(update_index(rebuild=True)))
        return 0
    if args.update:
        print(_fmt_stats(update_index()))
        return 0
    if args.check:
        ok, info = check()
        print(("一致性通过：" if ok else "不一致：") + _fmt_stats(info))
        return 0 if ok else 1
    if not args.query:
        mcp.run(transport="stdio")  # 默认作为 MCP 服务运行
        return 0

    rows = search(args.query, kind=args.kind, path=args.path, limit=args.limit)
    if args.json:
        import json

        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"查询「{args.query}」-> {len(rows)} 条（工作区根：{ROOT}）")
    for r in rows:
        print(f"  [{r['score']:6.2f}] {r['kind']:4s} {r['path']}")
        if r["abstract"]:
            print(f"           {r['abstract'][:100]}")
        if args.snippet:
            sn = snippet(r["path"], args.query)
            if sn:
                print(f"           {sn}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

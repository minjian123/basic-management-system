# -*- coding: utf-8 -*-
"""文档 ↔ 禅道双向同步 · 共享解析与口径（deploy/tools/zentao/zentao_sync_common.py）

被 zentao_sync_push.py（文档→禅道）与 zentao_sync_pull.py（禅道→文档）复用。

解析 文档/项目/{stage}/ 下三类文档：
    需求：需求/0X_需求_*.md
        形如「## N. 需求 01-1：mjbk Ubuntu 基础 <a id="r01-1"></a>」
        元信息行「优先级：2（高）　|　禅道 story：—　|　禅道任务：85（父任务 1）　|　状态：已完成　|　完成日期：2026-08-15」
        正文「**内容**（…）：」编号列表 +「**完成标准**：」+「**参考文档**：」
    任务：任务/0X_域_0X-Y_标题.md（子任务文档）
        信息表「| 项 | 值 |」：编号/父任务/禅道任务/工时（重估）/状态/完成日期…
        正文「## 2. 任务内容」「## 3. 完成标准」「## 4. 参考文档」
    计划：计划/01_计划_*.md
        「## 2. 已完成任务」表（编号/任务/工时/完成日期/任务文件）
        「## 3. 剩余任务排期」表（编号/任务/工时/依赖/排期窗口/备注）

状态口径（文档 → 禅道）：
    未开始 → wait            进行中 → doing（wait 先 start）
    部分完成 → doing（wait 先 start）
    已完成 → finished + closed（finish 必填 currentConsumed/realStarted/finishedDate）
    搁置   → wait（正文标注搁置原因）
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

# 仓库根（deploy/tools/zentao/zentao_sync_common.py → 上四级 = bms 根）
ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROJ = ROOT / "文档" / "项目"

CHILD_TASK_FILE_RE = re.compile(r"^(\d{2})_.+_(\d{2}-\d{1,2})_.+\.md$")
REQ_DOMAIN_FILE_RE = re.compile(r"^0([1-9])_需求_.+\.md$")
REQ_HEAD_RE = re.compile(r"^##\s+\d+\.\s+需求\s+(\d{2}-\d{1,2})：\s*(.+?)\s*<a id=\"r\d+-\d+\"></a>\s*$")

DOC2ZT_STATUS = {
    "未开始": "wait",
    "进行中": "doing",
    "部分完成": "doing",
    "已完成": "finished",
    "搁置": "wait",
}

_BASE_STATUS_RE = re.compile(r"^(未开始|进行中|部分完成|已完成|搁置)")


def base_status(status: str) -> str:
    """文档状态归一化：去掉括号后缀（如「部分完成（脚本就绪…）」→「部分完成」）。"""
    m = _BASE_STATUS_RE.match((status or "").strip())
    return m.group(1) if m else (status or "").strip()


def zt_status(status: str) -> str:
    """文档状态 → 禅道状态（wait/doing/finished）。"""
    return DOC2ZT_STATUS.get(base_status(status), "wait")


def parse_finished(finished: str) -> str:
    """完成日期提取：取首个 YYYY-MM-DD，忽略括号后缀（如「2026-08-19（脚本）」）。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", finished or "")
    return m.group(1) if m else ""


@dataclass
class Req:
    number: str            # 01-1
    title: str             # mjbk Ubuntu 基础
    pri: int               # 1-4
    story_id: str | None   # 已回填的禅道 story id
    task_id: str | None    # 已回填的禅道任务 id
    parent_task: int       # 父任务 id（1/2/3）
    status: str            # 未开始/进行中/部分完成/已完成/搁置
    finished: str          # 完成日期（YYYY-MM-DD 或 ""）
    content: str = ""
    accept: str = ""
    ref: str = ""
    file: str = ""         # 需求文档相对路径


@dataclass
class Task:
    number: str
    title: str
    parent_task: int
    task_id: str | None    # None 表示待建
    estimate: float
    status: str
    finished: str
    content: str = ""
    accept: str = ""
    ref: str = ""
    file: str = ""         # 任务文档相对路径


@dataclass
class Plan:
    done_date: str | None = None      # 已完成表：完成日期
    est_started: str | None = None    # 剩余排期表：estStarted
    deadline: str | None = None       # 剩余排期表：deadline
    held: bool = False                # 排期窗口为「搁置」


# ---------- 目录扫描 ----------

def stage_paths(stage: str) -> dict:
    """返回 stage 下 需求/任务/计划 目录 Path。"""
    base = PROJ / stage
    return {
        "req": base / "需求",
        "task": base / "任务",
        "plan": base / "计划",
    }


def list_req_files(req_dir: Path) -> list[Path]:
    return sorted(p for p in req_dir.glob("0*_需求_*.md")
                  if REQ_DOMAIN_FILE_RE.match(p.name))


def list_child_task_files(task_dir: Path) -> list[Path]:
    return sorted(p for p in task_dir.glob("*.md")
                  if CHILD_TASK_FILE_RE.match(p.name))


def list_plan_files(plan_dir: Path) -> list[Path]:
    return sorted(plan_dir.glob("*.md"))


# ---------- 需求文档解析 ----------

def _parse_meta(meta: str) -> dict:
    """解析需求元信息行。字段用「　|　」分隔，键值用全角冒号。"""
    d = {}
    for part in re.split(r"\s*\|\s*", meta):
        if "：" not in part:
            continue
        k, _, v = part.partition("：")
        d[k.strip()] = v.strip()
    pri = 2
    m = re.match(r"^(\d)", d.get("优先级", "2"))
    if m:
        pri = int(m.group(1))
    task_id, parent = None, 0
    t = d.get("禅道任务", "")
    m = re.match(r"^(\d+)", t)
    if m:
        task_id = m.group(1)
    m = re.search(r"父任务\s*(\d+)", t)
    if m:
        parent = int(m.group(1))
    story = d.get("禅道 story", "—")
    story_id = None if story in ("—", "") else story
    finished = d.get("完成日期", "—")
    return {
        "pri": pri,
        "story_id": story_id,
        "task_id": task_id,
        "parent_task": parent,
        "status": d.get("状态", "未开始"),
        "finished": "" if finished == "—" else finished,
    }


def _split_sections(body: str) -> tuple[str, str, str]:
    """把需求正文拆成 (内容, 完成标准, 参考文档)。忽略 > 注 与空行。"""
    content, accept, ref = [], [], []
    cur = None
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("**内容**"):
            cur = content
            continue
        if s.startswith("**完成标准**"):
            cur = accept
            rest = s.split("：", 1)[1] if "：" in s else ""
            if rest.strip():
                accept.append(rest.strip())
            continue
        if s.startswith("**参考文档**"):
            cur = ref
            rest = s.split("：", 1)[1] if "：" in s else ""
            if rest.strip():
                ref.append(rest.strip())
            continue
        if s.startswith("## ") or not s or s.startswith(">"):
            continue
        if cur is not None:
            cur.append(line.rstrip())
    return "\n".join(content).strip(), "\n".join(accept).strip(), "\n".join(ref).strip()


def parse_req_file(path: Path) -> list[Req]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    reqs: list[Req] = []
    i = 0
    while i < len(lines):
        m = REQ_HEAD_RE.match(lines[i])
        if not m:
            i += 1
            continue
        number, title = m.group(1), m.group(2).strip()
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        meta = lines[j] if j < len(lines) else ""
        k = j + 1
        while k < len(lines) and not lines[k].startswith("## "):
            k += 1
        body = "\n".join(lines[j + 1:k])
        md = _parse_meta(meta)
        content, accept, ref = _split_sections(body)
        reqs.append(Req(
            number=number, title=title, pri=md["pri"], story_id=md["story_id"],
            task_id=md["task_id"], parent_task=md["parent_task"],
            status=md["status"], finished=md["finished"],
            content=content, accept=accept, ref=ref,
            file=str(path.relative_to(ROOT)),
        ))
        i = k
    return reqs


# ---------- 任务文档解析 ----------

def _parse_task_table(lines: list[str]) -> dict:
    table: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if key in ("项", "值", "---") or set(key) <= set("- :"):
            continue
        table[key] = val
    return table


def _h2_sections(lines: list[str]) -> dict:
    """按「## N. 标题」切段，键为标题（去锚点与序号）。"""
    sections: dict[str, list[str]] = {}
    cur: list[str] | None = None
    for line in lines:
        m = re.match(r"^##\s+(?:\d+\.\s*)?(.+?)\s*(?:<a id=.+?></a>)?\s*$", line)
        if m:
            cur = sections.setdefault(m.group(1).strip(), [])
        elif cur is not None:
            cur.append(line)
    return sections


def parse_task_file(path: Path) -> Task:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    m = re.match(r"^#\s+(\d{2}-\d{1,2})\s+(.+)$", lines[0])
    if not m:
        raise ValueError(f"任务文档首行无法解析编号/标题：{path}")
    number, title = m.group(1), m.group(2).strip()
    table = _parse_task_table(lines)
    secs = _h2_sections(lines)

    task_id, parent = None, 0
    t = table.get("禅道任务", "")
    mm = re.match(r"^(\d+)", t)
    if mm:
        task_id = mm.group(1)
    mm = re.search(r"父任务\s*(\d+)", t)
    if mm:
        parent = int(mm.group(1))

    est = 0.0
    mm = re.match(r"^([\d.]+)\s*h", table.get("工时（重估）", ""))
    if mm:
        est = float(mm.group(1))
    finished = table.get("完成日期", "—")

    def sec(name: str) -> str:
        for k, v in secs.items():
            if k.startswith(name):
                return "\n".join(v).strip()
        return ""

    return Task(
        number=number, title=title, parent_task=parent, task_id=task_id,
        estimate=est, status=table.get("状态", "未开始"),
        finished="" if finished == "—" else finished,
        content=sec("任务内容"), accept=sec("完成标准"), ref=sec("参考文档"),
        file=str(path.relative_to(ROOT)),
    )


# ---------- 计划文档解析 ----------

def _parse_window(w: str) -> tuple[str | None, str | None, bool]:
    w = w.strip()
    if "搁置" in w:
        return None, None, True
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", w)
    if not dates:
        return None, None, False
    if len(dates) >= 2:
        return dates[0], dates[-1], False
    return dates[0], dates[0], False


def _table_rows(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set(cells[0]) <= set("- :") or cells[0] in ("编号",):
            continue
        rows.append(cells)
    return rows


def parse_plan_file(path: Path) -> dict[str, Plan]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    secs = _h2_sections(lines)
    plan: dict[str, Plan] = {}

    for k, v in secs.items():
        if not k.startswith("已完成"):
            continue
        for cells in _table_rows(v):
            if len(cells) < 4:
                continue
            number = cells[0]
            p = plan.setdefault(number, Plan())
            m = re.search(r"(\d{4}-\d{2}-\d{2})", cells[3])
            if m:
                p.done_date = m.group(1)

    for k, v in secs.items():
        if not k.startswith("剩余"):
            continue
        for cells in _table_rows(v):
            if len(cells) < 5:
                continue
            number = cells[0]
            est_s, ddl, held = _parse_window(cells[4])
            p = plan.setdefault(number, Plan())
            p.est_started, p.deadline, p.held = est_s, ddl, held
    return plan


# ---------- spec / desc 组装 ----------

def build_spec(req: Req) -> str:
    parts = []
    if req.content:
        parts.append("【内容】\n" + req.content)
    if req.accept:
        parts.append("【完成标准】\n" + req.accept)
    if req.ref:
        parts.append("【参考文档】\n" + req.ref)
    return "\n\n".join(parts)


def build_desc(task: Task) -> str:
    parts = []
    if task.content:
        parts.append("【任务内容】\n" + task.content)
    if task.accept:
        parts.append("【完成标准】\n" + task.accept)
    if task.ref:
        parts.append("【参考文档】\n" + task.ref)
    return "\n\n".join(parts)


# ---------- 回填 ----------

def backfill_story_id(path: Path, number: str, story_id: int) -> bool:
    """把需求文档中该条的「禅道 story：—」替换为 id。返回是否改动。"""
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    # 定位该条需求块（从 ## … 需求 {number}： 到下一个 ##）
    m = re.search(
        r"(##\s+\d+\.\s+需求\s+" + re.escape(number) + r"：[^\n]*\n\n[^\n]*禅道 story：)(—|[^　|\n]+)",
        text)
    if not m:
        return False
    repl = m.group(1) + str(story_id)
    new = text[:m.start()] + repl + text[m.end():]
    p.write_text(new, encoding="utf-8")
    return True


def backfill_task_id(path: Path, number: str, task_id: int, parent: int) -> bool:
    """把任务文档「| 禅道任务 | … |」行的值替换为「{id}（父任务 {parent}）」。"""
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^\|\s*禅道任务\s*\|\s*[^|\n]*\|\s*$", text, flags=re.M)
    if not m:
        return False
    repl = f"| 禅道任务 | {task_id}（父任务 {parent}） |"
    new = text[:m.start()] + repl + text[m.end():]
    p.write_text(new, encoding="utf-8")
    return True


def backfill_req_task_id(path: Path, number: str, task_id: int, parent: int) -> bool:
    """把需求文档元信息行「禅道任务：…」替换为「{id}（父任务 {parent}）」。"""
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    m = re.search(
        r"(##\s+\d+\.\s+需求\s+" + re.escape(number) + r"：[^\n]*\n\n[^\n]*禅道任务：)([^　|\n]*)",
        text)
    if not m:
        return False
    repl = m.group(1) + f"{task_id}（父任务 {parent}）"
    new = text[:m.start()] + repl + text[m.end():]
    p.write_text(new, encoding="utf-8")
    return True


if __name__ == "__main__":  # 自测：解析 00_准备期
    sp = stage_paths("00_准备期")
    reqs: list[Req] = []
    for f in list_req_files(sp["req"]):
        reqs += parse_req_file(f)
    print(f"需求 {len(reqs)} 条：")
    for r in reqs:
        print(f"  {r.number} {r.title} pri={r.pri} story={r.story_id} task={r.task_id} "
              f"parent={r.parent_task} status={r.status} finished={r.finished!r} "
              f"content_len={len(r.content)}")
    tasks: list[Task] = []
    for f in list_child_task_files(sp["task"]):
        tasks.append(parse_task_file(f))
    print(f"任务 {len(tasks)} 条：")
    for t in tasks:
        print(f"  {t.number} {t.title} parent={t.parent_task} task_id={t.task_id} "
              f"est={t.estimate} status={t.status} finished={t.finished!r} content_len={len(t.content)}")
    for f in list_plan_files(sp["plan"]):
        plan = parse_plan_file(f)
        print(f"计划 {f.name} → {len(plan)} 项：")
        for k in sorted(plan):
            p = plan[k]
            print(f"  {k} done={p.done_date} est={p.est_started} ddl={p.deadline} held={p.held}")

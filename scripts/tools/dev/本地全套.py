#!/usr/bin/env python3
"""本机裸跑「全套」后端：SQLite 本地库 + 内存缓存（无需 Docker / 无需 mjbk），供**本机开发与真机回归**。

为什么这样起（口径）：
- 开发态配置（`backend/config.dev.toml`）本就是 SQLite + 内存缓存 + 字典/参数走 SQL，**不依赖容器**；
- 服务间调用基址模板是 `http://{service}:8000`（`[service_client].options.base_url_template`），
  故本机给每个服务一个 loopback 别名（`127.0.0.2 tenant` …）+ **统一 8000 端口**，与容器形态同形；
- `require_auth` 支持「本地 Bearer 用户令牌」路径、`[edge].require_gateway_identity = false`
  ⇒ 不经网关直连服务可行；前端由 `VITE_LOCAL_API`（见 `env` 子命令）按服务就近代理。

用法: python3 本地全套.py <up|down|stop|status|seed|env|logs|unlock> [选项]
（Linux 同名 .sh / Windows 同名 .bat 均为转调本文件的薄包装；逻辑只维护在这里。）
  up                起服务（幂等；已在跑则跳过）+ 自愈 hosts 别名 / 开发密钥，并等待健康；
                    收尾自动确保 `.env.local` 的 `VITE_LOCAL_API`（同 env 子命令，缺则补、有则只提示）
  down              停本脚本起的服务（仅按 pid 文件；`--force` 才连带清理 IDE 起的同名进程）
  stop <服务名...>  只停指定服务（其余保持纳管）——供「用 debugpy 调试某服务」时腾出该服务
  status            进程与 /healthz、/readyz 一览
  seed              幂等种子：租户注册库 + 菜单元数据 + 建号（缺省账号 admin；口令随机生成并打印一次）
  env               确保 `frontend/apps/desktop/.env.local` 含 `VITE_LOCAL_API` 本地服务映射（up 已自动调用）
  logs [服务名]     打印日志尾部（缺省全部服务；追看用 tail -f）
  unlock [账号]     解锁账号：清 `sys_user.failed_count` / `locked_until` + 删 Redis 登录失败计数键
                    （登录阈值 5 次 / 锁 15 分钟：**验验证码请用不存在的账号试错口令**，
                     别拿真账号连试错密码，否则真账号被锁 20003「账号已锁定」）

选项:
  --services "a b c"   要起的服务（缺省 tenant platform identity）
  --redis URL          Redis 连接串（缺省远端开发机 DB5 的 redis://<开发机>:6379/5）
  --reset-db           起服务前把 `database/bms/bms_*.db` 备份移走（库结构/表归属变更后必须，否则 catalog 校验失败）
  --username NAME      建号账号（缺省 admin）
  --password PASS      建号口令（缺省**随机生成并仅打印一次**）
  --reset-password     建号时重置既有账号口令
  --force              down 时连带清理本机全部 `python -m bms_*` 进程

账号: `seed` 缺省建 `admin`，口令缺省随机生成并**仅打印一次**——**凭据只登记在
      《bms文档/用户文档/本地资源.md》「BMS 应用账号」节（凭据不入库、不写入其他文档，见《AI开发规范》）**；
      起栈后若登录 401，先看是否漏跑 seed。

状态目录: ${BMS_LOCAL_STATE_DIR:-/tmp/bms-local-stack}（pid 与日志；Windows 缺省为 %TEMP%\\bms-local-stack）
退出码: 0 = 成功；1 = 失败（含健康等待超时）；2 = 参数错误

平台口径（Linux / Windows 双平台）：
- 解释器：Linux 用 `backend/.venv/bin/python`，Windows 用 `backend\\.venv\\Scripts\\python.exe`；
- loopback 别名：两平台对 127.0.0.0/8 整段可绑定，无需额外加地址；仅需 hosts 别名
  （Linux 经 sudo tee 写 /etc/hosts；Windows 写 hosts 文件需管理员权限，失败时提示手工追加）；
- 后台进程：Linux 用新会话（等价 nohup），Windows 用分离进程；停止口径同为 TERM → 5s → 强杀 → 2s；
- 子进程枚举：Linux 用 /proc；Windows 服务本体为单进程，不枚举子进程。
"""

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

IS_WINDOWS = os.name == "nt"
PREFIX = "[本地全套]"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
DB_DIR = os.path.normpath(os.path.join(ROOT, "..", "database", "bms"))
FRONTEND_ENV = os.path.join(ROOT, "frontend", "apps", "desktop", ".env.local")
STATE_DIR = os.environ.get("BMS_LOCAL_STATE_DIR") or (
    os.path.join(tempfile.gettempdir(), "bms-local-stack") if IS_WINDOWS else "/tmp/bms-local-stack"
)
KEYS_FILE = os.path.join(BACKEND, ".dev-keys.local")
PY = (
    os.path.join(BACKEND, ".venv", "Scripts", "python.exe")
    if IS_WINDOWS
    else os.path.join(BACKEND, ".venv", "bin", "python")
)
PORT = os.environ.get("BMS_LOCAL_PORT") or "8000"
# Windows 进程创建标志：脱离 IDE 任务所在的 Job Object（否则关任务终端 / 重启 IDE 会连带强杀服务）
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

SERVICES_DEFAULT = "tenant platform identity"
# 说明：`org` 已随组织主数据归 mdm 产品服务（2026-10-07，bms 11_01）退出平台服务清单，
# 本机全套不再纳管（mdm 组织域服务在本机跑法随 mdm 仓工程骨架另定）。
SERVICES = SERVICES_DEFAULT
REDIS_URL = os.environ.get("BMS_LOCAL_REDIS") or "redis://192.168.0.107:6379/5"
RESET_DB = 0
USERNAME = "admin"
PASSWORD = ""
RESET_PASSWORD = 0
FORCE = 0
try:
    HEALTH_TIMEOUT = int(os.environ.get("BMS_LOCAL_HEALTH_TIMEOUT") or "45")
except ValueError:
    HEALTH_TIMEOUT = 45

_IP_MAP = {"tenant": "127.0.0.2", "platform": "127.0.0.4", "identity": "127.0.0.5"}


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def log(msg):
    print(f"{PREFIX} {msg}")


def err(msg):
    print(f"{PREFIX} {msg}", file=sys.stderr)


def usage():
    print(__doc__.strip())


def usage_stderr():
    print(__doc__.strip(), file=sys.stderr)


def services_list():
    return SERVICES.split()


def ip_of(svc):
    """服务 → loopback 别名（与服务基址模板 http://{service}:8000 同形）。"""
    return _IP_MAP.get(svc, "")


def py_ok():
    if not os.path.isfile(PY):
        return False
    return True if IS_WINDOWS else os.access(PY, os.X_OK)


# ---- 进程工具 ----


def pid_alive(pid):
    """进程存活判定（Windows 用 OpenProcess + GetExitCodeProcess 的 STILL_ACTIVE）。"""
    if not pid or pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def proc_cmdline_map():
    """全机 python 进程的 {pid: 命令行}（PID 复用校验用）；取不到时返回 {}。"""
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' } | "
                    "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return {}
            data = json.loads(result.stdout)
        except Exception:
            return {}
        if isinstance(data, dict):
            data = [data]
        procs = {}
        for item in data:
            with contextlib.suppress(KeyError, TypeError, ValueError):
                procs[int(item["ProcessId"])] = item.get("CommandLine") or ""
        return procs

    procs = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        if b"python" not in raw:
            continue
        procs[int(entry)] = raw.replace(b"\x00", b" ").decode("utf-8", "replace")
    return procs


def is_service_pid(svc, pid, procs=None):
    """pid 存活**且**确实是本服务进程（命令行含 `-m bms_<svc>`）。

    PID 会被系统复用：服务退出后同号被别的程序（如 IDE）拿走，旧逻辑只看 `pid_alive`
    就当成「在跑」⇒ up 跳过、status 假在跑、down 误杀无关进程。命令行取不到时降级为
    「存活即算」（保持旧行为，避免权限/CIM 异常导致全部判死）。
    """
    if not pid or not pid_alive(pid):
        return False
    if procs is None:
        procs = proc_cmdline_map()
    if not procs:
        return True
    cmdline = procs.get(pid)
    if cmdline is None:
        return False
    return f"-m bms_{svc}" in cmdline.replace("\\", "/")


def children_of(pid):
    """直接子进程（等价 pgrep -P）；Windows 不枚举（服务本体为单进程）。"""
    if IS_WINDOWS:
        return []
    kids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        try:
            tail = data.rsplit(b")", 1)[1].split()
            ppid = int(tail[1])
        except IndexError, ValueError:
            continue
        if ppid == pid:
            kids.append(int(entry))
    return kids


def _signal(pid, sig):
    try:
        os.kill(pid, sig)
        return True
    except OSError:
        return False


def kill_term(pid):
    return _signal(pid, signal.SIGTERM)


def kill_hard(pid):
    sig = signal.SIGTERM if IS_WINDOWS else getattr(signal, "SIGKILL", signal.SIGTERM)
    return _signal(pid, sig)


def http_code(url):
    """取 HTTP 状态码（等价 curl -s -o /dev/null -w '%{http_code}' --max-time 2）；失败为 000。"""
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception:
        return "000"


def tail_log(path, n, to_stderr=False):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-n:]
    except OSError:
        return
    out = sys.stderr if to_stderr else sys.stdout
    for line in lines:
        out.write(line if line.endswith("\n") else line + "\n")


def read_pid(pid_file):
    try:
        with open(pid_file, encoding="utf-8") as fh:
            return int(fh.read().strip() or 0)
    except OSError, ValueError:
        return 0


# ---- 目录 / hosts / 密钥 ----


def ensure_dirs():
    os.makedirs(STATE_DIR, exist_ok=True)


def _hosts_path():
    if IS_WINDOWS:
        return os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
    return "/etc/hosts"


def _resolves(svc):
    import socket

    try:
        socket.getaddrinfo(svc, None)
        return True
    except OSError:
        return False


def ensure_hosts():
    missing = []
    for svc in services_list():
        ip = ip_of(svc)
        if not ip:
            err(f"未知服务：{svc}（可选 tenant / platform / identity）")
            return 2
        if not _resolves(svc):
            missing.append((svc, ip))
    if not missing:
        return 0
    log("补 hosts 别名（服务间基址模板 http://{service}:8000 需要）")
    lines = ["# BMS 本地多服务寻址（本地全套.py；与服务基址模板 http://{service}:8000 同形）"]
    lines += [f"{ip} {svc}" for svc, ip in missing]
    block = "\n".join(lines)

    if IS_WINDOWS:
        path = _hosts_path()
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n" + block + "\n")
        except OSError:
            err(f"写入 hosts 失败（需管理员权限）：{path}——请以管理员身份重跑，或手工追加：")
            print(block, file=sys.stderr)
            return 1
        log(f"已写入 {path}")
        return 0

    result = subprocess.run(
        ["sudo", "-n", "tee", "-a", "/etc/hosts"], input=block + "\n", text=True, capture_output=True
    )
    if result.returncode == 0:
        log("已写入 /etc/hosts")
        return 0
    err("写入 /etc/hosts 失败（需 sudo）——请手工追加：")
    print(block, file=sys.stderr)
    return 1


_KEYS_CODE = """import json
from pathlib import Path
from joserfc.jwk import RSAKey


def pair():
    key = RSAKey.generate_key(2048, private=True)
    return key.as_pem(private=False).decode(), key.as_pem(private=True).decode()


user_pub, user_priv = pair()
svc_pub, svc_priv = pair()
Path(r"__KEYS_FILE__").write_text("\\n".join([
    "export BMS_SECURITY__KEYS='" + json.dumps(
        {"usr-k1": {"algorithm": "RS256", "public_key": user_pub, "private_key": user_priv}}) + "'",
    "export BMS_SECURITY__ACTIVE_KID='usr-k1'",
    "export BMS_SERVICE_TOKEN__KEYS='" + json.dumps(
        {"svc-k1": {"algorithm": "RS256", "public_key": svc_pub, "private_key": svc_priv}}) + "'",
    "export BMS_SERVICE_TOKEN__ACTIVE_KID='svc-k1'",
]) + "\\n", encoding="utf-8")
print("已生成")
"""


def ensure_keys():
    if os.path.isfile(KEYS_FILE):
        return 0
    if not py_ok():
        err(f"缺后端虚拟环境：{PY}（先跑 uv sync）")
        return 1
    log(f"生成开发密钥 → {KEYS_FILE}（用户令牌 usr- 前缀 + 服务令牌 svc- 前缀；本机专用、不入库）")
    code = _KEYS_CODE.replace("__KEYS_FILE__", KEYS_FILE)
    result = subprocess.run([PY], input=code, text=True)
    return 0 if result.returncode == 0 else 1


def load_keys_env():
    """等价 shell 的 `. "$KEYS_FILE"`：解析 `export KEY='VALUE'` 行并注入环境变量。"""
    try:
        with open(KEYS_FILE, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        err(f"开发密钥文件不可读：{KEYS_FILE}")
        return 1
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("export "):
            err(f"密钥文件存在无法解析的行，已跳过：{line[:60]}")
            continue
        key, _, value = line[len("export ") :].partition("=")
        if value.startswith("'") and value.endswith("'") and len(value) >= 2:
            value = value[1:-1]
        os.environ[key.strip()] = value
    return 0


def reset_db():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(DB_DIR, f".db-backup-{stamp}")
    os.makedirs(backup, exist_ok=True)
    moved = 0
    for name in sorted(os.listdir(DB_DIR)):
        if name.startswith("bms_") and name.endswith(".db"):
            shutil.move(os.path.join(DB_DIR, name), os.path.join(backup, name))
            moved += 1
    log(f"--reset-db：移走 {moved} 个本地库文件 → {backup}（服务启动会按当前表结构重建）")


# ---- 起停 ----

LOG_ROTATE_BYTES = 5 * 1024 * 1024


def open_log_append(log_path, svc):
    """追加打开服务日志（不再 truncate，历史留作排障证据）：先写启动分隔行；超阈值归档为 .1。"""
    with contextlib.suppress(OSError):
        if os.path.getsize(log_path) > LOG_ROTATE_BYTES:
            os.replace(log_path, log_path + ".1")
    with contextlib.suppress(OSError):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "ab")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    logf.write(f"\n===== {svc} 启动 @ {stamp}（本地全套.py）=====\n".encode())
    logf.flush()
    return logf


def start_one(svc, ip, procs=None):
    pid_file = os.path.join(STATE_DIR, f"{svc}.pid")
    pid = read_pid(pid_file) if os.path.isfile(pid_file) else 0
    if pid and is_service_pid(svc, pid, procs):
        log(f"{svc} 已在跑（pid {pid}），跳过")
        return
    if pid and pid_alive(pid):
        # PID 复用：旧服务退出后同号被别的程序（如 IDE）拿走，绝不能当「在跑」跳过
        log(f"{svc} 旧 pid {pid} 已被其他进程复用（不是本服务）——清残留 pid 文件后重新拉起")
    if pid:
        with contextlib.suppress(OSError):
            os.remove(pid_file)
    # 已在监听（例如 IDE 调试起的）→ 接管跳过，避免二次绑定端口失败
    if http_code(f"http://{ip}:{PORT}/healthz") == "200":
        log(f"{svc} 已在监听 {ip}:{PORT}（非本脚本启动；未纳管 pid），跳过")
        return
    # 后台起 python（**不套中间进程**）——否则记到的 pid 是包装进程而非服务本体，
    # 停服务会打空、留下孤儿进程。cwd 与密钥由 cmd_up 在主进程内设定，子进程自然继承。
    log_path = os.path.join(STATE_DIR, f"{svc}.log")
    env = dict(os.environ)
    env.update(
        {
            "BMS_SERVER__HOST": ip,
            "BMS_SERVER__PORT": PORT,
            "BMS_REDIS__URL": REDIS_URL,
            "PYTHONUNBUFFERED": "1",
        }
    )
    kwargs = {}
    if IS_WINDOWS:
        # DETACHED_PROCESS：不弹控制台窗口；CREATE_NEW_PROCESS_GROUP：独立信号组；
        # CREATE_BREAKAWAY_FROM_JOB：**脱离 IDE 任务容器**——关掉任务终端 / 重启 IDE 不会被连带强杀
        base_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        candidates = [base_flags | CREATE_BREAKAWAY_FROM_JOB, base_flags]
    else:
        kwargs["start_new_session"] = True  # nohup 等价（天然脱离父会话）
        candidates = [0]
    with open_log_append(log_path, svc) as logf:
        proc = None
        for flags in candidates:
            try:
                proc = subprocess.Popen(
                    [PY, "-m", f"bms_{svc}"],
                    cwd=BACKEND,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                    **kwargs,
                )
                break
            except OSError as exc:
                if flags is candidates[0] and IS_WINDOWS:
                    log(f"{svc} 无法脱离 IDE 任务容器（{exc}）——退化为普通后台进程：关 IDE 可能被连带停止")
                    continue
                raise
    with open(pid_file, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid) + "\n")
    log(f"{svc} 启动中：{ip}:{PORT}（pid {proc.pid}，日志 {log_path}）")


def stop_pid(svc, pid):
    """停一个进程：TERM → 等 5s → KILL → 再等 2s；仍活则**报错交人工**（绝不无限等）。"""
    kids = children_of(pid)
    if kids:
        log(f"{svc}：连带子进程 {' '.join(str(k) for k in kids)}")
    kill_term(pid)
    for k in kids:
        kill_term(k)

    def still_alive():
        return pid_alive(pid) or any(pid_alive(k) for k in kids)

    for _ in range(5):
        if not still_alive():
            log(f"已停 {svc}（pid {pid}{' + 子进程' if kids else ''}）")
            return 0
        time.sleep(1)
    err(f"{svc}（pid {pid}）TERM 后 5s 仍未退出 → 强制 KILL")
    kill_hard(pid)
    for k in kids:
        kill_hard(k)
    time.sleep(2)
    if still_alive():
        err(f"{svc}（pid {pid}）**无法终止**（僵尸 / 权限不足 / 内核 IO 阻塞）——请人工处理：kill -9 {pid}")
        return 1
    log(f"已强制停 {svc}（pid {pid}{' + 子进程' if kids else ''}）")
    return 0


def wait_all_health():
    """等待全部健康：单一总超时（不逐服务串行耗满），且**进程已退出 / pid 被复用即立刻报错 + 打印日志尾部**。"""
    deadline = time.time() + HEALTH_TIMEOUT
    procs = proc_cmdline_map()
    while True:
        pending = []
        for svc in services_list():
            ip = ip_of(svc)
            if http_code(f"http://{ip}:{PORT}/healthz") == "200":
                continue
            pid_file = os.path.join(STATE_DIR, f"{svc}.pid")
            pid = read_pid(pid_file) if os.path.isfile(pid_file) else 0
            if pid and not pid_alive(pid):
                err(f"{svc} 进程已退出（pid {pid}）——日志尾部：")
                tail_log(os.path.join(STATE_DIR, f"{svc}.log"), 20, to_stderr=True)
                return 1
            # 命令行明确采集到但与本服务不符 → PID 已被复用（别傻等满超时）
            if pid and procs and pid in procs and f"-m bms_{svc}" not in procs[pid].replace("\\", "/"):
                err(f"{svc} 的 pid {pid} 已被其他进程复用（不是本服务，端口无响应）——日志尾部：")
                tail_log(os.path.join(STATE_DIR, f"{svc}.log"), 20, to_stderr=True)
                return 1
            pending.append(svc)
        if not pending:
            log(f"全部健康（healthz 200）：{SERVICES}")
            return 0
        if time.time() >= deadline:
            err(f"健康等待超时（{HEALTH_TIMEOUT}s），未就绪：{' '.join(pending)} —— 看 {STATE_DIR}/<服务>.log")
            return 1
        time.sleep(1)
        if not pending:
            log(f"全部健康（healthz 200）：{SERVICES}")
            return 0
        if time.time() >= deadline:
            err(f"健康等待超时（{HEALTH_TIMEOUT}s），未就绪：{' '.join(pending)} —— 看 {STATE_DIR}/<服务>.log")
            return 1
        time.sleep(1)


# ---- 子命令 ----


def cmd_up():
    ensure_dirs()
    if not py_ok():
        err(f"缺后端虚拟环境：{PY}（先跑 uv sync）")
        return 1
    if ensure_keys():
        return 1
    rc = ensure_hosts()
    if rc:
        return rc
    if RESET_DB:
        reset_db()
    # 切到 backend 并加载开发密钥（服务子进程继承 cwd 与已导出的环境变量；脚本其余路径全用绝对路径）
    os.chdir(BACKEND)
    if load_keys_env():
        return 1
    procs = proc_cmdline_map()
    for svc in services_list():
        start_one(svc, ip_of(svc), procs)
    if wait_all_health():
        return 1
    # 收尾自动补齐前端 `.env.local`：缺 `VITE_LOCAL_API` 时前端 `/api` 会回落 VITE_API_PROXY 网关
    # （本机通常无该网关）⇒ 登录 502；此处幂等（已存在则只提示，不覆盖）。
    if cmd_env():
        return 1
    log("全套已就绪；前端请在 IDE 跑「前端：宿主 dev」")
    return 0


def find_unmanaged_backend_pids():
    """等价 pgrep -f '\\.venv/bin/python -m bms_'（Windows 走 CIM 命令行匹配）。"""
    procs = proc_cmdline_map()
    return sorted(pid for pid, cmdline in procs.items() if "-m bms_" in cmdline.replace("\\", "/"))


def cmd_down():
    ensure_dirs()
    rc = 0
    seen = set()
    for svc in (SERVICES_DEFAULT + " " + SERVICES).split():
        if svc in seen:
            continue
        seen.add(svc)
        pid_file = os.path.join(STATE_DIR, f"{svc}.pid")
        if not os.path.isfile(pid_file):
            continue
        pid = read_pid(pid_file)
        if pid and is_service_pid(svc, pid):
            if stop_pid(svc, pid):
                rc = 1
        elif pid and pid_alive(pid):
            err(f"{svc} 的 pid {pid} 已被其他进程复用——只清残留 pid 文件，不动该进程（避免误杀）")
        else:
            log(f"{svc} 已不在跑（残留 pid 文件，清理）")
        with contextlib.suppress(OSError):
            os.remove(pid_file)
    rest = find_unmanaged_backend_pids()
    if rest:
        if FORCE:
            log(f"--force：逐个停剩余进程：{' '.join(str(p) for p in rest)}")
            for pid in rest:
                if stop_pid("未纳管进程", pid):
                    rc = 1
        else:
            err(f"另有未跟踪的后端进程：{' '.join(str(p) for p in rest)}（可能是 IDE 调试起的；如需一并停用 --force）")
    elif rc == 0:
        log("本地后端已无残留进程")
    return rc


def cmd_stop(names):
    ensure_dirs()
    if not names:
        err("用法：本地全套.py stop <服务名...>（如 stop identity）")
        return 2
    rc = 0
    stopped = 0
    for svc in names:
        if svc.startswith("bms_"):
            svc = svc[len("bms_") :]
        if not ip_of(svc):
            err(f"未知服务：{svc}（可选 tenant / platform / identity）")
            rc = 2
            continue
        pid_file = os.path.join(STATE_DIR, f"{svc}.pid")
        if not os.path.isfile(pid_file):
            err(f"{svc} 未被本脚本纳管（无 pid 文件）——若它由 IDE 调试启动，请在 IDE 里停止")
            rc = 1
            continue
        pid = read_pid(pid_file)
        if pid and is_service_pid(svc, pid):
            if stop_pid(svc, pid):
                rc = 1
        elif pid and pid_alive(pid):
            err(f"{svc} 的 pid {pid} 已被其他进程复用——只清残留 pid 文件，不动该进程（避免误杀）")
        else:
            log(f"{svc} 已不在跑（清理残留 pid 文件）")
        with contextlib.suppress(OSError):
            os.remove(pid_file)
        stopped += 1
    if stopped > 0:
        log(f"已停 {stopped} 个服务（其余仍纳管）；调试完用 up 一键补回")
    return rc


def cmd_status():
    ensure_dirs()
    procs = proc_cmdline_map()
    print(f"{'服务':<10} {'地址':<12} {'PID':<8} {'healthz':<9} readyz")
    stale = []
    for svc in services_list():
        ip = ip_of(svc)
        pid_file = os.path.join(STATE_DIR, f"{svc}.pid")
        pid = read_pid(pid_file) if os.path.isfile(pid_file) else 0
        if pid and is_service_pid(svc, pid, procs):
            shown = str(pid)
        else:
            shown = "-"
            stale.append(svc)
        health = http_code(f"http://{ip}:{PORT}/healthz") or "000"
        ready = http_code(f"http://{ip}:{PORT}/readyz") or "000"
        print(f"{svc:<10} {ip + ':' + PORT:<12} {shown:<8} {health:<9} {ready}")
    if stale:
        print(f"\n提示：{' '.join(stale)} 无有效 pid（进程已退出 / pid 被复用）——需要时跑 up 补起")
    return 0


def _run_py(args):
    return subprocess.run([PY, *args], cwd=BACKEND).returncode


def cmd_seed():
    if not py_ok():
        err(f"缺后端虚拟环境：{PY}")
        return 1
    rc = 0
    # 库路径与连接串统一由配置解析（config.dev.toml 的 [database].sqlite_dir）；不再写死 --url
    log("种子：租户注册库（配置解析 bms_tenant.db）")
    if _run_py(["-m", "ops.seed_tenant"]):
        rc = 1
    log("种子：菜单元数据（配置解析 bms_platform.db）")
    if _run_py(["-m", "ops.seed_menu"]):
        rc = 1
    log(f"建号：{USERNAME}（demo 租户 platform 库；口令只打印这一次——请登记到《本地资源》「BMS 应用账号」节）")
    extra = []
    if RESET_PASSWORD:
        extra.append("--reset-password")
    # 口令不入库：未显式给 `--password` 时由建号脚本随机生成并打印一次（凭据只落《本地资源》）。
    if PASSWORD:
        extra += ["--password", PASSWORD]
    if _run_py(["-m", "ops.seed_user", "--username", USERNAME, *extra]):
        rc = 1
    # 内置角色与授权 + bootstrap 绑定（依赖上一步的动作码与已建账号）：把建出的账号绑到内置系统管理员，
    # 命中权限引擎豁免层级，使本地开发对全部 `require_permission` 端点开箱可用。
    log(f"种子：内置角色与授权（角色域 platform 租户库）+ 绑定 {USERNAME} → 内置系统管理员")
    if _run_py(["-m", "ops.seed_rbac", "--assign-user", USERNAME]):
        rc = 1
    if rc == 0:
        log("种子完成（幂等：重复执行新增为 0）")
    return rc


_UNLOCK_CODE = """import os
import sqlite3

import redis
from sqlalchemy.engine import make_url

from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key

account = os.environ["BMS_UNLOCK_ACCOUNT"]
# 库路径统一由配置解析（sqlite_dir 基址），不写死相对路径
factory = EngineFactory(get_settings(), allow_cross_service=True)
user_path = make_url(factory.resolved_url(build_tenant_db_key("demo", service="platform"))).database
tenant_path = make_url(factory.resolved_url(build_platform_db_key("tenant"))).database
conn = sqlite3.connect(user_path)
rows = list(conn.execute("select failed_count, locked_until from sys_user where username = ?", (account,)))
if not rows:
    print(f"[unlock] 未找到账号：{account}（{user_path} 的 sys_user）")
    raise SystemExit(2)
conn.execute("update sys_user set failed_count = 0, locked_until = NULL where username = ?", (account,))
conn.commit()
print(f"[unlock] {account}：failed_count / locked_until {rows[0]} → (0, None)")

tenants = list(sqlite3.connect(tenant_path).execute("select id from sys_tenant where code = 'demo'"))
client = redis.from_url(os.environ["BMS_UNLOCK_REDIS"], socket_timeout=5)
keys = [key for key in client.scan_iter("bms:*:rate:login*") if account.encode() in key]
print(f"[unlock] Redis 登录失败计数键：{keys or '（无）'}")
if keys:
    print(f"[unlock] 已删 {client.delete(*keys)} 个键（租户主键 {tenants[0][0] if tenants else '?'}）")
"""


def cmd_unlock():
    if not py_ok():
        err(f"缺后端虚拟环境：{PY}")
        return 1
    account = USERNAME
    log(f"解锁：{account}（清 platform 租户库失败计数 / 锁 + Redis 登录失败计数键）")
    env = dict(os.environ)
    env["BMS_UNLOCK_ACCOUNT"] = account
    env["BMS_UNLOCK_REDIS"] = REDIS_URL
    result = subprocess.run([PY], input=_UNLOCK_CODE, text=True, cwd=BACKEND, env=env)
    return result.returncode


def cmd_env():
    mapping = ",".join(f"{svc}={ip_of(svc)}" for svc in ("tenant", "platform", "identity"))
    if os.path.isfile(FRONTEND_ENV):
        with open(FRONTEND_ENV, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("VITE_LOCAL_API="):
                    log(f"已存在 VITE_LOCAL_API：{line.rstrip()}")
                    return 0
    os.makedirs(os.path.dirname(FRONTEND_ENV), exist_ok=True)
    with open(FRONTEND_ENV, "a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(
            "# 本机裸跑后端时的服务直连映射（由 scripts/tools/dev/本地全套.py env 维护；"
            "未列出的服务走 VITE_API_PROXY）\n"
        )
        fh.write(f"VITE_LOCAL_API={mapping}\n")
    log(f"已写入 {FRONTEND_ENV}：VITE_LOCAL_API={mapping}")
    return 0


def cmd_logs(names):
    ensure_dirs()
    targets = names[0].split() if names and names[0] else services_list()
    for svc in targets:
        print(f"===== {svc} =====")
        path = os.path.join(STATE_DIR, f"{svc}.log")
        if os.path.isfile(path):
            tail_log(path, 40)
        else:
            print(f"（无日志 {path}）")
    return 0


def main(argv):
    configure_stdio()
    global SERVICES, REDIS_URL, RESET_DB, USERNAME, PASSWORD, RESET_PASSWORD, FORCE

    if len(argv) < 2:
        usage()
        return 0
    cmd = argv[1]
    rest = argv[2:]
    positional = []
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--services":
            SERVICES = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--redis":
            REDIS_URL = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--reset-db":
            RESET_DB = 1
            i += 1
        elif arg == "--username":
            USERNAME = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--password":
            PASSWORD = rest[i + 1] if i + 1 < len(rest) else ""
            i += 2
        elif arg == "--reset-password":
            RESET_PASSWORD = 1
            i += 1
        elif arg == "--force":
            FORCE = 1
            i += 1
        elif arg in ("-h", "--help"):
            usage()
            return 0
        elif arg.startswith("-"):
            err(f"未知参数：{arg}")
            usage_stderr()
            return 2
        else:
            positional.append(arg)
            i += 1

    if cmd in ("", "-h", "--help", "help"):
        usage()
        return 0
    if cmd == "up":
        return cmd_up()
    if cmd == "down":
        return cmd_down()
    if cmd == "stop":
        return cmd_stop(positional)
    if cmd == "status":
        return cmd_status()
    if cmd == "seed":
        return cmd_seed()
    if cmd == "env":
        return cmd_env()
    if cmd == "logs":
        return cmd_logs(positional)
    if cmd == "unlock":
        return cmd_unlock()
    err(f"未知子命令：{cmd}")
    usage_stderr()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

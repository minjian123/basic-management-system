#!/usr/bin/env python3
"""本机裸跑「全套」后端：SQLite 本地库 + 内存缓存（无需 Docker / 无需 mjbk），供**本机开发与真机回归**。

为什么这样起（口径）：
- 开发态配置（`backend/config.dev.toml`）本就是 SQLite + 内存缓存 + 字典/参数走 SQL，**不依赖容器**；
- 服务间调用基址模板是 `http://{service}:8000`，故本机给每个服务一个 loopback 别名
  （`127.0.0.2 tenant` …）+ **统一 8000 端口**，与容器形态同形；别名到地址的映射由本脚本按声明
  注入 `[service_client].endpoints`（**不再需要写系统 hosts**，也就不再需要管理员权限）；
- `require_auth` 支持「本地 Bearer 用户令牌」路径、`[edge].require_gateway_identity = false`
  ⇒ 不经网关直连服务可行；前端由 `VITE_LOCAL_API`（见 `env` 子命令）按服务就近代理。

**服务清单来自各仓自持声明**（固定路径 `deploy/local_stack.toml`）：脚本扫「本仓 + 工作区平级仓」
装载——平台仓不出现产品仓字面，接新产品 = 产品仓加一份声明、脚本零改动。缺省起**全部已声明服务**，
`--services` 只作过滤（调试单服务 / 腾位用）。

用法: python3 本地全套.py <up|down|stop|status|seed|env|logs|unlock> [选项]
（Linux 同名 .sh / Windows 同名 .bat 均为转调本文件的薄包装；逻辑只维护在这里。）
  up                起服务（幂等；已在跑则跳过）+ 自愈开发密钥，并等待健康；
                    收尾自动确保 `.env.local` 的 `VITE_LOCAL_API`（同 env 子命令，缺则补、旧则按声明更新）
  down              停本脚本起的服务（仅按 pid 文件；`--force` 才连带清理 IDE 起的同名进程）
  stop <服务名...>  只停指定服务（其余保持纳管）——供「用 debugpy 调试某服务」时腾出该服务
  status            进程与 /healthz、/readyz 一览（含服务所属仓）
  seed              幂等种子：租户注册库 + 菜单元数据 + 建号（缺省账号 admin；口令随机生成并打印一次）
  env               确保 `frontend/apps/desktop/.env.local` 含 `VITE_LOCAL_API` 本地服务映射（up 已自动调用）；
                    并按声明为每个服务写 IDE 调试环境文件 `<仓>/deploy/.dev-env.<服务键>.local`
                    （供 IDE 启动项 `envFile` 注入——产品进程断点调试走这条路，见平台口径）
  logs [服务名]     打印日志尾部（缺省全部服务；追看用 tail -f）
  unlock [账号]     解锁账号：清 `sys_user.failed_count` / `locked_until` + 删 Redis 登录失败计数键
                    （登录阈值 5 次 / 锁 15 分钟：**验验证码请用不存在的账号试错口令**，
                     别拿真账号连试错密码，否则真账号被锁 20003「账号已锁定」）

选项:
  --services "a b c"   只起 / 只操作这些服务（缺省 = 全部已声明服务；键见 status）
  --redis URL          Redis 连接串（缺省远端开发机 DB5 的 redis://<开发机>:6379/5）
  --reset-db           起服务前把各服务声明的库目录（`database/<仓>`）里的 `*.db` 备份移走
                       （库结构 / 表归属变更后必须，否则 catalog 校验失败）
  --username NAME      建号账号（缺省 admin）
  --password PASS      建号口令（缺省**随机生成并仅打印一次**）
  --reset-password     建号时重置既有账号口令
  --force              down 时连带清理本机全部本栈 python 进程

账号: `seed` 缺省建 `admin`，口令缺省随机生成并**仅打印一次**——**凭据只登记在
      《bms文档/用户文档/本地资源.md》「BMS 应用账号」节（凭据不入库、不写入其他文档，见《AI开发规范》）**；
      起栈后若登录 401，先看是否漏跑 seed。

状态目录: ${BMS_LOCAL_STATE_DIR:-/tmp/bms-local-stack}（pid 与日志；Windows 缺省为 %TEMP%\\bms-local-stack）
退出码: 0 = 成功；1 = 失败（含健康等待超时）；2 = 参数 / 声明错误

平台口径（Linux / Windows 双平台）：
- 解释器：各服务取自己声明的后端工程根下 `.venv`（Linux `bin/python`、Windows `Scripts/python.exe`）；
- loopback 别名：两平台对 127.0.0.0/8 整段可绑定，无需额外加地址；**无需 hosts 别名**
  （寻址覆盖经 `[service_client].endpoints` 注入；`up` 只在缺别名时提示，不阻断）；
- 后台进程：Linux 用新会话（等价 nohup），Windows 用分离进程；停止口径同为 TERM → 5s → 强杀 → 2s；
- 子进程枚举：Linux 用 /proc；Windows 服务本体为单进程，不枚举子进程。
- IDE 调试：脚本起的都是**后台进程（不带调试器）**；断点调试须「先 stop 该服务，再由 IDE 启动项起它」。
  平台服务由 `backend/ops/dev_run.py` 注入环境后 runpy 进服务入口；**产品服务**的代码在产品仓，
  bms 侧脚本无法跨仓 runpy，故改由 IDE 原生 `module` 启动 + `envFile` 注入——环境文件即本脚本
  `env` 子命令生成的 `<仓>/deploy/.dev-env.<服务键>.local`（与本脚本起进程的口径完全同源）。
"""

import contextlib
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request

IS_WINDOWS = os.name == "nt"
PREFIX = "[本地全套]"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
WORKSPACE_ROOT = os.path.dirname(ROOT)
BACKEND = os.path.join(ROOT, "backend")
DECLARATION_REL = os.path.join("deploy", "local_stack.toml")
"""各仓自持的本机运行声明（固定路径；脚本扫本仓 + 工作区平级仓装载）。"""
FRONTEND_ENV = os.path.join(ROOT, "frontend", "apps", "desktop", ".env.local")
STATE_DIR = os.environ.get("BMS_LOCAL_STATE_DIR") or (
    os.path.join(tempfile.gettempdir(), "bms-local-stack") if IS_WINDOWS else "/tmp/bms-local-stack"
)
KEYS_FILE = os.path.join(ROOT, "deploy", ".dev-keys.local")
"""开发密钥文件（${ROOT}/deploy/.dev-keys.local）。

落仓级 deploy/、不落 backend/ 根：后端根只放受跟踪的工程文件，本地产物 / 凭据一律进
deploy/、.cache/ 或工作区 tmp/（2026-10-26 拍板）。本机全套生成一次，各服务子进程继承。
"""
PY = (
    os.path.join(BACKEND, ".venv", "Scripts", "python.exe")
    if IS_WINDOWS
    else os.path.join(BACKEND, ".venv", "bin", "python")
)
"""平台后端解释器（种子 / 解锁等运维步骤走它；服务进程各用自己的声明解释器）。"""
PORT = os.environ.get("BMS_LOCAL_PORT") or "8000"
# Windows 进程创建标志：脱离 IDE 任务所在的 Job Object（否则关任务终端 / 重启 IDE 会连带强杀服务）
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

SERVICES = ""
"""`--services` 过滤（空串 = 全部已声明服务）。"""
REDIS_URL = os.environ.get("BMS_LOCAL_REDIS") or "redis://192.168.0.107:6379/5"
RESET_DB = 0
USERNAME = "admin"
PASSWORD = ""
RESET_PASSWORD = 0
FORCE = 0
try:
    HEALTH_TIMEOUT = int(os.environ.get("BMS_LOCAL_HEALTH_TIMEOUT") or "60")
except ValueError:
    HEALTH_TIMEOUT = 60

_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
"""服务键形态（小写字母开头，允许数字 / 下划线 / 连字符；与网关 upstream / 清单 module_key 同名）。"""
_MODULE_TOKEN_RE = re.compile(r"(?:^|\s)-m\s+(\S+)")
"""命令行里 `-m <模块>` 的模块名（PID 复用校验与残留进程识别用）。"""


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


# ---- 声明装载 ----


class SpecError(Exception):
    """声明装载失败（声明缺失 / 字段非法 / 服务键冲突）。"""


class ServiceSpec:
    """一个服务的本机运行规格（由各仓 `deploy/local_stack.toml` 装载）。

    只承载「本机怎么跑」的开发事实（模块 / venv 基准 / 回环别名 / 库目录 / 前端前缀），
    不含部署契约；缺省值在 `_build_spec` 收口，声明里写最小必要项即可。
    """

    def __init__(
        self,
        repo_root,
        declaration,
        key,
        module,
        backend,
        host,
        port,
        db_dir,
        frontend_prefix,
        extra_env,
        after,
    ):
        self.repo_root = repo_root
        self.declaration = declaration
        self.key = key
        self.module = module
        self.backend = backend
        self.host = host
        self.port = port
        self.db_dir = db_dir
        self.frontend_prefix = frontend_prefix
        self.extra_env = extra_env
        self.after = after
        # 启动前置服务键（须先健康、本服务才能起：如产品进程启动期要向平台上报声明）

    @property
    def repo_name(self):
        """所属仓目录名（status 展示 / 排障定位用）。"""
        return os.path.basename(self.repo_root)

    @property
    def python(self):
        """服务解释器（各仓自己的后端 venv）。"""
        if IS_WINDOWS:
            return os.path.join(self.backend, ".venv", "Scripts", "python.exe")
        return os.path.join(self.backend, ".venv", "bin", "python")

    @property
    def address(self):
        """监听地址（`别名:端口`）。"""
        return f"{self.host}:{self.port}"

    def problems(self):
        """启动前置检查（依赖是否就位）；返回问题清单（空 = 可起）。"""
        found = []
        if not os.path.isdir(self.backend):
            found.append(f"后端工程根不存在：{self.backend}")
        if not os.path.isfile(self.python):
            found.append(f"缺后端虚拟环境：{self.python}（先在该仓跑 uv sync）")
        return found


def _text(raw, field, declaration):
    """取声明里的必填非空字符串字段。"""
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"缺字段 / 值非法：{field}（{declaration}）")
    return value.strip()


def _build_spec(repo_root, declaration, raw):
    """把一条 `[[services]]` 归一为 `ServiceSpec`（缺省值在此收口，非法即抛 `SpecError`）。"""
    if not isinstance(raw, dict):
        raise SpecError(f"[[services]] 条目必须是表（{declaration}）")
    key = _text(raw, "key", declaration)
    if not _KEY_RE.match(key):
        raise SpecError(f"服务键形态非法：{key!r}（小写字母开头，允许数字 / 下划线 / 连字符）")
    module = _text(raw, "module", declaration)
    backend = os.path.normpath(os.path.join(repo_root, _text(raw, "backend", declaration)))
    host = _text(raw, "host", declaration)
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise SpecError(f"host 不是合法 IP：{host!r}（{exc}）") from exc
    if not address.is_loopback:
        raise SpecError(f"host 须为回环地址（127.0.0.0/8）：{host!r}")
    port = str(raw.get("port", PORT)).strip()
    if not port.isdigit():
        raise SpecError(f"port 须为数字：{raw.get('port')!r}")
    db_dir = raw.get("db_dir")
    if db_dir is not None and (not isinstance(db_dir, str) or not db_dir.strip()):
        raise SpecError(f"db_dir 须为非空相对路径：{db_dir!r}")
    resolved_db = os.path.normpath(os.path.join(repo_root, db_dir.strip())) if db_dir else ""
    prefix = raw.get("frontend_prefix") or key
    if not isinstance(prefix, str) or not prefix.strip():
        raise SpecError(f"frontend_prefix 须为非空字符串：{prefix!r}")
    extra_env = raw.get("env") or {}
    if not isinstance(extra_env, dict):
        raise SpecError("env 须为表（键 = 环境变量名，值 = 字符串）")
    env_pairs = {}
    for env_key, env_value in extra_env.items():
        if not isinstance(env_key, str) or not env_key.strip() or not isinstance(env_value, str):
            raise SpecError(f"env 条目须为「字符串键 → 字符串值」：{env_key!r}")
        env_pairs[env_key.strip()] = env_value
    after = raw.get("after") or []
    if not isinstance(after, list) or not all(isinstance(item, str) and item.strip() for item in after):
        raise SpecError(f"after 须为服务键字符串列表：{after!r}")
    return ServiceSpec(
        repo_root=repo_root,
        declaration=declaration,
        key=key,
        module=module,
        backend=backend,
        host=host,
        port=port,
        db_dir=resolved_db,
        frontend_prefix=prefix.strip(),
        extra_env=env_pairs,
        after=[item.strip() for item in after],
    )


def declaration_paths():
    """待装载的声明路径：本仓固定路径 + 工作区平级仓的同名固定路径（去重、保序）。"""
    paths = []
    own = os.path.join(ROOT, DECLARATION_REL)
    if os.path.isfile(own):
        paths.append(own)
    try:
        entries = sorted(os.listdir(WORKSPACE_ROOT))
    except OSError:
        entries = []
    for entry in entries:
        candidate = os.path.join(WORKSPACE_ROOT, entry, DECLARATION_REL)
        if os.path.isfile(candidate) and candidate not in paths:
            paths.append(candidate)
    return paths


def load_specs():
    """装载全部声明（本仓优先，平级仓按目录名序）；任何非法项汇总后一次性报错。"""
    paths = declaration_paths()
    if not paths:
        raise SpecError(f"未找到本机运行声明（各仓固定路径 {DECLARATION_REL}）")
    specs = {}
    problems = []
    for path in paths:
        repo_root = os.path.dirname(os.path.dirname(path))
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            problems.append(f"{path}：读取失败（{exc}）")
            continue
        entries = data.get("services")
        if not isinstance(entries, list) or not entries:
            problems.append(f"{path}：缺少 [[services]] 段")
            continue
        for raw in entries:
            try:
                spec = _build_spec(repo_root, path, raw)
            except SpecError as exc:
                problems.append(f"{path}：{exc}")
                continue
            if spec.key in specs:
                problems.append(f"{path}：服务键重复 {spec.key}（已被 {specs[spec.key].declaration} 声明）")
                continue
            specs[spec.key] = spec
    for spec in specs.values():
        unknown = [dep for dep in spec.after if dep not in specs]
        if unknown:
            problems.append(f"{spec.declaration}：{spec.key} 的 after 指向未声明的服务：{' '.join(unknown)}")
    if problems:
        raise SpecError("；".join(problems))
    return specs


def select_specs():
    """按 `--services` 过滤装载结果（空 = 全部；含未声明键即报错）。"""
    specs = load_specs()
    wanted = SERVICES.split()
    if not wanted:
        return list(specs.values())
    unknown = [name for name in wanted if name not in specs]
    if unknown:
        raise SpecError(f"--services 里有未声明的服务：{' '.join(unknown)}（已声明：{' '.join(specs)}）")
    return [specs[name] for name in wanted]


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


def module_of(cmdline):
    """取命令行里的 `-m <模块>`（无则空串；路径分隔符统一后再匹配）。"""
    match = _MODULE_TOKEN_RE.search(cmdline.replace("\\", "/"))
    return match.group(1) if match else ""


def is_service_pid(module, pid, procs=None):
    """pid 存活**且**确实是本服务进程（命令行 `-m <模块>` 命中）。

    PID 会被系统复用：服务退出后同号被别的程序（如 IDE）拿走，旧逻辑只看 `pid_alive`
    就当成「在跑」⇒ up 跳过、status 假在跑、down 误杀无关进程。命令行取不到时降级为
    「存活即算」（保持旧行为，避免权限 / CIM 异常导致全部判死）。
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
    return module_of(cmdline) == module


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


def ensure_hosts(specs):
    """尽力补 hosts 别名（**不再必需**：寻址覆盖已由 endpoints 注入）；失败只提示不阻断。"""
    missing = [(spec.key, spec.host) for spec in specs if not _resolves(spec.key)]
    if not missing:
        return
    block = "\n".join([f"{host} {key}" for key, host in missing])
    if IS_WINDOWS:
        path = _hosts_path()
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n# BMS 本地多服务寻址（本地全套.py；与服务基址模板 http://{service}:8000 同形）\n")
                fh.write(block + "\n")
            log(f"已写入 hosts 别名（{path}）：{' '.join(key for key, _ in missing)}")
        except OSError:
            log("提示：hosts 别名未写入（需管理员权限）——本机全套已按声明注入端点覆盖，不影响联调；")
            print(block, file=sys.stderr)
        return
    result = subprocess.run(
        ["sudo", "-n", "tee", "-a", "/etc/hosts"], input=block + "\n", text=True, capture_output=True
    )
    if result.returncode == 0:
        log(f"已写入 /etc/hosts：{' '.join(key for key, _ in missing)}")
    else:
        log("提示：hosts 别名未写入（需 sudo）——本机全套已按声明注入端点覆盖，不影响联调；")
        print(block, file=sys.stderr)


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


def py_ok():
    """平台后端解释器是否就位（种子 / 解锁步骤用）。"""
    if not os.path.isfile(PY):
        return False
    return True if IS_WINDOWS else os.access(PY, os.X_OK)


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


def _parse_env_file(path):
    """解析环境文件（`export KEY='VALUE'` / `KEY=VALUE`，值可带成对引号）。

    Args:
        path: 环境文件路径（开发密钥文件 / IDE 调试环境文件同形态）。

    Returns:
        (键值对列表, 无法解析的行列表)；文件不可读时键值对为 None。
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None, []
    pairs = []
    bad = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            bad.append(line)
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        pairs.append((key.strip(), value))
    return pairs, bad


def _quote_env(value):
    """把环境变量值写成单引号形态（IDE 的 `envFile` 与 shell 都按字面取用）。"""
    return "'" + value + "'"


def load_keys_env():
    """等价 shell 的 `. "$KEYS_FILE"`：解析 `export KEY='VALUE'` 行并注入环境变量。"""
    pairs, bad = _parse_env_file(KEYS_FILE)
    if pairs is None:
        err(f"开发密钥文件不可读：{KEYS_FILE}")
        return 1
    for line in bad:
        err(f"密钥文件存在无法解析的行，已跳过：{line[:60]}")
    for key, value in pairs:
        os.environ[key] = value
    return 0


def reset_db(specs):
    """按声明的库目录把本地 `*.db` 备份移走（同目录下 `.db-backup-<时间戳>`）。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dirs = []
    for spec in specs:
        if spec.db_dir and spec.db_dir not in dirs:
            dirs.append(spec.db_dir)
    for db_dir in dirs:
        if not os.path.isdir(db_dir):
            log(f"--reset-db：库目录不存在，跳过 {db_dir}")
            continue
        backup = os.path.join(db_dir, f".db-backup-{stamp}")
        os.makedirs(backup, exist_ok=True)
        moved = 0
        for name in sorted(os.listdir(db_dir)):
            candidate = os.path.join(db_dir, name)
            if os.path.isfile(candidate) and name.endswith(".db"):
                shutil.move(candidate, os.path.join(backup, name))
                moved += 1
        log(f"--reset-db：{db_dir} 移走 {moved} 个本地库文件 → {backup}（服务启动会按当前表结构重建）")


# ---- 起停 ----

LOG_ROTATE_BYTES = 5 * 1024 * 1024


def open_log_append(log_path, svc):
    """追加打开服务日志（不再 truncate，历史留作排障证据）：先写启动分隔行；超阈值归档为 .1。"""
    with contextlib.suppress(OSError):
        if os.path.getsize(log_path) > LOG_ROTATE_BYTES:
            os.replace(log_path, log_path + ".1")
    with contextlib.suppress(OSError):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "ab")  # noqa: SIM115 —— 句柄交给 Popen 持有至进程结束，不能在此 with 关闭
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    logf.write(f"\n===== {svc} 启动 @ {stamp}（本地全套.py）=====\n".encode())
    logf.flush()
    return logf


def endpoints_payload(specs):
    """按声明生成 `[service_client].endpoints`（服务键 → 基址；注入每个服务子进程）。

    这就是「不必写系统 hosts」的落地：服务间调用与能力寻址都经基座端点覆盖取基址；
    容器部署不注入（按 Compose DNS 模板派生），两形态行为同构。
    """
    return json.dumps({spec.key: f"http://{spec.address}" for spec in specs})


DEBUG_ENV_TEMPLATE = ".dev-env.{key}.local"
"""IDE 调试环境文件（`<仓>/deploy/.dev-env.<服务键>.local`；`env` 子命令生成，`*.local` 已忽略）。"""


def write_debug_envs(specs, endpoints):
    """为每个服务写一份 IDE 调试环境文件（`KEY=VALUE`，供 launch.json 的 `envFile` 注入）。

    为什么需要：产品进程的代码在**产品仓**，bms 侧 `ops/dev_run.py` 无法跨仓 runpy 进产品服务；
    改由 IDE 原生 `module` 启动 + `envFile` 注入与本脚本**同一份**本机口径（回环别名 / 端口 /
    端点覆盖 / 开发密钥），断点、变量、调用栈与 `python -m <模块>` 完全一致。
    文件是「声明 + 密钥」的确定性产物，每次 `env`（`up` 收尾自动调用）重写，勿手改。

    Args:
        specs: 本次纳入的服务规格。
        endpoints: `endpoints_payload()` 的结果（端点覆盖 JSON）。

    Returns:
        写出的环境文件份数。
    """
    keys, _ = _parse_env_file(KEYS_FILE)
    if keys is None:
        err(f"开发密钥文件不可读，调试环境文件将不含密钥：{KEYS_FILE}")
        keys = []
    written = 0
    for spec in specs:
        deploy_dir = os.path.join(spec.repo_root, "deploy")
        try:
            os.makedirs(deploy_dir, exist_ok=True)
        except OSError as exc:
            err(f"调试环境文件目录不可写，跳过 {spec.key}：{deploy_dir}（{exc}）")
            continue
        pairs = [
            ("BMS_SERVER__HOST", spec.host),
            ("BMS_SERVER__PORT", spec.port),
            ("BMS_REDIS__URL", REDIS_URL),
            ("BMS_SERVICE_CLIENT__ENDPOINTS", endpoints),
            ("PYTHONUNBUFFERED", "1"),
        ]
        pairs.extend(sorted(spec.extra_env.items()))
        pairs.extend(keys)
        lines = [
            "# IDE 调试环境（由 scripts/tools/dev/本地全套.py 生成，勿手改；*.local 不入库）",
            f"# 服务 {spec.key}（仓 {spec.repo_name}）· {spec.address} · 模块 {spec.module}",
        ]
        lines.extend(f"{key}={_quote_env(value)}" for key, value in pairs)
        path = os.path.join(deploy_dir, DEBUG_ENV_TEMPLATE.format(key=spec.key))
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        written += 1
    return written


def start_one(spec, endpoints, procs=None):
    pid_file = os.path.join(STATE_DIR, f"{spec.key}.pid")
    pid = read_pid(pid_file) if os.path.isfile(pid_file) else 0
    if pid and is_service_pid(spec.module, pid, procs):
        log(f"{spec.key} 已在跑（pid {pid}），跳过")
        return
    if pid and pid_alive(pid):
        # PID 复用：旧服务退出后同号被别的程序（如 IDE）拿走，绝不能当「在跑」跳过
        log(f"{spec.key} 旧 pid {pid} 已被其他进程复用（不是本服务）——清残留 pid 文件后重新拉起")
    if pid:
        with contextlib.suppress(OSError):
            os.remove(pid_file)
    # 已在监听（例如 IDE 调试起的）→ 接管跳过，避免二次绑定端口失败
    if http_code(f"http://{spec.address}/healthz") == "200":
        log(f"{spec.key} 已在监听 {spec.address}（非本脚本启动；未纳管 pid），跳过")
        return
    # 后台起 python（**不套中间进程**）——否则记到的 pid 是包装进程而非服务本体，
    # 停服务会打空、留下孤儿进程。cwd / 解释器 / 密钥 / 寻址覆盖一律按该服务自己的声明给。
    log_path = os.path.join(STATE_DIR, f"{spec.key}.log")
    env = dict(os.environ)
    env.update(spec.extra_env)
    env.update(
        {
            "BMS_SERVER__HOST": spec.host,
            "BMS_SERVER__PORT": spec.port,
            "BMS_REDIS__URL": REDIS_URL,
            "BMS_SERVICE_CLIENT__ENDPOINTS": endpoints,
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
    with open_log_append(log_path, spec.key) as logf:
        proc = None
        for flags in candidates:
            try:
                proc = subprocess.Popen(
                    [spec.python, "-m", spec.module],
                    cwd=spec.backend,
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
                    log(f"{spec.key} 无法脱离 IDE 任务容器（{exc}）——退化为普通后台进程：关 IDE 可能被连带停止")
                    continue
                raise
    with open(pid_file, "w", encoding="utf-8") as fh:
        fh.write(str(proc.pid) + "\n")
    log(f"{spec.key} 启动中：{spec.address}（pid {proc.pid}，仓 {spec.repo_name}，日志 {log_path}）")


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


def wait_health(specs):
    """等待这批服务健康：单一总超时（不逐服务串行耗满），且**进程已退出 / pid 被复用即立刻报错 + 打印日志尾部**。"""
    deadline = time.time() + HEALTH_TIMEOUT
    procs = proc_cmdline_map()
    while True:
        pending = []
        for spec in specs:
            if http_code(f"http://{spec.address}/healthz") == "200":
                continue
            pid_file = os.path.join(STATE_DIR, f"{spec.key}.pid")
            pid = read_pid(pid_file) if os.path.isfile(pid_file) else 0
            if pid and not pid_alive(pid):
                err(f"{spec.key} 进程已退出（pid {pid}）——日志尾部：")
                tail_log(os.path.join(STATE_DIR, f"{spec.key}.log"), 20, to_stderr=True)
                return 1
            # 命令行明确采集到但与本服务不符 → PID 已被复用（别傻等满超时）
            if pid and procs and pid in procs and module_of(procs[pid]) != spec.module:
                err(f"{spec.key} 的 pid {pid} 已被其他进程复用（不是本服务，端口无响应）——日志尾部：")
                tail_log(os.path.join(STATE_DIR, f"{spec.key}.log"), 20, to_stderr=True)
                return 1
            pending.append(spec.key)
        if not pending:
            log(f"健康就绪（healthz 200）：{' '.join(spec.key for spec in specs)}")
            return 0
        if time.time() >= deadline:
            err(f"健康等待超时（{HEALTH_TIMEOUT}s），未就绪：{' '.join(pending)} —— 看 {STATE_DIR}/<服务>.log")
            return 1
        time.sleep(1)


# ---- 子命令 ----


def _load_or_report():
    """装载声明并按 `--services` 过滤；失败时打印原因并返回 (None, 退出码)。"""
    try:
        return select_specs(), 0
    except SpecError as exc:
        err(f"装载本机运行声明失败：{exc}")
        return None, 2


def _start_in_order(specs, endpoints, procs):
    """按声明的前置关系分批起：前一批**健康后**再起后一批。

    为什么需要：产品进程启动期要向平台上报声明并拉快照（`bootstrap_declarations`），
    平台没起来就报「服务不可用：platform（transport）」拒启——并发起全部服务必然踩这个竞态。
    前置关系由各仓**自己**在声明里写（`after = [...]`），脚本不猜。
    """
    selected = {spec.key for spec in specs}
    for spec in specs:
        missing = [dep for dep in spec.after if dep not in selected]
        if missing:
            log(f"提示：{spec.key} 的前置服务 {' '.join(missing)} 未在本次选择内，跳过等待")
    pending = list(specs)
    started = []
    while pending:
        ready = [spec for spec in pending if all(dep in started for dep in spec.after if dep in selected)]
        if not ready:
            err(f"启动顺序无法推进（循环依赖）：{' '.join(spec.key for spec in pending)}")
            return 1
        for spec in ready:
            start_one(spec, endpoints, procs)
        if wait_health(ready):
            return 1
        started.extend(spec.key for spec in ready)
        pending = [spec for spec in pending if spec not in ready]
    return 0


def cmd_up():
    ensure_dirs()
    specs, rc = _load_or_report()
    if specs is None:
        return rc
    problems = [f"{spec.key}：{msg}" for spec in specs for msg in spec.problems()]
    if problems:
        err("启动前置检查未通过：")
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if ensure_keys():
        return 1
    ensure_hosts(specs)
    if RESET_DB:
        reset_db(specs)
    if load_keys_env():
        return 1
    endpoints = endpoints_payload(specs)
    procs = proc_cmdline_map()
    if _start_in_order(specs, endpoints, procs):
        return 1
    # 收尾自动补齐前端 `.env.local`：缺 `VITE_LOCAL_API` 时前端 `/api` 会回落 VITE_API_PROXY 网关
    # （本机通常无该网关）⇒ 登录 502；此处按声明幂等维护（缺则补、旧则更新）。
    if cmd_env():
        return 1
    log("全套已就绪；前端请在 IDE 跑「前端：宿主 dev」")
    return 0


def find_unmanaged_backend_pids(specs):
    """本栈但未被纳管的后端进程（IDE 调试起的同款服务）。"""
    modules = {spec.module for spec in specs.values()}
    procs = proc_cmdline_map()
    found = []
    for pid, cmdline in procs.items():
        module = module_of(cmdline)
        if not module:
            continue
        if module.startswith("bms_") or module in modules:
            found.append(pid)
    return sorted(found)


def cmd_down():
    ensure_dirs()
    try:
        specs = load_specs()
    except SpecError as exc:
        err(f"装载本机运行声明失败（改为只按残留 pid 文件清理）：{exc}")
        specs = {}
    rc = 0
    for spec in specs.values():
        pid_file = os.path.join(STATE_DIR, f"{spec.key}.pid")
        if not os.path.isfile(pid_file):
            continue
        pid = read_pid(pid_file)
        if pid and is_service_pid(spec.module, pid):
            if stop_pid(spec.key, pid):
                rc = 1
        elif pid and pid_alive(pid):
            err(f"{spec.key} 的 pid {pid} 已被其他进程复用——只清残留 pid 文件，不动该进程（避免误杀）")
        else:
            log(f"{spec.key} 已不在跑（残留 pid 文件，清理）")
        with contextlib.suppress(OSError):
            os.remove(pid_file)
    # 声明里已不存在的服务（如产品仓移出工作区）留下的 pid 文件：死进程清文件、活进程交人工
    for name in sorted(os.listdir(STATE_DIR)):
        if not name.endswith(".pid"):
            continue
        svc = name[: -len(".pid")]
        if svc in specs:
            continue
        pid_file = os.path.join(STATE_DIR, name)
        pid = read_pid(pid_file)
        if pid and pid_alive(pid):
            err(f"{svc} 无声明但仍有进程（pid {pid}）——请人工确认后处理；本次不动它")
            continue
        log(f"{svc} 无声明且已不在跑（清理残留 pid 文件）")
        with contextlib.suppress(OSError):
            os.remove(pid_file)
    rest = find_unmanaged_backend_pids(specs)
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
        err("用法：本地全套.py stop <服务名...>（如 stop identity / stop mdm）")
        return 2
    specs, rc = _load_or_report()
    if specs is None:
        return rc
    by_key = {spec.key: spec for spec in specs}
    stopped = 0
    for svc in names:
        if svc.startswith("bms_"):
            svc = svc[len("bms_") :]
        spec = by_key.get(svc)
        if spec is None:
            err(f"未知服务：{svc}（已声明：{' '.join(by_key)}）")
            rc = 2
            continue
        pid_file = os.path.join(STATE_DIR, f"{spec.key}.pid")
        if not os.path.isfile(pid_file):
            err(f"{spec.key} 未被本脚本纳管（无 pid 文件）——若它由 IDE 调试启动，请在 IDE 里停止")
            rc = 1
            continue
        pid = read_pid(pid_file)
        if pid and is_service_pid(spec.module, pid):
            if stop_pid(spec.key, pid):
                rc = 1
        elif pid and pid_alive(pid):
            err(f"{spec.key} 的 pid {pid} 已被其他进程复用——只清残留 pid 文件，不动该进程（避免误杀）")
        else:
            log(f"{spec.key} 已不在跑（清理残留 pid 文件）")
        with contextlib.suppress(OSError):
            os.remove(pid_file)
        stopped += 1
    if stopped > 0:
        log(f"已停 {stopped} 个服务（其余仍纳管）；调试完用 up 一键补回")
    return rc


def cmd_status():
    ensure_dirs()
    specs, rc = _load_or_report()
    if specs is None:
        return rc
    procs = proc_cmdline_map()
    print(f"{'服务':<10} {'仓':<8} {'地址':<16} {'PID':<8} {'healthz':<9} readyz")
    stale = []
    for spec in specs:
        pid_file = os.path.join(STATE_DIR, f"{spec.key}.pid")
        pid = read_pid(pid_file) if os.path.isfile(pid_file) else 0
        if pid and is_service_pid(spec.module, pid, procs):
            shown = str(pid)
        else:
            shown = "-"
            stale.append(spec.key)
        health = http_code(f"http://{spec.address}/healthz") or "000"
        ready = http_code(f"http://{spec.address}/readyz") or "000"
        print(f"{spec.key:<10} {spec.repo_name:<8} {spec.address:<16} {shown:<8} {health:<9} {ready}")
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
    # 产品（如组织主数据）的种子按清单 `[[seeds]]` 声明由平台种子编排装载，无需在此另跑。
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


def _ensure_frontend_env(specs):
    """确保前端 `.env.local` 的 `VITE_LOCAL_API` 与声明一致（缺则补、旧则更新）。

    Args:
        specs: 本次纳入的服务规格。

    Returns:
        0 = 已就绪；1 = 写入失败。
    """
    mapping = ",".join(f"{spec.frontend_prefix}={spec.address}" for spec in specs)
    line = f"VITE_LOCAL_API={mapping}"
    if os.path.isfile(FRONTEND_ENV):
        with open(FRONTEND_ENV, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        for index, existing in enumerate(lines):
            if not existing.startswith("VITE_LOCAL_API="):
                continue
            if existing.strip() == line:
                log(f"已存在 VITE_LOCAL_API：{line}")
                return 0
            lines[index] = line + "\n"
            with open(FRONTEND_ENV, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            log(f"已更新 {FRONTEND_ENV}：{line}（服务清单来自各仓声明；重启「前端：宿主 dev」生效）")
            return 0
    try:
        os.makedirs(os.path.dirname(FRONTEND_ENV), exist_ok=True)
        with open(FRONTEND_ENV, "a", encoding="utf-8") as fh:
            fh.write("\n")
            fh.write(
                "# 本机裸跑后端时的服务直连映射（由 scripts/tools/dev/本地全套.py env 按各仓 "
                "deploy/local_stack.toml 维护；未列出的服务走 VITE_API_PROXY）\n"
            )
            fh.write(line + "\n")
    except OSError as exc:
        err(f"前端环境文件写入失败：{FRONTEND_ENV}（{exc}）")
        return 1
    log(f"已写入 {FRONTEND_ENV}：{line}")
    return 0


def cmd_env():
    """按声明维护前端服务映射 + 各服务的 IDE 调试环境文件。"""
    specs, rc = _load_or_report()
    if specs is None:
        return rc
    if _ensure_frontend_env(specs):
        return 1
    written = write_debug_envs(specs, endpoints_payload(specs))
    if written:
        log(
            f"已写 {written} 份 IDE 调试环境文件（<仓>/deploy/.dev-env.<服务键>.local）——"
            "IDE 启动项用 envFile 注入（产品进程断点调试走这条路）"
        )
    return 0


def cmd_logs(names):
    ensure_dirs()
    try:
        specs = load_specs()
    except SpecError as exc:
        err(f"装载本机运行声明失败：{exc}")
        return 2
    if names and names[0]:
        wanted = names[0].split()
        unknown = [name for name in wanted if name not in specs]
        if unknown:
            err(f"未知服务：{' '.join(unknown)}（已声明：{' '.join(specs)}）")
            return 2
        targets = wanted
    else:
        targets = list(specs)
    for svc in targets:
        print(f"===== {svc} =====")
        log_path = os.path.join(STATE_DIR, f"{svc}.log")
        if os.path.isfile(log_path):
            tail_log(log_path, 40)
        else:
            print(f"（无日志 {log_path}）")
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

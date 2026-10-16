#!/usr/bin/env python3
"""BMS 开发服务器每日备份总控（部署于 mjbk ~/deploy/backup/）。

组件：MySQL 全量、PostgreSQL 单库、达梦 DM8 dexp、GitLab、Kiwi TCMS 附件、百度网盘云同步
凭据：读 ~/deploy/.env 与 ~/.config/baidunetdisk/Cookies（官方客户端登录态）；不硬编码
落位：本地 /mnt/data/backup/<组件>/；云端 /apps/bms-backup/<日期>/（加密 .gpg）
用法：bash backup_daily.sh；cron 02:30 每日（亦可直接 python3 backup_daily.py，口径相同；
      与原 shell 版一致不接收参数，多余参数忽略）

单一实现：逻辑全在本文件；同目录 backup_daily.sh 仅为「转调本文件」的瘦包装（本脚本只跑
Linux 服务器，无 .bat 形态）。**部署时须把 backup_daily.py 与 backup_daily.sh 两个文件一起
拷贝**到 mjbk `~/deploy/backup/`（包装缺 .py 会直接报错退出）；触发由服务器侧 cron /
systemd 用户级 timer（bms-backup.timer，见《数据备份与恢复部署使用说明》）负责。

与原 shell 版（git 历史 backup_daily.sh；2026-10-16 起改本实现）的等价口径：
- 各组件成败沿用「产物文件非空」（`[ -s 产物 ]`）判定，不升级为数据完整性校验
  （改进项登记见《数据备份与恢复部署使用说明》第 4.2 节）；
- `docker ... | gzip > 产物` 管道用 subprocess + gzip 模块流式等价实现：生产命令退出码不参与
  判定（与原 shell 一致，成果只由产物是否非空决定），命令输出与报错一并追加进 cron.log；
- 组件顺序、STATUS 汇总行（`[时间] daily backup: <组件>:OK/FAIL ...`）与退出码规则不变：
  主组件（mysql / postgres / dameng / gitlab / kiwi）任一 FAIL → 退出 1；cloud FAIL 仅记录。
"""

import contextlib
import fnmatch
import glob
import gzip
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

BASE_DIR = "/mnt/data/backup"
ENV_FILE = os.path.join(os.path.expanduser("~"), "deploy", ".env")
KEEP_DAYS = 7
CLOUD_KEEP_DAYS = 30
DM_HOME = "/opt/dmdbms"

LOG_PATH = os.path.join(BASE_DIR, "cron.log")

# 运行时状态（main 中初始化）
STATUS = []
LOG = None
TS = ""
TODAY = ""


def configure_stdio():
    """输出统一 UTF-8（Windows 管道 / 重定向下同样稳妥）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def log_write(text):
    """向 cron.log 追加一行（等价 shell 的 `>>"$BASE_DIR/cron.log" 2>&1` 落点）。"""
    if LOG is None:
        return
    LOG.write((text if text.endswith("\n") else text + "\n").encode("utf-8", errors="replace"))
    LOG.flush()


def get_env(name):
    """读 $HOME/deploy/.env：等价 shell 的 `grep -E "^<name>=" | tail -n1 | cut -d= -f2-`。

    取文件内最后一个匹配行的「首个 = 之后全部内容」；文件不存在或无匹配时返回空串。
    """
    found = ""
    try:
        with open(ENV_FILE, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith(name + "="):
                    found = line.rstrip("\n")[len(name) + 1 :]
    except OSError:
        return ""
    return found


def run_step(name, func):
    """执行组件步骤：成功记 `<name>:OK`、失败记 `<name>:FAIL`（等价原 run_step）。

    与原 shell 同口径：步骤内任何异常 / 非零退出都只记 FAIL，不中断总控。
    """
    try:
        ok = bool(func())
    except Exception as exc:
        log_write(f"{name}: 步骤异常（{exc}）")
        ok = False
    STATUS.append(f"{name}:{'OK' if ok else 'FAIL'}")


def nonempty(path):
    """等价 shell 的 `[ -s 文件 ]`：存在且非空。"""
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def gzip_stream_to(out_path, cmd):
    """等价管道 `cmd | gzip > out_path`：流式压缩生产命令的 stdout，结果只看产物非空。

    与原 shell 一致：生产命令退出码不参与判定；命令无法启动（如可执行文件缺失）时按「空输入」
    处理——同样产出 gzip 空档文件，与 shell 管道 + `[ -s ]` 的历史口径一致。
    """
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=LOG)
    except OSError as exc:
        log_write(f"backup_daily: 无法执行 {cmd[0]}（{exc}）")
    with open(out_path, "wb") as target, gzip.GzipFile(fileobj=target, mode="wb") as gz:
        if proc is not None and proc.stdout is not None:
            for chunk in iter(lambda: proc.stdout.read(1 << 16), b""):
                gz.write(chunk)
            proc.stdout.close()
            proc.wait()
    return nonempty(out_path)


def dump_mysql():
    """MySQL 全量 dump（容器内 mysqldump，gzip 直出）。"""
    password = get_env("MYSQL_ROOT_PASSWORD")
    cmd = [
        "docker",
        "exec",
        "-e",
        f"MYSQL_PWD={password}",
        "bms-mysql",
        "mysqldump",
        "--user=root",
        "--single-transaction",
        "--all-databases",
        "--routines",
        "--triggers",
        "--events",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
    ]
    return gzip_stream_to(os.path.join(BASE_DIR, "mysql", f"all_{TS}.sql.gz"), cmd)


def dump_postgres():
    """单库 pg_dump（bms_dev）：恢复时可干净导入任意临时库，无 pg_dumpall 的角色冲突与 \\connect 直写问题。"""
    password = get_env("POSTGRES_PASSWORD")
    cmd = [
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={password}",
        "bms-postgres",
        "pg_dump",
        "--username=postgres",
        "--dbname=bms_dev",
    ]
    return gzip_stream_to(os.path.join(BASE_DIR, "postgres", f"bms_dev_{TS}.sql.gz"), cmd)


def dump_dameng():
    """达梦 DM8 全库 dexp 导出（产物 .dmp + .log 落 dameng 目录）。"""
    password = get_env("DM8_SYSDBA_PASSWORD")
    cmd = [
        os.path.join(DM_HOME, "bin", "dexp"),
        f"SYSDBA/{password}@localhost:5236",
        f"FILE=dexp_all_{TS}.dmp",
        f"LOG=dexp_all_{TS}.log",
        f"DIRECTORY={os.path.join(BASE_DIR, 'dameng')}",
        "FULL=Y",
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=LOG, check=False)  # 退出码不参与判定
    return nonempty(os.path.join(BASE_DIR, "dameng", f"dexp_all_{TS}.dmp"))


def backup_gitlab():
    """GitLab 数据包（容器内 gitlab-backup + docker cp）与配置打包（secrets/ssl/gitlab.rb 不在数据备份内）。"""
    # 1) 容器内 gitlab-backup（产物落挂载盘 /mnt/ssd2t/gitlab/data/backups/）
    try:
        subprocess.run(
            ["docker", "exec", "bms-gitlab", "gitlab-backup", "create"],
            stdout=subprocess.DEVNULL,
            stderr=LOG,
            check=True,
        )
    except subprocess.CalledProcessError:
        return False
    time.sleep(2)
    result = subprocess.run(
        [
            "docker",
            "exec",
            "bms-gitlab",
            "bash",
            "-c",
            "ls -t /var/opt/gitlab/backups/*_gitlab_backup.tar 2>/dev/null | head -1",
        ],
        stdout=subprocess.PIPE,
        stderr=LOG,
        check=False,
    )
    latest = result.stdout.decode("utf-8", "replace").rstrip("\n")  # $(...) 仅去尾部换行
    if not latest:
        return False
    fname = os.path.basename(latest)
    try:
        subprocess.run(
            ["docker", "cp", f"bms-gitlab:{latest}", os.path.join(BASE_DIR, "gitlab", fname)],
            stdout=LOG,
            stderr=LOG,
            check=True,
        )
    except subprocess.CalledProcessError:
        return False
    subprocess.run(
        ["docker", "exec", "bms-gitlab", "rm", "-f", latest], stdout=subprocess.DEVNULL, stderr=LOG, check=False
    )
    # 2) 配置备份（secrets/ssl/gitlab.rb 不在数据备份内）
    config_tar = os.path.join(BASE_DIR, "gitlab", f"gitlab-config_{TS}.tar.gz")
    subprocess.run(["tar", "czf", config_tar, "-C", "/mnt/ssd2t/gitlab", "config"], stdout=LOG, stderr=LOG, check=False)
    return nonempty(os.path.join(BASE_DIR, "gitlab", fname)) and nonempty(config_tar)


def backup_kiwi_uploads():
    """Kiwi TCMS 附件卷（compose_kiwi-uploads -> 容器 /Kiwi/uploads）：测试用例附件等文件数据，不在数据库内。"""
    kiwi_dir = os.path.join(BASE_DIR, "kiwi")
    os.makedirs(kiwi_dir, exist_ok=True)
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--volumes-from",
            "bms-kiwi",
            "-v",
            f"{kiwi_dir}:/backup",
            "alpine:latest",
            "tar",
            "czf",
            f"/backup/kiwi-uploads_{TS}.tar.gz",
            "-C",
            "/Kiwi/uploads",
            ".",
        ],
        stdout=LOG,
        stderr=LOG,
        check=False,
    )
    return nonempty(os.path.join(kiwi_dir, f"kiwi-uploads_{TS}.tar.gz"))


def _baidu_ls_ok(path):
    """`BaiduPCS-Go ls <path> >/dev/null 2>&1`：仅看退出码（前置校验目录是否真实存在）。"""
    result = subprocess.run(
        ["BaiduPCS-Go", "ls", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )
    return result.returncode == 0


def _baidu_ls_output(path):
    """`BaiduPCS-Go ls <path> 2>/dev/null` 的标准输出文本（云端按文件名比对用）。"""
    result = subprocess.run(["BaiduPCS-Go", "ls", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout.decode("utf-8", "replace")


def _cookie_value(db_path, name, host=".baidu.com"):
    """等价 shell 里的 gc：`sqlite3 <库> "SELECT value FROM cookies WHERE name='…' AND host_key='…' LIMIT 1"`。

    读不到（库不可读 / 表缺失等）时返回空串——与 sqlite3 CLI 失败时标准输出为空同效。
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT value FROM cookies WHERE name = ? AND host_key = ? LIMIT 1",
                (name, host),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log_write(f"cloud: 读取 Cookies 失败（{exc}）")
        return ""
    return row[0] if row and row[0] is not None else ""


def cloud_sync():
    """百度网盘云同步（加密后单向上传；失败不影响主备份结论）。"""
    passphrase = get_env("BACKUP_CRYPT_PASSPHRASE")
    if not passphrase:
        log_write("cloud: no BACKUP_CRYPT_PASSPHRASE")
        return False
    db_path = os.path.join(os.path.expanduser("~"), ".config", "baidunetdisk", "Cookies")
    if not os.path.isfile(db_path):
        log_write("cloud: 客户端 Cookies 库不存在")
        return False
    cookie = (
        "BDUSS=" + _cookie_value(db_path, "BDUSS", ".pan.baidu.com") + "; "
        "STOKEN=" + _cookie_value(db_path, "STOKEN", ".pan.baidu.com") + "; "
        "BAIDUID=" + _cookie_value(db_path, "BAIDUID", ".baidu.com") + "; "
        "PTOKEN=" + _cookie_value(db_path, "PTOKEN", ".passport.baidu.com")
    )
    result = subprocess.run(
        ["BaiduPCS-Go", "login", f"-cookies={cookie}"], stdout=subprocess.DEVNULL, stderr=LOG, check=False
    )
    if result.returncode != 0:
        log_write("cloud: 登录失败")
        return False
    # 目标目录：/apps/bms-backup（应用隔离目录，网页端从「我的应用数据」进入查看）
    # 校验目录真实存在（upload 对不存在目录静默失败且返回 0，必须前置 ls 检查防假阳性）
    # 目录策略：mkdir 老 API 已失效（31030）无法自动建目录——若网页端手动建了当月子目录
    # （如 2026-08）则用之，否则平铺根目录
    dest = "/apps/bms-backup"
    month = datetime.now().strftime("%Y-%m")
    monthly = f"/apps/bms-backup/{month}"
    if _baidu_ls_ok(monthly):
        dest = monthly
        log_write(f"cloud: 使用月度目录 {dest}")
    else:
        log_write(f"cloud: 无月度目录，平铺 {dest}（文件名自带日期；如需分目录请在网页端建 {month} 文件夹）")
    if not _baidu_ls_ok(dest):
        log_write(f"cloud: 网盘 {dest} 不存在（需网页端手动创建），跳过云同步")
        return False
    # 加密当日清单内全部产物（含 GitLab 数据包）
    cloud_today = os.path.join(BASE_DIR, "cloud", TODAY)
    filelist = os.path.join(cloud_today, ".filelist")
    try:
        handle = open(filelist, encoding="utf-8", errors="replace")  # noqa: SIM115 — 失败分支需记日志返回；成功路径由下方 with 收口
    except OSError as exc:
        log_write(f"cloud: 无法读取当日清单 {filelist}（{exc}）")
        return False
    n = 0
    with handle:
        for raw_line in handle:
            path = raw_line.rstrip("\n")  # 同 shell `while IFS= read -r f`：仅去行尾换行
            if not os.path.isfile(path):
                continue
            out = os.path.join(cloud_today, os.path.basename(path) + ".gpg")
            # gpg 退出码不参与判定（与原 shell 一致；缺失件由上方清单与下方云端比对暴露）
            subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--yes",
                    "--passphrase-fd",
                    "0",
                    "--symmetric",
                    "--cipher-algo",
                    "AES256",
                    "--compress-algo",
                    "none",
                    "-o",
                    out,
                    path,
                ],
                input=passphrase.encode("utf-8"),
                stdout=LOG,
                stderr=LOG,
                check=False,
            )
            n += 1
    log_write(f"cloud: 加密 {n} 个产物 -> 上传 {dest}/")
    local_gpg = sorted(glob.glob(os.path.join(cloud_today, "*.gpg")))
    # 无匹配时 shell 会把通配符字面量原样传给命令（nullglob 未开），保持同口径
    upload_targets = local_gpg if local_gpg else [os.path.join(cloud_today, "*.gpg")]
    result = subprocess.run(
        ["BaiduPCS-Go", "upload", *upload_targets, dest + "/"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    up_out = result.stdout.decode("utf-8", "replace").rstrip("\n")  # $(...) 去尾部换行
    log_write("\n".join(up_out.splitlines()[-3:]))  # 仅回显末 3 行（同 `echo "$up_out" | tail -3`）
    # 真实性核验：云端按文件名比对（缺失行仅记录；与原 shell 一样不参与函数成败判定）
    for path in upload_targets:
        if os.path.basename(path) not in _baidu_ls_output(dest):
            log_write(f"cloud 缺失: {os.path.basename(path)}")
    total = len(local_gpg)
    log_write(f"cloud sync: 目标={dest} 本地加密件={total}")
    return total > 0


def prune_older_than(directory, pattern, days):
    """等价 `find <目录> -name '<模式>' -mtime +<days> -delete`（递归、按文件名匹配）。

    与 find 同口径：mtime 距今按 24 小时取整后严格大于 days 才删（+7 即约 8 天及以上）。
    """
    now = time.time()
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if not fnmatch.fnmatchcase(name, pattern):
                continue
            path = os.path.join(root, name)
            try:
                age_days = int((now - os.path.getmtime(path)) // 86400)
            except OSError:
                continue
            if age_days > days:
                with contextlib.suppress(OSError):
                    os.remove(path)


def prune_empty_dirs(base):
    """等价 `find <目录> -mindepth 1 -type d -empty -delete`（自深向浅删除空目录）。"""
    for root, _dirs, _files in os.walk(base, topdown=False):
        if root == base:
            continue
        with contextlib.suppress(OSError):
            os.rmdir(root)


def build_filelist():
    """当日产物清单（含 GitLab 数据包，按 mtime 当日过滤）→ cloud/<日期>/.filelist。"""
    cloud_today = os.path.join(BASE_DIR, "cloud", TODAY)
    midnight = datetime.strptime(TODAY, "%Y-%m-%d").timestamp()  # find -newermt "$TODAY"
    patterns = ("*.sql.gz", "*.dmp", "*.tar", "*.tar.gz")
    found = []
    for sub in ("mysql", "postgres", "dameng", "gitlab", "kiwi"):
        for root, _dirs, files in os.walk(os.path.join(BASE_DIR, sub)):
            for name in sorted(files):
                if not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
                    continue
                path = os.path.join(root, name)
                try:
                    newer = os.path.getmtime(path) > midnight
                except OSError:
                    newer = False
                if newer:
                    found.append(path)
    try:
        os.makedirs(cloud_today, exist_ok=True)
        with open(os.path.join(cloud_today, ".filelist"), "w", encoding="utf-8") as handle:
            for path in found:
                handle.write(path + "\n")
    except OSError as exc:
        log_write(f"backup_daily: 写入当日清单失败（{exc}）")


def main(argv):
    global TS, TODAY, LOG
    now = datetime.now()
    TS = now.strftime("%Y-%m-%d_%H%M%S")
    TODAY = now.strftime("%Y-%m-%d")
    STATUS.clear()  # 等价 shell 脚本开头的 `STATUS=()`（单进程重复调用时同样从空开始）

    # mkdir -p "$BASE_DIR"/{mysql,postgres,dameng,gitlab,cloud/$TODAY}
    try:
        for rel in ("mysql", "postgres", "dameng", "gitlab", os.path.join("cloud", TODAY)):
            os.makedirs(os.path.join(BASE_DIR, rel), exist_ok=True)
        LOG = open(LOG_PATH, "ab")  # noqa: SIM115 — 进程级日志句柄（全程持有，结束统一关闭）
    except OSError as exc:
        sys.stderr.write(f"[backup_daily] 初始化失败（{exc}）\n")
        return 1

    try:
        run_step("mysql", dump_mysql)
        run_step("postgres", dump_postgres)
        run_step("dameng", dump_dameng)
        run_step("gitlab", backup_gitlab)
        run_step("kiwi", backup_kiwi_uploads)

        build_filelist()

        # ---------- 本地保留策略：7 天 ----------
        prune_older_than(os.path.join(BASE_DIR, "mysql"), "all_*.sql.gz", KEEP_DAYS)
        prune_older_than(os.path.join(BASE_DIR, "postgres"), "bms_dev_*.sql.gz", KEEP_DAYS)
        prune_older_than(os.path.join(BASE_DIR, "postgres"), "all_*.sql.gz", KEEP_DAYS)  # 清理旧 dumpall 格式
        prune_older_than(os.path.join(BASE_DIR, "dameng"), "dexp_all_*.dmp", KEEP_DAYS)
        prune_older_than(os.path.join(BASE_DIR, "dameng"), "dexp_all_*.log", KEEP_DAYS)
        prune_older_than(os.path.join(BASE_DIR, "gitlab"), "*_gitlab_backup.tar", KEEP_DAYS)
        prune_older_than(os.path.join(BASE_DIR, "gitlab"), "gitlab-config_*.tar.gz", KEEP_DAYS)
        prune_older_than(os.path.join(BASE_DIR, "kiwi"), "kiwi-uploads_*.tar.gz", KEEP_DAYS)

        # ---------- 云同步（百度网盘，加密后单向上传；失败不影响主备份结论）----------
        run_step("cloud", cloud_sync)

        # 云端暂存目录与网盘侧保留策略：30 天
        prune_older_than(os.path.join(BASE_DIR, "cloud"), "*.gpg", CLOUD_KEEP_DAYS)
        prune_empty_dirs(os.path.join(BASE_DIR, "cloud"))

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] daily backup: {' '.join(STATUS)}")
        # 主组件任一 FAIL 以非零退出（cloud FAIL 仅记录，不影响退出码）
        for entry in STATUS:
            if entry.endswith(":FAIL") and not entry.startswith("cloud:"):
                return 1
        return 0
    finally:
        LOG.close()


if __name__ == "__main__":
    configure_stdio()
    sys.exit(main(sys.argv))

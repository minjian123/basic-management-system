# deepseek_harness Windows 部署使用说明

> mjw（Windows 11 开发服务器）上 DeepSeek Harness（DSH）的部署、启停、访问与排障实录
> 对应 Linux/mjpc 版部署说明（安装主体、插件扩展、撤销快照等通用内容）见《[deepseek_harness部署使用说明](../../AI/deepseek_harness部署使用说明.md)》

[文档首页](../../../文档首页.md) › 资料 › 开发服务器 › [windows](开发服务器Windows部署使用说明总览.md) › deepseek_harness Windows 部署使用说明　|　[总览 →](开发服务器Windows部署使用说明总览.md)

---

## 1. 目的与适用范围 <a id="purpose"></a>

本文档记录 DSH 在 **mjw（Windows 11 专业版）** 上的部署与运维：源码安装、桌面启停入口、
web 访问边界（仅本机 127.0.0.1）与 Windows 特有排障。mjw 定位 Windows 开发服务器 / 本地模型机，
DSH 用于其上的本机管理与会话（远程访问经 RDP 后进行，见[第 4 节](#run)）。

| 项 | 值 |
| --- | --- |
| 部署日期 | 2026-09-10（昨天尝试未成，今天打通） |
| 版本 | `dsh-v0.1.5-alpha.2`（commit `b2e3b2a0`，与 mjpc 一致） |
| 源码目录 | `C:\Users\minjian\develop\deepseek-harness` |
| 用户配置 | `C:\Users\minjian\.dsh`（首次启动 web 自动生成 profile） |
| 启停入口 | mjw 桌面「启动 dsh web.cmd」「停止 dsh web.cmd」 |
| web 地址 | `http://127.0.0.1:3080/?token=…`（token 启动时打印） |

## 2. 环境与前提 <a id="prereq"></a>

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| 系统 | Windows 11 专业版（Build 26200） | 见《[开发服务器Windows部署使用说明总览](开发服务器Windows部署使用说明总览.md)》 |
| Node.js | 24.19.0 | `C:\Program Files\nodejs` |
| npm | 11.17.0 | registry 已配 npmmirror |
| pnpm | **11.7.0**（2026-09-10 修复重装） | 与 mjpc 同版；bin 为 `.cjs` + `.cmd/.ps1` shim（**不存在 `pnpm.exe`**，属正常） |
| git | 2.55.0 | 源码经 ghfast 镜像克隆 |
| pwsh | 7.6.6（可选） | mjpc 侧远程管理 mjw 用（见《[远程控制部署使用说明](远程控制部署使用说明.md)》4.4） |

网络：GitHub 走 ghfast 镜像；npm/pnpm 包源走 npmmirror（mjw 已配置）。

## 3. 安装 <a id="install"></a>

### 3.1 源码 <a id="install-clone"></a>

```bash
git clone https://ghfast.top/https://github.com/deepseek-ai/deepseek-harness.git
# 2026-09-10 版本: commit b2e3b2a0 (0.1.5-alpha.2)
```

### 3.2 pnpm 修复（昨天失败根因） <a id="install-pnpm"></a>

昨天 `npm install -g pnpm@11.7.0` 从 npmmirror 下载报
`UNABLE_TO_GET_ISSUER_CERT_LOCALLY`（TLS 证书校验失败），留下残缺 shim
（`pnpm.ps1` 指向的 `pnpm.exe` 不存在——pnpm 11 本就没有 exe，但当时 `node_modules\pnpm` 也因中断缺失）。
定位口径：mjw 上 `curl.exe -I https://registry.npmmirror.com` 返回 200 → **系统 TLS 正常，纯 npm 层问题**。

修复（在 mjw PowerShell 执行）：

```powershell
# 清理残缺 shim 与包目录
$npm = "$env:APPDATA\npm"
Remove-Item "$npm\pnpm","$npm\pnpm.cmd","$npm\pnpm.ps1","$npm\pnpx*","$npm\pn","$npm\pn.*","$npm\pnx*" -Force -ErrorAction SilentlyContinue
Remove-Item "$npm\node_modules\pnpm" -Recurse -Force -ErrorAction SilentlyContinue
npm install -g pnpm@11.7.0     # 重装成功后 pnpm --version = 11.7.0
```

### 3.3 依赖安装与构建 <a id="install-build"></a>

在源码根执行（长命令见[第 5 节](#long-task)的执行法）：

```powershell
pnpm install          # 实测 47 秒；日志尾部 3 条 ".bin\dsh … ENOENT" 属子包 shim 警告，可忽略
pnpm run build        # 实测 2 分 45 秒，产出 234 个 web 资产
pnpm dsh --version    # 验证: 0.1.5-alpha.2
```

### 3.4 长命令执行法（计划任务） <a id="long-task"></a>

WinRM 会话结束会杀掉子进程，长命令/常驻进程须**注册计划任务**脱离会话生命周期，
日志落文件轮询（`SYSTEM` 账号无需密码）：

```powershell
$arg = '/c ""C:\Users\minjian\AppData\Roaming\npm\pnpm.cmd" install 1> C:\Windows\Temp\dsh-task.log 2>&1'
$a = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $arg -WorkingDirectory 'C:\Users\minjian\develop\deepseek-harness'
$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName DSH_TASK -Action $a -Principal $p -Force
Start-ScheduledTask -TaskName DSH_TASK
# 轮询: Get-ScheduledTaskInfo 的 LastTaskResult（0=成功）与日志尾部
```

## 4. 启动 / 停止与访问 <a id="run"></a>

### 4.1 桌面入口 <a id="run-desktop"></a>

| 入口（mjw 用户桌面） | 行为 |
| --- | --- |
| `启动 dsh web.cmd` | `cd` 源码根 → `pnpm dsh web --no-open`（前台窗口显示 URL 与 token；退出后按任意键关闭） |
| `停止 dsh web.cmd` | 按端口 3080 定位 PID → `taskkill /T /F` 杀进程树 |

### 4.2 访问边界（重要） <a id="run-bind"></a>

**dsh web 只绑定 `127.0.0.1`**。`--host 0.0.0.0` 被官方**故意禁止**，报错原文：
`intentionally not supported yet for safety: it would expose remote code execution to the network`。
因此：

- 在 mjw 本机（桌面 / RDP 会话）浏览器打开启动时打印的 `http://127.0.0.1:3080/?token=…`；
- 无需也不应放行 mjw 防火墙 3080（曾放行内网网段的规则已撤销，保持最小暴露面）；
- 从 mjpc 等其他机器访问不可行（官方安全设计，勿用端口转发绕过）。

### 4.3 首次启动 <a id="run-first"></a>

首次 `dsh web` 自动初始化 `C:\Users\minjian\.dsh`（profiles / storages / 凭据文件），
web profile 为全新默认（未装 mjpc 上的 dsh-free-vision、dsh-undo-savepoint 等 bundle；
如需安装见 Linux 版部署说明第 8 节，mjw 上执行 `pnpm dsh plugin --profile web add <pkg>`）。

## 5. 更新 <a id="update"></a>

按 Linux/mjpc 版同款顺序手动执行（Windows 无 dsh-update.sh）：

```powershell
cd C:\Users\minjian\develop\deepseek-harness
git pull --ff-only                 # 走 ghfast 远端
pnpm install
pnpm run build
# 桌面「启动 dsh web.cmd」重新拉起
```

> mjw 仓库有未提交改动时先处理再 pull（与 mjpc 脚本口径一致）。

## 6. 与 Linux/mjpc 部署的差异 <a id="diff"></a>

| 项 | mjpc（Linux） | mjw（Windows） |
| --- | --- | --- |
| 源码运行 | `~/develop/deepseek-harness` | `C:\Users\minjian\develop\deepseek-harness` |
| 一键更新 | `scripts/tools/dsh/dsh-update.sh`（桌面项） | 无，按第 5 节手动 |
| 启停 | `dsh-web-start.sh` / `dsh-web-stop.sh` | 桌面「启动/停止 dsh web.cmd」 |
| web 绑定 | 127.0.0.1（同） | 127.0.0.1（同，官方禁 0.0.0.0） |
| 插件 bundle | free-vision / undo-savepoint / graphify 等 | 默认全新（按需 `dsh plugin add`） |
| 通用内容 | 插件/撤销/救援工具见 Linux 版第 8 节 | 同左（mjw 未装时先看再装） |

## 7. 排障（Windows 特有） <a id="faq"></a>

| 现象 | 根因 / 处理 |
| --- | --- |
| `pnpm install` 报 `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` | npm 层 TLS 问题（curl 验证系统 TLS 正常）；按 3.2 修复重装 pnpm |
| `pnpm` 命令报"找不到 pnpm.exe" | pnpm 11 bin 无 exe，仅 `.cjs`+shim；检查 `node_modules\pnpm\bin\pnpm.cjs` 与 shim 完整性，残缺则重装 |
| `dsh web --host 0.0.0.0` 启动即退 | 官方安全禁令（见 4.2）；去掉 `--host` 即可 |
| 计划任务起 `dsh web` 不监听 | 任务 Execute 不能直接指向 `.cmd`（非 PE）；用 `cmd.exe /c` 包装（3.4 模板）；双击桌面 `.cmd` 由 Explorer 执行，二者不互替 |
| cmd 参数里命令带空格报"不是内部或外部命令" | cmd 引号规则：可执行文件单独引号、参数放引号外（`/c ""exe" args …`）；子命令（如 `run build`）勿进引号 |
| web 启动打印"could not open the default browser" | Session 0 / 无交互桌面属正常；用打印的 URL 手动访问 |
| 远程（WinRM）执行 GUI 类命令无反应 | 非交互会话限制；见《[远程控制部署使用说明](远程控制部署使用说明.md)》6.3 计划任务交互法 |

## 8. 关联文档 <a id="related"></a>

- 《[deepseek_harness部署使用说明](../../AI/deepseek_harness部署使用说明.md)》：Linux/mjpc 版（主体部署、插件扩展、undo 快照等通用内容）
- 《[开发服务器Windows部署使用说明总览](开发服务器Windows部署使用说明总览.md)》：mjw 总览
- 《[远程控制部署使用说明](远程控制部署使用说明.md)》：WinRM/RDP 通道与计划任务交互法
- 《[开发服务器Windows电源控制使用说明](开发服务器Windows电源控制使用说明.md)》：mjw 唤醒/睡眠/关机工具链
- 《[文档生成规范](../../../规范/文档生成规范.md)》与《[命名规范](../../../规范/命名规范.md)》：本文档遵循的规范

> 依《文档生成规范》编写 · 2026-09-10 mjw 部署打通实录

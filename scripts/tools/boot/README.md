# 说明：本目录存放双系统引导的辅助脚本（开发机 mjpc：Windows 11 + Ubuntu）
#
# 目录内容
#   安装-重启到Windows快捷方式.py   在 Ubuntu 侧安装「重启到 Windows」桌面快捷方式（同名 .sh 为薄包装）
#   生成-Windows侧一键重启.ps1      在 Windows 侧（管理员）生成「重启到 Ubuntu」快捷方式与计划任务
#   校验脚本编码.ps1                改动脚本后必须运行：校验 .ps1 的 BOM 与 5.1 语法、.sh 的换行符
#
# 背景与完整说明见 bms 文档《双系统引导部署使用说明》：
#   bms文档/资料/开发机/双系统引导部署使用说明.md
#
# 关键约束（改动脚本时务必遵守，均由实测得出）
#   1. Windows 侧 .ps1 必须存为 UTF-8 带 BOM：计划任务用 Windows PowerShell 5.1 执行，
#      它按系统 ANSI（中文环境为 GBK）解码无 BOM 的 UTF-8 文件，中文会被解码坏并破坏语法，
#      脚本直接解析失败。校验也必须用 5.1，不能用 pwsh 7（pwsh 7 能正确读无 BOM UTF-8，
#      会给出「语法正常」的错误结论）。
#   2. 写 EFI 变量前必须显式启用 SeSystemEnvironmentPrivilege：即使以 SYSTEM 运行也不会
#      自动获得，不启用时返回错误 1314（权限不足）。
#   3. 删除固件启动项只能用 bcdedit /delete {GUID} /f：Windows 不允许按 UEFI 规范以
#      0 长度删除 EFI 变量（实测 SetFirmwareEnvironmentVariableEx 返回 err=87）。
#   4. 引导切换用 UEFI BootNext（一次性），不要改 BootOrder。
#   5. 以 SYSTEM 注册计划任务后，必须再追加普通用户的运行权限 (A;;GRGX;;;AU)：
#      Register-ScheduledTask 的默认 ACL 只含管理员组与 SYSTEM，普通用户既不能 /run
#      也不能 /query，schtasks /run 报 "Access is denied."（exit=1），表现为双击快捷
#      方式弹了确认框却没反应。生成脚本已内置该步。
#   6. 双系统时钟：Windows 默认把 RTC 当本地时间、Linux 当 UTC，会导致切换系统后时间
#      偏移一个时区。本机已设 RealTimeIsUniversal=1（与 Linux 一致），并启用 w32time。
#      改动该值时须同时把当前 UTC 写进 RTC，否则下次开机会偏一个时区。
#
# 编辑脚本后务必运行：powershell -File 校验脚本编码.ps1
#   （很多编辑器/工具写回文件会丢掉 BOM，导致 5.1 解析失败，见第 1 条）

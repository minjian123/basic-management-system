# 说明：本目录存放 WSL 相关辅助脚本（开发机 mjpc：Windows 侧）
#
# 目录内容
#   挂载Ubuntu盘.py       把双系统 Ubuntu 的数据盘（磁盘 3 分区 2，ext4）以只读方式挂进 WSL；
#                         同名 .bat 为双击薄包装（需管理员）
#   部署WSL开发环境.py     在 WSL 内复刻 bizs 开发环境：从挂载分区复制工作区 + 依赖仓 +
#                         用户级配置，并做导入自检（跑测试用，与双系统 Linux 侧逐项对齐）；
#                         --sync 复制后同步四仓到远端最新并按锁文件重装依赖；
#                         --sync-only 只做同步（日常刷新用）；
#                         同名 .sh 为薄包装（在 WSL 内执行）
#
# 背景与完整说明见 bms 文档《WSL 部署使用说明》：
#   bms文档/资料/开发机/WSL部署使用说明.md
#   - 挂载相关：第 2~5 节
#   - WSL 内开发环境：第 6 节
#
# 关键约束（改动脚本时务必遵守）
#   1. 挂物理盘需管理员权限（wsl --mount）：桌面快捷方式「挂载 Ubuntu 盘」已勾「以管理员身份运行」。
#   2. 一律只读挂载（--options ro）：目的只是读文件，避免在 Windows 侧误写损坏双系统 Linux。
#   3. 挂载在 Windows 重启 / wsl --shutdown 后失效，需要时重跑本脚本（脚本幂等，已挂载则只校验）。
#   4. 磁盘整盘挂给 WSL 期间，Windows 访问不到该盘的任何分区（含 ESP）：要动 ESP 先 --
#      wsl --unmount \\.\PHYSICALDRIVE3。
#
# 开发环境脚本的额外约束（部署WSL开发环境.py）
#   5. 目标路径必须与双系统 Linux 侧一致（~/develop/bizs + ~/dev-deps）：Linux 侧 .venv 的
#      shebang、pyvenv.cfg、node_modules 软链全是绝对路径，路径不一致则依赖全部失效。
#   6. 源端（挂载分区）全程只读，脚本不做任何写入。
#   7. 脚本要幂等：重复运行只增量同步，不得重复下载依赖、不得覆盖用户已改的配置。
#   8. /usr/local/bin/python 软链由脚本补建（venv 的 bin/python 指向它，WSL 默认没有）。
#   9. 复制 ≠ 可用：源端常落后远端（实测 bms 曾落后 204 个提交，含 pytest 启动插件等测试
#      基础设施改动）。脚本必须提供 --sync，且同步后必须按锁文件重装依赖——锁文件随代码变，
#      只 pull 不重装会得到「代码新、依赖旧」的半新状态。
#  10. 重装依赖必须走「还原 -> 装 -> 再外置」：pnpm/uv 在符号链接状态下会误判已安装而跳过。
#  11. 集合声明遵守《后端开发规范》集合护栏（scripts/tools 也在扫描范围）：确需内置 list 的
#      subprocess argv / argparse 入参，用行尾 # bare-collections:allow 附理由豁免。
